"""清单指纹这一把尺的常驻牙（F-REPORT-MANIFEST-FINGERPRINT 第 83 片）。

它管三件事：**规范摘要的规则**（只剥 `generated_at`，键序与缩进不参与）、
**读不出清单时的三态**（空串 + 说明，不抛也不当"值为空"），以及最要紧的一条——
**生产侧真被走过**：直接用真 `pytest --json-report` 跑一条真用例，读那份真报告。
最后这条是本仓的老教训：手写夹具全绿并不能证明 `tests/conftest.py` 里那个 hook
在生产姿势下被调用过（第 79 片用同一手法一次抓出 3 个缺陷）。

独立性说明：`_independent_digest` 是把规则**另写一遍**，不是复用被测模块的函数。
它挡的是"某一侧被改动而另一侧没跟着改"——把 `VOLATILE_KEYS` 清空、或把 `sort_keys`
关掉，模块侧读数变了而这把盲尺没变，等式当场翻。两侧同时改等于公开改契约，
diff 里看得见，不在它职责内。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_fingerprint as rf  # noqa: E402

MANIFEST = ROOT / "SOURCE_MANIFEST.json"
TOOL = ROOT / "scripts" / "release_fingerprint.py"
# 种子用例要"与本片的仓库状态无关"：第一次试跑借的是
# `tests/test_packaging.py::test_source_manifest_hashes_match_disk`，结果它自己先红了——
# 我正在改 `scripts/` 与 `tests/conftest.py` 而清单还没刷，那条用例判的就是清单↔磁盘一致。
# 换成读本文件那条纯函数的规则用例：不依赖清单新鲜度，也不依赖外部服务。
SEED_FILE = "tests/test_report_manifest_fingerprint.py"
SEED_SPEC = SEED_FILE + "::test_reordering_keys_does_not_move_the_digest"


def _independent_digest(path: Path) -> str:
    doc = json.loads(path.read_text(encoding="utf-8"))
    del doc["generated_at"]          # 缺键就该翻：夹具前提是生产形状
    blob = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def test_module_digest_matches_an_independently_written_copy() -> None:
    """同一把尺的两份写法必须在真清单上得同一个数（只有一份的话就没人管它写错没写错）。"""
    fp, err = rf.fingerprint_from_file(MANIFEST)
    assert err == "", err
    assert fp == _independent_digest(MANIFEST), "模块算法与另写一遍的那份不一致"
    assert len(fp) == 64 and fp == fp.lower()


def test_digest_ignores_only_generated_at_among_top_level_fields() -> None:
    """两极：只换时间戳 ⇒ 同一个数；动文件条目 ⇒ 不同的数。

    "只换时间戳必须绿"这一格是本片存在的理由——
    `release_evidence.py` → `generate_source_manifest` 每次生成都重写 `generated_at`，
    用整份文件的 sha256 当判据会把每轮正常收尾判成假红。
    """
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = rf.fingerprint_of_document(doc)

    only_timestamp = json.loads(json.dumps(doc))
    only_timestamp["generated_at"] = "2099-01-01T00:00:00+00:00"
    assert rf.fingerprint_of_document(only_timestamp) == base, "只换时间戳必须读成同一份清单"

    content_moved = json.loads(json.dumps(doc))
    content_moved["files"][0]["sha256"] = "0" * 64
    assert rf.fingerprint_of_document(content_moved) != base, "文件内容动了必须不同"

    added = json.loads(json.dumps(doc))
    added["files"].append({"path": "tests/zzz-new.py", "size": 1, "sha256": "1" * 64})
    assert rf.fingerprint_of_document(added) != base, "多一个文件条目也是内容变了"


def test_reordering_keys_does_not_move_the_digest(tmp_path: Path) -> None:
    """键序与缩进不参与摘要：同一内容两种排版必须同一个数（否则重排一下就成了"换清单"）。"""
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    want = rf.fingerprint_of_document(doc)
    shuffled = {k: doc[k] for k in sorted(doc, reverse=True)}
    assert rf.fingerprint_of_document(shuffled) == want
    path = tmp_path / "SOURCE_MANIFEST.json"
    path.write_text(json.dumps(shuffled, ensure_ascii=False, indent=4), encoding="utf-8")
    got, err = rf.fingerprint_from_file(path)
    assert err == "" and got == want, (err, got)


def test_unreadable_manifest_is_three_state_not_an_empty_value(tmp_path: Path) -> None:
    """读不出清单 ⇒ 空串 + 一句说明；缺文件/是目录/坏 JSON/顶层不是对象四档都要能归因。"""
    for build, needle in (
        (lambda p: None, "不存在"),
        (lambda p: p.mkdir(), "是目录"),
        (lambda p: p.write_text("{ not json", encoding="utf-8"), "JSONDecodeError"),
        (lambda p: p.write_text("[1, 2]", encoding="utf-8"), "顶层不是对象"),
    ):
        target = tmp_path / f"case{needle}.json"
        build(target)
        fp, err = rf.fingerprint_from_file(target)
        assert fp == "" and needle in err, (needle, fp, err)


def test_tool_face_prints_the_digest(tmp_path: Path) -> None:
    """命令行面（README 会这么写）：打的就是那个数，读不出时退 2 而不是打空行。"""
    proc = subprocess.run([sys.executable, str(TOOL), str(MANIFEST)],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == _independent_digest(MANIFEST)

    missing = subprocess.run([sys.executable, str(TOOL), str(tmp_path / "nope.json")],
                             capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    assert missing.returncode == 2, missing.stdout + missing.stderr
    assert "不存在" in missing.stdout, missing.stdout


def test_production_conftest_stamps_a_real_json_report(tmp_path: Path) -> None:
    """真生产者路径：用真 `pytest --json-report` 跑一条真用例，读那份真报告。

    这条是本片的牙。`closeout_verifier._pristine_report` 那种手写夹具全绿并不能证明
    `tests/conftest.py` 的 hook 真在生产姿势下写字段——把那段注入删掉，这里必须翻。
    """
    out = tmp_path / "producer-report.json"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", SEED_SPEC, "--json-report",
         f"--json-report-file={out}", "-q"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-2500:] + proc.stderr[-1500:]
    assert out.is_file(), f"报告没落盘：{proc.stdout[-800:]}"
    data = json.loads(out.read_text(encoding="utf-8"))
    fp = data.get("source_manifest_fingerprint")
    assert fp, f"真报告没带清单指纹——conftest 的注入没生效：{sorted(data)}"
    assert fp == _independent_digest(MANIFEST), "生产侧算的数与另写一遍的那份不一致"
    assert data["source_commit"], "夹具前提：同一只 hook 的旧面（source_commit）还在写"
