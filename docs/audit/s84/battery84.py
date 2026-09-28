# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 84 片（绑定前的清单同源闸）的变异电池。

每条臂撤掉本片新增的一根牙，必须在
`tests/test_release_evidence_preflight.py` + `tests/test_closeout_verifier.py` 上**增量开火**。

判决按"增量开火"而不是退码：基线不全绿
（`tests/test_closeout_verifier.py::test_roster_gap_equals_tests_changed_since_the_report`
 在本片新用例文件还没提交、报告还没重跑的那段窗口里合法地红——这是本仓认得的在途态，
 不是电池的判据）。同一因的形状在第 83 片记过一次，规矩沿用。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
EV = ROOT / "scripts/release_evidence.py"
COV = ROOT / "scripts/closeout_verifier.py"
PY_BIN = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_release_evidence_preflight.py", "tests/test_closeout_verifier.py"]

ARMS = [
    {"id": "W1-missing-field-no-longer-refused", "file": EV,
     "reps": [('    if not rec:\n        raise BindPreflightError(',
               '    if False:\n        raise BindPreflightError(')],
     "note": "报告没带指纹这一支沉默：那种报告被写成 attestation，等于没人能归因它测的是哪份清单"},
    {"id": "W2-content-drift-no-longer-refused", "file": EV,
     "reps": [('    if rec != want:\n        raise BindPreflightError(',
               '    if False:\n        raise BindPreflightError(')],
     "note": "清单动过这一支沉默：第 81 片那笔『绑完报告又改参与哈希的文档』的债重新无人守"},
    {"id": "W3-compares-raw-bytes", "file": EV,
     "reps": [('    want = release_fingerprint.fingerprint_of_document(source_doc)',
               '    want = hashlib.sha256(json.dumps(source_doc, ensure_ascii=False).encode()).hexdigest()')],
     "note": "改成比原始字节：每轮刷清单都会换 generated_at ⇒ 正常收尾被自己拒掉（假红档）"},
    {"id": "W4-gate-moved-after-the-write", "file": EV,
     "reps": [('    if test_report is not None:\n        preflight_report_vs_source(prov.get("test_report") or {}, source)\n\n',
               ''),
              ('        json.dumps(source, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")\n    (out_dir / "PROVENANCE.json").write_text(',
               '        json.dumps(source, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")\n    if test_report is not None:\n        preflight_report_vs_source(prov.get("test_report") or {}, source)\n    (out_dir / "PROVENANCE.json").write_text(')],
     "note": "闸挪到 SOURCE_MANIFEST 落盘之后：拒写变成半写，树里留下一份与清单不同源的证据"},
    {"id": "W5-refusal-laundered-to-zero", "file": EV,
     # 锚点必须跟着那句文案走：本文件把 print 改成"未建目录、未写任何文件"之后，
     # 旧锚点命中 0 次 ⇒ 这一臂被记 BAD-ANCHOR（不是存活，是注入没落地）。
     "reps": [('        print(f"拒绝写入证据（未建目录、未写任何文件）：{exc}")\n        return 2',
               '        print(f"拒绝写入证据（未建目录、未写任何文件）：{exc}")\n        return 0')],
     "note": "退码被洗成 0：配方看不出这一步被拒过，绑定就当成成功了"},
    {"id": "W6-production-doesnt-record-field", "file": EV,
     "reps": [('        "source_manifest_fingerprint": (data.get("source_manifest_fingerprint")\n'
               '                                        if isinstance(data, dict) else None),',
               '')],
     "note": "PROVENANCE 不再抄这个键：证据自己说不清测的是哪份清单，跨面审计退回靠记忆"},
    {"id": "W7-fixture-stops-mirroring-field", "file": COV,
     "reps": [('                        "failed": max(total - passed - skipped, 0), "total": total,\n'
               '                        "source_manifest_fingerprint":\n'
               '                            data.get("source_manifest_fingerprint")}',
               '                        "failed": max(total - passed - skipped, 0), "total": total}')],
     "note": "验签夹具与生产形状脱钩：量具只读其中几格，这种漂移它自己永远不红，"
             "只有那条跨文件键集对照用例看得见（两处各写一遍的标准失效方式）"},
    {"id": "W8-mkdir-moved-before-the-gate", "file": EV,
     "reps": [("    source = generate_source_manifest(repo, source_commit)",
               "    out_dir.mkdir(parents=True, exist_ok=True)\n"
               "    source = generate_source_manifest(repo, source_commit)"),
              ("    out_dir.mkdir(parents=True, exist_ok=True)\n    results = {}",
               "    results = {}")],
     "note": "落盘副作用（建目录）挪回闸之前：'拒写不半写'退化成'拒写但留下一个空目录'，"
             "AST 那条只盯 write_text 的接线断言对它是盲的——这一臂证明盲区已经被堵上"},
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def run_tests():
    proc = subprocess.run([PY_BIN, "-m", "pytest", *TESTS, "-q", "--no-header", "-rf",
                           "-p", "no:cacheprovider"], capture_output=True,
                          text=True, cwd=str(ROOT), timeout=1200)
    out = proc.stdout + proc.stderr
    lines = out.splitlines()
    tally = [ln for ln in lines if "passed" in ln or "failed" in ln or "error" in ln][-1:]
    fired = {ln[len("FAILED "):] for ln in lines if ln.startswith("FAILED ")}
    return proc.returncode, (tally[0][:70] if tally else ""), fired


RC0, BASE_TALLY, BASE_FIRED = run_tests()
print(f"基线 rc={RC0} {BASE_TALLY}")
for f in sorted(BASE_FIRED):
    print(f"              基线红（非电池判据）: {f}")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]
    arms = [a for a in ARMS if not only or only in a["id"]]
    if only and not arms:
        print(f"--only {only!r} 一支都没匹配上；现有臂：" + ", ".join(a["id"] for a in ARMS))
        return 2
    if only:
        print(f"子集复算：只跑 {len(arms)}/{len(ARMS)} 臂（{', '.join(a['id'] for a in arms)}）"
              "——合计行的分母按本次实跑的臂数算，不是整支电池")
    srcs = {a["file"]: a["file"].read_text(encoding="utf-8") for a in arms}
    bases = {k: sha(k) for k in srcs}
    rows = []
    for arm in arms:
        tgt = arm["file"]
        src = srcs[tgt]
        mutated = src
        bad = None
        # 「插入体已经在树上」这一条只对**纯插入**成立（`old` 是 `new` 的子串）。
        # 对删除型 rep（`new` 反过来是 `old` 的子串，例如 W4 第一步把整段闸摘掉）它必然为真，
        # 于是把一条合法注入误判成 BAD-ANCHOR——W4 第一版就是这么被吞掉的。
        # 真正的"什么都没改"由下面的 `mutated == src` 判，那一条对所有形状都成立。
        for old, new in arm["reps"]:
            if src.count(old) != 1:
                bad = f"old 命中 {src.count(old)} 次"
                break
            if old in new and new in src:
                bad = "插入体已在树上（重复注入）"
                break
            mutated = mutated.replace(old, new, 1)
        if bad:
            rows.append((arm["id"], "BAD-ANCHOR", bad, []))
            continue
        if mutated == src:
            rows.append((arm["id"], "BAD-MUTATION", "改写后与原文逐字节相同", []))
            continue
        try:
            compile(mutated, str(tgt), "exec")
        except SyntaxError as exc:
            rows.append((arm["id"], "BAD-MUTATION", str(exc), []))
            continue
        tgt.write_text(mutated, encoding="utf-8")
        try:
            assert sha(tgt) != bases[tgt], "落地失败"
            _rc, line, fired = run_tests()
            new = sorted(fired - BASE_FIRED)
            if not new:
                verdict = "SURVIVED"
            elif "error" in line.lower():
                verdict = "CRASH-KILL"
            else:
                verdict = "KILLED"
        finally:
            tgt.write_text(src, encoding="utf-8")
            assert sha(tgt) == bases[tgt], "还原失败"
        rows.append((arm["id"], verdict, line, new))
    for k, v in bases.items():
        print(f"基线 {k.name} sha={v}")
    for rid, v, d, fired in rows:
        print(f"[{v:11}] {rid}  {d[:70]}")
        for f in fired:
            print(f"              增量开火: {f}")
    good = sum(1 for _r, v, _d, _f in rows if v in ("KILLED", "CRASH-KILL"))
    other: dict = {}
    for _r, v, _d, _f in rows:
        if v not in ("KILLED", "CRASH-KILL"):
            other[v] = other.get(v, 0) + 1
    print(f"合计 KILLED+CRASH-KILL {good} / {len(arms)}；其余按判决分类："
          + ("、".join(f"{k} {n}" for k, n in sorted(other.items())) or "无"))
    return 0 if good == len(arms) else 1


if __name__ == "__main__":
    sys.exit(main())
