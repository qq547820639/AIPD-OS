"""发布 / 测试 / 评估 / 打包 / 审计相关命令。

- ``aipd audit``：生成能力矩阵审计产物；
- ``aipd release check``：版本真实性审计 + 生产发布门禁；
- ``aipd release manifest``：从 BOM 库 / Product Truth / 图纸证据现取装配门禁可消费的
  发布就绪证据文档（门禁的 ``gdt_covers_ctq`` 因此不再依赖手写 JSON）；
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


# ---- release manifest：现取装配发布就绪证据文档（数字不手抄）----
def cmd_release_manifest(args):
    from aipd_os.release_manifest import build_release_manifest

    db = Path(args.db)
    if not db.is_file():
        print(f"状态库不存在：{db}")
        return 2
    out = Path(args.out) if args.out else db.parent / "release-evidence.json"
    doc = build_release_manifest(
        db_path=db, tenant_id=args.tenant, project_id=args.project,
        drawings=[Path(p) for p in (args.drawing or [])], bom_id=args.bom,
        model=args.model, steps_doc=args.steps_doc, dfm_doc=args.dfm_doc,
        assembly_step=args.assembly_step,
        units=args.units,
        datum_scheme=args.datum_scheme, approval_status=args.approval_status,
        out_path=out, baseline_path=getattr(args, "baseline", None))

    baseline_note = ""
    if getattr(args, "write_baseline", None):
        from aipd_os.delivery_baseline import artefact_index, write_baseline
        from aipd_os.release_manifest import _hashed_artifacts

        ack = getattr(args, "acknowledge_not_ready", "") or ""
        blocking = sorted(i["kind"] for i in doc["issues"] if i["blocking"])
        if blocking and not ack:
            print(f"这份证据还有阻断项（{blocking}），不落成基线：下一版会把「没人放行过的"
                  "一次运行」当成上一版交付来比对。确实要先落盘就加 "
                  "--acknowledge-not-ready 写明理由")
            return 2
        raw = _hashed_artifacts({k: v for k, v in doc.items()
                                 if k not in ("issues", "eco")})
        artifacts = {path: entry["sha256"] for path, entry
                     in artefact_index(raw, out.parent).items()}
        written = write_baseline(Path(args.write_baseline), artifacts, out.parent,
                                 release=getattr(args, "release_label", ""),
                                 release_ready=bool(doc["ok"]), acknowledgement=ack)
        baseline_note = (f"基线已落盘：{args.write_baseline}"
                         f"（{len(written['artifacts'])} 条，就绪={doc['ok']}"
                         + (f"，已承认未就绪：{ack}" if ack else "")
                         + "，下一版用 --baseline 指回它）")

    def prose():
        print(f"发布就绪证据文档：{out}")
        print(f"  runtime={doc['runtime']} ctq={len(doc['ctq'])} gdt={len(doc['gdt'])} "
              f"图纸={doc['producer']['drawings_referenced']} 张")
        for key in ("model_version", "bom_version", "drawings_version",
                    "model_part_count", "bom_line_count", "drawing_count",
                    "assembly_drawing_count", "part_drawing_count",
                    "assembly_instructions", "assembly_steps",
                    "step_assemblies", "assembly_model",
                    "dfm_dfa", "dfm_summary"):
            if key in doc:
                print(f"  {key} = {doc[key]}")
            else:
                print(f"  {key} = （未取到，不编造）")
        eco = doc.get("eco") or {}
        if eco:
            print(f"  eco 覆盖={eco.get('coverage', '（未取到，不编造）')} "
                  f"单={eco.get('orders')} 条 / 交付物={eco.get('artifacts')} 条："
                  f"已闭合 {len(eco.get('covered_paths', []))}"
                  f"、无有效单 {len(eco.get('uncovered', []))}"
                  f"、待复验 {len(eco.get('unverified', []))}"
                  f"、无单可判 {len(eco.get('undetermined', []))}")
            since = eco.get("since_baseline") or {}
            print(f"  基线={eco.get('baseline') or '（未给 ⇒ 不声称「只改了这些」）'} "
                  f"判定={eco.get('baseline_coverage')}"
                  f"：新增 {len(since.get('added', []))}、变了 {len(since.get('modified', []))}"
                  f"、下线未认领 {len(eco.get('removed_unclaimed', []))}"
                  f"、证明没改 {len(eco.get('unchanged_since_baseline', []))}")
            if baseline_note:
                print(f"  {baseline_note}")
        else:
            print("  eco 覆盖 = （未取到，不编造）")
        for issue in doc["issues"]:
            mark = "阻断" if issue["blocking"] else "提示"
            print(f"  [{mark}] {issue['kind']}: {issue['detail']}")
        if not doc["issues"]:
            print("  无问题项")
        print("  说明：gdt 只从「图纸上真标了公差 + 显式 ctq_ref + 数值与 CTQ 一致」"
              "长出来；未对齐的版本字段留给门禁判红，不代为统一。")
    _emit(args, doc, prose)
    return 0 if doc["ok"] else 4


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
