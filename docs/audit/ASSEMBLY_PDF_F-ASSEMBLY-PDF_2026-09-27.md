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

## 五、终局读数（由 `docs/audit/s80/terminal80.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s80/final`，报告产出于提交 `8160e17`，主树当时 HEAD `4a2d9cf`）：`exitcode=0`、`collected=2627`、`passed=2622`、`skipped=5`、其余终态 `{'skipped': 5}`、用时 `250.8s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s80/final`、`source_commit=a66040520139`
- **同族尺子 `doc_command_census`**：`rc=0`；权威面：90 条 argparse 路径（契约 deprecated 别名不并进权威面，由 alias_unregistered 单独核），15 个组名；只报面（live，可行动）47 处；记录性引述（只数不列名）1022 处 {'CHANGELOG.md': 82, 'docs/audit': 829, 'tests': 65, '.trae': 46}；全量扫描 1399 处，live + record = 1069 处（与减去三档判红面覆盖后的行数同构）；现状面缺陷 0 条：文档与登记表点名的命令都注册着
- **同族回归 `absence_claim_census`**：`rc=0`；能力缺失句（窄档＝判据面）：16 句 = 登记 6 + 豁免 10 + **未处置 0**；被挡在窄档外的 18 句，按轴分开：无缺失谓词 10、无能力名词 5、谈判决/谈口径 3（三档各有常驻用例钉住它非空）；具名样本 8 句、样本问题 0 条
- **两把尺子的 `--self-test`**：`rc=0/0`，合计 **32 条**合成读数全对上（条数由本次运行现数）
- **常驻用例（全文步骤与连接器映射合跑，两个不同文件）**：`pytest tests/test_assembly_steps_pdf.py tests/test_cad_assembly_steps.py tests/test_research_fulltext_live.py -q` → `48 passed in 47.91s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s80/battery80.py` → `rc=0`，合计 KILLED 5 / 其余 0
- **两档分母现读**：宽档 34 句、窄档 16 句（差的 18 句按轴分：无缺失谓词 10、无能力名词 5、谈判决/谈口径 3）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2627 条 / 215 个文件，树 215 个文件 / 2541 个 def，终态 {'passed': 2622, 'skipped': 5}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **具名样本核对**：四档共 8 条，样本问题 0 条；分档 {'no-noun': 5, 'non-claim': 3, 'narrow': 16, 'no-predicate': 10}
- **沿第 71 片那条轴的例行复算**：`external_callers` 对 `commit_approved` / `commit_snapshot` 判 HOLDS，正向对照 `record_dxf_lineage` 判 CONTRADICTED（同一函数换个名字就翻红 ⇒ 探针会开火；第一版这里用的是改口前的旧锚点，读出来是「账文脱钩」而不是「过期」，已更正）
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=4a`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `680`；**相对 tag v5.6.0** 的清单：新增 169 个、消失 9 个（这是 25 片的累计漂移，不是本片增量——本片增量看 `chore(sN): 清单再锚` 那两条提交里的文件数）
- **相对 tag 新增的被哈希文件（前 5 个）**：`assets/templates/fact.json`、`docs/architecture/project_boundary.md`、`docs/architecture/state_infrastructure.md`、`docs/architecture/state_inventory.md`、`scripts/absence_claim_census.py`
- **工作树**：`git status --porcelain` 输出 0 行

## 六、下一片入口

1. PDF 版式没有插图（图纸页/爆炸图占位）；要接需要把 2D 图纸 PNG 作为图片层嵌入，
   并保留文字层——那是另一片。
2. 第 79 片留的两件：其余开放来源主机的路径级收紧、`rerun_for_rework` 多轮失败/退避形状。
