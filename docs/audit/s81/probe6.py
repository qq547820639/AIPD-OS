"""六道拒绝规则走真 CLI，逐条记 rc / 盘上残留 / 首行 / 有没有栈。

与上一版 probe 的差别：多了 ⑥ `--pdf ""`，并把 ⑤ `--pdf <目录>` 也按同一形状记。
每条各起一个进程（同一棵树、同一个清单），跑前删干净同名产物，跑后按 glob 数残留——
"没落盘"必须是数出来的，不是从退码推的。
"""
import json
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[3]
P = Path("/Volumes/Extra/CodeProj/AI全链路自研/tmp/s81/e2e")
sys.path.insert(0, str(R / "src"))
from PIL import Image  # noqa: E402

(P / "支架.step").write_bytes(b"ISO-10303-21;HEADER;")
(P / "压板.step").write_bytes(b"ISO-10303-21;HEADER;")
(P / "assy.json").write_text(json.dumps({
    "parts": [{"name": "支架", "balloon": 1, "step": "支架.step"},
              {"name": "压板", "balloon": 2, "step": "压板.step"}],
    "assembly_steps": [{"no": 1, "action": "支架贴合基面", "balloons": [1]}]},
    ensure_ascii=False), encoding="utf-8")
Image.new("RGB", (320, 200), (240, 240, 240)).save(P / "good.png")
(P / "fake.png").write_text("文本冒充\n", encoding="utf-8")
(P / "zero.png").write_bytes(b"")
(P / "trunc.png").write_bytes((P / "good.png").read_bytes()[40:])
(P / "adir").mkdir(exist_ok=True)


def cli(tag, extra):
    for f in list(P.glob(f"{tag}.*")):
        f.unlink()
    base = ["drawing", "assembly-steps", "--manifest", str(P / "assy.json"),
            "--out", str(P / f"{tag}.md"), "--part", f"ASSY-{tag}"]
    cp = subprocess.run([sys.executable, "-m", "aipd_os.cli.main"] + base + extra,
                        capture_output=True, text=True, cwd=str(R), timeout=300)
    left = sorted(f.name for f in P.glob(f"{tag}.*"))
    first = [x for x in cp.stdout.splitlines() if x.strip()][:1]
    print(f"  [{tag}] rc={cp.returncode} 残留={left or '无'} 首行={first} "
          f"栈={'Traceback' in cp.stderr}")
    return cp.returncode, left, first


rows = [
    ("r1", "① 图文件不存在", ["--pdf", str(P / "p1.pdf"), "--draw-image", str(P / "nope.png")]),
    ("r2", "② --draw-image 空值", ["--pdf", str(P / "p2.pdf"), "--draw-image", ""]),
    ("r3", "③ 只给图不给 --pdf", ["--draw-image", str(P / "good.png")]),
    ("r4a", "④a 文本冒充 PNG", ["--pdf", str(P / "p4a.pdf"), "--draw-image", str(P / "fake.png")]),
    ("r4b", "④b 零字节", ["--pdf", str(P / "p4b.pdf"), "--draw-image", str(P / "zero.png")]),
    ("r4c", "④c 截断 PNG", ["--pdf", str(P / "p4c.pdf"), "--draw-image", str(P / "trunc.png")]),
    ("r5", "⑤ --pdf 是目录", ["--pdf", str(P / "adir"), "--draw-image", str(P / "good.png")]),
    ("r6", "⑥ --pdf 空值（只给旗子）", ["--pdf", ""]),
    ("r6b", "⑥' --pdf 空值 + 同时给图（看先撞上哪条）",
     ["--pdf", "", "--draw-image", str(P / "good.png")]),
    ("ok", "正例 全覆盖清单+真图", None),
]

collide = []
print("===== 六道规则 × 真 CLI =====")
bad = []
for tag, label, extra in rows:
    if extra is None:
        # 正例：全覆盖清单（两个球标都进步骤），必须 rc=0 且三份产物都在
        full = json.loads((P / "assy.json").read_text(encoding="utf-8"))
        full["assembly_steps"][0]["balloons"] = [1, 2]
        (P / "assy_full.json").write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")
        extra = ["--pdf", str(P / "ok.pdf"), "--draw-image", str(P / "good.png")]
        for f in list(P.glob("ok.*")):
            f.unlink()
        base = ["drawing", "assembly-steps", "--manifest", str(P / "assy_full.json"),
                "--out", str(P / "ok.md"), "--part", "ASSY-OK"]
        cp = subprocess.run([sys.executable, "-m", "aipd_os.cli.main"] + base + extra,
                            capture_output=True, text=True, cwd=str(R), timeout=300)
        left = sorted(f.name for f in P.glob("ok.*"))
        print(f"  [正例] rc={cp.returncode} 残留={left} 首行="
              f"{[x for x in cp.stdout.splitlines() if x.strip()][:1]}")
        if cp.returncode != 0 or len(left) != 3:
            bad.append(f"正例 rc={cp.returncode} 残留={left}")
        continue
    rc, left, first = cli(tag, extra)
    if rc != 2 or left:
        bad.append(f"{label} rc={rc} 残留={left}")
    if tag == "r6b" and first and "给了空值" in first[0]:
        collide.append(label)  # 若哪天先撞上 ⑥ 的话，这条记录要改

print("r6b 先撞上 ⑥ 而非 ③ 的次数：", len(collide))
print("判定：", "六道全部 rc=2 且零残留、正例三份产物齐" if not bad else f"有异常 ⇒ {bad}")
sys.exit(1 if bad else 0)
