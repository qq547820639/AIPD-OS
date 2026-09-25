#!/usr/bin/env python3
"""门禁自检：这两台门**必须各带一支合规侧对照**。

为什么非要有合规侧：只看「改坏了该红」分不清「门真在拦」与「门永久红/顺带牵连」——
两侧读数一样的判据等于什么都没判。旧版这份自检只有两支负向断言
（只看子进程 `returncode != 0`，不看它为什么非零），⇒ 把 `outcome_acceptance.py`
或 `cad_maturity_gate.py` 改成「任何输入都退 1」，它照样绿。

四支读数：
- A1 只有产物、没有形状与验收字段的项目 ⇒ communication 不放行，且理由必须落在
     `communication_accepted=false` 这一格上；
- A2 同一族里把数字全链路铺齐、验收字段达标的项目 ⇒ communication 放行
     （A1 的开火前提，缺了它 A1 不可信）；
- B1 `faceted_brep` 运行时不论堆多少证据都到不了 C7；
- B2 `native_brep` 运行时把 C0..C7 全部要求项填上 ⇒ C7 放行（B1 的开火前提）。
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
GOOD_CHECKPOINT = ROOT / "assets" / "templates" / "project_checkpoint.json"

# 数字全链路的六个前置产物 + 两份验收/契约文件（与 outcome_acceptance 的判据同源）
THREAD_ARTIFACTS = ["requirements/requirements.md", "engineering/v1_engineering.md",
                    "manual/manual.pdf", "cad/model.step",
                    "cad/inspection_report.json", "manufacturing/bom.xlsx"]


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def _write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _acceptance(root: Path, require: str = "communication") -> tuple[int, dict]:
    proc = run([sys.executable, str(SCRIPTS / "outcome_acceptance.py"),
                "--project-root", str(root), "--require", require])
    try:
        body = json.loads(proc.stdout)
    except ValueError:
        body = {"_unparsed": proc.stdout[-400:]}
    return proc.returncode, body


def _maturity_gate(manifest: Path, target: str) -> tuple[int, str]:
    proc = run([sys.executable, str(SCRIPTS / "cad_maturity_gate.py"),
                "--manifest", str(manifest), "--target", target])
    return proc.returncode, proc.stdout


def _all_requirements_true() -> dict[str, bool]:
    """证据字典**从门禁模块自己取**，不在这里重抄一份键名。"""
    spec = importlib.util.spec_from_file_location("cad_maturity_gate_under_test",
                                                  SCRIPTS / "cad_maturity_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return {key: True for keys in module.REQUIREMENTS.values() for key in keys}


def checks(tmp: Path) -> list[dict]:
    out: list[dict] = []

    # ---- A1 只有产物：不放行，且理由落在 communication 这一格 -------------------
    a1 = tmp / "a1"
    for rel in THREAD_ARTIFACTS[:3]:
        _write(a1, rel, "x\n")
    _write(a1, "quality/outcome_contract.json", "{}")
    rc, body = _acceptance(a1)
    a1_ok = rc != 0 and body.get("communication_accepted") is False \
        and body.get("artifact_complete") is True
    out.append({"id": "A1_artifact_only_holds_communication", "passed": a1_ok,
                "read": {"rc": rc, "artifact_complete": body.get("artifact_complete"),
                         "digital_thread_complete": body.get("digital_thread_complete"),
                         "communication_accepted": body.get("communication_accepted")}})

    # ---- A2 合规侧：全链路 + 验收达标 ⇒ 放行（否则 A1 只是「永远红」）---------
    a2 = tmp / "a2"
    for rel in THREAD_ARTIFACTS:
        _write(a2, rel, "x\n")
    _write(a2, "quality/outcome_contract.json", "{}")
    _write(a2, "state/project_checkpoint.json", GOOD_CHECKPOINT.read_text(encoding="utf-8"))
    _write(a2, "manual/manual_quality_review.json", json.dumps(
        {"golden_reference_compared": True,
         "owner_or_independent_visual_acceptance": True,
         "score": 9.2, "threshold": 8.0}, ensure_ascii=False))
    rc, body = _acceptance(a2)
    a2_ok = rc == 0 and body.get("communication_accepted") is True \
        and body.get("checkpoint_shape", {}).get("status") == "valid"
    out.append({"id": "A2_full_thread_passes_communication", "passed": a2_ok,
                "read": {"rc": rc, "shape": body.get("checkpoint_shape", {}).get("status"),
                         "communication_accepted": body.get("communication_accepted")}})

    # ---- B1 faceted BREP 到不了 C7 -------------------------------------------
    evidence = _all_requirements_true()
    b1 = tmp / "b1_manifest.json"
    b1.write_text(json.dumps({"runtime": "faceted_brep", "evidence": evidence}),
                  encoding="utf-8")
    rc, stdout = _maturity_gate(b1, "C7")
    b1_ok = rc != 0 and "C7" in stdout
    out.append({"id": "B1_faceted_brep_cannot_reach_C7", "passed": b1_ok,
                "read": {"rc": rc}})

    # ---- B2 合规侧：native BREP + 全证据 ⇒ C7 放行（否则 B1 只是「永远红」）----
    b2 = tmp / "b2_manifest.json"
    b2.write_text(json.dumps({"runtime": "native_brep", "evidence": evidence}),
                  encoding="utf-8")
    rc, stdout = _maturity_gate(b2, "C7")
    b2_ok = rc == 0
    out.append({"id": "B2_native_brep_reaches_C7", "passed": b2_ok,
                "read": {"rc": rc, "tail": stdout.strip().splitlines()[-1:]}})

    return out


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        results = checks(Path(td))
    failures = [r for r in results if not r["passed"]]
    print(json.dumps({"passed": not failures,
                      "checks": results,
                      "failures": [r["id"] for r in failures]},
                     ensure_ascii=False, indent=2))
    # 少跑到任何一支都算失败：四支都在，才说明「红」与「绿」两侧都被看过
    if len(results) != 4:
        return 7
    return 0 if not failures else 6


if __name__ == "__main__":
    raise SystemExit(main())
