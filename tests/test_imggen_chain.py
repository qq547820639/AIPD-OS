"""连续附件产品手册链 + 可替换 ImageGen Provider 端到端测试。

诚实性断言：
- 连续批次之间流转的是真实图像字节（content/bytes），不是路径字符串。
- 无真实后端时链输出外部任务包并保持 HOLD，绝不假装成图。
- 视觉失败阻止发布；单页失败仅重建责任页；参数变更传播到相关页；
  已通过且不受影响的页面不会被重新生成。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from aipd_os.imggen.providers import (
    BatchRequest,
    ExternalImageGenProvider,
    PILImageGenProvider,
    PriorBatchContent,
)
from aipd_os.imggen.registry import AnchorRegistry, VisualBible

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "scripts" / "manual_chain.py"

FACTS = {
    "params": {
        "peak_torque": 120,
        "weight": 8.5,
        "battery_capacity": 60,
        "max_speed": 20,
        "input_voltage": 48,
        "max_load": 100,
    },
    "product": {
        "name": "智能外骨骼助力系统",
        "tagline": "降低重体力作业风险，提升职业健康。",
        "structure": "腰部助力外骨骼，模块化动力/控制/供电",
    },
    "modules": [
        {"name": "动力模块", "desc": "高密度无刷电机与谐波减速器"},
        {"name": "控制模块", "desc": "力矩感知与运动意图识别"},
    ],
    "scenes": [
        {"title": "物流搬运", "desc": "仓库装卸缓解腰部劳损"},
        {"title": "制造车间", "desc": "产线搬运装配"},
    ],
    "cmf": {"color": "工程橙/金属灰", "material": "铝合金6061", "finish": "阳极氧化"},
    "characters": [{"appearance": "工业操作者，穿橙色工装与 PPE"}],
    "camera": {"focal": "35mm", "angle": "3/4 视角", "lighting": "车间环境光"},
    "lighting": {"type": "环境光", "color": "中性白"},
    "qa": [{"q": "电池续航多久", "a": "依据负载约4-6小时"}],
    "closure": [{"text": "本产品致力于降低重体力作业风险。"}],
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cli(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        [sys.executable, str(MANUAL), *args], capture_output=True, text=True, cwd=str(cwd)
    )
    assert r.returncode == 0, f"cli failed: {args}\nstdout={r.stdout}\nstderr={r.stderr}"
    return r.stdout


def cli_expect(cwd: Path, code: int, *args: str) -> str:
    r = subprocess.run(
        [sys.executable, str(MANUAL), *args], capture_output=True, text=True, cwd=str(cwd)
    )
    assert r.returncode == code, f"expected {code} got {r.returncode}: {args}\n{r.stdout}\n{r.stderr}"  # noqa: E501
    return r.stdout


def load_state(state: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(Path(state).read_text(encoding="utf-8")))


def batch_run(state: Path, batch_id: str) -> dict[str, Any]:
    for br in load_state(state)["batch_runs"]:
        if br["batch_id"] == batch_id:
            return cast(dict[str, Any], br)
    raise AssertionError(f"batch {batch_id} not found")


def setup_plan(tmp_path: Path, state: Path) -> list:
    cli(tmp_path, "init", "--state", str(state), "--project-id", "chain-exo", "--minimum-pages", "10")  # noqa: E501
    cli(tmp_path, "plan-batches", "--state", str(state), "--minimum-pages", "10")
    plan = load_state(state)["batch_plan"]
    assert len(plan) >= 10
    return sorted({e["batch_id"] for e in plan}, key=lambda s: int(s.split("_")[1]))


def run_batch_pil(tmp_path: Path, state: Path, bid: str, facts_json: Path, out: Path,
                  prior_batch: Path | None = None, seed: int = 0) -> str:
    args = [
        "run-batch", "--state", str(state), "--batch-id", bid,
        "--prompt", f"chain {bid} 提示词", "--theory-version", "T4.1",
        "--truth-version", "PT-3", "--anchors", f"{bid}-anchors",
        "--output-dir", str(out), "--facts", str(facts_json),
        "--imggen-provider", "pil", "--seed", str(seed),
    ]
    if prior_batch is not None:
        args += ["--prior-batch", str(prior_batch)]
    return cli(tmp_path, *args)


def snapshot_dir(d: Path) -> dict:
    out = {}
    for p in sorted(d.rglob("*.*")):
        if p.is_file():
            out[str(p.relative_to(d))] = p.read_bytes()
    return out


# ---------------------------------------------------------------- 接口诚实性
def test_providers_interface_honesty(tmp_path) -> None:
    # PIL 本地确定性后端：产生真实 PNG 字节
    pil = PILImageGenProvider()
    assert pil.available() is True
    assert pil.external_dependency is False
    req = BatchRequest(
        pages=[{"page_id": "cover", "title": "封面", "role": "cover"}],
        model_version="m1", prompt_template="p", generation_params={"size": [1024, 1024]},
        seed=7,
    )
    imgs = pil.generate_batch(req, None)
    assert len(imgs) == 1
    g = imgs[0]
    assert g.data[:8] == b"\x89PNG\r\n\x1a\n"  # 真实 PNG 魔数
    assert g.sha256 == sha(g.data)
    assert g.meta["seed"] == 7
    assert g.meta["attachment_hash"] is None  # 首批无前批

    # External 桩：external_dependency，未配置后端时不可用并拒绝假装
    ext = ExternalImageGenProvider()
    assert ext.external_dependency is True
    assert ext.available() is False
    try:
        ext.generate_batch(req, None)
        raise AssertionError("external provider must refuse without backend")
    except Exception as e:
        assert "HOLD" in str(e) or "refusing" in str(e)


def test_prior_batch_content_attachment_hash(tmp_path) -> None:
    a = PILImageGenProvider()
    im1 = a.generate_batch(BatchRequest(pages=[{"page_id": "p1", "title": "t"}],
                                        model_version="m", prompt_template="p",
                                        generation_params={}, seed=1), None)[0]
    im2 = a.generate_batch(BatchRequest(pages=[{"page_id": "p2", "title": "t2"}],
                                        model_version="m", prompt_template="p",
                                        generation_params={}, seed=1), None)[0]
    pc = PriorBatchContent(images=[
        {"page_id": "p1", "data": im1.data, "sha256": im1.sha256},
        {"page_id": "p2", "data": im2.data, "sha256": im2.sha256},
    ])
    assert pc.total_bytes() == len(im1.data) + len(im2.data)
    assert len(pc.attachment_hash()) == 64
    # 第二批 provider 收到第一批字节：attachment_hash 与首批字节完全一致
    second = a.generate_batch(
        BatchRequest(pages=[{"page_id": "p3", "title": "t3"}], model_version="m",
                     prompt_template="p", generation_params={}, seed=2),
        pc,
    )[0]
    assert second.meta["attachment_hash"] == pc.attachment_hash()
    assert second.meta["prior_image_count"] == 2


# ---------------------------------------------------------------- 端到端批次字节流转
def test_second_batch_receives_first_batch_image_bytes(tmp_path) -> None:
    state = tmp_path / "state.json"
    facts_json = tmp_path / "facts.json"
    facts_json.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")
    batches = setup_plan(tmp_path, state)

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    # 第一批：用 PIL provider 真实生成配图字节
    run_batch_pil(tmp_path, state, batches[0], facts_json, out1)
    br1 = batch_run(state, batches[0])
    assert br1["status"] == "completed"
    assert br1["completed"] and not br1["external_pending"]
    fig1 = out1 / "figures"
    assert fig1.exists() and any(fig1.glob("*.png"))

    # 第二批：把第一批的 figures 目录作为 prior_batch，字节必须真实流转
    run_batch_pil(tmp_path, state, batches[1], facts_json, out2, prior_batch=fig1)
    br2 = batch_run(state, batches[1])
    assert br2["status"] == "completed"
    # 状态记录真实字节（非路径字符串）
    assert br2["prior_batch_content"]["image_count"] > 0
    assert br2["prior_batch_content"]["total_bytes"] > 0
    assert br2["prior_batch_content"]["attachment_hash"]

    # 重新计算第一批字节的附件哈希，必须与第二批记录一致
    # （按文件名排序读取，与 provider 消费前批的字节顺序一致）
    first_bytes = b"".join(p.read_bytes() for p in sorted(fig1.glob("*.png")))
    assert br2["prior_batch_content"]["attachment_hash"] == sha(first_bytes)

    for op in br2["output_pages"]:
        gen = op["generation"]
        assert gen["attachment_hash"] == sha(first_bytes)  # 收到的是真实字节哈希
        assert gen["prior_image_count"] == len(list(fig1.glob("*.png")))
        assert gen["request_id"] and gen["model_version"] and gen["seed"] is not None
        assert "prompt" in gen and "prompt_hash" in gen
        assert "generation_params" in gen and "cost" in gen and "latency_ms" in gen
        assert gen["artifact_hash"] == op["figure_sha256"]
        # 第二批产生的配图是真实 PNG 字节且与第一批不同
        fig2_path = Path(op["figure_path"])
        assert fig2_path.exists()
        assert fig2_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert fig2_path.read_bytes() != first_bytes


# ---------------------------------------------------------------- 锚点注册表 / Visual Bible
def test_anchor_registry_and_visual_bible_persisted(tmp_path) -> None:
    state = tmp_path / "state.json"
    facts_json = tmp_path / "facts.json"
    facts_json.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")
    setup_plan(tmp_path, state)

    cli(tmp_path, "build-visual-bible", "--state", str(state), "--facts", str(facts_json))
    cli(tmp_path, "build-anchor-registry", "--state", str(state), "--facts", str(facts_json))
    d = load_state(state)
    vb = d["visual_bible"]
    assert vb["cmf"]["color"] == "工程橙/金属灰"
    assert vb["camera"]["focal"] == "35mm"
    assert vb["modules"] == FACTS["modules"]
    reg = d["anchor_registry"]
    assert reg["product_structure"]["name"] == "智能外骨骼助力系统"
    assert reg["anchors"], "anchor pages must be recorded"
    assert all(a["role"] in {"cover", "principle", "parameter_table", "module_main"}
               for a in reg["anchors"])
    # 结构可往返
    assert AnchorRegistry.from_dict(reg).to_dict() == reg
    assert VisualBible.from_dict(vb).to_dict() == vb


# ---------------------------------------------------------------- 正文来自 Product Truth
def test_body_copy_from_product_truth(tmp_path) -> None:
    state = tmp_path / "state.json"
    facts_json = tmp_path / "facts.json"
    facts_json.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")
    setup_plan(tmp_path, state)
    # cover/module 在 batch_1，cmf 在 batch_2；跨批次合并检索正文来源
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    run_batch_pil(tmp_path, state, "batch_1", facts_json, out1)
    run_batch_pil(tmp_path, state, "batch_2", facts_json, out2)
    pages = [op for br in load_state(state)["batch_runs"] for op in br["output_pages"]]
    op = next(o for o in pages if o["page_id"] == "cover")
    assert op["defn"]["title"] == "智能外骨骼助力系统 产品手册"  # 来自 product.name
    op_mod = next(o for o in pages if o["role"] == "module")
    assert any("动力模块" in b for b in op_mod["defn"]["body"])  # 来自 modules
    op_cmf = next(o for o in pages if o["role"] == "cmf")
    assert any("工程橙/金属灰" in b for b in op_cmf["defn"]["body"])  # 来自 cmf


# ---------------------------------------------------------------- 视觉失败阻止发布
def test_visual_failure_blocks_release(tmp_path) -> None:
    state = tmp_path / "state.json"
    facts_json = tmp_path / "facts.json"
    facts_json.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")
    setup_plan(tmp_path, state)
    out = tmp_path / "out"
    run_batch_pil(tmp_path, state, "batch_1", facts_json, out)

    # 检查发布门：无前哈希、全新页面，仅视觉维度 requiring_vision → release_blocked=True（绝不假通过）  # noqa: E501
    pages_dir = out / "pages"
    cli_expect(tmp_path, 1, "check-release", "--state", str(state),
               "--pages-dir", str(pages_dir), "--facts", str(facts_json))

    # 人为破坏一页：把 parameter_table 参数改成与事实不符 → 非视觉维度失败
    d = load_state(state)
    for br in d["batch_runs"]:
        for op in br["output_pages"]:
            if op.get("page_id") == "parameter_table":
                for row in op["defn"].get("param_table", []):
                    row["value"] = 999  # 与 facts 中 peak_torque=120 不符
    Path(state).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    res = cli_expect(tmp_path, 1, "check-release", "--state", str(state),
                     "--pages-dir", str(pages_dir), "--facts", str(facts_json))
    out_json = json.loads(res)
    assert out_json["release_blocked"] is True
    assert "parameter_table" in out_json["audit"]["failing_pages"]


# ---------------------------------------------------------------- 单页失败仅重建责任页
def test_rebuild_only_failing_page(tmp_path) -> None:
    state = tmp_path / "state.json"
    facts_json = tmp_path / "facts.json"
    facts_json.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")
    setup_plan(tmp_path, state)
    out = tmp_path / "out"
    run_batch_pil(tmp_path, state, "batch_1", facts_json, out, seed=1)

    before = snapshot_dir(out)
    # 仅重建 cover 页（用不同 seed 让其真实变化）
    cli(tmp_path, "rebuild-page", "--state", str(state), "--page-id", "cover",
        "--output-dir", str(out), "--imggen-provider", "pil", "--seed", "999")
    after = snapshot_dir(out)

    assert before["figures/cover.png"] != after["figures/cover.png"]  # 责任页图已重建
    # 其它页（principle / module 等）完全未被触碰
    for rel, data in before.items():
        if rel not in ("figures/cover.png",):
            assert after[rel] == data, f"unaffected page regenerated: {rel}"
    d = load_state(state)
    rebuilds = d.get("rebuilds", [])
    assert len(rebuilds) == 1
    assert rebuilds[0]["page_id"] == "cover"


def test_already_passed_unaffected_pages_not_regenerated(tmp_path) -> None:
    state = tmp_path / "state.json"
    facts_json = tmp_path / "facts.json"
    facts_json.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")
    setup_plan(tmp_path, state)
    out = tmp_path / "out"
    run_batch_pil(tmp_path, state, "batch_1", facts_json, out, seed=1)
    before = snapshot_dir(out)
    # 重建一个页（module_main 在 batch_1 中），其它已通过页保持字节不变
    cli(tmp_path, "rebuild-page", "--state", str(state), "--page-id", "module_main",
        "--output-dir", str(out), "--imggen-provider", "pil", "--seed", "555")
    after = snapshot_dir(out)
    for rel, data in before.items():
        if rel != "figures/module_main.png":
            assert after[rel] == data, f"unaffected page regenerated: {rel}"


# ---------------------------------------------------------------- 参数变更传播到相关页
def test_parameter_change_propagates_to_related_pages(tmp_path) -> None:
    state = tmp_path / "state.json"
    facts_json = tmp_path / "facts.json"
    facts_json.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")
    setup_plan(tmp_path, state)
    out = tmp_path / "out"
    run_batch_pil(tmp_path, state, "batch_1", facts_json, out, seed=1)
    before = snapshot_dir(out)

    # 参数 peak_torque 从 120 改为 150，重建 parameter_table 页
    new_facts = json.loads(json.dumps(FACTS))
    new_facts["params"]["peak_torque"] = 150
    new_facts_json = tmp_path / "facts2.json"
    new_facts_json.write_text(json.dumps(new_facts, ensure_ascii=False), encoding="utf-8")
    cli(tmp_path, "rebuild-page", "--state", str(state), "--page-id", "parameter_table",
        "--output-dir", str(out), "--imggen-provider", "pil", "--seed", "1",
        "--facts", str(new_facts_json))
    after = snapshot_dir(out)

    # 责任页 A4 页面字节变化（参数表数值变了）
    assert before["pages/parameter_table.png"] != after["pages/parameter_table.png"]
    # 重建记录的 defn 中参数值已更新为 150（参数变更传播到相关页）
    d = load_state(state)
    rebuild = d["rebuilds"][-1]
    row = next(r for r in rebuild["defn"]["param_table"] if r["param"] == "peak_torque")
    assert row["value"] == 150
    # 无关页字节不变
    assert before["pages/cover.png"] == after["pages/cover.png"]


# ---------------------------------------------------------------- 无后端 -> 外部任务包 + HOLD
def test_no_backend_external_task_package_and_hold(tmp_path) -> None:
    state = tmp_path / "state.json"
    facts_json = tmp_path / "facts.json"
    facts_json.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")
    setup_plan(tmp_path, state)
    out = tmp_path / "out"

    # 默认 external provider（无后端）→ 外部任务包 + HOLD，绝不假装成图
    cli(tmp_path, "run-batch", "--state", str(state), "--batch-id", "batch_1",
        "--prompt", "无后端批次", "--theory-version", "T4.1", "--truth-version", "PT-3",
        "--anchors", "a1", "--output-dir", str(out), "--facts", str(facts_json))
    br = batch_run(state, "batch_1")
    assert br["status"] == "external_pending"
    assert br["external_pending"] and not br["completed"]
    assert br["provider"]["external_dependency"] is True
    # 不生成任何假配图字节
    for op in br["output_pages"]:
        assert op["status"] == "external_pending"
        assert op["sha256"] is None
        assert op["generation"]["status"] == "external_pending"
        fig = Path(op["figure_path"]) if op.get("figure_path") else None
        if fig is not None:
            assert not fig.exists() or fig.suffix.endswith(".task.json")
    # 外部任务包确实写出
    ext_dir = out / "external_tasks"
    assert ext_dir.exists()
    assert any(ext_dir.glob("*.task.json"))
    # 绝不生成任何假配图 PNG
    assert not any((out / "figures").glob("*.png"))
    # 页面级状态保持 HOLD（external_pending），发布门放行会被阻止
    d = load_state(state)
    assert all(p["status"] == "external_pending" for p in d["pages"])


# ---------------------------------------------------------------- 预览与批准
def test_preview_and_approve(tmp_path) -> None:
    state = tmp_path / "state.json"
    facts_json = tmp_path / "facts.json"
    facts_json.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")
    setup_plan(tmp_path, state)
    out = tmp_path / "out"
    run_batch_pil(tmp_path, state, "batch_1", facts_json, out, seed=1)

    preview_json = tmp_path / "preview.json"
    cli(tmp_path, "preview-batch", "--state", str(state), "--batch-id", "batch_1",
        "--json-out", str(preview_json))
    preview = json.loads(Path(preview_json).read_text(encoding="utf-8"))
    assert preview["batch_id"] == "batch_1"
    assert preview["approved"] is False
    assert all("after_sha256" in item for item in preview["preview"])

    cli(tmp_path, "approve-batch", "--state", str(state), "--batch-id", "batch_1",
        "--approver", "owner", "--note", "ok")
    d = load_state(state)
    assert d["approvals"][0]["batch_id"] == "batch_1"
    assert d["approvals"][0]["approved_by"] == "owner"
    cli(tmp_path, "preview-batch", "--state", str(state), "--batch-id", "batch_1",
        "--json-out", str(preview_json))
    assert json.loads(Path(preview_json).read_text(encoding="utf-8"))["approved"] is True
