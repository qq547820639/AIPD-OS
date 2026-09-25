"""图纸声明 → Product Truth 血缘边的**生产者**（F-LINEAGE-PROD 第 43 片）。

改前 `truth_lineage` 在生产侧只有一个来源：`product_intelligence/gate.commit_snapshot`
写的「PI 需求 / Feature → truth 记录」。CTQ 与图纸之间**没有人连边**，所以
`aipd truth propagate --upstream <CTQ>` 走到第二跳就断——一份已经按旧 CTQ 出好的
声明不会被打上 stale。这一片把那条边补上：`aipd drawing spec` 成功落盘时，
按声明里**实际引用到**的 `ctq_ref` 连 `ctq → artifact_version` 边。

口径：

1. **只连真引用到的**：`spec_from_ctq` 会把有歧义/未收口的条目的 `ctq_ref` 去掉
   （见其口径 4），所以取的是 spec 里剩下的那些 ref，而不是库里全部 active CTQ。
   给没参与的 CTQ 连边 = 让传播去打扰一条与本图无关的要求。
2. **HOLD 不写血缘**：有 gap 时连 spec 文件都不落盘（口径 6），血缘同理不写——
   一份不存在的声明没有版本可言。
3. **一条内容一个版本**：`artifact_version` 记录的 content 带声明正文的 sha256，
   所以"重跑但内容没变"命中同一行（幂等），"CTQ 改了 ⇒ 声明变了"自然另起一行。
4. **信任上限 high**：这条记录陈述的是"这个哈希的这份声明由这几条 CTQ 生成"，
   哈希是自证的，但"生成过程对不对"没有独立复核，故不给 `verified`
   （与第 42 片 `_write_back_facts` 同一取舍）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = ["consumed_ctq_ids", "record_spec_lineage"]


def consumed_ctq_ids(spec: dict[str, Any]) -> list[str]:
    """声明正文里真正引用的 CTQ 记录号（尺寸条目、形位条目、基准三处都算）。"""
    refs: set[str] = set()
    for entry in spec.get("features") or []:
        candidates = [entry.get("ctq_ref")]
        candidates += [g.get("ctq_ref") for g in entry.get("gdt") or []]
        for ref in candidates:
            if ref:
                refs.add(str(ref))
    for datum in spec.get("datums") or []:
        if datum.get("ctq_ref"):
            refs.add(str(datum["ctq_ref"]))
    return sorted(refs)


def record_spec_lineage(store: Any, spec: dict[str, Any], *, path: Path,
                        relation: str = "affects",
                        tenant_id: str | None = None,
                        project_id: str | None = None) -> dict[str, Any]:
    """写一条 `artifact_version` 记录 + 每条参与 CTQ 一条边，返回落库摘要。

    边由 `LineageGraph.add_edge` 写（`INSERT OR IGNORE` + 环检测），
    所以重跑同一份内容既不会重复建行也不会因重复边报错。
    """
    from aipd_os.product_truth.lineage import LineageGraph
    from aipd_os.product_truth.models import SourceRef, TruthRecord

    refs = consumed_ctq_ids(spec)
    digest = hashlib.sha256(
        json.dumps(spec, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    name = Path(path).name
    content = f"drawing spec {name} sha256={digest[:16]} ← CTQ {'、'.join(refs)}"

    found = store.find_id_by_type_and_content(
        "artifact_version", content, tenant_id=tenant_id, project_id=project_id)
    created = found is None
    record_id = found or store.add(
        TruthRecord(
            record_type="artifact_version",
            content=content,
            source=SourceRef(file=str(path), note=f"spec_sha256={digest}"),
            trust_level="high",
            metadata={"artifact": "drawing_spec", "path": str(path),
                      "spec_sha256": digest, "ctq_refs": refs}),
        tenant_id=tenant_id, project_id=project_id)

    graph = LineageGraph(store, tenant_id=tenant_id or store.tenant_id,
                         project_id=project_id or store.project_id)
    for ctq_id in refs:
        graph.add_edge(ctq_id, record_id, relation)
    return {"record_id": record_id, "created": created,
            "ctq_refs": refs, "edges": len(refs),
            "spec_sha256": digest}
