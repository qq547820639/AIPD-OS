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
    assert c["report_only_mentions"] >= 500, c


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
    spots = {(r["doc"], r["written"]) for r in rep["report_only_unmatched"]}
    assert (".trae/specs/v9/checklist.md", "aipd ghostspec run") in spots, rep["corpus"]
    assert (".github/workflows/ci.yml", "aipd ghostci check") in spots, rep["corpus"]
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
    assert any(r["written"] == "aipd truth show" for r in rep["report_only_unmatched"]), rep


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
    names = {r["written"] for r in rep["report_only_unmatched"]}
    assert g in names, rep["report_only_unmatched"]


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
