# 取到字节 ≠ 抽出正文（F-FULLTEXT-EXTRACTION，第 77 片，2026-09-27）

产物：`scripts/research/fetch_fulltexts.py`（`sniff_bytes` / `pdf_to_text` /
`MIN_FULL_TEXT_CHARS` / 新计数词）、`pyproject.toml` 的 `full` extra 与
`scripts/research/requirements.txt`（pypdf>=4）、`tests/test_research_fulltext_step.py`（+3）、
`tests/test_research_fulltext_live.py`（在线，默认跳过）、登记表 `research.fulltext_fetch` 改口、
README、`docs/audit/s77/battery77.py`。

## 一、上一片的一句假话

我在第 76 片的"未证实"里写"沙箱无出网，联网端到端未跑"。**没查就写了**。
这一轮先查：`arxiv.org` 返回 200。真跑之后暴露的不是"少一次验证"，而是能力名不副实。

## 二、在线实测把误标逼出来

| 目标 | 下载 | 第 76 片报的 | 应为 |
| --- | --- | --- | --- |
| arXiv 官方 PDF（1638905 B） | 成功 | `access=restricted` | 开放、可抽 ⇒ 抽出 **80991 字**，`open` |
| arXiv `/abs` 落地页 | 成功（服务器实际回了 PDF，sha 与上一行同为 `b852a161da…`） | `restricted` | 同上 |
| OpenAlex 给的出版商 OA PDF（3651992 B） | 成功 | `restricted` | 开放但只抽出空白 ⇒ `pdf_without_text`，**不记 open** |

`restricted` 的含义是"来源不让我拿"，这里是"我拿到了但没抽取器/抽不出文本"。
两者混成一个词，读数就会把**我们缺组件**说成**文章不开放**——方向相反的错误。

## 三、形状

- 三档结论词彼此不相容：`restricted`/`blocked`（不该拿）、
  `pdf_extractor_unavailable`/`pdf_without_text`/`pdf_extract_failed:*`（能拿、抽不出）、
  `short_or_landing_page`（抽出来的短于 `MIN_FULL_TEXT_CHARS=2000`，多半是摘要页）。
- 抽不到文本时**绝不**记 `open`，也不进全文缓存。
- pypdf 是**可选**依赖：缺它只是能力降级，不是失败。

## 四、选型（六维，结论：pypdf）

| 候选 | 功能匹配 | License | 维护 | 安全 | 质量 | 适配成本 |
| --- | --- | --- | --- | --- | --- | --- |
| pypdf 6.19 | 页级 `extract_text()`，够本用途 | BSD-3-Clause（读 wheel METADATA 的 `License-Expression` 现证） | 活跃 | 纯 Python，异常可控 | 单一入口 | 一个 import，最低 |
| PyMuPDF | 抽取质量更高 | **AGPL-3.0** ⇒ 与 Apache-2.0 项目不兼容 | 活跃 | 原生库 | 高 | 直接排除 |
| pdfminer.six | 偏底层（需自己管布局/编码） | MIT | 活跃 | 纯 Python | 高 | 成本高于所需 |
| 外部 `pdftotext` | 够 | 工具本身 GPL（进程调用可用） | — | 依赖系统 | — | 跨平台安装不可控 |

## 五、电池第一版也有活臂

U1（把 strip 判空改成永不空）第一版**存活**：我的空白 PDF 用例喂的是坏文件，
走 `pdf_extract_failed` 分支，压根没经过那道闸。改法：monkeypatch `pypdf.PdfReader`
让页返回 `"   
	  "`，控制打在它声称要防的那一行上。之后 4 臂全杀。

