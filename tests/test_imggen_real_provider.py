"""真实图像 Provider / 视觉审核 Provider 凭据门控测试。

- 无凭据：HOLD + 完整外部任务包 + 不生成图像文件；PIL 后端仅作确定性 contract-test，
  绝不冒充真实文生图（分类诚实断言）。
- 有凭据：用 mock 本地 HTTP 端点模拟 OpenAI-compatible 协议，断言真实发送请求并解析
  真实图像字节；视觉审核解析结构化评分并记录 provider/model/token/延迟/trace。
- 失败页单页重建：重建失败页后未修改页哈希不变。
- Anchor / Visual Bible 可机器比较接口可用。
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image

from aipd_os.imggen.adapter import ImageGenUnavailable
from aipd_os.imggen.anchors import (
    AnchorRegistry,
    VisualBible,
    extract_hex,
    features_from_facts,
)
from aipd_os.imggen.providers import (
    BatchRequest,
    PILImageGenProvider,
    PriorBatchContent,
    RealImageGenProvider,
)
from aipd_os.imggen.rebuild import rebuild_failed_pages
from aipd_os.visual_audit.providers import VisionAuditProvider, VisionAuditUnavailable


def _png_bytes(size=(64, 64), color=(200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


KNOWN_PNG = _png_bytes()


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def clear_image_creds(monkeypatch):
    for k in (
        "AIPD_IMAGE_PROVIDER_URL",
        "AIPD_IMAGE_API_KEY",
        "AIPD_IMAGE_MODEL",
        "AIPD_IMAGE_OUTPUT",
        "AIPD_VISION_PROVIDER_URL",
        "AIPD_VISION_API_KEY",
        "AIPD_VISION_MODEL",
    ):
        monkeypatch.delenv(k, raising=False)


# ---------------------------------------------------------------- 无凭据：HOLD + 外部任务包
def test_no_creds_hold_external_package_no_image(clear_image_creds, tmp_path):
    p = RealImageGenProvider()
    assert p.available() is False

    # 无凭据时 generate 必须抛（HOLD），绝不假装成图
    req = BatchRequest(
        pages=[{"page_id": "cover", "title": "封面"}],
        model_version="gen-1.0",
        prompt_template="generate",
        generation_params={"size": [1024, 1024]},
    )
    with pytest.raises(ImageGenUnavailable):
        p.generate_batch(req)

    # 输出完整外部任务包
    out_dir = tmp_path / "tasks"
    pkg = p.write_external_task_package(req, str(out_dir))
    assert pkg["status"] == "external_pending"
    assert pkg["hold"] is True
    # 完整外部任务包必须写明：URL / API key / 模型名 / 期望输出格式
    rc = pkg["required_config"]
    for key in ("url", "api_key", "model", "output_format"):
        assert key in rc, f"required_config 缺少 {key}"

    # 不生成任何图像文件
    pngs = list(out_dir.glob("*.png"))
    assert pngs == []
    assert list(out_dir.glob("*.task.json"))


# ---------------------------------------------------------------- PIL 后端分类诚实（contract-test）
def test_pil_is_deterministic_contract_not_real(clear_image_creds):
    # PIL 后端是确定性本地后端，绝不冒充真实文生图
    pil = PILImageGenProvider()
    assert pil.id == "pil"
    assert pil.external_dependency is False
    assert not isinstance(pil, RealImageGenProvider)

    req = BatchRequest(
        pages=[{"page_id": "p1", "title": "测试页"}],
        model_version="gen-1.0",
        prompt_template="t",
        generation_params={"size": [1024, 1024]},
        seed=7,
    )
    out = pil.generate_batch(req)[0]
    # 分类诚实：meta 明确为本地确定性，cost_unit 非 provider_billed
    assert out.meta["provider_id"] == "pil"
    assert out.meta["cost_unit"] == "local_deterministic"
    assert out.meta["cost"] == 0.0
    # 它是真实字节（contract-test 用），但接口明确不声称真实文生图端点
    assert out.sha256 == out.meta["artifact_hash"]


# ---------------------------------------------------------------- 有凭据：真实 HTTP（mock 端点）
class _MockState:
    last_body = None
    requests = 0
    handler_cls = None


class _OpenAIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        server = self.server  # type: ignore[attr-defined]
        server._mock_state.requests += 1  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        server._mock_state.last_body = body  # type: ignore[attr-defined]
        if self.path.endswith("/chat/completions"):
            payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "score": 0.92,
                                    "passed": True,
                                    "conclusion": "人物与 CMF 一致",
                                    "dimensions": {"character": 0.9, "cmf": 0.94},
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
            }
            data = json.dumps(payload).encode("utf-8")
        else:  # /images/generations
            data = json.dumps(
                {"data": [{"b64_json": base64.b64encode(KNOWN_PNG).decode("ascii")}]}
            ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # 静默
        pass


@pytest.fixture
def mock_openai_server():
    state = _MockState()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _OpenAIHandler)
    httpd._mock_state = state  # type: ignore[attr-defined]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield state, url
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_credentialed_real_http_parses_image_bytes(mock_openai_server):
    state, url = mock_openai_server
    p = RealImageGenProvider(url=url, api_key="test-key", model="mock-model")
    assert p.available() is True

    prior = PriorBatchContent(
        images=[{"page_id": "prev", "data": _png_bytes((32, 32), (10, 200, 10)), "sha256": "x"}]
    )
    req = BatchRequest(
        pages=[{"page_id": "cover", "title": "封面", "expected_cmf": "工程橙/金属灰"}],
        model_version="gen-1.0",
        prompt_template="生成",
        generation_params={"size": [1024, 1024]},
    )
    out = p.generate_batch(req, prior)[0]

    # 真实发送了 HTTP 请求
    assert state.requests >= 1
    # 真实解析了图像字节
    assert out.data == KNOWN_PNG
    assert out.sha256 == _sha_bytes(KNOWN_PNG)
    assert out.meta["provider_id"] == "real"
    assert out.meta["http_status"] == 200
    assert out.meta["source"] in ("b64_json", "binary")
    assert out.meta["latency_ms"] >= 0

    # 请求体包含模型、提示词、前批图像条件（先验图像作为 input_images）
    sent = json.loads(state.last_body.decode("utf-8"))
    assert sent["model"] == "mock-model"
    assert "封面" in sent["prompt"]
    assert sent["prior_image_count"] == 1
    assert sent["input_images"] and sent["input_images"][0].startswith("data:image/png;base64,")


# ---------------------------------------------------------------- 视觉审核 Provider
def test_vision_no_creds_hold_external_package(clear_image_creds, tmp_path):
    v = VisionAuditProvider()
    assert v.available() is False
    with pytest.raises(VisionAuditUnavailable):
        v.audit("/tmp/none.png", "人物一致吗？")
    img = tmp_path / "p.png"
    img.write_bytes(KNOWN_PNG)
    out_dir = tmp_path / "vis_tasks"
    pkg = v.write_external_task_package(str(img), "人物一致吗？", str(out_dir))
    assert pkg["status"] == "external_pending"
    assert pkg["hold"] is True
    for key in ("url", "api_key", "model", "expected_output_format"):
        assert key in pkg["required_config"]


def test_vision_credentialed_parses_structured_result(mock_openai_server, tmp_path):
    state, url = mock_openai_server
    v = VisionAuditProvider(url=url, api_key="k", model="mock-vision")
    assert v.available() is True
    img = tmp_path / "page.png"
    img.write_bytes(KNOWN_PNG)
    res = v.audit(str(img), "人物与 CMF 是否一致？")
    assert res["score"] == 0.92
    assert res["passed"] is True
    assert res["conclusion"]
    assert res["provider"]["model"] == "mock-vision"
    assert res["tokens"]["total_tokens"] == 150
    assert res["network"]["http_status"] == 200
    assert res["trace_id"].startswith("vision-")


# ---------------------------------------------------------------- 失败页单页重建
def test_rebuild_failed_pages_preserves_unchanged_hashes(tmp_path):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    for pid in ("p1", "p2", "p3"):
        (pages_dir / f"{pid}.png").write_bytes(_png_bytes((32, 32), (10, 200, 10)))

    def sha(name):
        import hashlib
        return hashlib.sha256((pages_dir / name).read_bytes()).hexdigest()

    p2_before = sha("p2.png")
    p3_before = sha("p3.png")

    report = rebuild_failed_pages(
        {"project_id": "x"},
        ["p1"],  # 只重建失败页 p1
        str(pages_dir),
        rebuild_page=lambda pid: _png_bytes((64, 64), (5, 5, 5)),  # 返回新字节
    )

    assert report["rebuilt_page_ids"] == ["p1"]
    assert len(report["rebuilt"]) == 1
    # 未修改页哈希保持不变
    assert sha("p2.png") == p2_before
    assert sha("p3.png") == p3_before
    assert report["unchanged_pages_verified"] == 2
    assert report["unexpected_changes"] == []
    assert report["hash_preservation_ok"] is True
    # 失败页本身被改写
    assert report["rebuilt"][0]["before_sha256"] != report["rebuilt"][0]["after_sha256"]


# ---------------------------------------------------------------- Anchor / Visual Bible 可机器比较
def test_anchor_visual_bible_machine_comparable():
    facts = {
        "product": {"name": "外骨骼助力系统", "structure": "谐波减速器 + 高密度电机 + 锂电池组"},
        "cmf": {"color": "工程橙/金属灰", "material": "铝合金6061", "finish": "阳极氧化"},
        "characters": [{"name": "操作员", "appearance": "工业级外骨骼，工程橙与金属灰"}],
        "modules": [{"name": "动力模块", "desc": "无刷电机与谐波减速器"}],
    }
    reg_a = AnchorRegistry.build(facts)
    reg_b = AnchorRegistry.build(facts)

    # 颜色归一为 HEX
    assert "#FF6A00" in extract_hex("工程橙")
    assert "#8A8D91" in extract_hex("金属灰")

    # 相同注册表一致度 = 1.0
    cmp = reg_a.compare(reg_b)
    assert cmp["overall_score"] == 1.0
    assert cmp["consistent"] == cmp["total"]

    # 页面特征与注册表一致
    page = reg_a.compare_page(features_from_facts(facts))
    assert page["score"] == 1.0 and page["consistent"] == page["total"]

    # 特征哈希可机器比较
    feats = features_from_facts(facts)
    assert all(f.digest() for f in feats)

    # Visual Bible 结构化约束
    vb = VisualBible.from_truth(facts)
    con = vb.to_constraints()
    assert con["cmf"]["color_hex"] == ["#FF6A00", "#8A8D91"]
    tokens = ["color=工程橙/金属灰", "material=铝合金6061", "finish=阳极氧化"]
    assert con["cmf"]["tokens"] == tokens
    assert vb.fingerprint()["digest"]


def test_decode_image_rejects_error_body_and_non_image_bytes(clear_image_creds):
    """回归：JSON 错误体/非图像字节不得被当真实图产出。"""
    from aipd_os.imggen.providers import ImageGenUnavailable, RealImageGenProvider

    with pytest.raises(ImageGenUnavailable):
        RealImageGenProvider._decode_image(
            b'{"error": {"message": "invalid api key"}}', "application/json")
    with pytest.raises(ImageGenUnavailable):
        RealImageGenProvider._decode_image(b"<html>not an image</html>", "text/html")
    with pytest.raises(ImageGenUnavailable):
        RealImageGenProvider._decode_image(
            b'{"data": [{"prompt": "x"}]}', "application/json")
    # 合法 PNG 签名可正常通过
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "YAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
    raw, fmt, src = RealImageGenProvider._decode_image(
        b'{"data": [{"b64_json": "' + base64.b64encode(png) + b'"}]}',
        "application/json")
    assert raw[:4] == b"\x89PNG" and fmt == "PNG" and src == "b64_json"
