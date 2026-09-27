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
    {"id": "Y13-pdf-target-is-a-directory-untouched", "file": GEN,
     "note": "撤掉「--pdf 是目录」这条前置拒绝 ⇒ 又回到「先写 Markdown 再在 canvas 处炸」",
     "reps": [('    if pdf_path is not None and Path(pdf_path).is_dir():\n'
               '        # 同一格的另一半：PDF 目标是个目录时，reportlab 要到 canvas 创建才炸，\n'
               '        # 那时 Markdown 已经落盘 —— 与上面四条不同源，判的是"能不能写"而不是"内容对不对"。\n'
               '        raise ValueError(f"--pdf 要的是一个文件路径，它现在是个目录：{pdf_path}")\n', '')]},
    {"id": "Y14-bomb-error-escapes-the-rejection", "file": PDF,
     "note": "从 except 里摘掉 DecompressionBombError ⇒ 超大图绕过 ValueError，CLI 变成 traceback",
     "reps": [('    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:',
               '    except (UnidentifiedImageError, OSError) as exc:')
     ]},
    {"id": "Y15-placed-size-not-recorded", "file": PDF,
     "note": "证据里去掉实际排版尺寸 ⇒ 一张 1×1 的图被缩成 0.35 mm 小点，读者只看 pixels 会被误导",
     "reps": [('                    "placed_mm": [round(draw_w / mm, 1), round(draw_h / mm, 1)]}',
               '                    "placed_mm": [0.0, 0.0]}')
     ]},
    {"id": "Y16-cli-reads-blank-pdf-as-no-pdf", "file": CLI,
     "reps": [('    if pdf_arg is not None and not str(pdf_arg).strip():\n        # 与 --draw-image 的空值同一条纪律：不给 --pdf 就不出 PDF（pdf_path=None，合法），\n        # 给了 --pdf "" 是"要 PDF 但路径写错了"，静默读成"没要"就丢掉了作者的请求。\n        print("--pdf 给了空值：不给这个旗子就是不出 PDF；要出就给路径（裸 --pdf 走同名 .pdf）")\n        return 2\n', '')],
     "note": "撤掉 --pdf 空值检查 ⇒ 只给 `--pdf \"\"` 照样落 Markdown+侧车、退码是清单自己的读数（HEAD 6ca9c41 实测 rc=4），不是拒绝专用的 rc=2 ⇒ 作者的请求被静默丢掉"},
    {"id": "Y17-check-order-lets-the-pairing-line-win", "file": CLI,
     "reps": [('    pdf_arg = getattr(args, "pdf", None)\n    if pdf_arg is not None and not str(pdf_arg).strip():\n        # 与 --draw-image 的空值同一条纪律：不给 --pdf 就不出 PDF（pdf_path=None，合法），\n        # 给了 --pdf "" 是"要 PDF 但路径写错了"，静默读成"没要"就丢掉了作者的请求。\n        print("--pdf 给了空值：不给这个旗子就是不出 PDF；要出就给路径（裸 --pdf 走同名 .pdf）")\n        return 2\n    if draw_image is not None and not getattr(args, "pdf", None):\n        print("--draw-image 要和 --pdf 一起给：Markdown 版式不嵌图，"\n              "只给图就等于把这张图丢掉")\n        return 2\n', '    if draw_image is not None and not getattr(args, "pdf", None):\n        print("--draw-image 要和 --pdf 一起给：Markdown 版式不嵌图，"\n              "只给图就等于把这张图丢掉")\n        return 2\n    pdf_arg = getattr(args, "pdf", None)\n    if pdf_arg is not None and not str(pdf_arg).strip():\n        # 与 --draw-image 的空值同一条纪律：不给 --pdf 就不出 PDF（pdf_path=None，合法），\n        # 给了 --pdf "" 是"要 PDF 但路径写错了"，静默读成"没要"就丢掉了作者的请求。\n        print("--pdf 给了空值：不给这个旗子就是不出 PDF；要出就给路径（裸 --pdf 走同名 .pdf）")\n        return 2\n')],
     "note": "把 ③『只给图不给 --pdf』挪回 ⑥ 之前 ⇒ 叠用 `--pdf \"\"` + 图时读者拿到的是"                    "『要和 --pdf 一起给』，被支去补一个已经写过的旗子；退码两条都是 2，"                    "所以只有话术用例抓得到"},
    {"id": "Y11-library-stops-probing-the-image-bytes", "file": GEN,
     "note": "撤掉落盘前的图片可读性校验（第 81 片补的第四条拒绝）⇒ 坏图又变成「写完 .md 才炸 PIL 栈」",
     "reps": [('    if draw_image is not None:\n'
               '        # 第四条：文件在但内容不是可读图片（文本冒充 .png、零字节、截断、超大图）。\n'
               '        # 判据与排版侧同一个来源 `read_image_size`，坏图同样必须在任何字节落盘之前被拒。\n'
               '        from aipd_os.cad.assembly_steps_pdf import read_image_size\n\n'
               '        read_image_size(draw_image)\n', '')]},
    {"id": "Y12-cli-lets-the-library-word-the-rejection", "file": CLI,
     "note": "撤掉 CLI 侧的图片校验 ⇒ 坏图仍被拒，但话被套成「装配步骤声明不合法」，读者会去改 manifest",
     "reps": [('    if draw_image is not None:\n'
               '        # 文件在不等于图能用：内容坏（文本冒充 .png、零字节、截断）也要在这里就 rc=2，\n'
               '        # 判据与库侧同一个来源，不许两边各写一遍。\n'
               '        from aipd_os.cad.assembly_steps_pdf import read_image_size\n\n'
               '        try:\n'
               '            read_image_size(draw_image)\n'
               '        except ValueError as exc:\n'
               '            print(str(exc))\n'
               '            return 2\n', '')]},
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
    # "其余"必须分类抄：BAD-MUTATION/BAD-ANCHOR 是电池自己的问题，不是"臂存活"——
    # 混成一格会把"这条变异没落地"读成"这条牙没人守"。
    other: dict[str, int] = {}
    for _r, v, _d, _f in rows:
        if v != "KILLED":
            other[v] = other.get(v, 0) + 1
    print(f"合计 KILLED {killed} / {len(ARMS)}；其余按判决分类："
          + ("、".join(f"{k} {n}" for k, n in sorted(other.items())) or "无"))
    return 0 if killed == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