## 六、终局读数（由 `docs/audit/s77/terminal77.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s77/final`，报告产出于提交 `ab1389b`，主树当时 HEAD `e8febed`）：`exitcode=0`、`collected=2611`、`passed=2607`、`skipped=4`、其余终态 `{'skipped': 4}`、用时 `215.1s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s77/final`、`source_commit=a66040520139`
- **同族尺子 `doc_command_census`**：`rc=0`；权威面：90 条 argparse 路径（契约 deprecated 别名不并进权威面，由 alias_unregistered 单独核），15 个组名；只报面（live，可行动）47 处；记录性引述（只数不列名）1019 处 {'CHANGELOG.md': 82, 'docs/audit': 826, 'tests': 65, '.trae': 46}；全量扫描 1396 处，live + record = 1066 处（与减去三档判红面覆盖后的行数同构）；现状面缺陷 0 条：文档与登记表点名的命令都注册着
- **同族回归 `absence_claim_census`**：`rc=0`；能力缺失句（窄档＝判据面）：17 句 = 登记 7 + 豁免 10 + **未处置 0**；被挡在窄档外的 18 句，按轴分开：无缺失谓词 10、无能力名词 5、谈判决/谈口径 3（三档各有常驻用例钉住它非空）；具名样本 8 句、样本问题 0 条
- **两把尺子的 `--self-test`**：`rc=0/0`，合计 **32 条**合成读数全对上（条数由本次运行现数）
- **常驻用例（全文步骤与连接器映射合跑，两个不同文件）**：`pytest tests/test_research_fulltext_step.py tests/test_research_fulltext_fetcher.py tests/test_research_fulltext_live.py -q` → `48 passed in 27.73s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s77/battery77.py` → `rc=0`，合计 KILLED 4 / 其余 0
- **两档分母现读**：宽档 35 句、窄档 17 句（差的 18 句按轴分：无缺失谓词 10、无能力名词 5、谈判决/谈口径 3）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2611 条 / 214 个文件，树 214 个文件 / 2525 个 def，终态 {'passed': 2607, 'skipped': 4}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **具名样本核对**：四档共 8 条，样本问题 0 条；分档 {'no-noun': 5, 'non-claim': 3, 'narrow': 17, 'no-predicate': 10}
- **沿第 71 片那条轴的例行复算**：`external_callers` 对 `commit_approved` / `commit_snapshot` 判 HOLDS，正向对照 `record_dxf_lineage` 判 CONTRADICTED（同一函数换个名字就翻红 ⇒ 探针会开火；第一版这里用的是改口前的旧锚点，读出来是「账文脱钩」而不是「过期」，已更正）
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=e8`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `678`；**相对 tag v5.6.0** 的清单：新增 167 个、消失 9 个（这是 25 片的累计漂移，不是本片增量——本片增量看 `chore(sN): 清单再锚` 那两条提交里的文件数）
- **相对 tag 新增的被哈希文件（前 5 个）**：`assets/templates/fact.json`、`docs/architecture/project_boundary.md`、`docs/architecture/state_infrastructure.md`、`docs/architecture/state_inventory.md`、`scripts/absence_claim_census.py`
- **工作树**：`git status --porcelain` 输出 0 行

**§六 那条读数差点成了假话**：我把"跑验签 + 跑门禁"写在同一条命令里，而**在同一条命令的后面**才
`git add && git commit` 读数那一步的文档改动。于是闸看到的是脏树 ⇒ `verifier rc=4`、`gate rc=2`（7/8），
而我已经先提交了一条写着"8/8、验签 rc=0"的 commit message。顺序修正后（树干净再跑）：
`closeout_verifier rc=0`、`production_release_gate rc=0`、`"passed": true` 8 条、`release_ready: true`
——结论没变，但**先写结论再取读数**这件事本身要被记下来：
规则是"闸门必须在写盘之前跑完，读数必须在树干净之后取"，两步不能挤在同一条命令的两侧。

## 七、下一片入口

1. 在线用例今天只打 arXiv 一个域（出版商 OA 那份抽不出文本是事实，不是缺陷）；
   要扩到多域需先加"从引用元数据推可抽源"的映射（PMC/EURSCIENC 这类真文本源）。
2. 【第 79 片更正】套件构造早在第 72 片已合并；"门的规则只许一处实现"与
   "前缀级信任"由第 79 片钉成用例；narrow 样本与处置账的联动经核与 `UNACCOUNTED` 等价，不另建守卫。
