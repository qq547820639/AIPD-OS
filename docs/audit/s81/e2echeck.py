"""正例端到端：真 CLI 出 md+pdf+侧车，再用 pypdf 独立解码回来核。

不信 CLI 自报：图片对象数、可抽取文本、`pdf.image` 的 sha/字节数都独立重算一遍。
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

R = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
P = Path("/Volumes/Extra/CodeProj/AI全链路自研/tmp/s81/e2e")
sys.path.insert(0, str(R / "src"))
from PIL import Image  # noqa: E402

big = P / "assy.png"
if not big.is_file():
    Image.new("RGB", (1140, 1728), (250, 250, 250)).save(big)
full = json.loads((P / "assy_full.json").read_text(encoding="utf-8"))
(P / "assy_full2.json").write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")

for f in list(P.glob("fin.*")):
    f.unlink()
cp = subprocess.run([sys.executable, "-m", "aipd_os.cli.main", "drawing", "assembly-steps",
                     "--manifest", str(P / "assy_full2.json"), "--out", str(P / "fin.md"),
                     "--part", "ASSY-FIN", "--pdf", str(P / "fin.pdf"),
                     "--draw-image", str(big)],
                    capture_output=True, text=True, cwd=str(R), timeout=600)
print("CLI rc =", cp.returncode)
print("CLI 自报 =", [x for x in cp.stdout.splitlines() if x.strip()][:3])

from pypdf import PdfReader  # noqa: E402

pdf = P / "fin.pdf"
rd = PdfReader(str(pdf))
per_page = [len(list(pg.images)) for pg in rd.pages]
text = "\n".join((pg.extract_text() or "") for pg in rd.pages)
ev = json.loads((P / "fin.md.evidence.json").read_text(encoding="utf-8"))
raw = big.read_bytes()
info = Image.open(big); size = list(info.size); info.close()
img_ev = ev["pdf"]["image"]

checks = [
    ("每页图片对象", per_page, [1, 0]),
    ("图注在文本里", "装配示意图（由作者提供）" in text, True),
    ("图文件名在文本里", "assy.png" in text, True),
    ("步骤原文在文本里", "支架贴合基面" in text, True),
    ("本文档不承载在文本里", "本文档不承载" in text, True),
    ("证据像素=源像素", img_ev["pixels"], size),
    ("证据字节=文件大小", img_ev["bytes"], len(raw)),
    ("证据 sha=文件 sha", img_ev["sha256"], hashlib.sha256(raw).hexdigest()),
    ("证据 placed_mm", img_ev.get("placed_mm"), None),
]
bad = []
for name, got, want in checks:
    ok = "(不判，只抄)" if want is None else ("一致" if got == want else "不一致")
    print(f"  {name:22} {got!r}  {ok}")
    if want is not None and got != want:
        bad.append(name)
print("页数 =", len(rd.pages), "| not_covered =", ev["not_covered"])
print("判定：", "正例端到端全部对上" if not bad else f"有不对上的格 ⇒ {bad}")
sys.exit(1 if bad else 0)
