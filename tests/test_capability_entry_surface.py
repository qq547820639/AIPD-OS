"""F-REG-01：能力登记表里「入口可调用」这一列必须是真的证据，不是装饰。

修前实测（`docs/audit/capability_matrix.json` 的 probe 字段）：78 行里 **11 行**
`entry_callable=false`，其中 `research.attachment_reading` 还被判成
`fully_implemented`。逐条诊断后分成三类，而这三类此前混在同一个 false 里：

1. **入口字符串本身就是错的**：`cad.2d_drawings` 写成
   ``src/aipd_os/cli/commands_drawing.py:cmd_drawing``（文件路径形态，被 ``/``
   候选分隔符拆成一地碎片）、`cad.text_to_cad` 写成裸词 ``cad_adapter``、
   `manual.real_image_generation` 写成 ``imggen.adapter``（少了包名）、
   `research.multi_source_search` 指向一个**不存在的函数** ``selftest``；
2. **探针自己的假负**：`research.source_worker.run_source` 写法正确，但
   `scripts/research/` 不在探测临时加的 path 上（那批脚本用顶层
   ``import _http_runtime``），于是一行真入口被读成不可调用；
3. 合法的 ``entry_point=None``（5 行 external_dependency）。

`probe_classification` 明确不看 `entry_callable`（文件 + 测试决定分类），所以这一列
过去只是写着好看：错的入口字符串永远不会判红。这里把它变成常驻门禁——
不可解析的入口要么不存在，要么必须在本文件的声明表里写明理由。
"""
from __future__ import annotations

from pathlib import Path

from aipd_os.registry import (
    load_default_registry,
    probe_classification,
    probe_entry_callable,
)

REPO = Path(__file__).resolve().parent.parent

#: entry_point 有意留空的能力：外部依赖未配置，没有本地入口可指
EXTERNAL_WITHOUT_ENTRY = {
    "research.standards_regulations",
    "research.patents_competitors",
    "cad.assembly_constraints",
    "cad.continuous_kinematics",
    "cad.cae_fatigue",
}


def _rows():
    return load_default_registry().all()


def _unresolved():
    return [c for c in _rows() if not probe_entry_callable(c.entry_point, REPO)]


def test_every_entry_point_resolves_or_is_declared() -> None:
    """不可解析的入口必须被逐条声明，新增一条不写理由就判红。"""
    stray = [c.id for c in _unresolved()
             if c.id not in EXTERNAL_WITHOUT_ENTRY
             and not (c.entry_point is None and c.external_dependency)]
    assert not stray, f"这些能力声明的 entry_point 解析不到可调用对象：{stray}"


def test_fully_implemented_never_rests_on_a_dead_entry_point() -> None:
    """自称"完全实现"的能力，其声明入口必须真的能取到——否则结论建立在空名字上。

    分类用 `probe_classification` 现算（登记表里的静态字段可能已是旧值）。
    """
    dead = [c.id for c in _unresolved()
            if probe_classification(c, REPO,
                                    external_dependency=c.external_dependency)
            == "fully_implemented"]
    assert not dead, f"fully_implemented 却入口不可解析：{dead}"


def test_probe_reads_the_whole_surface() -> None:
    """分母前提：探针必须覆盖到全表，且绝大多数行确实解析得到（否则上面两条是空转）。"""
    rows = _rows()
    assert len(rows) > 60, f"登记表只读到 {len(rows)} 行，分母不对"
    resolved = len(rows) - len(_unresolved())
    assert resolved >= len(rows) * 0.9, (
        f"只有 {resolved}/{len(rows)} 行入口可解析，探针或数据已经烂到不可信")


def test_probe_can_fire_on_a_wrong_entry_point() -> None:
    """注入反证：路径形态与裸词都必须读成 false（这两类就是本轮修掉的真实错法）。"""
    assert probe_entry_callable("cad_adapter", REPO) is False
    assert probe_entry_callable("src/aipd_os/cli/commands_drawing.py:cmd_drawing",
                                REPO) is False
    assert probe_entry_callable("no_such_module.nope", REPO) is False
    # 同一条能力的正确写法必须为 true —— 否则上面那条 false 只是探针坏了
    assert probe_entry_callable("aipd_os.cli.commands_drawing.cmd_drawing", REPO) is True


def test_script_style_entries_resolve() -> None:
    """第 2 类（探针假负）不得复发：scripts/research 下的顶层互引必须解析得到。"""
    assert probe_entry_callable("research.source_worker.run_source", REPO) is True
    assert probe_entry_callable("research.search_papers.search_papers", REPO) is True
