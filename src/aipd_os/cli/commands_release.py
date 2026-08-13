"""发布 / 测试 / 评估 / 打包 / 审计相关命令。

- ``aipd audit``：生成能力矩阵审计产物；
- ``aipd release check``：版本真实性审计 + 生产发布门禁；
- ``aipd test`` / ``aipd eval`` / ``aipd package``：测试 / 评估 / 构建发布包。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from aipd_os.cli._helpers import (
    _build_release_impl,
    _emit,
    _import_module,
    _repo_root,
    _run_evals_cli,
    _run_pytest,
    _run_script_main,
)


# ---- audit：生成能力矩阵审计产物（repository_snapshot / capability_matrix）----
def cmd_audit(args):
    repo = Path(args.repo) if args.repo else _repo_root()
    out = Path(args.out)
    mod = _import_module("capability_matrix")
    summary = mod.generate(str(repo), str(out))
    result = {"command": "audit", "ok": True, **summary}
    _emit(args, result, lambda: print(json.dumps(summary, ensure_ascii=False, indent=2)))
    return 0


# ---- release check：版本真实性审计 + 生产发布门禁 + 通过性报告 ----
def cmd_release_check(args):
    repo = Path(args.repo) if args.repo else _repo_root()
    manifest_path = repo / "RELEASE_MANIFEST.json"
    if not manifest_path.exists():
        err = f"未找到 {manifest_path}，无法进行发布就绪检查；请先构建发布包。"
        if getattr(args, "json", False):
            print(json.dumps({"command": "release check", "ok": False, "error": err},
                             ensure_ascii=False))
        else:
            print(f"错误：{err}", file=sys.stderr)
        return 1

    audit = _import_module("audit_repo").audit_repo(repo)
    prg = _import_module("production_release_gate")
    rc, out = _run_script_main(prg, ["--manifest", str(manifest_path), "--target", args.target])
    try:
        gate = json.loads(out)
    except Exception:
        gate = {"passed": rc == 0}
    result = {"command": "release check", "ok": True, "repo": str(repo),
              "target": args.target, "audit": audit,
              "gate_passed": gate.get("passed", rc == 0), "gate": gate}
    _emit(args, result, lambda: print(json.dumps(result, ensure_ascii=False, indent=2)))
    return 0


# ---- test：运行测试套件（映射 run-tests）----
def cmd_test(args):
    rc = _run_pytest(_repo_root())
    result = {"command": "test", "ok": rc == 0, "exit_code": rc}
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    return rc


# ---- eval：运行评估套件（映射 run-evals）----
def cmd_eval(args):
    out = args.out or str(_repo_root() / "evals_out")
    rc = _run_evals_cli(_repo_root(), args.evals, args.provider, out,
                        args.threshold, getattr(args, "baseline", None),
                        json_mode=bool(getattr(args, "json", False)))
    result = {"command": "eval", "ok": rc == 0, "out": out}
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    return rc


# ---- package：构建发布包（映射 build-release）----
def cmd_package(args):
    rc = _build_release_impl(args)
    result = {"command": "package", "ok": rc == 0, "version": args.version}
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    return rc
