"""CHANGELOG.md「整块被重贴」常驻守卫（F-CHANGELOG-INTEGRITY，本轮未登记，见收尾说明）。

钉的是**这一类**损坏，不是这一次的现场。`CHANGELOG.md` 参与发布哈希、每轮由一次性
Python 补丁脚本追加写入；就在本轮开工之前它已经静默坏过一次——某个补丁脚本把文件
自己尾部的 **2074 行逐字节又贴了一遍**，而且接在中途（从 `- **v5.41 F-ASSEMBLY-PDF
第 80 片：…` 这行标题的中间断开处续上）。全仓两千多条常驻用例没有一条为此翻红：
损坏的是一份"给人看的账"，此前没有一条断言看过它的形状。

两把判据都是**纯函数**（只吃 `lines`，内部不读任何全局路径），所以既能钉真文件，
也能被合成语料喂出开火/不开火两侧：

1. `find_duplicate_blocks(lines, min_run=…)`：同文件里两个不同位置，从各自位置起
   连续 `min_run` 行（空行不参与比对）逐行相同 ⇒ 判一个重复块。它同时覆盖两种形状：
   "同一段落被贴两次"（真实事故）与"同一条非空行连着重复"（判据字面要求，开火下界
   见 `find_duplicate_blocks` 的推论）；成片空行不会自己咬成一块。
2. `find_duplicate_entry_headings(lines)`：条目记号三元组
   `(v<MAJOR.MINOR>, F-<缺陷号>, 第 <N> 片)` 在全文件唯一。单行级重复差 `min_run-1`
   行，块判据在结构上看不见，所以这条必须独立存在。

真文件语法是**读出来的**，不是猜的，口径由下面的分母断言现算钉住：
条目行一律以 `- **v` 起头，实测 106 行；其中带完整记号的实测 79 行，写法有三种
`- **v5.10 F-DRAW-01 第 2 片：…`、`- **v5.10 推进 F-DRAW-01 第 1 片：…`、
`- **v5.10 修复 F-EVID-02 第 21 片：…`（版本号与 `F-` 号之间可能夹一个动词）。
正文里的 `v5.x` 散文、`第 8 片` 这种回指、以及 `## [5.6.0] — 2026-08-06` 之类小节
标题都不在「行首 `- **v`」这一格里，故一律不算条目。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "CHANGELOG.md"

# min_run 的取法由三件事一起定，不是拍的：
# * 抓到真实事故：尾部 2074 行被逐字节重贴 ⇒ 任何远小于 2074 的取值都抓得到；
#   验收还要求"只重贴最后 30 行"这种小规模损坏也开火 ⇒ 上界必须压进几十。
# * 在真文件上绿：余量由本文件 `test_real_changelog_headroom_is_printed` 现算并打印
#   （`pytest -s` 读数：真文件 3047 行 / 2923 非空行，从 min_run=2 起一路不开火，
#   即整个文件里连一对相同的非空行都找不到），所以取 2 今天也红不了。
# * 但判据要留给合法样板的余量：markdown 表头/分隔行、`---` 规则线这类小段样板将来
#   可能合法地重复出现，取 2 等于把自己钉死在一次正常记账上。
# 取 6：容得下 5 行样板，又比任何一次真实批量误贴（本轮实测最小的一次也有 25 行）小一个数量级。
MIN_RUN = 6

# 判红消息里带几行块首内容，够人眼定位就停。
_SAMPLE_LINES = 3

_ENTRY_HEAD_RE = re.compile(r"^- \*\*v(?P<version>[0-9]+(?:\.[0-9]+)*)")
# 条目记号：`- **v5.10 [动词] F-DRAW-01 第 2 片`；版本号与 F- 号之间的动词段用 .*? 吸收。
_ENTRY_MARKER_RE = re.compile(
    r"^- \*\*v(?P<version>[0-9]+(?:\.[0-9]+)*)"
    r"\s+.*?(?P<defect>F-[A-Za-z0-9][A-Za-z0-9-]*)"
    r"\s+第\s*(?P<slice>[0-9]+)\s*片"
)


@dataclass(frozen=True)
class DuplicateBlock:
    """一个"同样的连续若干行出现在两个以上位置"的判红单元。"""

    starts: tuple[int, ...]
    """各次出现的首行下标（0 基，指向传进来的 `lines`，含空行的原始坐标）。"""
    length: int
    """重复块长度，按**参与比对的非空行**计（空行不占长度，也不打断块）。"""
    sample: tuple[str, ...]
    """块首 `_SAMPLE_LINES` 行内容，够人眼认出被重贴的是哪一段。"""

    def describe(self) -> str:
        where = "、".join(f"第 {i + 1} 行" for i in self.starts)
        head = self.sample[0][:60] if self.sample else ""
        return f"[{where}] 连续 {self.length} 行重复，起于 {head!r}"


@dataclass(frozen=True)
class EntryHeading:
    """一行被认成的登记册条目（`- **v` 起头的 bullet）。"""

    line_no: int
    version: str
    defect_id: str
    slice_no: str
    text: str


@dataclass(frozen=True)
class DuplicateEntryHeading:
    """同一组条目记号出现两次以上的判红单元。"""

    marker: tuple[str, str, str]
    line_numbers: tuple[int, ...]
    texts: tuple[str, ...]

    def describe(self) -> str:
        v, fid, n = self.marker
        where = "、".join(f"第 {i + 1} 行" for i in self.line_numbers)
        return f"条目记号 v{v} {fid} 第 {n} 片 出现在 {where}"


def _nonblank(lines: list[str]) -> tuple[list[int], list[str]]:
    """剔除空行/纯空白行，返回（原下标列表，内容列表）。

    空白行不进比对序列 ⇒ 成片空行不会被报成重复块（真实文件里有 124 行空白，
    若把空白当可比内容，两个各含空行的小段就会互相咬上）。
    """
    idx: list[int] = []
    seq: list[str] = []
    for i, line in enumerate(lines):
        if line.strip():
            idx.append(i)
            seq.append(line)
    return idx, seq


def find_duplicate_blocks(lines: list[str], *, min_run: int) -> list[DuplicateBlock]:
    """纯函数：报出 `lines` 里所有"连续 ≥ min_run 行非空内容出现在两个不同位置"的块。

    实现按 `min_run` 长的窗口分桶（键就是那 `min_run` 行的元组，逐字比较、无哈希风险），
    同桶即候选；再沿两个位置向右延伸到不再相同为止，得到共享长度。已被前一个块覆盖住
    的位置不再单独报，于是一次重贴只产出一条判红。结果按首个位置升序，可复现。

    推论（由 `test_run_of_identical_lines_fires` 钉住）：连着重复的同一条非空行，
    R 次会给出 R - min_run + 1 个窗口起点 ⇒ 要 R ≥ min_run + 1 才算"出现在两个位置"，
    恰好 min_run 次只落一处、不开火。
    """
    if min_run < 2:
        raise ValueError("min_run 必须 ≥ 2，否则任何一句被重复说的话都会红")
    idx, seq = _nonblank(lines)
    n = len(seq)
    if n < min_run:
        return []

    windows: dict[tuple[str, ...], list[int]] = {}
    for i in range(n - min_run + 1):
        windows.setdefault(tuple(seq[i:i + min_run]), []).append(i)

    groups = sorted(starts for starts in windows.values() if len(starts) > 1)
    findings: list[DuplicateBlock] = []
    covered = [False] * n
    for starts in groups:
        first = starts[0]
        if covered[first]:
            continue
        length = n - first
        for other in starts[1:]:
            a, b = first + min_run, other + min_run
            while b < n and seq[a] == seq[b]:
                a += 1
                b += 1
            length = min(length, a - first)
        length = max(length, min_run)
        for start in starts:
            for k in range(start, min(start + length, n)):
                covered[k] = True
        findings.append(
            DuplicateBlock(
                starts=tuple(idx[s] for s in starts),
                length=length,
                sample=tuple(seq[first:first + _SAMPLE_LINES]),
            )
        )
    return findings


def find_entry_headings(lines: list[str]) -> list[EntryHeading]:
    """纯函数：认出行首为 `- **v` 的登记册条目，并解析其记号三元组。

    入口门槛刻意写成与独立分母同一个字面判据（`startswith("- **v")`），这样
    `test_entry_heading_marker_denominator` 比的才是"正则有没有悄悄匹配不到"，
    而不是两个不同口径互相圆场。缺版本号的条目 `version` 为 `""`，
    不带 `F-` 号或 `第 N 片` 的条目对应字段为 `""`（如 `- **v5.9 产品智能**：`）。
    """
    out: list[EntryHeading] = []
    for i, line in enumerate(lines):
        if not line.startswith("- **v"):
            continue
        head = _ENTRY_HEAD_RE.match(line)
        marker = _ENTRY_MARKER_RE.match(line)
        out.append(
            EntryHeading(
                line_no=i,
                version=head.group("version") if head else "",
                defect_id=marker.group("defect") if marker else "",
                slice_no=marker.group("slice") if marker else "",
                text=line,
            )
        )
    return out


def find_duplicate_entry_headings(lines: list[str]) -> list[DuplicateEntryHeading]:
    """纯函数：条目记号 `(v<MAJOR.MINOR>, F-<缺陷号>, 第 <N> 片)` 出现两次以上即判红。

    只判三元组齐全的条目——文件开头那批 `- **v5.7 状态服务生产化**：` 式的能力条目
    本来就没有 `F-` 号与片号，按 `v5.10` 去重会把它们全部误判成重复。
    """
    groups: dict[tuple[str, str, str], list[EntryHeading]] = {}
    for entry in find_entry_headings(lines):
        if entry.version and entry.defect_id and entry.slice_no:
            key = (entry.version, entry.defect_id, entry.slice_no)
            groups.setdefault(key, []).append(entry)
    return [
        DuplicateEntryHeading(
            marker=key,
            line_numbers=tuple(e.line_no for e in hits),
            texts=tuple(e.text for e in hits),
        )
        for key, hits in groups.items()
        if len(hits) > 1
    ]


# ---------------------------------------------------------------- 合成语料小工具


def _synthetic_corpus(entries: int) -> list[str]:
    """造一份小登记册：条目之间夹空行，每个条目 3 行非空正文，行行互不相同。"""
    lines = ["# 合成登记册（只在内存里，不落盘）"]
    for i in range(entries):
        lines.append("")
        lines.append(f"- **v5.{200 + i} F-SYNTH-{i} 第 {i} 片：合成条目 {i}，不是真登记**：")
        lines.append(f"  第 {i} 条的第一行说明，内容只在这一行出现一次。")
        lines.append(f"  第 {i} 条的第二行说明，证据见 tests/synth-{i}.md。")
    return lines


@pytest.fixture(scope="module")
def changelog_lines() -> list[str]:
    """真文件先证明读得到，再谈"读出来是干净的"——空读不算绿。"""
    path = CHANGELOG_PATH.resolve()
    assert path.is_file(), f"找不到 {path}，本文件的判绿无从谈起"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"{path} 内容为空，读不到东西不算绿"
    return text.splitlines()


# ------------------------------------------------------------------ ① 真文件门禁


def test_real_changelog_has_no_duplicated_block(changelog_lines: list[str]) -> None:
    """真 `CHANGELOG.md` 上两把判据都必须为空读数，且分母是现算的下界。"""
    lines = changelog_lines
    total = len(lines)
    nonblank = sum(1 for line in lines if line.strip())
    entries = find_entry_headings(lines)
    markers = [e for e in entries if e.defect_id and e.slice_no]
    print(
        f"CHANGELOG.md 行数={total} 非空行={nonblank} "
        f"条目行={len(entries)} 完整记号={len(markers)} min_run={MIN_RUN}"
    )
    # 分母下界：报 0 之前要先证明读到了不小的一段（被静默截窄就红）。
    assert total >= 2000, f"只读到 {total} 行，分母不对"
    assert nonblank >= 1800, f"只读到 {nonblank} 行非空内容，分母不对"
    assert len(entries) >= 60, f"只认到 {len(entries)} 个条目行，分母不对"
    assert len(markers) >= 60, f"只认到 {len(markers)} 个完整条目记号，分母不对"

    blocks = find_duplicate_blocks(lines, min_run=MIN_RUN)
    assert blocks == [], "CHANGELOG.md 出现整块重复：" + "；".join(
        b.describe() for b in blocks[:5]
    )
    dups = find_duplicate_entry_headings(lines)
    assert dups == [], "条目记号被登记了两次：" + "；".join(d.describe() for d in dups[:5])


def test_entry_heading_marker_denominator(changelog_lines: list[str]) -> None:
    """条目识别的分母要用第二把尺子对一遍，正则悄悄失配时必须红而不是绿。"""
    lines = changelog_lines
    entries = find_entry_headings(lines)
    # 独立口径 1：纯 startswith 计数，不碰任何正则。
    plain = sum(1 for line in lines if line.startswith("- **v"))
    assert entries, "一个条目都没认出来 ⇒ 判据在空转"
    assert len(entries) == plain, f"条目识别 {len(entries)} 与 startswith 计数 {plain} 不等"
    assert all(entry.version for entry in entries), "有条目行解析不出版本号 ⇒ 正则与口径漂了"

    markers = [e for e in entries if e.defect_id and e.slice_no]
    # 独立口径 2：只看字面出现「第 … 片」的行首条目，与正则无关。
    loose = sum(
        1 for line in lines if line.startswith("- **v") and "第" in line and "片" in line
    )
    assert len(markers) == loose, f"完整记号 {len(markers)} 与字面口径 {loose} 不等"
    print(f"条目行={len(entries)}/{plain} 完整记号={len(markers)}/{loose}")


def test_real_changelog_headroom_is_printed(changelog_lines: list[str]) -> None:
    """把常量注释里那句"取 6 有余量"变成现算读数 + 对阈值本身的卡尺。

    逐档从 2 往上现算真文件在哪一档开火，只报数不判红（拿 2 去断言等于把门禁
    钉死在一次正常记账上）；"min_run=6 必须绿"这一格由
    `test_real_changelog_has_no_duplicated_block` 判。这里判的是阈值还在不在
    事故尺度里：取到 30 以上就抓不到"只重贴最后几十行"，取到 2 就一次正常记账
    就能红 ⇒ 想靠调大 MIN_RUN 把判据关掉，会在这里红。
    """
    lines = changelog_lines
    firing = [mr for mr in range(2, MIN_RUN + 1) if find_duplicate_blocks(lines, min_run=mr)]
    print(
        f"min_run 余量读数：2..{MIN_RUN} 中开火的取值 = {firing or '一个都没有'}"
        f"（真文件 {len(lines)} 行）"
    )
    assert 2 <= MIN_RUN <= 30, f"MIN_RUN={MIN_RUN} 已跳出事故尺度，判据等于自废"


# ---------------------------------------------------------------- ② 判据自己会开火


def test_duplicate_tail_block_fires() -> None:
    """必开火一侧：把尾部若干行逐字节重贴到文件末尾——真实事故的形状。"""
    corpus = _synthetic_corpus(20)
    tail = corpus[-14:]
    damaged = corpus + tail
    assert find_duplicate_blocks(corpus, min_run=MIN_RUN) == [], "合成底稿本身就该干净"

    blocks = find_duplicate_blocks(damaged, min_run=MIN_RUN)
    print("注入重贴后的读数：", [b.describe() for b in blocks])
    assert blocks, "重贴尾部没有被判出来 ⇒ 这条门禁是假的"
    assert len(blocks) == 1, f"一次重贴应当只判一条，实得 {len(blocks)} 条"
    block = blocks[0]
    nonblank_tail = sum(1 for line in tail if line.strip())
    first_of_tail = next(i for i, line in enumerate(tail) if line.strip())
    assert block.length == nonblank_tail, f"块长 {block.length} != 尾部非空行 {nonblank_tail}"
    assert block.starts == (
        len(corpus) - len(tail) + first_of_tail,
        len(corpus) + first_of_tail,
    ), f"报出的位置不对：{block.starts}"
    # 同一份损坏里被重贴的那段含 3 个条目标题，条目判据也该同时开火。
    dups = find_duplicate_entry_headings(damaged)
    expected_headings = sum(1 for line in tail if line.startswith("- **v"))
    assert len(dups) == expected_headings, f"条目判据没有跟着开火：{dups}"
    assert all(len(d.line_numbers) == 2 for d in dups), dups
    assert all(d.line_numbers[1] > d.line_numbers[0] for d in dups), dups

    # 边界：恰好 min_run 个非空行被重贴 ⇒ 刚够判据的胃口，必须开火。
    lines = [f"L{i} 独立内容" for i in range(24)]
    exactly = find_duplicate_blocks(lines + lines[-MIN_RUN:], min_run=MIN_RUN)
    assert len(exactly) == 1 and exactly[0].length == MIN_RUN, exactly


def test_small_repetition_does_not_fire() -> None:
    """必不开火一侧：短于 min_run 的重复样板不许红，否则 min_run 这个数就是没证过。"""
    lines = [f"L{i} 独立内容" for i in range(24)]
    assert find_duplicate_blocks(lines, min_run=MIN_RUN) == []
    # 只差一行的重贴（min_run - 1）不许开火。
    assert find_duplicate_blocks(lines + lines[-(MIN_RUN - 1):], min_run=MIN_RUN) == []
    # 两个一模一样的 2 行样板（题面点名的例子）。
    boiler = ["| --- | --- |", "| 说明 | 证据 |"]
    corpus = boiler + lines[:8] + boiler + lines[8:16] + boiler
    assert find_duplicate_blocks(corpus, min_run=MIN_RUN) == []
    # 成片空行不构成块：三份同样的「A + 6 个空行 + B」也不许互相咬上。
    spacer = ["A"] + [""] * 6 + ["B"]
    assert find_duplicate_blocks(spacer * 3, min_run=MIN_RUN) == []


def test_run_of_identical_lines_fires() -> None:
    """判据字面那一半：同一条非空行连着 ≥ min_run+1 次 ⇒ 窗口有两个以上起点 ⇒ 开火。"""
    head = [f"H{i} 上半段独立内容" for i in range(6)]
    foot = [f"T{i} 下半段独立内容" for i in range(6)]
    rule = "| === | === |"
    blocks = find_duplicate_blocks(head + [rule] * (MIN_RUN + 2) + foot, min_run=MIN_RUN)
    assert blocks, "连着重复 8 次的同一条非空行没被判出来"
    assert len(blocks) == 1, f"一处损坏应当只判一条，实得 {len(blocks)} 条：{blocks}"
    assert blocks[0].starts == (6, 7, 8), blocks[0]
    assert blocks[0].length >= MIN_RUN, blocks[0]
    # 恰好 min_run 次：同一段内容只落得下一个起点，按定义不算"两个不同位置"。
    assert find_duplicate_blocks(head + [rule] * MIN_RUN + foot, min_run=MIN_RUN) == []


def test_duplicate_entry_heading_fires() -> None:
    """单行级重复差 min_run-1 行，块判据结构上看不见 ⇒ 条目判据必须补上这一格。"""
    corpus = _synthetic_corpus(8)
    heading = "- **v5.99 F-SOMETHING 第 999 片：说明**："
    damaged = corpus + [heading, "  这一条被登记了第二次，正文也只有一行。"] + [heading]
    recognized = find_entry_headings(corpus + [heading])
    assert recognized[-1].text == heading, "行首 `- **v` 的条目没被认出来"
    assert recognized[-1].defect_id == "F-SOMETHING", recognized[-1]
    assert recognized[-1].slice_no == "999", recognized[-1]

    dups = find_duplicate_entry_headings(damaged)
    print("注入重复条目后的读数：", [d.describe() for d in dups])
    assert len(dups) == 1, f"没有把重登的条目认出来：{dups}"
    assert dups[0].marker == ("5.99", "F-SOMETHING", "999"), dups[0].marker
    assert dups[0].line_numbers == (len(corpus), len(corpus) + 2), dups[0].line_numbers
    assert all("第 999 片" in text for text in dups[0].texts)
    # 互补性：同样的损坏交给块判据是看不见的（只有 1 行重复）。
    assert find_duplicate_blocks(damaged, min_run=MIN_RUN) == []
    # 动词那一半写法也要认（`推进/修复 F-… 第 N 片`），否则真文件 79 个记号会漏判两类。
    verb = "- **v5.10 修复 F-SYNTH-7 第 7 片：说明**："
    assert len(find_duplicate_entry_headings(_synthetic_corpus(3) + [verb, verb])) == 1
