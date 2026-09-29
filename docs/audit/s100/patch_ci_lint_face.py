r"""第 100 片：把 `scripts/` 的 lint 面接进 CI，并按锚点同批改三处镜像（两阶段落盘）。

改的三面必须**逐字同源**，否则常驻用例当场翻红（这正是第 91 片立消费表对账的理由）：
① `.github/workflows/ci.yml` 里那条 `run: ruff check …` 的命令字符串；
② `tests/test_ci_face_gates.py` 的 `COVERED` 字典——它的**键**就是①的逐字，
   它的**值**是本地怎么跑同一条判据；
③ `docs/audit/CI_SURFACE_REGISTER.json` 由 `docs/audit/s91/build_ci_surface_register.py`
   **现读现写**（不在这里手改，手改就等于造第二份事实）。

文件清单不手写：从 `scripts_lint_ratchet` 的测量结果里取"今天真正 0 债"的那批，
所以这条脚本跑第二次时会把清单刷新而不是抄旧数（幂等靠"重算"而不是"重复替换"）。

两阶段：全部替换先在内存里算完并过闸门（任一锚点命中数 ≠ 预期 ⇒ 一份都不落盘），
再统一落盘并读回复算；写完立刻跑 `bash`/`ruff`/判据三样复验。
"""
from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CI = ROOT / ".github" / "workflows" / "ci.yml"
GATES = ROOT / "tests" / "test_ci_face_gates.py"
TOOL = ROOT / "scripts" / "scripts_lint_ratchet.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("slr100", TOOL)
    assert spec is not None and spec.loader is not None, "载入不了量具 ⇒ 不是它绿，是没跑到"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def zero_debt_files(mod) -> list[str]:
    root = mod.Path(ROOT)
    hits, files, problems = mod.measure(root)
    assert not problems, problems
    return sorted(f for f in files if not any(k[0] == f for k in hits))


def old_ci_line() -> str:
    # **整行**当锚（带尾换行）。只取前缀的话，接好面之后的那一行仍然"含有"这个前缀 ⇒
    # `count(old)==1` 依旧成立、脚本会把清单再贴一遍（第 100 片实测踩过，键与命令差在
    # 后半段的重复文件名上）。整行锚 + 下面的"点名数==清单长度"复验是同一件事的两道门。
    return "        run: ruff check src tests state_service\n"


def new_ci_line(files: list[str]) -> str:
    return "        run: ruff check src tests state_service " + " ".join(files) + "\n"


OLD_KEY = '''# 本文件负责接住的 CI 命令（键必须与 ci.yml 里的逐字一致，由 `census` 那边对账）。
COVERED = {
    "ruff check src tests state_service": [sys.executable, "-m", "ruff", "check",
                                           "src", "tests", "state_service"],
'''


def new_key(files: list[str]) -> str:
    """键**由一份 token 清单拼出来**，并在同一个文件里只写一次（`RUFF_CMD`）。

    抄 544 列整串会当场撞 E501；把整串拆成续行字符串又会造出"键与 ci.yml 不再逐字相同"
    的假绿；而键写在两处（`COVERED` 里一次、用例里查一次）就是两份事实——第 100 片实测
    过：改了 `COVERED` 之后 `_run(COVERED["ruff check src tests state_service"])` 直接
    `KeyError`。所以引一个 `RUFF_CMD` 名字，`COVERED` 的键与用例的查表都指它。
    """
    lst = "SCRIPTS_LINT_FACE = [\n" + "".join(f'    "{f}",\n' for f in files) + "]\n"
    return ("""# 本文件负责接住的 CI 命令（键必须与 ci.yml 里的逐字一致，由 `census` 那边对账）。
# 第 100 片把 `scripts/` 里今天 0 债的那批直接接进 CI 的 ruff 面：清单只存一份 token，
# 键（`RUFF_CMD`）与本地 argv 都由它拼出来——抄 544 列整串会撞 E501，拆成续行字符串
# 又会造出"键与 ci.yml 不再逐字相同"的假绿。清单本身的正确性由
# `scripts/scripts_lint_ratchet.py` 的 `lint面直连清单不同源` 那一格判。
""" + lst + """RUFF_CMD = " ".join(["ruff", "check", "src", "tests", "state_service",
                     *SCRIPTS_LINT_FACE])
COVERED = {
    RUFF_CMD: [sys.executable, "-m", "ruff", "check", "src", "tests", "state_service",
               *SCRIPTS_LINT_FACE],
""")


