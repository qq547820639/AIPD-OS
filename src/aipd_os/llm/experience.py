"""成功经验回灌（把已有成功轨迹作为运行时资产注入 LLM 提示）。

定位修正（对应「所有规则都是为了将已有经验赋予 AI」的原初意图）：
此前 golden samples / 成功轨迹只作为**评测资产**使用，从不回灌模型——
经验被写成了硬代码，而不是喂给 AI。本模块把它们变成 LLM Provider 的
运行时提示资产（确定性、可哈希、可审计）：

- ``DEFAULT_EXPERIENCE``：从黄金项目（tests/fixtures/golden_projects，
  演示资产已撤出产品树）蒸馏出的
  紧凑经验条目（随包内置，不依赖仓库文件路径）；
- :func:`render_experience`：渲染为系统提示补充段落（受 max_chars 限制）；
- :class:`ExperienceFeedback`：持有经验集合，提供
  ``system_supplement()`` 与 ``fingerprint()``（提示内容可追溯）。
"""
from __future__ import annotations

import hashlib

# 从黄金项目蒸馏的既有成功经验（紧凑、领域无关、可审计）。
# 每条：objective（目标）、practice（已验证的做法）、outcome（结果）。
DEFAULT_EXPERIENCE: list[dict[str, str]] = [
    {
        "objective": "连续附页产品手册（外骨骼/消费电子/手动工具黄金项目）",
        "practice": "先规划页数、页任务、锚点与批次；封面/原理/样板页建立 "
                    "Visual Bible，锚点通过独立视觉审计后再扩页；每批 2-5 页且"
                    "输入包含上一批页面与事实版本；图像后端不可用时写外部任务包"
                    "并 HOLD，绝不伪造图片。",
        "outcome": "手册链黄金项目全绿：页面产出、批次连续性、PDF/ZIP、"
                   "页面谱系与质量报告全部落地。",
    },
    {
        "objective": "参数化 CAD 黄金闭环（真实 B-Rep 内核）",
        "practice": "从 Product Truth Baseline 与 Engineering Baseline 取参数，"
                    "生成可编辑参数化源码；改参→重生成→STEP→源导出→重载→几何"
                    "校验→哈希→差异→写回；faceted/mesh 永不越 C1 声称工程级。",
        "outcome": "C0→C3 真实内核闭环通过（参数可追溯、可重生成、可校验）。",
    },
    {
        "objective": "RFQ-报价-实验-纠正 供应链闭环",
        "practice": "正式报价与实验数据必须真实取得并登记（来源/时间/证据），"
                    "失败项登记风险并生成纠偏任务；等待外部输入时标记 "
                    "blocked_external 并继续其他独立工作。",
        "outcome": "供应链黄金项目全绿：报价/实验/纠偏/写回全部有证据。",
    },
]

# 经验条目之上恒附加的行为原则（护栏的"经验"面，与硬门禁互补）
_EXPERIENCE_PRINCIPLES = (
    "已核准的经验原则：检索到 ≠ 证实（外部来源最多作为可靠外部证据，绝不"
    "自动当作已验证事实）；无法验证的数值不得填充伪精确默认值；能力不足时"
    "诚实标记外部依赖并给出可操作下一步，绝不假装成功；涉及方向、价值、"
    "不可逆投入、安全法规时生成决策包交由所有者拍板。"
)


def render_experience(examples: list[dict[str, str]],
                      max_chars: int = 2400) -> str:
    """把经验条目渲染为系统提示补充段落（受 max_chars 截断，保证确定性）。"""
    if not examples:
        return ""
    parts = [_EXPERIENCE_PRINCIPLES, "既有成功经验（供参考，非强制规则）："]
    for i, ex in enumerate(examples, 1):
        text = (
            f"{i}. 目标：{ex.get('objective', '')}\n"
            f"   已验证做法：{ex.get('practice', '')}\n"
            f"   结果：{ex.get('outcome', '')}"
        )
        parts.append(text)
    rendered = "\n".join(parts)
    if len(rendered) > max_chars:
        rendered = rendered[:max_chars]
    return rendered


class ExperienceFeedback:
    """经验回灌资产：渲染提示补充 + 内容指纹（可审计）。"""

    def __init__(self, examples: list[dict[str, str]] | None = None,
                 source: str = "bundled-golden-trajectories",
                 max_chars: int = 2400) -> None:
        self.examples = list(examples if examples is not None
                             else DEFAULT_EXPERIENCE)
        self.source = source
        self.max_chars = max_chars

    def system_supplement(self) -> str:
        """渲染系统提示补充（无经验时为空串——不改变基线行为）。"""
        return render_experience(self.examples, max_chars=self.max_chars)

    def fingerprint(self) -> str:
        """经验内容的 SHA-256 指纹（记录到 meta，提示内容可追溯）。"""
        digest = hashlib.sha256()
        digest.update(self.source.encode("utf-8"))
        for ex in self.examples:
            digest.update("\x00".join(
                [ex.get("objective", ""), ex.get("practice", ""),
                 ex.get("outcome", "")]).encode("utf-8"))
        return digest.hexdigest()[:16]


def load_experience_from_dir(path: str, max_chars: int = 2400) -> ExperienceFeedback:
    """从黄金项目目录装载经验条目（仓库/评测场景使用；安装包用内置默认）。"""
    import json
    from pathlib import Path

    examples: list[dict[str, str]] = []
    base = Path(path)
    if base.is_dir():
        for proj_file in sorted(base.glob("*/project.json")):
            try:
                data = json.loads(proj_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - 单个项目解析失败不影响其余
                continue
            if isinstance(data, dict) and data.get("brief"):
                examples.append({
                    "objective": f"{data.get('name', '')}: {data.get('goal', '')}",
                    "practice": str(data.get("brief", "")),
                    "outcome": "黄金项目验收项：" + ", ".join(
                        data.get("expected") or []),
                })
    return ExperienceFeedback(examples=examples or DEFAULT_EXPERIENCE,
                              source=f"golden-dir:{path}", max_chars=max_chars)


__all__ = [
    "DEFAULT_EXPERIENCE",
    "ExperienceFeedback",
    "render_experience",
    "load_experience_from_dir",
]
