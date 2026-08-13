"""小平面（faceted）B-Rep 适配器（'cad.faceted-fallback'）。

作为本地降级，生成小平面 STEP 数字样机；成熟度上限必须封顶为 C1。
"""

from __future__ import annotations

from typing import Any

from aipd_os.execution.adapter import ToolAdapter, now, output_dir
from aipd_os.tool_adapters._common import meta, token_meta


def _cube_mesh(size: float = 10.0) -> dict[str, Any]:
    h = size / 2.0
    v = [
        (-h, -h, -h), (h, -h, -h), (h, h, -h), (-h, h, -h),
        (-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h),
    ]
    f = [
        (0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (2, 3, 7), (2, 7, 6),
        (0, 3, 7), (0, 7, 4), (1, 2, 6), (1, 6, 5),
    ]
    return {"name": "cube", "vertices": v, "faces": f}


class FacetedAdapter(ToolAdapter):
    provider = "local-faceted-step"
    version = "1.0"
    maturity_ceiling = "C1"  # 必须封顶为 C1

    def capability_id(self) -> str:
        return "cad.faceted-fallback"

    def discover(self) -> dict[str, Any]:
        return meta(
            self.capability_id(),
            "Faceted B-Rep Fallback",
            self.provider,
            self.version,
            maturity_ceiling=self.maturity_ceiling,
        )

    def validate_input(self, input: dict[str, Any]) -> list:
        return []

    def execute(self, input: dict[str, Any]) -> dict[str, Any]:
        meshes = input.get("meshes") or [_cube_mesh(float(input.get("size", 10.0)))]
        # 生成真实的小平面 STEP 文件（复用 scripts/faceted_step.py 的写入逻辑）
        step_text, stats = self._write_step(meshes)
        out_dir = output_dir()
        path = out_dir / "faceted_digital_prototype.step"
        path.write_text(step_text, encoding="ascii")
        result = {
            "path": str(path),
            "stats": stats,
            "maturity_ceiling": self.maturity_ceiling,
            "note": "小平面数字样机：不可用于正式图纸/量产的 B-Rep 与 GD&T 发布",
            "_meta": token_meta(step_text),
        }
        return result

    def _write_step(self, meshes: list) -> tuple:
        # 精简的 STEP 生成器（与 scripts/faceted_step.py 语义一致）
        entities: list = []
        solids = []
        faces = 0
        points = 0
        for item in meshes:
            name = str(item["name"]).replace("'", "")
            vrefs = []
            for v in item["vertices"]:
                vrefs.append(len(entities) + 1)
                entities.append(
                    "CARTESIAN_POINT('',(" + ",".join(f"{float(x):.8f}" for x in v) + "))"
                )
            points += len(vrefs)
            frefs = []
            for tri in item["faces"]:
                loop = len(entities) + 1
                entities.append(
                    "POLY_LOOP('',(" + ",".join(f"#{vrefs[int(i)]}" for i in tri) + "))"
                )
                bound = len(entities) + 1
                entities.append(f"FACE_OUTER_BOUND('',#{loop},.T.)")
                frefs.append(len(entities) + 1)
                entities.append(f"FACE('',(#{bound}))")
            faces += len(frefs)
            shell = len(entities) + 1
            entities.append("CLOSED_SHELL('',(" + ",".join(f"#{i}" for i in frefs) + "))")
            solids.append(len(entities) + 1)
            entities.append(f"FACETED_BREP('{name}',#{shell})")
        header = [
            "ISO-10303-21;", "HEADER;",
            "FILE_DESCRIPTION(('AIPD faceted BREP'),'2;1');",
            f"FILE_NAME('faceted_digital_prototype.step','{now()}',('AIPD'),('AIPD'),'local fallback','AIPD-OS','internal digital prototype');",  # noqa: E501
            "FILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));", "ENDSEC;", "DATA;",
        ]
        data = [f"#{i}={e};" for i, e in enumerate(entities, 1)]
        text = "\n".join(header + data + ["ENDSEC;", "END-ISO-10303-21;", ""])
        stats = {
            "entities": len(entities),
            "solids": len(solids),
            "faces": faces,
            "points": points,
        }
        return text, stats

    def collect_artifacts(self, result: Any) -> list:
        if isinstance(result, dict) and result.get("path"):
            return [result["path"]]
        return []

    def persist_evidence(self, result: Any, run_id: str) -> list:
        if isinstance(result, dict) and result.get("path"):
            return [result["path"]]
        return []


__all__ = ["FacetedAdapter"]
