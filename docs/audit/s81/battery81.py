# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 81 片（装配步骤 PDF 的图片层）的变异电池。

每条臂都是"把这一片新增的一条牙撤掉"，必须在 `tests/test_assembly_steps_pdf.py`
上开火；Y3/Y4 两支是**撤我自己的修复**（拒绝时机、空值处置），用来证明那两条
不是顺手加的装饰。跑法：`docs/audit/s81/battery81.py`（要落盘改源文件，跑完逐臂还原）。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
PDF = ROOT / "src/aipd_os/cad/assembly_steps_pdf.py"
GEN = ROOT / "src/aipd_os/cad/assembly_steps.py"
CLI = ROOT / "src/aipd_os/cli/commands_drawing.py"
CENSUS = ROOT / "scripts/doc_reference_census.py"
PY_BIN = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_assembly_steps_pdf.py", "tests/test_cad_assembly_steps.py",
         "tests/test_doc_reference_census.py"]
# 占位图用的真 PNG（仓库自带）：Y1 要让"没图"那条路也落一个图片对象
PLACEHOLDER = "assets/golden-references/wbx1/manual_montage.png"

ARMS = [
    {"id": "Y1-absent-image-gets-a-placeholder", "file": PDF,
     "note": "没给图时塞一张占位 PNG：文档写着「没有示意图」而页里真有图 ⇒ 负向断言必须抓到",
     "reps": [
         ('    if draw_image is None:\n        line("- 本档没有装配示意图：--draw-image 未给（本仓不自动出装配图，见模块说明）")',
          '    if draw_image is None:\n'
          '        c.drawImage("' + PLACEHOLDER + '", MARGIN + 3 * mm, y - 20 * mm,\n'
          '                    width=40 * mm, height=20 * mm)\n'
          '        line("- 本档没有装配示意图：--draw-image 未给（本仓不自动出装配图，见模块说明）")')]},
    {"id": "Y2-document-stops-stating-the-absence", "file": PDF,
     "note": "撤掉「本档没有装配示意图」那一行 ⇒ 空白页会被读成「有但没显示」",
     "reps": [
         ('    if draw_image is None:\n        line("- 本档没有装配示意图：--draw-image 未给（本仓不自动出装配图，见模块说明）")',
          '    if False:\n        line("- 本档没有装配示意图：--draw-image 未给（本仓不自动出装配图，见模块说明）")')]},
    {"id": "Y3-rejection-moved-back-after-the-write", "file": GEN,
     "note": "把参数拒绝挪回 Markdown 落盘之后（第 81 片第一版的形状）⇒ 被拒的调用留下孤儿 .md",
     "reps": [
         ('    # 参数形状先判，判完才动盘：这条 raise 原先写在 Markdown 落盘之后，\n'
          '    # 于是"只给图不给 PDF"会留下一个没有 PDF 的孤儿 .md（同一条拒绝路径的另一半\n'
          '    # ——图文件不存在——是在 CLI 里落盘前就 rc=2 的，两条路径原本该同一个形状）。\n'
          '    if draw_image is not None and pdf_path is None:\n'
          '        raise ValueError("--draw-image 只在同时出 PDF 时有意义（Markdown 版式不嵌图）")\n\n',
          ''),
         ('    else:\n        pdf = None\n',
          '    else:\n        pdf = None\n\n'
          '    if draw_image is not None and pdf is None:\n'
          '        raise ValueError("--draw-image 只在同时出 PDF 时有意义（Markdown 版式不嵌图）")\n')]},
    {"id": "Y4-cli-treats-blank-flag-as-not-given", "file": CLI,
     "note": "空值按「没给」处理 ⇒ 作者要的图被静默丢掉，且照样出文档",
     "reps": [
         ('    if draw_image is not None and not str(draw_image).strip():\n'
          '        # 与上面 --db/--bom 那条不同：那里"空值"就是没给，这里空值是"给了但没给对"。\n'
          '        # 按没给处理等于把作者要的图静默丢掉，本仓对这一类一律当场拒。\n'
          '        print("--draw-image 给了空值：要么给图片路径，要么别给这个旗子")\n'
          '        return 2\n'
          '    if draw_image is not None and not Path(draw_image).is_file():',
          '    if draw_image and not Path(draw_image).is_file():')]},
    {"id": "Y5-image-key-omitted-not-none", "file": PDF,
     "note": "没图时省掉 `image` 键 ⇒ 读者分不出「没要图」与「要了但没落地」（第 80 片对 pdf 键同一条纪律）",
     "reps": [('    out["image"] = image_info',
               '    if image_info:\n        out["image"] = image_info')]},
    {"id": "Y6-pixel-reading-fabricated", "file": PDF,
     "note": "证据里的像素写成常量 ⇒ 侧车读数与图本身脱钩",
     "reps": [('"pixels": [int(iw), int(ih)],', '"pixels": [0, 0],')]},
    {"id": "Y7-image-sha-not-the-real-file", "file": PDF,
     "note": "图的 sha256 不来自文件字节 ⇒ 「图与 sha256 一起进证据」这句话成空话",
     "reps": [('img_sha = hashlib.sha256(img_path.read_bytes()).hexdigest()',
               'img_sha = "0" * 64')]},
    {"id": "Y8-stale-boundary-item-put-back", "file": GEN,
     "note": "把「PDF/图框版式」放回 not_covered（第 80 片之后的假话）⇒ 反转断言必须有牙",
     "reps": [('NOT_COVERED = ["维护指引", "工时与工序成本", "扭矩或拧紧值", "检验点与点检项"]',
               'NOT_COVERED = ["维护指引", "工时与工序成本", "扭矩或拧紧值", "PDF/图框版式"]')]},
    {"id": "Y9-frame-keeps-its-own-copy-of-the-boundary", "file": PDF,
     "note": "标题栏改回自己写一句边界 ⇒ 同一事实两处各写一遍，谁改了另一边都不会红",
     "reps": [('                 "本文档不承载：" + "、".join(not_covered)',
               '                 "本文档不承载：工时、扭矩值、检验点、维护指引"')]},
    {"id": "Y10-census-sort-lost-its-total-order", "file": CENSUS,
     "note": "撤掉普查的全序 key ⇒ 同一目标既裸引又带行号引时整把尺子连同 8 条常驻用例崩在 TypeError",
     "reps": [('    history_defects = sorted({r.key() for r in refs\n'
               '                              if r.klass in defect_kinds and _is_history(r.doc)},\n'
               '                             key=_defect_sort_key)',
               '    history_defects = sorted({r.key() for r in refs\n'
               '                              if r.klass in defect_kinds and _is_history(r.doc)})')]},
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def run_tests():
    proc = subprocess.run([PY_BIN, "-m", "pytest", *TESTS, "-q", "--no-header", "-rf",
                           "-p", "no:cacheprovider"], capture_output=True,
                          text=True, cwd=str(ROOT), timeout=900)
    out = proc.stdout + proc.stderr
    lines = out.splitlines()
    tally = [ln for ln in lines if "passed" in ln or "failed" in ln][-1:]
    fired = [ln[len("FAILED "):] for ln in lines if ln.startswith("FAILED ")]
    return proc.returncode, (tally[0][:60] if tally else ""), fired


def main():
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
            # new == "" 是"整段删掉"，合法；只有非空的 new 才要判它是否已在树上（空改写永远绿）
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
            rc, line, fired = run_tests()
        finally:
            tgt.write_text(src, encoding="utf-8")
            assert sha(tgt) == bases[tgt], "还原失败"
        rows.append((arm["id"], "KILLED" if rc != 0 else "SURVIVED", line, fired))
    for k, v in bases.items():
        print(f"基线 {k.name} sha={v}")
    for rid, v, d, fired in rows:
        print(f"[{v:11}] {rid}  {d[:70]}")
        for f in fired:
            print(f"              开火: {f}")
    killed = sum(1 for _r, v, _d, _f in rows if v == "KILLED")
    print(f"合计 KILLED {killed} / {len(ARMS)}，其余 {len(rows) - killed}")
    return 0 if killed == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
