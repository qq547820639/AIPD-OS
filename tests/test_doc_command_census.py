"""文档/登记表点名的命令必须注册着（F-DOC-CMD 第 60 片）——量具的常驻牙。

第 59 片的事故是这条链的起点：重写能力行的限制句时，我在里面写了一条**不存在的命令**
`aipd truth show`，而没有任何常驻判据看得见它（`capability_matrix.py` 只把 `run_command`
原样渲染成 markdown）。本轮把它抓回来靠的是只读普查。这一片把这件事交给机器，
并把"谁保证机器真会开火"钉在这里。

三档判红面（登记表 `run_command` 段、文档行首速查行、生产代码提及）+ 只报面，
用例分四组：
① 量具必须被真的 spawn（孤儿门禁与没有门禁看不出差别）；
② 真仓库上现状面干净**且三档分母都非空**——空读数不算绿；
③ 注入必须开火 / 合规侧必须不开火的两两对照，含两条最容易做假的方向：
   组名存在而子命令不存在（第 59 片的原件是 `aipd truth show`，夹具现由 `ghost()` 生成）、
   契约别名（`aipd init-project`）不许被当幻影；
④ 本轮修掉的两处**代码里的幻影**（写进每条记录的 source.note、payload 自报的命令标签）
   由真数据反证钉住。

一处自己踩过的坑写在这里以免重犯：本文件最初的"作用域"fixture 是 autouse 的，
于是真仓库那两条用例也被它扫窄成只剩 `docs/`，**绿得毫无意义**（量具自指、
tests 里的反向夹具都看不见）。现在作用域只给 tmp 用例用，真仓库用例反过来
断言三档分母的下界，作用域再被收窄就会红。
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import doc_command_census as census  # noqa: E402

TOOL = ROOT / "scripts" / "doc_command_census.py"
T, P = "default", "DOC-CMD"

GOOD_README = ("# 命令\naipd ctq add --db x --project p --by 张工\n"
               "aipd truth drift --db x --project p\n运行 `aipd usage` 列出全部命令\n"
               "aipd <命令> --help\naipd-os 与 aipd_os 都不是命令写法\n")
GOOD_REGISTRY = ('CAPABILITIES = [{"id": "a", "run_command": "aipd ctq revise --db x"},\n'
                 ' {"id": "b", "run_command": "python scripts/x.py"}]\n')


@pytest.fixture()
def tmp_scope(monkeypatch):
    """只给临时语料用例用：把三档面指到 tmp。权威面仍取自本仓（这是设计）。"""
    monkeypatch.setattr(census, "REGISTRY_FILES", ("src/aipd_os/registry_data.py",))
    monkeypatch.setattr(census, "QUICKREF_FILES", ("README.md",))
    monkeypatch.setattr(census, "QUICKREF_DIRS", ())
    monkeypatch.setattr(census, "CODE_DIRS", ("src",))
    monkeypatch.setattr(census, "REPORT_ONLY_FILES", ())
    monkeypatch.setattr(census, "REPORT_ONLY_DIRS", ("docs", "src", ".trae", ".github"))


def write_tree(tmp: Path, readme: str, registry: str, code: str | None = None,
               prose: str | None = None) -> Path:
    (tmp / "README.md").write_text(readme, encoding="utf-8")
    (tmp / "src" / "aipd_os").mkdir(parents=True, exist_ok=True)
    (tmp / "src" / "aipd_os" / "registry_data.py").write_text(registry, encoding="utf-8")
    if code is not None:
        (tmp / "src" / "aipd_os" / "handlers.py").write_text(code, encoding="utf-8")
    if prose is not None:
        (tmp / "docs" / "audit").mkdir(parents=True, exist_ok=True)
        (tmp / "docs" / "audit" / "note.md").write_text(prose, encoding="utf-8")
    return tmp


def fields(rep: dict, written: str) -> set[str]:
    return {v["field"] for v in rep["violations"] if v["written"] == written}


def ghost(suffix: str) -> str:
    """夹具幻影名：`ctq` 必须是组、`aipd ctq <suffix>` 今天必须仍不存在。

    写死一个**将来可能被注册**的名字等于给自己埋定时炸弹，第 62 片实测两种坏法：
    `aipd ctq list` 成为主线命令后，两处夹具当场报错（"判据把合法名判红了"，排查方向正好反了），
    而 `test_negation_in_production_code_is_reported_not_judged` **静默变成空转**——
    那行仍带否定标记所以 `code_negated` 照样为 1，只是标记指向的命令已经存在，
    例外这一支再没有被任何东西验过。`zzz-` 前缀不进产品命名空间；
    这里仍用真组名 `ctq`，是为了保住"组存在而子命令不存在"那个形状。
    """
    paths, groups, problems = census.valid_commands()
    assert not problems, problems
    assert "ctq" in groups, "夹具前提：ctq 必须是权威面上的组"
    assert f"ctq {suffix}" not in paths, f"夹具名 ctq {suffix} 已注册成真命令，换后缀"
    return f"aipd ctq {suffix}"


def test_instrument_self_test_is_actually_run_and_green() -> None:
    proc = subprocess.run([sys.executable, str(TOOL), "--self-test"],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "条合成读数全部对上" in proc.stdout, proc.stdout
    assert "✓立住" in proc.stdout, proc.stdout


def test_real_repo_clean_and_all_three_judging_faces_live() -> None:
    rep = census.audit(ROOT)
    assert rep["problems"] == [], rep["problems"]
    assert rep["ok"] is True, rep["violations"]
    c = rep["corpus"]
    # 三档分母各自非空：任何一档被静默收窄（包括被测试自己的 monkeypatch 收窄）都会在这里红
    assert c["run_command_segments"] >= 50, c
    assert c["quickref_lines"] >= 50, c
    assert c["code_mentions"] >= 100, c
    # 去重生效：只报面必须小于全量扫描，否则"Σ 分桶"式的自证是恒真的
    assert c["report_only_mentions"] < c["prose_mentions"], c
    # 第 75 片把只报面拆成 live（可行动）与 record（记录性引述）：
    # 两桶各自都要非空、加起来要等于拆桶前的总数——否则"拆桶"就是"藏起一半语料"。
    assert c["report_only_mentions"] >= 20, c
    assert c["report_record_mentions"] >= 500, c
    assert c["report_only_mentions"] + c["report_record_mentions"] == \
        c["report_total_mentions"], c
    assert set(c["report_record_dirs"]) == {"CHANGELOG.md", "docs/audit", "tests", ".trae"}, c
    # 第 82 片新格的真仓库读数：今天必须 0（不是"看不见"——同一把尺在历史原件上开火，
    # 见 test_broken_continuation_fires_on_the_real_historical_shape）
    assert c["continuation_breaks"] == 0, c


def test_injected_phantoms_fire_on_all_three_judging_faces(tmp_path: Path,
                                                           tmp_scope) -> None:
    # 三个名字各写各的档：同名会让"这条只该在 X 档开火"的归因读不出来
    qref, run_cmd = ghost("zzz-quickref"), ghost("zzz-listy")
    write_tree(
        tmp_path,
        GOOD_README + f"{qref} --db x\n",
        GOOD_REGISTRY.replace('"aipd ctq revise --db x"',
                              f'"aipd ctq revise --db x / {run_cmd}"'),
        code='BAD = "先跑 aipd ghost cmd 再看"\n',
    )
    rep = census.audit(tmp_path)
    # 三条注入各落在自己那一档：假命令写在速查行 / run_command 段 / 生产代码里
    assert fields(rep, qref) == {"quickref"}, rep["violations"]
    assert fields(rep, run_cmd) == {"run_command"}, rep["violations"]
    assert fields(rep, "aipd ghost cmd") == {"code"}, rep["violations"]
    assert census.main(["--repo", str(tmp_path)]) == 4


def test_compliant_side_does_not_fire(tmp_path: Path, tmp_scope) -> None:
    """反向对照：真命令、占位符、`aipd-os` 一律不开火（只测会红的一侧等于没测）。"""
    write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
               code='GOOD = "先跑 aipd ctq add 再看"\n')
    rep = census.audit(tmp_path)
    assert rep["ok"] is True, rep["violations"]
    c = rep["corpus"]
    assert c["quickref_lines"] == 3, c      # `<命令>` 那行数进语料但不产生判定
    assert c["run_command_segments"] == 1, c
    assert c["code_mentions"] == 1, c
    # 去重真生效：三档判红面覆盖的行不许再被只报面数一遍（prose 数 2 处，全被判红面吃过）
    assert c["prose_mentions"] == 2, c
    assert c["report_only_mentions"] == 0, c


def _readme_at(rev: str) -> list[str]:
    """从 git 取某一版 README 的逐行原文：夹具的必开火形状不许我手写。"""
    proc = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:README.md"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-300:]
    return proc.stdout.splitlines()


def _pair(lines: list[str], want_next_command: bool) -> tuple[str, str]:
    """找"一行以 `\\` 收尾"的第一处，返回它和下一行；`want_next_command` 决定要哪种下一行。"""
    for i in range(len(lines) - 1):
        if not lines[i].rstrip().endswith("\\"):
            continue
        nxt = lines[i + 1].strip().lstrip("#").strip()
        if nxt.startswith("aipd ") is want_next_command:
            return lines[i], lines[i + 1]
    raise AssertionError(f"语料里没有『下一行是另一条命令={want_next_command}』的续行形状")


def test_broken_continuation_fires_on_the_real_historical_shape(tmp_path: Path,
                                                               tmp_scope) -> None:
    """判据的原告是**真的坏过那一次**：`3784a0a` 之前 README 里的断续行。

    第 81 片把 README 那三条示例拆开了（补丁脚本把上一行的 `\\` 直接接上另一条命令，
    照抄的人只会跑到半条命令）。夹具从那次提交的 README 里取**逐字**相邻两行，
    所以判据的必开火形状与本仓文档的后续改写无关——本仓 README 再怎么改，历史那份不会变。
    """
    old = _readme_at("3784a0a")
    broken, following = _pair(old, want_next_command=True)
    assert broken.rstrip().endswith("\\") and following.strip().startswith("aipd ")
    write_tree(tmp_path, GOOD_README + broken + "\n" + following + "\n", GOOD_REGISTRY,
               code='GOOD = "先跑 aipd ctq add 再看"\n')
    rep = census.audit(tmp_path)
    assert fields(rep, broken.rstrip()) == {"续行"}, rep["violations"]
    assert rep["corpus"]["continuation_breaks"] == 1, rep["corpus"]
    # 下一行本身是真命令 ⇒ 它不许被名字档判成"权威面上没有"
    assert "aipd drawing assembly-steps" not in {v["written"] for v in rep["violations"]}, \
        rep["violations"]
    assert census.main(["--repo", str(tmp_path)]) == 4


def test_legal_continuation_does_not_fire(tmp_path: Path, tmp_scope) -> None:
    """合规侧：续行的下一行是**旗子**时不开火（今天 README 就是这个形状）。"""
    cur = _readme_at("HEAD")
    cont, tail = _pair(cur, want_next_command=False)
    assert not tail.strip().startswith("aipd "), tail
    write_tree(tmp_path, GOOD_README + cont + "\n" + tail + "\n", GOOD_REGISTRY)
    rep = census.audit(tmp_path)
    assert rep["corpus"]["continuation_breaks"] == 0, rep["corpus"]
    assert rep["violations"] == [], rep["violations"]


def test_broken_continuation_is_also_judged_under_quickref_dirs(
        tmp_path: Path, monkeypatch) -> None:
    """钉住"② 与 ②b 共用同一份遍历"这件事本身。

    两档各写一遍语料遍历是本仓记过的老坑（排除档一漂就出现"一档看得见、一档看不见"）。
    上一条用例的断掉的续行写在 `README.md`（`QUICKREF_FILES` 档），只测它就允许 ②b 偷偷
    只读 files 不读 dirs——所以这一条把它放进 `QUICKREF_DIRS` 那一侧，并要求同一格开火。
    """
    monkeypatch.setattr(census, "REGISTRY_FILES", ("src/aipd_os/registry_data.py",))
    monkeypatch.setattr(census, "QUICKREF_FILES", ("README.md",))
    monkeypatch.setattr(census, "QUICKREF_DIRS", ("docs/architecture",))
    monkeypatch.setattr(census, "CODE_DIRS", ("src",))
    monkeypatch.setattr(census, "REPORT_ONLY_FILES", ())
    monkeypatch.setattr(census, "REPORT_ONLY_DIRS", ("docs", "src"))
    broken, following = _pair(_readme_at("3784a0a"), want_next_command=True)
    (tmp_path / "docs" / "architecture").mkdir(parents=True)
    (tmp_path / "docs/architecture/guide.md").write_text(
        "# 指南\n" + broken + "\n" + following + "\n", encoding="utf-8")
    write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
               code='GOOD = "先跑 aipd ctq add 再看"\n')
    rep = census.audit(tmp_path)
    hits = [v for v in rep["violations"] if v["field"] == "续行"]
    assert [h["doc"] for h in hits] == ["docs/architecture/guide.md"], rep["violations"]
    assert rep["corpus"]["continuation_breaks"] == 1, rep["corpus"]
    assert rep["corpus"]["quickref_lines"] >= 2, rep["corpus"]      # ② 也真的看见了同一份语料


def test_group_with_missing_subcommand_is_not_degraded_to_ok(tmp_path: Path,
                                                             tmp_scope) -> None:
    """组存在不代表组里每个子命令都存在——退化成"组存在就放行"就成了一把恒真的尺。

    （第 59 片的原件是 `aipd truth show`；夹具改用 `ghost()` 生成的名字，理由见那里。）
    """
    show = ghost("zzz-show")
    write_tree(tmp_path, show + "\n", GOOD_REGISTRY)
    rep = census.audit(tmp_path)
    assert fields(rep, show) == {"quickref"}, rep["violations"]


def test_negation_in_production_code_is_reported_not_judged(tmp_path: Path,
                                                            tmp_scope) -> None:
    """带否定标记的行不许判红：限制句「没有 `aipd X`」是合法写法，判红等于惩罚写下缺口的人。"""
    g = ghost("zzz-unlisted")
    write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
               code='GOOD = "先跑 aipd ctq add 再看"\n'
                    f'# 本轮实测：`{g}` 仍然没有，只能读库\n')
    rep = census.audit(tmp_path)
    assert rep["ok"] is True, rep["violations"]
    assert fields(rep, g) == set(), rep["violations"]
    assert rep["corpus"]["code_negated"] == 1, rep["corpus"]


def test_contract_alias_is_legal(tmp_path: Path, tmp_scope) -> None:
    from aipd_os.cli.command_contract import CommandStatus, get_all_commands

    alias = next(e.name for e in get_all_commands()
                 if e.status is CommandStatus.DEPRECATED and e.replacement)
    write_tree(tmp_path, f"aipd {alias} --db x\n", GOOD_REGISTRY,
               code='GOOD = "先跑 aipd ctq add 再看"\n')
    rep = census.audit(tmp_path)
    assert rep["ok"] is True, rep["violations"]
    paths, _g, problems = census.valid_commands()
    assert not problems, problems
    # 别名合法的真实原因不是"契约说它存在"，而是**它还注册在 argparse 树上**——
    # 第 60 片电池 B4 实测：把别名并进权威面是死代码（10 个别名全在树上），
    # 撤掉那条并集八臂全绿。故该步已改成活的前置 `alias_unregistered`。
    assert alias in paths, alias


def test_a_single_empty_judging_face_reads_as_failure_not_green(tmp_path: Path,
                                                                tmp_scope) -> None:
    """README 有速查行、登记表与代码档都空 ⇒ 必须读成「前提不成立」，不是「0 违规」。

    这条是电池 B3 教出来的：原来只有 `--self-test` 里那个空仓库用例钉它，而那副语料
    **同时**踩了 `quickref_corpus_empty` —— 把 `judging_face_empty` 整条撤掉它照样退 2，
    于是"撤守卫"那一臂读成没牙。这里把两个原因分开：速查档非空、只有另两档空，
    能救场的就只剩 `judging_face_empty`。
    """
    write_tree(tmp_path, "aipd ctq add --db x --project p\n",
               'CAPABILITIES = []\n')
    rep = census.audit(tmp_path)
    assert rep["corpus"]["quickref_lines"] == 1, rep["corpus"]
    assert rep["corpus"]["run_command_segments"] == 0, rep["corpus"]
    assert not rep["ok"], rep
    assert any("judging_face_empty" in x for x in rep["problems"]), rep["problems"]
    assert not any("quickref_corpus_empty" in x for x in rep["problems"]), rep["problems"]
    assert census.main(["--repo", str(tmp_path)]) == 2


def test_other_registry_fields_on_a_judged_line_are_still_reported(tmp_path: Path,
                                                                   tmp_scope) -> None:
    """第 60 片留下的**双重盲**：登记表一条记录常写在一个物理行里。

    三档的排除在这一行上叠加：档 ① 只读 `run_command` 一个键、档 ③ 显式跳过
    `REGISTRY_FILES`、只报面又按"该行已被判红面吃过"做**行级**减法 ⇒
    同一行 `current_limitation` 里点名的命令**既不判也不报**。
    夹具故意写成**正向断言**（不带任何否定词），所以这不是"合法否定句被放行"，
    而是彻底的看不见。修完的最低要求：**至少要在只报面里出现**；
    要不要升格成判红是裁决项，所以这里同时钉住"它今天不判红"。
    """
    reg = ('CAPABILITIES = [{"id": "a", "run_command": "aipd ctq revise --db x",'
           ' "current_limitation": "先跑 `aipd ghost cmd` 再导出结果"}]\n')
    write_tree(tmp_path, GOOD_README, reg, code='GOOD = "aipd ctq add 的调用点"\n')
    rep = census.audit(tmp_path)
    # 夹具必须是**一个物理行**：拆成两行就同时躲开了行级减法，测的就不再是那个盲区
    spots = {(r["doc"], r["line"], r["written"]) for r in rep["report_only_unmatched"]}
    assert ("src/aipd_os/registry_data.py", 1, "aipd ghost cmd") in spots, (rep["corpus"], spots)
    assert fields(rep, "aipd ghost cmd") == set(), rep["violations"]


def test_report_only_face_counts_each_mention_once(tmp_path: Path, tmp_scope) -> None:
    """只报面不许把带否定标记的行数两遍。

    第 60 片的写法是 `只报 = 全量扫描 − 判过的行 + code_neg`，而 `CODE_DIRS` 与
    `REPORT_ONLY_DIRS` 都含 `src` ⇒ 那批否定行**本来就已经在全量扫描里**，
    再加一遍就是重复计数（真仓库实测：5 条 `code_negated` 全部命中只报面，
    所以 `report_only_mentions` 一直比应有的多 5）。
    修法是"补集"而不是"并集"：只加**尚未出现在只报面里**的那些。
    """
    code = '# 没有 `aipd ghostly cmd` 这条命令\nGOOD = "aipd ctq add 的调用点"\n'
    write_tree(tmp_path, GOOD_README, GOOD_REGISTRY, code=code)
    rep = census.audit(tmp_path)
    triples = [(r["doc"], r["line"], r["written"]) for r in rep["report_only_unmatched"]]
    assert len(triples) == len(set(triples)), triples
    dup = [t for t in set(triples) if triples.count(t) > 1]
    assert dup == [], dup


def test_spec_and_ci_writers_are_watched_by_the_report_face(tmp_path: Path,
                                                            tmp_scope) -> None:
    """`.trae/specs/**` 与 `.github/workflows/*` 第 61 片前**四档全看不见**。

    这两类文本是会被真的执行的（agent 照 spec 跑、runner 照 yml 跑），所以至少要**可见**。
    这里同时钉住两头的判决：可见（进只报面）但**不判红**——
    行内命令要不要升成第四档判红面是裁决项，今天两向都是 0 幻影，升与不升不改判决。
    """
    write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
               code='GOOD = "aipd ctq add 的调用点"\n')
    spec = tmp_path / ".trae" / "specs" / "v9" / "checklist.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("全部测试通过（`aipd ghostspec run`）与 `aipd eval` 通过\n", encoding="utf-8")
    ci = tmp_path / ".github" / "workflows"
    ci.mkdir(parents=True, exist_ok=True)
    (ci / "ci.yml").write_text("    - run: aipd ghostci check --db x\n", encoding="utf-8")
    rep = census.audit(tmp_path)
    # 第 75 片把只报面拆成 live / record 两桶：`.trae`（轮次 spec）归记录面、`.github`（CI 定义）
    # 归 live。两桶都要**可见**、都不判红——拆桶的目的是让可行动清单可读，不是把一半语料藏起来。
    live = {(r["doc"], r["written"]) for r in rep["report_only_unmatched"]}
    record = {(r["doc"], r["written"]) for r in rep["report_record_unmatched"]}
    spots = live | record
    assert (".trae/specs/v9/checklist.md", "aipd ghostspec run") in spots, rep["corpus"]
    assert (".github/workflows/ci.yml", "aipd ghostci check") in spots, rep["corpus"]
    assert (".trae/specs/v9/checklist.md", "aipd ghostspec run") in record, live
    assert (".github/workflows/ci.yml", "aipd ghostci check") in live, record
    judged = {v["written"] for v in rep["violations"]}
    assert "aipd ghostspec run" not in judged and "aipd ghostci check" not in judged
    assert rep["ok"] is True, rep["violations"]      # 只报面不改判决


def test_the_instruments_own_files_are_out_of_all_four_faces() -> None:
    """量具与它的用例必须**四档全排除**——第 60 片只在判红面 ③ 排除，只报面照收。

    后果不是判错而是**报表说谎**：这两份文件为了证明"会开火"而故意写的幻影名
    （`aipd ghost cmd`/`ghostly`/`ghostspec`/`ghostci`）会混进"正文里点到未注册命令"
    那张名单，读的人以为仓库里有这些缺口。第 61 片实测这两份文件贡献 **68** 处提及
    （用例 41 + 脚本 27）。对照组钉住"排除没有外溢"：普通文档里的幻影仍要出现。
    """
    rep = census.audit(ROOT)
    own = [r["doc"] for r in rep["report_only_unmatched"] if "doc_command_census" in r["doc"]]
    assert own == [], own
    prose, _ = census.prose_mentions(ROOT)
    assert not [r for r in prose if Path(r[0]).stem in census.SELF_STEMS]
    # 对照组：真仓库正文里合法记下的幻影仍必须可见。用 `aipd truth show` 是因为它是
    # 今天**还在语料里**的活例（CHANGELOG 与取证文档记的是我引错名的经过）；
    # 前提单独钉住，将来谁把它注册了，这里报的是"对照组名字过期"而不是"排除外溢了"。
    paths, _g, _p = census.valid_commands()
    assert "truth show" not in paths, "对照组名 `aipd truth show` 已注册，换一个仍在语料里的幻影"
    assert any(r["written"] == "aipd truth show" for r in rep["report_record_unmatched"]), rep
    assert all("doc_command_census" not in r["doc"] for r in rep["report_record_unmatched"])


def test_those_two_dirs_are_actually_walked_in_the_real_repo() -> None:
    """分母前提：真仓库上 `.trae` **今天就有内容可走**。

    上一条用例的 tmp 夹具证明"走得到"，但证明不了"本仓这两个目录还在"——
    目录被改名/删掉时 `rglob` 安静地给 0 命中，读起来与"这里没有幻影"完全同形。
    `.trae` 第 61 片实测 46 处提及、21 个 md，所以钉一个下界。
    `.github` 今天 0 命中是**事实**而不是失效，不能拿它当下界（那会变成把现状钉成应然），
    它的"走得到"由上一条夹具证明。
    """
    prose, problems = census.prose_mentions(ROOT)
    assert problems == [], problems
    trae = sorted({r[0] for r in prose if r[0].startswith(".trae")})
    assert len(trae) >= 10, f"只报面没再走到 .trae：{len(trae)} 个文件"
    assert all(not r[0].startswith(".trae") or ".trae/specs/" in r[0] for r in prose
               if r[0].startswith(".trae")), trae




def test_absence_written_in_prose_is_reported_not_judged(tmp_path: Path,
                                                         tmp_scope) -> None:
    g = ghost("zzz-unlisted")
    write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
               code='GOOD = "先跑 aipd ctq add 再看"\n',
               prose=f"本轮实测：`{g}` 仍然没有，只能读库。\n")
    rep = census.audit(tmp_path)
    assert rep["ok"] is True, rep["violations"]
    # 夹具把这句写在 `docs/audit/note.md` ⇒ 第 75 片之后它属于记录面：
    # 仍然**可见**（进 record 清单）、仍然**不判红**（两向都要钉住）。
    names = {r["written"] for r in rep["report_record_unmatched"]}
    assert g in names, rep["report_record_unmatched"]
    assert g not in {v["written"] for v in rep["violations"]}, rep["violations"]
    assert rep["report_only_unmatched"] == [], rep["report_only_unmatched"]


def test_record_produced_by_the_command_names_a_real_command(tmp_path: Path) -> None:
    """`ctq.py` 曾把 `aipd truth ctq add` 烙进每条记录的 source.note——本轮实测修掉的幻影。"""
    from aipd_os.cli.main import main
    from aipd_os.product_truth import ProductTruthStore
    from aipd_os.state.db import AIPDStateDB

    db = tmp_path / "state.db"
    state = AIPDStateDB(str(db))
    state.ensure_default_tenant(T)
    state.init_project(T, P, "命令名对账", "evidence")
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(["ctq", "add", "--db", str(db), "--project", P,
                     "--feature", "hole", "--drawing-feature", "TOP.hole_1",
                     "--nominal", "8.0", "--lower", "7.95", "--upper", "8.05",
                     "--inspection", "CMM", "--by", "潘工"]) == 0
    note = ProductTruthStore(str(db), tenant_id=T,
                             project_id=P).query(record_type="ctq")[0].source.note
    paths, groups, problems = census.valid_commands()
    assert not problems, problems
    mentions = census._mentions(note)
    assert mentions, f"记录里的 source.note 没提到任何命令写法：{note}"
    for first, second in mentions:
        assert census.resolve(first, second or None, paths, groups) is not None, \
            f"记录里写着 `aipd {first} {second}`，权威面上没有：{note}"


def test_payload_command_labels_are_registered(tmp_path: Path) -> None:
    """`--json` 的 `command` 标签也是给读者的命令名：三条 ctq 命令都要自报得准。"""
    from aipd_os.cli.main import main
    from aipd_os.state.db import AIPDStateDB

    db = tmp_path / "state.db"
    state = AIPDStateDB(str(db))
    state.ensure_default_tenant(T)
    state.init_project(T, P, "命令名对账", "evidence")
    paths, _groups, problems = census.valid_commands()
    assert not problems, problems
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert main(["ctq", "add", "--db", str(db), "--project", P,
                     "--feature", "hole", "--drawing-feature", "TOP.hole_1",
                     "--nominal", "8.0", "--lower", "7.95", "--upper", "8.05",
                     "--inspection", "CMM", "--by", "潘工", "--json"]) == 0
    payload = json.loads(out.getvalue().strip().splitlines()[-1])
    assert payload["command"] == "ctq add", payload["command"]
    assert payload["command"] in paths, payload["command"]


def test_live_bucket_has_no_unregistered_commands_in_this_repo() -> None:
    """拆桶的**目的**本身要钉住：live（现在还有人在敲的文本）里一个未注册名都不许留。

    拆之前这件事看不见——1059 处只报面里混着 1012 处记录性引述与测试里故意写的幻影名，
    未注册清单永远是"十几行噪音"。拆之后它是空表，
    而任何新写进 src/scripts/模板/架构文档里的假命令都会让它变非空。
    """
    rep = census.audit(ROOT)
    assert rep["report_only_unmatched"] == [], rep["report_only_unmatched"]
    assert rep["corpus"]["report_record_mentions"] > rep["corpus"]["report_only_mentions"], \
        rep["corpus"]


# ---------------------------------------------------------------------------
# 判红面 ④（第 85 片）：文档里行首的 `python scripts/X.py …` 必须真能照着跑。
# 立条前先在真语料上量过：今天 4 行、判 4 行，其中 1 行是假话
# （`references/cad-runtime-acceptance.md` 原本写 `--require-cad`，脚本只认
# `--require-any-cad`，实跑 rc=2 `unrecognized arguments`）。
# 所以这一格不是橡皮章——但也正因如此，两极都必须钉住。


def _mk_scripts(tmp: Path) -> None:
    (tmp / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp / "scripts/zzz_a.py").write_text(
        "import argparse\nap = argparse.ArgumentParser()\n"
        "ap.add_argument('--alpha')\nap.add_argument('--beta-two')\n", encoding="utf-8")
    (tmp / "scripts/zzz_dyn.py").write_text(
        "import argparse\nNAMES = ['--gamma']\nap = argparse.ArgumentParser()\n"
        "ap.add_argument(*NAMES)\n", encoding="utf-8")


def test_script_rows_fire_on_bogus_flag_and_missing_script(tmp_path: Path,
                                                           tmp_scope) -> None:
    """三行三种判决各归各位；合规那行（含反斜杠续行）不许开火。"""
    _mk_scripts(tmp_path)
    write_tree(tmp_path, GOOD_README + (
        "python scripts/zzz_a.py --alpha\n"
        "python scripts/zzz_a.py --zzz-not-declared\n"
        "python scripts/zzz_nosuch.py --alpha\n"
        "python scripts/zzz_a.py --beta-two \\\n    --alpha\n"),
        GOOD_REGISTRY, code='GOOD = "先跑 aipd ctq add 再看"\n')
    rep = census.audit(tmp_path)
    assert fields(rep, "zzz_a.py --zzz-not-declared") == {"脚本旗子"}, rep["violations"]
    assert fields(rep, "scripts/zzz_nosuch.py") == {"脚本缺失"}, rep["violations"]
    assert not any(v["written"].endswith("--alpha") or "--beta-two" in v["written"]
                   for v in rep["violations"]), rep["violations"]
    c = rep["corpus"]
    assert c["script_rows"] == 4 and c["script_rows_judged"] == 4, c
    assert c["script_rows_unbounded"] == [], c
    assert census.main(["--repo", str(tmp_path)]) == 4


def test_unbounded_argparse_is_not_judged(tmp_path: Path, tmp_scope) -> None:
    """`add_argument(*NAMES)` 读不到全集 ⇒ 不判。

    这是"看不见 ≠ 违规"那一极：把读不到当成不存在，就会在合法脚本上造假红，
    而且只有分母键能证明它是**因为**不封闭才没判（不是因为整档没跑）。
    """
    _mk_scripts(tmp_path)
    write_tree(tmp_path, GOOD_README + "python scripts/zzz_dyn.py --whatever\n",
               GOOD_REGISTRY)
    rep = census.audit(tmp_path)
    assert fields(rep, "zzz_dyn.py --whatever") == set(), rep["violations"]
    c = rep["corpus"]
    assert c["script_rows"] == 1, c
    assert c["script_rows_judged"] == 0, c
    assert c["script_rows_unbounded"] == ["zzz_dyn"], c


def test_fourth_judging_face_is_live_in_the_real_repo() -> None:
    """真仓库上这一档必须**真的走到**（分母下界），否则上面两条只是合成语料里的自证。"""
    c = census.audit(ROOT)["corpus"]
    assert c["script_rows"] >= 4, c
    assert c["script_rows_judged"] >= 4, c
    assert c["script_rows_judged"] <= c["script_rows"], c


# ---------------------------------------------------------------------------
# 判红面 ⑤（第 87 片）：文档里 `<解释器> 路径.py|.sh` 形态的复算入口要能落地。
# ---------------------------------------------------------------------------

DEAD = "/tmp/zzz_unregistered_battery.py"


def _git(tmp: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(tmp), *args], capture_output=True, check=True)


def _seed_git(tmp: Path, track: list[str]) -> None:
    _git(tmp, "init", "-q")
    _git(tmp, "add", *track)
    _git(tmp, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")


def test_dead_entrypoint_without_register_fires(tmp_path: Path, tmp_scope) -> None:
    """必开火臂：让人跑一条绝对 /tmp 脚本、册上又没登记 ⇒ 「入口不可解析」。"""
    tree = write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
                      code="# 参见 aipd usage 的说明\nVALUE = 1\n",
                      prose=f"复算入口：`.venv/bin/python {DEAD}` 杀 9/9\n")
    rep = census.audit(tree)
    assert "入口不可解析" in fields(rep, DEAD), rep["violations"]
    assert not rep["problems"], rep["problems"]      # 判红面三档都非空，否则退 2 不是退 4
    assert census.main(["--repo", str(tree)]) == 4


def test_register_is_load_bearing_for_the_same_line(tmp_path: Path, tmp_scope) -> None:
    """同一行、同一判据，只多一本登记册 ⇒ 由红转只记。

    先证它是红的再登记：豁免类判据最常见的退化是"名单其实没被消费"，
    两趟同树读数才能把这条排除掉。
    """
    tree = write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
                      prose=f"复算入口：`python {DEAD}`\n")
    assert "入口不可解析" in fields(census.audit(tree), DEAD)
    reg = tree / census.ENTRY_REGISTER_REL
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps({"entries": [{"path": DEAD, "note": "宿主 /tmp，已不可再生",
                                           "cited_by_at_emit_time":
                                               ["docs/audit/note.md:1"]}]},
                              ensure_ascii=False), encoding="utf-8")
    rep = census.audit(tree)
    assert not fields(rep, DEAD), rep["violations"]
    assert rep["corpus"]["entry_states"]["dead_registered"] == 1, rep["corpus"]


def test_register_entry_that_resolved_again_or_is_uncited_fires(tmp_path: Path,
                                                                tmp_scope) -> None:
    """登记册要双向对账：条目"现在能解析了"与"再没被引用"各开一次火。"""
    (tmp_path / "docs/audit/zzz").mkdir(parents=True)
    (tmp_path / "docs/audit/zzz/live.sh").write_text("echo ok\n", encoding="utf-8")
    write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
               prose="入口：bash docs/audit/zzz/live.sh\n")
    reg = tmp_path / census.ENTRY_REGISTER_REL
    reg.write_text(json.dumps({"entries": [
        {"path": "docs/audit/zzz/live.sh", "note": "已入库，还挂在死链册上"},
        {"path": "docs/audit/zzz/gone.sh", "note": "再没有任何文档引用"}]},
        ensure_ascii=False), encoding="utf-8")
    _seed_git(tmp_path, ["docs/audit/zzz/live.sh"])
    rep = census.audit(tmp_path)
    got = {v["written"]: v["detail"] for v in rep["violations"] if v["field"] == "登记册该撤"}
    assert set(got) == {"docs/audit/zzz/live.sh", "docs/audit/zzz/gone.sh"}, rep["violations"]
    assert "已入库" in got["docs/audit/zzz/live.sh"] or "能解析" in got["docs/audit/zzz/live.sh"]
    assert "引用" in got["docs/audit/zzz/gone.sh"], got


def test_untracked_entrypoint_fires_only_when_git_is_readable(tmp_path: Path,
                                                              tmp_scope) -> None:
    """「文件在本地但没入库」这一档：没有 git 时必须退成不判，而不是整片假红。"""
    (tmp_path / "docs/audit/zzz").mkdir(parents=True)
    (tmp_path / "docs/audit/zzz/lab.py").write_text("print(1)\n", encoding="utf-8")
    write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
               prose="入口：python docs/audit/zzz/lab.py\n")
    rep = census.audit(tmp_path)           # 还没有 .git ⇒ 读不出跟踪面
    assert not any(v["field"] == "入口未入库" for v in rep["violations"]), rep["violations"]
    assert rep["corpus"]["entry_states"].get("git_unknown") == 1, rep["corpus"]
    _seed_git(tmp_path, ["README.md"])     # 提交一半：lab.py 仍未入库
    rep2 = census.audit(tmp_path)
    assert "入口未入库" in fields(rep2, "docs/audit/zzz/lab.py"), rep2["violations"]
    assert not rep2["corpus"]["entry_states"].get("git_unknown"), rep2["corpus"]


def test_placeholder_and_scripts_forms_are_counted_not_judged(tmp_path: Path,
                                                              tmp_scope) -> None:
    """模板写法不判只数；`scripts/…` **只有真被面 ④ 收进那一行**才免责（第 89 片改）。

    第 87 片那版把"交给面 ④"当成无条件豁免，而面 ④ 的语料不含 `docs/audit/`、
    正则只认行首扁平形状 ⇒ 取证文档里点名的、嵌套路径的脚本，两把尺都不判。
    这一条现在同时钉两极：README 行首那条走面 ④（判"脚本缺失"），
    取证文档那条走面 ⑤（判"入口不可解析"）。
    """
    tree = write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
                      prose="模板：python scripts/X.py\n已判面：python scripts/"
                            "zzz_delegated_tool.py --zzz 1\n")
    rep = census.audit(tree)
    st = rep["corpus"]["entry_states"]
    assert st["placeholder"] >= 1, st
    assert st["delegated"] == 0, st          # docs/audit 里的行面 ④ 收不到 ⇒ 不再免责
    ent = {(v["doc"], v["line"], v["field"], v["written"]) for v in rep["violations"]}
    assert ("docs/audit/note.md", 2, "入口不可解析",
            "scripts/zzz_delegated_tool.py") in ent, ent
    assert ("scripts/X.py", "入口不可解析") not in {(w, f) for _d, _l, f, w in ent}, ent


def test_scripts_row_face4_can_see_is_delegated_not_double_judged(tmp_path: Path,
                                                                  tmp_scope) -> None:
    """同一句话换个位置就换个尺子：README 行首的 `python scripts/X.py` 归面 ④。

    没有这一条，上面那条"取证文档不免责"可以靠"干脆谁都不免责"绿过去——
    两极都在，才叫"让渡是可核对的"而不是"让渡被删了"。
    """
    tree = write_tree(tmp_path, GOOD_README + "\npython scripts/zzz_handed_tool.py --zzz 1\n",
                      GOOD_REGISTRY, code="# 参见 aipd usage 的说明\nVALUE = 1\n")
    rep = census.audit(tree)
    fields_h = {(v["field"], v["written"]) for v in rep["violations"]}
    assert ("脚本缺失", "scripts/zzz_handed_tool.py") in fields_h, rep["violations"]
    assert not any(f.startswith("入口") and w == "scripts/zzz_handed_tool.py"
                   for f, w in fields_h), rep["violations"]
    assert rep["corpus"]["entry_states"]["delegated"] == 1, rep["corpus"]


def test_staged_but_uncommitted_entrypoint_is_untracked(tmp_path: Path, tmp_scope) -> None:
    """`git add` 而没 `git commit` 的取证件必须判「未入库」：判据读 HEAD 的树，不读索引。

    第 87 片 §九#7 量到的正是这一格：面 ⑤ 问的是"干净签出拿不拿得到"，
    而 `git ls-files` 读索引 ⇒ 只 add 未 commit 的文件被算成已入库，
    那条入口在别人的签出里根本不存在，却读成合规。
    """
    tree = write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
                      code="# 参见 aipd usage 的说明\nVALUE = 1\n",
                      prose="入口：python docs/audit/zzz/staged.py\n")
    (tree / "docs" / "audit" / "zzz").mkdir(parents=True, exist_ok=True)
    (tree / "docs" / "audit" / "zzz" / "staged.py").write_text("print(1)\n", encoding="utf-8")
    _seed_git(tree, ["README.md", "src/aipd_os/registry_data.py"])   # 提交里**没有** staged.py
    subprocess.run(["git", "-C", str(tree), "add", "docs/audit/zzz/staged.py"],
                   capture_output=True, check=True)
    # 两把尺同时读同一个文件，差集就是这一条用例的存在理由：
    # 索引（`git ls-files`）看得见它，HEAD 的树（`git ls-tree -r HEAD`）看不见。
    import subprocess as _sp
    idx = _sp.run(["git", "-C", str(tree), "ls-files"], capture_output=True,
                  text=True).stdout.splitlines()
    assert "docs/audit/zzz/staged.py" in idx, idx
    assert "docs/audit/zzz/staged.py" not in census.tracked_paths(tree)[0], \
        census.tracked_paths(tree)[0]
    rep = census.audit(tree)
    assert "入口未入库" in fields(rep, "docs/audit/zzz/staged.py"), rep["violations"]


ZZZ_LOCAL = "zzz_local_tool.sh"


def test_git_unreadable_tree_does_not_fabricate_stale_removal(tmp_path: Path,
                                                              tmp_scope) -> None:
    """git 读不出的树：降级出来的 `tracked` 不许被当成"已入库"去判「登记册该撤」。

    第 87 片 §九#2 的原话是"降级自己造出一条违规，还附一句从没证实过的文件已入库"，
    与"不知道≠违规"这条纪律正面冲突。现在的形状是：那一半**只记读数**
    （`entry_register_stale_unjudged`），而"再没被引用"那一半与 git 无关、照旧开火。
    """
    tree = write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
                      code="# 参见 aipd usage 的说明\nVALUE = 1\n",
                      prose=f"入口 A：python docs/audit/zzz/{ZZZ_LOCAL} \n")
    (tree / "docs" / "audit" / "zzz").mkdir(parents=True, exist_ok=True)
    (tree / "docs" / "audit" / "zzz" / ZZZ_LOCAL).write_text("echo ok\n", encoding="utf-8")
    reg = tree / census.ENTRY_REGISTER_REL
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps({"entries": [
        {"path": f"docs/audit/zzz/{ZZZ_LOCAL}", "note": "降级会把它读成 tracked"},
        {"path": "docs/audit/zzz/never_written.sh", "note": "再没被任何文档引用"}]},
        ensure_ascii=False), encoding="utf-8")
    assert not (tree / ".git").exists(), "夹具前提：这棵树必须读不出 git"
    rep = census.audit(tree)
    assert rep["corpus"]["entry_states"].get("git_unknown") == 1, rep["corpus"]
    fired = {v["written"] for v in rep["violations"] if v["field"] == "登记册该撤"}
    assert f"docs/audit/zzz/{ZZZ_LOCAL}" not in fired, rep["violations"]
    assert "docs/audit/zzz/never_written.sh" in fired, rep["violations"]
    assert rep["corpus"]["entry_register_stale_unjudged"] == [f"docs/audit/zzz/{ZZZ_LOCAL}"], \
        rep["corpus"]



# ---------------------------------------------------------------------------
# 第 88 片：登记册的 `cited_by` 降级。
# 第 87 片立这一列时，登记册自己的 `rule` 文本写着"这一列为空 ⇒ 反向开火"，
# 而 `load_entry_register` 只取 `path`/`note`——文档说了一套、实现做了另一套。
# 本轮把列名改成 `cited_by_at_emit_time`（"生成时的路标"）并让 `rule` 由共享常量生成，
# 下面三条分别钉：这一列不参与判决、草案不抹手写依据、真仓库的册与量具同源。


def test_the_snapshot_column_is_decoration_not_authority(tmp_path: Path,
                                                         tmp_scope) -> None:
    """快照列填对的、填错的、整列缺的，判决一字不变——它现在名字里就说了不参与判决。

    每档额外断 `dead_registered == 1`：只比"判决相同"的话，四种写法可能一起落在
    "面 ⑤ 根本没看见那一行"的状态上（把 `startswith("/")` 那支改成 tracked 就能这样绿过去）。
    这根计数把"看得见、且被免判"钉成每一档的共同前提，四种写法才真的只是列的形状之差。

    最后一段是**分辨性夹具**：一条在册、带着完整且真实的 `cited_by_at_emit_time`、
    但语料里没有对应行的条目。判据现在必须开火（「登记册该撤」）；
    将来谁把这列接回判据，它就闭嘴。"这一列被忽略"与"这一列被查到、值为空"
    两种实现，只有这个形状能分开。
    """
    tree = write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
                      code="# 参见 aipd usage 的说明\nVALUE = 1\n",
                      prose=f"复算入口：python {DEAD}\n")
    reg = tree / census.ENTRY_REGISTER_REL
    reg.parent.mkdir(parents=True, exist_ok=True)
    base: list[str] | None = None
    for col in ({"cited_by_at_emit_time": ["docs/audit/note.md:1"]},
                {"cited_by_at_emit_time": ["docs/audit/根本没这行.md:99"]},
                {"cited_by": ["第 87 片那个旧键名"]},
                {}):
        reg.write_text(json.dumps({"entries": [{"path": DEAD, "note": "宿主 /tmp", **col}]},
                                  ensure_ascii=False), encoding="utf-8")
        rep = census.audit(tree)
        assert not rep["problems"], rep["problems"]
        assert rep["corpus"]["entry_states"]["dead_registered"] == 1, (col, rep["corpus"])
        fields_now = sorted({v["field"] for v in rep["violations"]})
        if base is None:
            base = fields_now
        assert fields_now == base, (col, rep["violations"])
    assert base == [], base

    ghost = "/tmp/zzz_column_only.py"
    reg.write_text(json.dumps({"entries": [
        {"path": DEAD, "note": "宿主 /tmp"},
        {"path": ghost, "note": "第 88 片分辨性夹具",
         "cited_by_at_emit_time": ["docs/audit/note.md:1"]}]}, ensure_ascii=False),
        encoding="utf-8")
    rep = census.audit(tree)
    fired = {v["written"] for v in rep["violations"] if v["field"] == "登记册该撤"}
    assert ghost in fired, (fired, "在册条目带着一整列引用仍被判「该撤」⇒ 这列不被消费")
    assert DEAD not in fired, rep["violations"]


def test_emit_register_carries_notes_reports_drops_and_refuses(tmp_path: Path) -> None:
    """`--emit-register` 的三个面：带旧 note、报出"有依据却被丢"的条目、目标不像册子就不落盘。

    前两半是同一条纪律的两端——豁免依据不许**静默**消失：留在 `dead` 档的按 `path` 带过来，
    离开那一档的（最常见原因是有人把最后一处命令形态改写成叙述，而不是"修好了"）
    必须连原文一起报出来，由操作者决定要不要手工留档。
    后半用两种"读不出"：非法 JSON，以及"能解析但不是字典"——后者以前会抛
    `AttributeError`、退 1 加一段 traceback，而 docstring 承诺的是"整批不写"。

    不需要 `tmp_scope`：`emit_register` 只走 `entry_points`，那是按本仓 `ENTRY_FILES`/
    `ENTRY_DIRS` 的名字在**传入的树**里找文件，与被 monkeypatch 的判决面无关。
    """
    tree = write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
                      prose=f"复算入口：python {DEAD}\n")
    dst = tree / census.ENTRY_REGISTER_REL
    got = census.emit_register(tree, dst)
    assert got["refused"] == "" and got["written"] == 1, got
    assert got["missing_notes"] == [DEAD] and got["dropped"] == [], got
    doc = json.loads(dst.read_text(encoding="utf-8"))
    assert doc["entries"][0]["cited_by_at_emit_time"], doc
    # 五段说明文字都得由常量生成：只比磁盘册子与常量的那条同源用例抓不到"草案漏字段"，
    # 因为漏了的那一段在册子里同样不存在——两边就"一致地缺"了。
    for key, const in (("what", census.REGISTER_WHAT), ("rule", census.REGISTER_RULE),
                       ("cited_by_at_emit_time_semantics",
                        census.REGISTER_SNAPSHOT_SEMANTICS),
                       ("note_semantics", census.REGISTER_NOTE_SEMANTICS),
                       ("shape_borrowed_from", census.REGISTER_SHAPE_BORROWED_FROM)):
        assert doc[key] == const, (key, doc.get(key))

    filled = "第 88 片夹具：宿主 /tmp，重启即没，读数已抄进取证文档"
    doc["entries"][0]["note"] = filled
    dst.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    again = census.emit_register(tree, dst)
    assert again["missing_notes"] == [] and again["dropped"] == [], again
    assert json.loads(dst.read_text(encoding="utf-8"))["entries"][0]["note"] == filled

    # 把引用那一行从语料里撤掉 ⇒ 条目离开 dead 档：文件可以少这一条，依据不许悄悄没
    (tree / "docs" / "audit" / "note.md").write_text("改成叙述，不再有命令形态\n",
                                                     encoding="utf-8")
    third = census.emit_register(tree, dst)
    assert third["written"] == 0, third
    assert third["dropped"] == [{"path": DEAD, "note": filled}], third
    left = [e["path"] for e in json.loads(dst.read_text(encoding="utf-8"))["entries"]]
    assert DEAD not in left, left

    broken = "{ 这不是 JSON"
    dst.write_text(broken, encoding="utf-8")
    refused = census.emit_register(tree, dst)
    assert "读不出" in refused["refused"], refused
    assert dst.read_text(encoding="utf-8") == broken, "拒绝时不许动目标文件"

    notadict = '["这不是字典"]'
    dst.write_text(notadict, encoding="utf-8")
    refused2 = census.emit_register(tree, dst)
    assert "不是字典" in refused2["refused"], refused2
    assert dst.read_text(encoding="utf-8") == notadict, "非字典目标同样不许被覆盖"


def test_real_repo_register_shares_the_instrument_constants() -> None:
    """真仓库那本册的五段说明文字必须与量具的常量逐字同源。

    钉关系不钉数字。第 87 片实测到册里的 `rule` 写"四种归属"而代码写"五种"——
    两份手抄各漂各的，谁都不判。把常量拿出来比，这类漂移当场变红。
    """
    reg = json.loads((ROOT / census.ENTRY_REGISTER_REL).read_text(encoding="utf-8"))
    for key, const in (("what", census.REGISTER_WHAT),
                       ("rule", census.REGISTER_RULE),
                       ("cited_by_at_emit_time_semantics", census.REGISTER_SNAPSHOT_SEMANTICS),
                       ("note_semantics", census.REGISTER_NOTE_SEMANTICS),
                       ("shape_borrowed_from", census.REGISTER_SHAPE_BORROWED_FROM)):
        assert reg[key] == const, (key, reg[key])
    for e in reg["entries"]:
        assert "cited_by" not in e, f"{e['path']} 还是旧列名"
        assert isinstance(e["cited_by_at_emit_time"], list), e


def test_real_repo_entry_face_is_live_and_every_dead_link_is_registered() -> None:
    """真仓库侧：面 ⑤ 不是摆设，且现在 0 条未登记死链。"""
    rep = census.audit(ROOT)
    assert not rep["problems"], rep["problems"]
    st = rep["corpus"]["entry_states"]
    assert st["dead"] == st["dead_registered"] > 0, st
    # `untracked == 0` 单独看是"零违规"的同形读法：在一棵读不出 git 的树（镜像、无 .git 的副本）
    # 上它恒真。必须同时钉"这棵树 git 读得出"，那条 0 才是判过的结果而不是没判。
    assert not st.get("git_unknown"), st
    assert rep["corpus"]["entry_git_unknown"] is False, rep["corpus"]
    assert st["untracked"] == 0, st
    # 登记册自己也必须在 HEAD 的树里：它是判据消费的豁免名单，
    # 只躺在工作树里＝下一轮换一棵干净签出就变成"一本空册"，所有死链当场重开。
    assert census.ENTRY_REGISTER_REL in (census.tracked_paths(ROOT)[0] or set()), \
        census.ENTRY_REGISTER_REL
    assert not rep["corpus"]["entry_register_stale_unjudged"], rep["corpus"]
    assert st["tracked"] > 0 and st["delegated"] > 0 and st["placeholder"] > 0, st
    assert not [v for v in rep["violations"]
                if v["field"].startswith("入口") or v["field"] == "登记册该撤"], rep["violations"]
    reg = json.loads((ROOT / census.ENTRY_REGISTER_REL).read_text(encoding="utf-8"))
    assert len(reg["entries"]) >= 1, reg
    for e in reg["entries"]:
        assert e["note"], f"登记条目 {e['path']} 没写为什么不再可复算"
        # （第 89 片）原来这里写的是 `startswith("/") or not (ROOT/path).exists()`：
        # 今天 13 条**全是绝对路径**，`or` 的左半边恒真 ⇒ 右半边从没执行过，
        # 这条断言对"注册的东西其实还在仓库里"这种状态是瞎的（§九#8b）。
        # 换掉它的是上面那对扫描侧断言（`dead == dead_registered` 且无「该撤」）
        # ——它们由判据现读，绝对/相对两种形状都走同一条路；
        # 相对路径那条分支由合成语料的 `test_register_entry_that_resolved_again_or_is_uncited_fires`
        # 与 `test_git_unreadable_tree_does_not_fabricate_stale_removal` 负责。
    # 独立分母（比判据宽：不看有没有解释器前缀）：登记册必须落在它的真子集里
    loose: set[str] = set()
    for d in [ROOT / "README.md", ROOT / "QUICKSTART.md", ROOT / "SKILL.md"] + \
             sorted((ROOT / "docs").rglob("*.md")) + sorted((ROOT / "references").rglob("*.md")):
        if d.is_file():
            loose.update(re.findall(r"/tmp/[A-Za-z0-9_./-]+\.py", d.read_text(encoding="utf-8")))
    registered = {e["path"] for e in reg["entries"]}
    assert registered <= loose, sorted(registered - loose)
    assert loose - registered, "登记册与宽口径分母相等 ⇒ 宽尺多半也没看见东西"
    # 宽尺可见、判据没判的，只允许是"非命令形态的叙述引用"（本轮普查已登记为度量，不做门）
    assert census.main(["--repo", str(ROOT)]) == 0


def test_absolute_path_is_dead_even_when_that_file_exists(tmp_path: Path,
                                                          tmp_scope) -> None:
    """绝对路径那一支为什么不能省：`Path(root) / "/tmp/x.py"` 会把 root 丢掉，
    于是"这台机器上恰好还有那个文件"会被读成可解析。判据必须按"干净签出"判，
    所以绝对路径一律算死链——本用例就是那支的唯一反证（电池 X1 臂靠它翻红）。"""
    outside = tmp_path / "abs"
    outside.mkdir()
    (outside / "battery.py").write_text("print(1)\n", encoding="utf-8")
    written = f"{outside}/battery.py"
    tree = write_tree(tmp_path, GOOD_README, GOOD_REGISTRY,
                      code="# 参见 aipd usage 的说明\nVALUE = 1\n",
                      prose=f"复算入口：python {written}\n")
    assert outside.is_dir() and (outside / "battery.py").is_file()
    rep = census.audit(tree)
    assert "入口不可解析" in fields(rep, written), rep["violations"]
    assert rep["corpus"]["entry_states"]["dead"] == 1, rep["corpus"]
    assert not any(v["field"] == "入口未入库" for v in rep["violations"]), rep["violations"]


def test_tracked_face_reads_non_ascii_paths_unescaped(tmp_path: Path) -> None:
    """非 ASCII 文件名必须原样出现在跟踪面里：git 默认把它们转义成八进制串。

    `git ls-tree`/`git ls-files` 都不加 `-c core.quotePath=false` 时输出
    `"\\344\\270\\255\\346\\226\\207/x.py"` 这种形状 ⇒ 成员判定必然落空，
    一条明明入库的入口会被读成"未入库"再判红（假红，不是漏判）。
    本仓今天 1049 条跟踪路径全是 ASCII，所以这一格不咬现有语料——
    钉它是因为它一旦咬就是**假红**，而假红正是这把尺最贵的失败模式。
    注意：面 ⑤ 的识别正则 `[A-Za-z0-9_./-]+` 本身**看不见**非 ASCII 路径，
    所以这里直接验 `tracked_paths()`（修复所在的那一层），识别面的这一漏排在第 90 片。
    """
    tree = tmp_path / "repo"
    (tree / "docs" / "audit" / "中文 目录").mkdir(parents=True)
    (tree / "docs" / "audit" / "中文 目录" / "电池.py").write_text("print(1)\n",
                                                                   encoding="utf-8")
    (tree / "with space.py").write_text("print(2)\n", encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"]):
        subprocess.run(["git", "-C", str(tree), *args], capture_output=True, check=True)
    tracked = census.tracked_paths(tree)[0]
    assert tracked is not None, census.tracked_paths(tree)[1]
    assert "docs/audit/中文 目录/电池.py" in tracked, sorted(tracked)
    assert "with space.py" in tracked, sorted(tracked)
    assert not any(p.startswith('"') for p in tracked), sorted(tracked)
