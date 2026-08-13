"""本地 B-Rep 适配器（'cad.local-brep'）。

本地参数化建模的轻量通道，通过 :mod:`aipd_os.cad.backends` 的真实可编辑
参数化 B-Rep 内核（CadQuery/OpenCASCADE）执行“改参 -> 重生成 -> STEP 导出
-> 可编辑原生源导出 -> 几何校验 -> 产物哈希/版本”的黄金闭环。

模块级导入 cx_mods 时若真实内核可用则优先使用 ``CadQueryBackend``（成熟度
上限 C2）；否则回退到 ``ContractBackend`` 仅作降级后端（成熟度诚实封顶 C1，
绝不冒充 C2）。
"""

from __future__ import annotations

from typing import Any, Dict

from aipd_os.cad.backends import get_default_backend
from aipd_os.execution.adapter import ToolAdapter, now, output_dir
from aipd_os.tool_adapters._common import meta, token_meta


class LocalBrepAdapter(ToolAdapter):
    provider = "local-opencascade-proxy"
    version = "1.0"
    maturity_ceiling = "C2"  # 真实内核实例化时达到；否则降级后端诚实封顶 C1

    def __init__(self) -> None:
        self._backend = get_default_backend()

    def capability_id(self) -> str:
        return "cad.local-brep"

    def discover(self) -> Dict[str, Any]:
        # 能力上限随实际后端运行时推导：真实内核可用 -> C2，降级后端 -> C1。
        ceiling = self._backend.maturity_ceiling()
        return meta(
            self.capability_id(),
            "Local B-Rep Parametric CAD",
            self.provider,
            self.version,
            available=True,
            maturity_ceiling=ceiling,
        )

    def validate_input(self, input: Dict[str, Any]) -> list:
        errors = []
        has_input = (input.get("features") or input.get("model_script")
                     or input.get("parameters"))
        if not has_input:
            errors.append("'features'、'model_script' 或 'parameters' 至少提供一个")
        return errors

    def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        backend = self._backend
        params = input.get("parameters")
        if isinstance(params, dict) and params:
            model = backend.load_native_model(None)
            for k, v in params.items():
                try:
                    model = backend.edit_parameter(model, k, v)
                except (KeyError, ValueError):
                    raise  # 未知/非法参数：如实失败，不吞异常
        else:
            model = backend.load_native_model(input.get("model_script"))

        # 几何有效性检查（不通过则如实失败，不产出伪造模型）。
        check = backend.geometry_validity_check(model)
        if not check["valid"]:
            raise ValueError(
                f"cad.local-brep 几何校验未通过: {check['errors']}")

        out_dir = output_dir()
        step_path = out_dir / "local_brep_model.step"
        native_path = out_dir / "local_brep_model.py"
        step_rec = backend.export_step(model, step_path)
        native_rec = backend.export_native(model, native_path)

        regen = backend.regenerate(model)
        result = {
            "backend": backend.name,
            "tool_version": backend.tool_version(),
            "maturity_ceiling": backend.maturity_ceiling(),
            "capability_status": backend.capability_status(),
            "parameters": regen.get("parameters"),
            "derived_geometry": regen.get("derived"),
            "geometry_validity": check,
            "artifacts": {
                "step": step_rec,
                "native_source": native_rec,
            },
            "generated_at": now(),
            "_meta": token_meta(str({"model": model.get("name"),
                                     "params": regen.get("parameters")})),
        }
        return result

    def normalize(self, result: Any) -> Dict[str, Any]:
        return result if isinstance(result, dict) else {"result": result}

    def collect_artifacts(self, result: Any) -> list:
        if isinstance(result, dict):
            artifacts = result.get("artifacts", {})
            return [art["path"] for art in artifacts.values() if art.get("path")]
        return []

    def persist_evidence(self, result: Any, run_id: str) -> list:
        return self.collect_artifacts(result)


__all__ = ["LocalBrepAdapter"]