def main() -> int:
    mod = _load_tool()
    files = zero_debt_files(mod)
    print(f"[测量] 今天 0 债的文件 {len(files)} 个：{', '.join(files[:3])}…")
    pairs = [(CI, old_ci_line(), new_ci_line(files)),
             (GATES, OLD_KEY, new_key(files)),
             (GATES, '    proc = _run(COVERED["ruff check src tests state_service"])',
              "    proc = _run(COVERED[RUFF_CMD])"),
             (GATES, '    """CI 的 lint job 第一条：`ruff check src tests state_service`。"""',
              '    """CI 的 lint job 第一条；第 100 片起它还点名 `scripts/` 里 0 债的那批。\n\n'
              '    命令串不写第二遍：`RUFF_CMD` 由 `SCRIPTS_LINT_FACE` 拼出来、\n'
              '    与 ci.yml 逐字同源（键抄两份的那版实测过 KeyError）。\n    """'),
             # 派生键之后，"册子声称的命令要能在本文件里找到整串"这一格不能再按字面判：
             # 整串是跑出来的，不是写出来的。改钉更强的那一格——拼出来的键必须等于
             # ci.yml 上那条命令本身（权威面），而不是"文件里出现过这串字"。
             (GATES,
              '    src = Path(__file__).read_text(encoding="utf-8")\n'
              '    for cmd in claimed:\n'
              '        assert cmd in src, f"{cmd!r} 在册子里挂着，但本文件里没有它的身影"',
              '    src = Path(__file__).read_text(encoding="utf-8")\n'
              '    for cmd in claimed:\n'
              '        if cmd == RUFF_CMD:\n'
              '            lines = [ln.strip()[len("run: "):] for ln in\n'
              '                     (ROOT / ".github" / "workflows" / "ci.yml")\n'
              '                     .read_text(encoding="utf-8").splitlines()\n'
              '                     if ln.strip().startswith("run: ruff check")]\n'
              '            assert len(lines) == 1 and lines[0] == cmd, (\n'
              '                f"派生键与权威面不同源：ci.yml 上读到 {len(lines)} 条 {lines}")\n'
              '            continue\n'
              '        assert cmd in src, f"{cmd!r} 在册子里挂着，但本文件里没有它的身影"')]
    texts: dict[Path, str] = {}
    todo: dict[Path, list[tuple[str, str]]] = {}
    for path, old, new in pairs:
        text = texts.get(path) or path.read_text(encoding="utf-8")
        got, already = text.count(old), text.count(new)
        if got == 0 and already >= 1:
            print(f"[幂等] {path.name} 的这一处已是新形状（命中 {already} 次），跳过")
            texts[path] = text
            continue
        if got != 1:
            print(f"[BAD-ANCHOR] {path.name} 的锚点 {old[:44]!r} 命中 {got} 次（要 1）、"
                  f"新形状命中 {already} 次 ⇒ 一份都不落盘")
            return 7
        texts[path] = text.replace(old, new, 1)
        todo.setdefault(path, []).append((old, new))
    if not todo:
        print("[无事可做] 各处都已是新形状")
        return 0
    for path in todo:
        path.write_text(texts[path], encoding="utf-8")
        print(f"[落盘] {path.relative_to(ROOT)}（{len(todo[path])} 处锚点）")

    back_ci = CI.read_text(encoding="utf-8")
    back_g = GATES.read_text(encoding="utf-8")
    cmds = [ln.strip()[5:] for ln in back_ci.splitlines()
            if ln.strip().startswith("run: ruff check")]
    assert len(cmds) == 1, cmds
    cmd = cmds[0]
    tok = cmd.split()
    named = [t for t in tok[2:] if t.startswith("scripts/")]
    if len(named) != len(files) or sorted(named) != files:
        print(f"[复验失败] ci.yml 点名 {len(named)} 个（去重后 {len(set(named))}），"
              f"应为 {len(files)} 个 ⇒ 清单被贴了两遍或少了一截，不落盘的状态不可信")
        return 6
    for f in files:
        if f'    "{f}",' not in back_g:
            print(f"[复验失败] 清单里少了 {f} ⇒ 键会与 ci.yml 不同源")
            return 6
    # 真对账：从门文件里把 SCRIPTS_LINT_FACE 用 ast 读出来拼成键，与 ci.yml 的命令逐字比。
    # （不 import 那个测试文件——模块级一跑就连带把 pytest 的收集副作用拖进来。）
    face = None
    for node in ast.parse(back_g).body:
        if (isinstance(node, ast.Assign)
                and getattr(node.targets[0], "id", "") == "SCRIPTS_LINT_FACE"):
            face = [ast.literal_eval(e) for e in node.value.elts]
    assert face is not None, "读不出 SCRIPTS_LINT_FACE ⇒ 门文件的形状变了，本脚本的锚点要跟着改"
    joined = " ".join(["ruff", "check", "src", "tests", "state_service", *face])
    if joined != cmd:
        print("[复验失败] 拼出来的键与 ci.yml 的命令不逐字相同：")
        print(f"  键     = {joined[:110]}…")
        print(f"  ci.yml = {cmd[:110]}…")
        return 6
    print(f"[复验] 拼出来的键 == ci.yml 的命令（逐字 {len(cmd)} 列，点名 {len(face)} 个文件）")
    rc = subprocess.run([str(ROOT / ".venv/bin/ruff"), "check", "--no-cache",
                         "--output-format", "concise", *tok[2:]],
                        cwd=str(ROOT), capture_output=True, text=True)
    print(f"[复验] 本地照 CI 那样逐字跑这条命令（{len(tok) - 2} 个参数）⇒ rc={rc.returncode}")
    if rc.returncode != 0:
        print("        " + (rc.stdout or "").replace("\n", "\n        ")[:600])
        return 4
    print(f"[复验] 面已接上：SCRIPTS_LINT_FACE {len(files)} 项，ci.yml 命令 {len(cmd)} 列"
          f"（不再有 544 列的字面量），键由同一份清单拼出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
