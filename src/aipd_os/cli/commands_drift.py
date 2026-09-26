"""`aipd truth drift`：让库自己发现「上游已变、下游还 active」（F-DRIFT 第 51 片）。

分档判据在 `product_truth/drift.py`（纯分类、可测）；这一层只负责
**每类制品怎么从当前世界把键重算出来**——它要知道 `bom.db` 在哪、声明文件在哪个路径、
模型是黄金件还是 STEP，这些都不该漏进 `product_truth` 层。

四类键的两端（实测得到，不是设定的）：

| 制品 | 记录里存的那份 → 当前怎么重算 |
|---|---|
| `drawing_spec` | `metadata.spec_sha256`（第 43 片起；**没有** input_signature）
  → 重新读那份声明文件求哈希 |
| `drawing_dxf` | `metadata.input_signature`（第 46 片）
  → `dxf_input_signature(当前声明哈希 + 当前模型摘要 + 出图参数)` |
| `bom` | `metadata.input_signature`（第 48 片）
  → `bom_input_signature(当前 header + 当前行)` |
| `bom_cost` | `metadata.input_signature`（第 48 片）
  → `cost_input_signature(当前 BOM 签名 + 记录里的口径五项)` |

拿不齐输入的，一律回 `(None, 原因)` 让上层判「不可判」——
第 46 片之前的 DXF、第 48 片那批没存口径值的 `bom_cost` 就落在这一档。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from aipd_os.product_truth.drift import Resolver, scan_drift

__all__ = ["build_resolvers", "cmd_truth_drift"]


def _spec_signature_resolver() -> Resolver:
    from aipd_os.cad.dxf_lineage import spec_file_digest

    def resolve(meta: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        stored = meta.get("spec_sha256")
        path = str(meta.get("path") or "")
        if not path:
            return None, stored, "记录里没写声明文件路径"
        current = spec_file_digest(Path(path))
        if current is None:
            return None, stored, f"声明文件读不到或不是合法 JSON：{path}"
        return current, stored, None

    return resolve


def _dxf_signature_resolver() -> Resolver:
    from aipd_os.cad.dxf_lineage import dxf_input_signature, model_input_digest, spec_file_digest

    def resolve(meta: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        stored = meta.get("input_signature")
        missing = [k for k in ("part", "revision", "views", "scale", "sheet",
                               "material", "sections", "details", "model_kind")
                   if meta.get(k) in (None, "") and not isinstance(
                       meta.get(k), (list, float))]
        if missing:
            return None, stored, ("出图参数没记全，重建不出同一次出图："
                                  + "、".join(missing))
        spec_path = str(meta.get("spec_path") or "")
        spec_sha: str | None = None
        if spec_path:
            spec_sha = spec_file_digest(Path(spec_path))
            if spec_sha is None:
                return None, stored, f"上游声明文件读不到：{spec_path}"
        kind = str(meta.get("model_kind") or "")
        source = str(meta.get("model_source") or "")
        if kind == "golden_default":
            model_digest = model_input_digest(step=None, native=None)["digest"]
        elif kind in ("step", "native"):
            if not source or not Path(source).is_file():
                return None, stored, f"模型源文件读不到：{source or '（记录里没写路径）'}"
            kwargs = {"step": source} if kind == "step" else {"native": source}
            model_digest = model_input_digest(**kwargs)["digest"]
        else:
            return None, stored, f"不认识的模型来源类型：{kind!r}"
        current = dxf_input_signature(
            spec_sha256=spec_sha,
            model={"kind": kind, "source": source, "digest": model_digest},
            part=str(meta["part"]), revision=str(meta["revision"]),
            views=[str(v) for v in meta.get("views") or []],
            scale=float(meta.get("scale") or 1.0), sheet=str(meta["sheet"]),
            material=str(meta.get("material") or ""),
            sections=[str(s) for s in meta.get("sections") or []],
            details=[str(d) for d in meta.get("details") or []])
        return current, stored, None

    return resolve


def _bom_resolvers(db_path: str, project_id: str) -> dict[str, Resolver]:
    """`bom` 与 `bom_cost` 共用一次「读当前 BOM」的开销。"""
    from aipd_os.bom import BomStore
    from aipd_os.bom.cost_lineage import bom_input_signature, cost_input_signature
    from aipd_os.cli._helpers import DEFAULT_TENANT
    from aipd_os.cli.commands_manufacturing import _bom_store_path

    CALIBER = ("tooling_fee", "target_quantity", "amortize_over", "nre",
               "margin_pct")

    def _current_bom_signature() -> tuple[str | None, str | None]:
        store = BomStore(str(_bom_store_path(db_path)))
        header = store.get_bom(DEFAULT_TENANT, project_id)
        if header is None:
            return None, "项目当前没有 BOM 头，无从重算 BOM 版本签名"
        lines = store.list_lines(DEFAULT_TENANT, project_id, bom_id=header.bom_id)
        if not lines:
            return None, "当前 BOM 没有任何行"
        return bom_input_signature(bom_id=header.bom_id,
                                   revision=str(header.revision),
                                   version_no=header.version_no, lines=lines), None

    def bom(meta: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        stored = meta.get("input_signature")
        if not str(meta.get("bom_id") or "").strip():
            return None, stored, "记录里没写 bom_id，认不出该重算哪张 BOM"
        current, why = _current_bom_signature()
        return current, stored, why

    def bom_cost(meta: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        stored = meta.get("input_signature")
        lacking = [k for k in CALIBER if k not in meta]
        if lacking:
            return None, stored, ("口径五项没记进 metadata（第 48 片那批记录），"
                                  "重建不出同一次核算：" + "、".join(lacking))
        bom_sig, why = _current_bom_signature()
        if bom_sig is None:
            return None, stored, why
        current = cost_input_signature(
            bom_signature=bom_sig, tooling_fee=meta["tooling_fee"],
            target_quantity=meta["target_quantity"],
            amortize_over=meta["amortize_over"], nre=meta["nre"],
            margin_pct=meta["margin_pct"])
        return current, stored, None

    return {"bom": bom, "bom_cost": bom_cost}


def build_resolvers(db_path: str, project_id: str) -> dict[str, Resolver]:
    resolvers: dict[str, Resolver] = {
        "drawing_spec": _spec_signature_resolver(),
        "drawing_dxf": _dxf_signature_resolver()}
    resolvers.update(_bom_resolvers(db_path, project_id))
    return resolvers


def cmd_truth_drift(args: Any) -> int:
    """``aipd truth drift``：只读地扫一遍有效记录，报告哪几条「该 stale 却还是 active」。

    不改任何状态（判据与理由见 `product_truth/drift.py` 的模块 docstring）。
    有漂移就退 4（与 propagate「有下游待返工即 4」同一档），不可判只报不判。
    """
    from aipd_os.cli._helpers import _emit
    from aipd_os.cli.commands_manufacturing import _resolve_project
    from aipd_os.product_truth import ProductTruthStore
    from aipd_os.state.db import AIPDStateDB

    db = Path(args.db)
    if not db.exists():
        print(f"状态库不存在：{db}")
        return 2
    tenant = str(getattr(args, "tenant", None) or "default")
    try:
        pid = _resolve_project(AIPDStateDB(str(db)), getattr(args, "project", None))
    except ValueError as exc:
        print(f"错误：{exc}")
        return 1
    store = ProductTruthStore(str(db), tenant_id=tenant, project_id=pid)
    report = scan_drift(store, resolvers=build_resolvers(str(db), pid),
                        tenant_id=tenant, project_id=pid)
    counts = report["counts"]
    payload = {"command": "truth drift", "ok": report["clean"],
               "project": pid, "scanned": report["scanned"],
               "counts": counts,
               "should_be_stale": report["should_be_stale"],
               "drifted": counts["drifted"],
               "undecidable": counts["undecidable"],
               "no_key": counts["no_record_signature"],
               "undecidable_items": (report["buckets"]["undecidable"]
                                     + report["buckets"]["no_record_signature"]),
               "nothing_scanned": report["nothing_scanned"]}

    def prose():
        if report["nothing_scanned"]:
            print("库里没有任何有效（active/stale）的制品版本记录可扫"
                  "（先跑 aipd drawing generate --db / cost calc --truth-lineage）")
            return
        print(f"扫描 {report['scanned']} 条有效制品记录："
              f"一致 {counts['in_sync']}、漂移 {counts['drifted']}、"
              f"不可判 {counts['undecidable']}、没有可比对的键 "
              f"{counts['no_record_signature']}")
        for r in report["should_be_stale"]:
            print(f"  ! {r['record_id']}（{r['artifact']}）还挂着 active，"
                  f"但当前输入算出的键已经不同："
                  f"{r['stored_signature']} → {r['current_signature']}")
        stale_ids = {r["record_id"] for r in report["should_be_stale"]}
        for r in report["buckets"]["drifted"]:
            if r["record_id"] in stale_ids:
                continue
            print(f"  · {r['record_id']}（{r['artifact']}）状态 {r['status']}："
                  "键已不同（已被标过，不算待处理）")
        for r in report["buckets"]["undecidable"]:
            print(f"  ? {r['record_id']}（{r['artifact']}）不可判：{r['reason']}")
        for r in report["buckets"]["no_record_signature"]:
            print(f"  ? {r['record_id']}（{r['artifact']}）没有可比对的键：{r['reason']}")
        if counts["drifted"]:
            print("未收口：有制品记录的当前输入与登记时不一致（退码 4）。")
            print("本命令只读：不会替你把它标 stale——要传播请跑 aipd truth propagate。")
        else:
            print("没有发现漂移（不可判的那几条不算通过，也不算漂移）。")

    _emit(args, payload, prose)
    return 0 if report["clean"] else 4
