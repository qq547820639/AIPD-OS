# ruff: noqa: E501   # 长中文读数串，不为过 lint 而拆坏字面量

"""第 81 片收尾读数：从原件现跑生成《六、终局读数》，取不到就整轮拒写。"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
# 取证目录在**项目持久卷**上（`REPO.parent/tmp`），不在 `/tmp`：宿主重启会清空 `/tmp`，
# 而一整轮 4 分钟的全量跑结果不该住在易失目录里（这条教训在项目记忆里）。
TMP, PY = REPO.parent / "tmp" / "s81", str(REPO / ".venv/bin/python")
FINAL = TMP / "final"
REPORT = FINAL / "report.json"
DRC, BATTERY = TMP / "doc_reference_census.json", REPO / "docs/audit/s81/battery81.log"
DOC = REPO / "docs/audit/ASSEMBLY_PDF_IMAGE_F-ASSEMBLY-PDF-IMAGE_2026-09-27.md"
HEADING = "## 六、终局读数"
# 终态名按 pytest-json-report 的实际形状取（`serialize.make_summary` 就是对逐条 outcome
# 计数）⇒ 键名是单数 `error`，且为 0 的那几档整键缺席，所以 summary 与逐条要对着数。
OUTCOMES = ("collected", "passed", "skipped", "failed", "error", "xfailed", "xpassed")


def sh(args: list[str], timeout: int = 600) -> tuple[int, str]:
    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(REPO), timeout=timeout)
    return proc.returncode, proc.stdout + proc.stderr


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                          text=True).stdout.strip()


def run_tool(rows: list[str], fails: list[str], label: str, args: list[str],
             starts: tuple[str, ...], must: str = "") -> None:
    """跑一把兄弟尺子：rc 与关键行进读数，rc 非 0 或该干净的面不干净就整轮拒写。
    `✗ ! ·` 打头的行一律原样留着——缺陷条目不许被汇总成"有 N 条"就交出去。"""
    rc, out = sh(args)
    ln = [x.strip() for x in out.splitlines() if x.strip()]
    got = [x for x in ln if x.startswith(starts) or x[:1] in "✗!·"]
    if rc != 0 or (must and must not in out):
        fails.append(f"{label} rc={rc}" + (f"、缺「{must}」" if must and must not in out else "")
                     + " ⇒ " + "；".join(got))
    rows.append("- **{}**：`rc={}`；{}".format(label, rc, "；".join(got)))


def outcome_readings(rep: dict) -> tuple[dict, list[str], list[str]]:
    """终态计数由 `summary` 与逐条 `tests` **各读一遍再对账**，不默认哪一边是准的。"""
    s, tests = rep.get("summary") or {}, rep.get("tests") or []
    tally: Counter = Counter(str(t.get("outcome")) for t in tests)
    counts = {k: (int(s[k]) if k in s else tally[k]) for k in OUTCOMES}
    problems = [f"summary.{k}={s[k]} 与逐条现数 {tally[k]} 打架"
                for k in OUTCOMES[1:] if k in s and int(s[k]) != tally[k]]
    if "total" in s and int(s["total"]) != sum(tally.values()):
        problems.append(f"summary.total={s['total']} != 逐条合计 {sum(tally.values())}")
    if "collected" not in s:
        problems.append("summary 里没有 collected（收集数取不到，不拿 total 顶替）")
    if "duration" not in rep:
        problems.append("报告顶层没有 duration（用时取不到，不报成 0）")
    bad = [str(t.get("nodeid")) for t in tests if str(t.get("outcome")) in ("failed", "error")]
    return counts, problems, bad


def splice(text: str, rows: list[str]) -> tuple[str, str]:
    """按**内容锚点**替换《六、终局读数》：只动标题行之后到下一个 `## ` 之前。

    不按行号定位——插过一段之后行号全体漂移，按号改会把读数写进别的节。标题行原样从
    磁盘取回（源码里不重抄它，反引号与否都跟着文件走），锚点判不出来就不落盘。
    """
    lines = text.split("\n")
    hits = [i for i, x in enumerate(lines) if x.startswith(HEADING)]
    if len(hits) != 1:
        return "", f"锚点《{HEADING}》命中 {len(hits)} 处（要恰好 1 处）"
    ends = [i for i in range(hits[0] + 1, len(lines)) if lines[i].startswith("## ")]
    if not ends:
        return "", f"《{HEADING}》之后没有下一个 `## ` 标题，节的右边界判不出来"
    return "\n".join(lines[:hits[0]] + [lines[hits[0]], ""] + rows + [""] + lines[ends[0]:]), ""


def main() -> int:
    # 门禁排在**任何量具之前**：报告没落盘就整轮拒跑——不去烧那几把尺子，更不留下半满的
    # 读数节。文档保持"占位"原样，比写一串 `?` 好。
    if not REPORT.is_file():
        print(f"REFUSE-WRITE：测试报告不存在：{REPORT}\n"
              "  终局读数只从那份干净检出的 pytest-json-report 现跑取得；报告未落盘 ⇒ "
              "本轮不写任何数、不碰审计文档。")
        return 2
    TMP.mkdir(parents=True, exist_ok=True)
    rows, fails = [], []

    man = json.loads((REPO / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    tagsha = git("rev-parse", "v5.6.0^{commit}")
    # SHA 由清单与 tag 两处各读一次并当场对账，源码里不出现它：把本片 HEAD 冒充 tag SHA
    # 交进去，代价是烧掉一整轮全量跑（项目记忆里那格就是这么亏的）。
    if not tagsha or str(man.get("source_commit")) != tagsha:
        fails.append(f"tag SHA 与清单不符：rev-parse v5.6.0^{{commit}}={tagsha!r} vs "
                     f"SOURCE_MANIFEST.source_commit={man.get('source_commit')!r}")

    rep = json.loads(REPORT.read_text(encoding="utf-8"))
    counts, problems, bad_ids = outcome_readings(rep)
    fails += problems
    wt, head = git("-C", str(FINAL), "rev-parse", "--short", "HEAD"), git("rev-parse", "--short", "HEAD")
    if not wt:
        fails.append(f"读不到签出树的 HEAD（{FINAL} 不是工作树？）")
    if Path(str(rep.get("root"))).resolve() != FINAL.resolve():
        fails.append(f"报告 root={rep.get('root')!r} 不是本轮签出树 {FINAL}")
    if str(rep.get("source_commit")) != tagsha:
        fails.append(f"报告 source_commit={str(rep.get('source_commit'))[:12]!r} != tag SHA"
                     "（那格陷阱：报告跑在本片 HEAD 上而不是 tag 上）")
    if rep.get("exitcode") != 0:
        fails.append(f"全量 exitcode={rep.get('exitcode')!r}")
    rows.append(f"- **签出那一跑**（`tmp/s81/final`，报告产出于提交 `{wt}`，主树当时 HEAD `{head}"
                f"`）：`exitcode={rep.get('exitcode')}`、" + "、".join(f"`{k}={counts[k]}`"
                for k in OUTCOMES) + f"、用时 `{float(rep.get('duration', 0)):.1f}s`、"
                f"`root={rep.get('root')}`、`source_commit={str(rep.get('source_commit'))[:12]}`")
    rows.append("- **读数来处（两棵树不许互换引用）**：全量报告出自**干净签出树** "
                f"`{FINAL}`（未跟踪文件不在里面）；下面四把尺子与那条常驻门禁都跑在**主树** "
                f"`{REPO}`（cwd 就是主树），主树看得见本篇与 `docs/audit/s81/` 这些未跟踪件，"
                "签出树看不见 ⇒ 普查的历史面计数只在主树这一侧成立，别拿它去核对签出树的报告。")
    rows.append("- **报告 `summary` 原样与红名单**：`{}`；逐条红面（outcome 为 failed/error）共 "
                "{} 条 ⇒ {}".format(dict(sorted((rep.get("summary") or {}).items())), len(bad_ids),
                                     "、".join(f"`{b}`" for b in bad_ids) or "一条都没有"))

    rc, out = sh([PY, "scripts/doc_command_census.py", "--self-test"])
    marks = out.count("✓立住")
    if rc != 0 or marks == 0:
        fails.append(f"doc_command_census --self-test rc={rc}、立住标记 {marks} 条")
    rows.append(f"- **`doc_command_census --self-test`**：`rc={rc}`，**{marks} 条**合成读数全对上")
    run_tool(rows, fails, "同族尺子 `doc_command_census --repo .`（README 这轮加了旗子 ⇒ 命令名"
             "普查是本片的主面）", [PY, "scripts/doc_command_census.py", "--repo", "."],
             ("权威面", "判红面语料", "只报面", "现状面缺陷"), must="现状面缺陷 0 条")
    run_tool(rows, fails, "同族尺子 `absence_claim_census --repo .`（这轮翻了 `NOT_COVERED` 里"
             "那句假话 ⇒ 看有没有没处置的否定句）",
             [PY, "scripts/absence_claim_census.py", "--repo", "."],
             ("语料", "能力缺失句", "被挡在窄档外"))

    rc, out = sh([PY, "scripts/doc_reference_census.py", "--repo", ".", "--json", str(DRC)])
    drc = json.loads(DRC.read_text(encoding="utf-8")) if DRC.is_file() else {}
    live, hist = drc.get("live_defects") or [], drc.get("history_defects") or []
    if rc != 0 or not drc.get("ok") or live or not hist:
        fails.append(f"doc_reference_census rc={rc}、ok={drc.get('ok')}、live_defects 逐条原样="
                     + json.dumps(live, ensure_ascii=False) + f"、history_defects={len(hist)}")
    rows.append("- **本片修过的那把尺子 `doc_reference_census --repo . --json {}`**（`Ref.key()` "
                "混着空串与整数两种行号形状，全序由 `_defect_sort_key` 给）：`rc={}`、`ok={}`、"
                "`docs={}` / `denominator={}` / 分档 `{}` / `live_defects={}`{} / "
                "`history_defects={}`（只报不判）/ `problems={}`".format(
                    DRC.name, rc, drc.get("ok"), drc.get("docs"), drc.get("denominator"),
                    drc.get("buckets"), len(live),
                    "" if not live else " ⇒ 逐条：" + json.dumps(live, ensure_ascii=False),
                    len(hist), drc.get("problems")))

    rc, out = sh([PY, "-m", "pytest", "tests/test_changelog_integrity.py", "-q"])
    tail = [x for x in out.splitlines() if "passed" in x or "failed" in x][-1:]
    if rc != 0 or not tail:
        fails.append(f"test_changelog_integrity rc={rc} 尾部读数={tail}")
    # 只取终态那半截：`in 0.48s` 是 pytest 自己的墙钟，跑两遍必然不同，留着就破坏
    # "同一棵树上复跑字节相同"这条判据（整串仍进拒写理由，不丢诊断信息）。
    rows.append("- **本片新增的常驻门禁**：`pytest tests/test_changelog_integrity.py -q` → "
                "`{}`（rc={}）".format(tail[0].split(" in ")[0].strip() if tail else "", rc))

    # 电池只现读日志、不重跑：battery81.py 会临时改写 src/ 里的源文件，收尾时它已跑完落盘。
    bat = BATTERY.read_text(encoding="utf-8").splitlines() if BATTERY.is_file() else []
    arms, tot = [x for x in bat if x.startswith("[")], [x for x in bat if x.startswith("合计")]
    killed = [x for x in arms if x.startswith("[KILLED")]
    if not tot or not arms or len(killed) != len(arms):
        fails.append(f"变异电池读数取不到或有臂存活：{BATTERY} 合计行={tot[:1]}、"
                     f"现数 {len(killed)}/{len(arms)} 臂 KILLED")
    rows.append(f"- **变异电池（现读 `{BATTERY.name}`）**：`{tot[0] if tot else ''}`；逐臂现数 "
                f"KILLED {len(killed)} / 共 {len(arms)} 臂，存活臂："
                + ("、".join(x.strip() for x in arms if not x.startswith("[KILLED")) or "无"))
    # 逐臂开火的用例名原样抄进来：这一节被替换前那段手写字就在讲这件事（Y3/Y4 各多打红
    # 一条 census 用例），只报"全杀"会把那两条连带开火洗掉。
    fired = [x.strip()[len("开火:"):].strip() for x in bat if x.strip().startswith("开火")]
    rows.append(f"- **逐臂开火的用例名（日志原样 {len(fired)} 条）**："
                + ("、".join(f"`{x}`" for x in fired) or "日志里没打开火名"))

    tag_man = subprocess.run(["git", "show", "v5.6.0:SOURCE_MANIFEST.json"], cwd=str(REPO),
                             capture_output=True, text=True)
    now = {str(e.get("path") or e.get("file")) for e in man.get("files") or []}
    try:
        tag = {str(e.get("path") or e.get("file")) for e in json.loads(tag_man.stdout)["files"]}
    except (ValueError, KeyError):
        tag = set()
        fails.append("读不到 v5.6.0:SOURCE_MANIFEST.json ⇒ 差集判不了（不当成 0 个新增）")
    rows.append(f"- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = "
                f"`{str(man.get('source_commit'))[:12]}` == tag；被哈希文件数 "
                f"`{len(man.get('files') or [])}`（去重后 {len(now)} 条路径）；**相对 tag v5.6.0** "
                f"的清单：新增 {len(now - tag)} 个、消失 {len(tag - now)} 个——累计漂移不是本片增量")

    if fails:
        print("REFUSE-WRITE：")
        for one in fails:
            print("  -", one)
        return 2
    # 取数失败被写成字面量（`?`/`None`）比整轮拒写更坏——它是一条看起来正常的假读数。
    # 这里不用 assert：AssertionError 只会抛一个栈，不告诉你是哪一行取不到数。
    poisoned = [r for r in rows if "?" in r or "None" in r]
    if poisoned:
        print(f"REFUSE-WRITE：{len(poisoned)} 行读数里出现占位符/None，不落盘：")
        for one in poisoned:
            print("  -", one[:200])
        return 2
    merged, why = splice(DOC.read_text(encoding="utf-8"), rows)
    if why:
        print(f"REFUSE-WRITE：锚点判不出来，不落盘：{why}")
        return 2
    DOC.write_text(merged, encoding="utf-8")
    after = DOC.read_text(encoding="utf-8")
    assert sum(1 for x in after.split("\n") if x.startswith(HEADING)) == 1, "写完标题丢了/重复"
    assert after == merged, "写完复读与内存里的合并结果不一致"
    print("WROTE 终局读数一节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
