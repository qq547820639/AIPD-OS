# 装配步骤的 PDF 版式与图框（F-ASSEMBLY-PDF，第 80 片，2026-09-27）

产物：`src/aipd_os/cad/assembly_steps_pdf.py`、`assembly_steps.generate_assembly_steps(pdf_path=…)`、
`--pdf` 旗子（`cli/main.py` + `commands_drawing.py`）、证据侧车 `pdf` 字段、
`tests/test_assembly_steps_pdf.py`（6 条）、README、登记表 `cad.assembly_instructions`、
账本缺席式→存在式互换、`docs/audit/s80/battery80.py`。

## 一、为什么用内置 CID 字体

`STSong-Light` 是 reportlab 自带的 Adobe CJK CID 字体：**不需要字体文件**，
不赌本机装了什么中文字体（手册那条 PNG 路要 `aipd_os/layout/fonts.py` 找本机字体文件）。
更关键的是它输出的是**文字**而不是像素：实测 pypdf 能读回
"支架贴合基面 / 压板压在支架上并拧至规定扭矩"，所以验收可以是"解码回来逐条对"，
而不是"文件存在 + 字节数够大"。这也把它和手册的 PNG 拼 PDF 区分开：
那条要的是逐页渲染图，这条要的是可检索、可复制、能进打印流程的作业文件。

## 二、只有一份投影

PDF 不解析 manifest：`generate_assembly_steps` 把 `columns / table / plan` 原样交给渲染器。
常驻用例 `test_pdf_and_markdown_come_from_one_projection` 把这条变成断言——
从 Markdown 里解析出每条步骤动作，要求在 PDF 解码文本里逐条出现。
两份投影各写一遍时最坏的错不是格式不同，而是**其中一份少一行还两边都自洽**。

## 三、图框是每页都画的

`test_frame_and_page_numbers_appear_on_every_page` 造 14 步长文档逼出多页，
逐页断言 `第 N 页` 存在：第二页没页码就等于版式在长内容下悄悄失效。

## 四、判据的连锁（这一片是被自己的机器逼着改口的）

登记表那句一改，第 67 片的缺席式登记当场 `CLAIM_TEXT_ABSENT`；换成存在式后第一版又用错档
（`identifier` 是缺席极性，符号被找到 = 句子过期 ⇒ 判成 CONTRADICTED），
改成 `external_callers + expect=present` 并把锚点取在**消费方调用点**才对上。
两次都是判据在替我说话，不是我改了读数。

## 五、终局读数（占位）

## 六、下一片入口

1. PDF 版式没有插图（图纸页/爆炸图占位）；要接需要把 2D 图纸 PNG 作为图片层嵌入，
   并保留文字层——那是另一片。
2. 第 79 片留的两件：其余开放来源主机的路径级收紧、`rerun_for_rework` 多轮失败/退避形状。
