# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 83 片（报告自证清单指纹）的变异电池。

每条臂撤掉本片新增的一根牙，必须在
`tests/test_report_manifest_fingerprint.py` + `tests/test_closeout_verifier.py`
上开火。跑法：`python docs/audit/s83/battery83.py`（要落盘改源文件，
跑完逐臂还原并校验 sha）。

两类红要分清（沿用第 81 片的记账法）：
**判决翻转**＝量具给出了不同的判读；**CRASH-KILL**＝变异把量具自己弄崩了。
两者都算撤掉了牙，但只有前者能证明"这条判据本来在判什么"。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
CONF = ROOT / "tests/conftest.py"
RFP = ROOT / "scripts/release_fingerprint.py"
COV = ROOT / "scripts/closeout_verifier.py"
PY_BIN = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_report_manifest_fingerprint.py", "tests/test_closeout_verifier.py"]

ARMS = [
    {"id": "Y1-producer-computes-but-doesnt-write", "file": CONF,
     "reps": [('        json_report["source_manifest_fingerprint"] = fp',
               '        pass  # 变异：算出来了却不写进报告')],
     "note": "生产侧静默失联：真报告不再带指纹。只有用真 `pytest --json-report` 那条用例看得见，"
             "手写夹具那一侧照绿"},
    {"id": "Y2-volatile-key-not-stripped", "file": RFP,
     "reps": [('VOLATILE_KEYS = ("generated_at",)', 'VOLATILE_KEYS = ()')],
     "note": "把 `generated_at` 也端进摘要 ⇒ 每轮刷清单都读成"
             "「清单换了」；独立盲尺那条与 --self-test 的假红控制都得翻"},
    {"id": "Y3-verifier-uses-raw-bytes-sha", "file": COV,
     "reps": [('    disk_fp, fp_err = release_fingerprint.fingerprint_from_file(manifest_path)',
               '    disk_fp, fp_err = _sha256_path(manifest_path), ""')],
     "note": "验签侧改成比原始字节 sha：字节面每轮必变，"
             "--self-test 里「只换 generated_at 必须绿」那一支就该红"},
    {"id": "Y4-C10-silenced", "file": COV,
     "reps": [('    if not rec_fp:\n        # 前提塌而不是判红',
               '    if False:\n        # 前提塌而不是判红')],
     "note": "把「报告没带指纹」那一支整支沉默：verifier 会对着没有字段的旧证据退 0，"
             "换绑配方与常驻两极用例（problem 那一判）都该翻"},
    {"id": "Y5-C11-fires-without-baseline", "file": COV,
     "reps": [('    elif not rec_fp:', '    elif False:')],
     "note": "报告没带指纹时让 C11 也开火：self-test 的「每支注入只点亮自己那一格」"
             "当场拒绝这种连带判红"},
    {"id": "Y6-unreadable-manifold-becomes-red", "file": COV,
     "reps": [('    if fp_err:', '    if False:')],
     "note": "磁盘清单读不出时不再退 2，而是拿空串去比 ⇒ 判成违规："
             "把「看不见」折算成红，正是本仓三态纪律禁止的"},
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
    fired = [ln[len("FAILED "):] for ln in lines if ln.startswith("FAILED ")]
    return proc.returncode, (tally[0][:70] if tally else ""), set(fired)


# 基线**不是**全绿：这一片的新判据把第 82 片那份旧报告判红（它出自没有注入的 conftest），
# 而换绑在电池之后。所以判决不能看退码——退码非零在每条臂上都成立，等于什么都没判。
# 这里比"增量开火"：arm 的 FAILED 集合减掉基线的 FAILED 集合，非空才算杀掉。
RC0, BASE_TALLY, BASE_FIRED = run_tests()
print(f"基线 rc={RC0} {BASE_TALLY}")
print(f"基线已红 {len(BASE_FIRED)} 条（换绑之前这是预期，不是电池的判据）")
for f in sorted(BASE_FIRED):
    print(f"              基线红: {f}")


def main() -> int:
    srcs = {a["file"]: a["file"].read_text(encoding="utf-8") for a in ARMS}
    bases = {k: sha(k) for k in srcs}
    rows = []
    for arm in ARMS:
        tgt = arm["file"]
        src = srcs[tgt]
        mutated = src
        bad = None
        for old, new in arm["reps"]:
            if src.count(old) != 1:
                bad = f"old 命中 {src.count(old)} 次"
                break
            if new and new in src:
                bad = "new 已在树上（空改写）"
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
            print(f"              开火: {f}")
    good = sum(1 for _r, v, _d, _f in rows if v in ("KILLED", "CRASH-KILL"))
    other: dict = {}
    for _r, v, _d, _f in rows:
        if v not in ("KILLED", "CRASH-KILL"):
            other[v] = other.get(v, 0) + 1
    print(f"合计 KILLED+CRASH-KILL {good} / {len(ARMS)}；其余按判决分类："
          + ("、".join(f"{k} {n}" for k, n in sorted(other.items())) or "无"))
    return 0 if good == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
