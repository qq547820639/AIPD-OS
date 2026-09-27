# 信任降到主机 + 路径前缀级（F-PREFIX-SCOPED-TRUST，第 79 片，2026-09-27）

产物：`src/aipd_os/research/fulltext.py`（`OPEN_ACCESS_PREFIXES` + 重写 `is_open_access_url`，
两个 Europe PMC 主机移出主机级表）、`src/aipd_os/research/__init__.py` 导出、
`tests/test_research_fulltext_step.py`（前缀级双向 + 门规则单点）、`tests/test_closeout_verifier.py`
所在的结构守卫保持、README、登记表该行限制句、两篇旧文档的队列更正、`docs/audit/s79/battery79.py`（4 臂杀 4 活 0：W1 前缀换成不存在的、W2 退回主机级、W3 不查前缀表、W4 把门的规则抄第二份）。

## 一、为什么"注释 + 自律"不算边界

第 78 片的信任扩张是这么写的：加两个主机进 `OPEN_ACCESS_DOMAINS`，注释说明"我们只构造
`/webservices/rest/PMC…/fullTextXML`"，另配一条用例钉"只构造这一种 URL"。
问题是那条用例钉的是**我们**的行为，不是**判定**的边界：任何人后来传一个
`https://www.ebi.ac.uk/anything` 进来都会被判开放。EBI 上还有 UniProt、ENA 等服务，
它们的路径不是全文端点。机制版本是把边界写进判定函数。

## 二、双向证据

| URL | 第 78 片 | 第 79 片 |
| --- | --- | --- |
| `www.ebi.ac.uk/europepmc/webservices/rest/PMC12900525/fullTextXML` | open | open |
| `europepmc.org/articles/PMC8783953` | open | open |
| `www.ebi.ac.uk/` | open | **不开放** |
| `www.ebi.ac.uk/some/other/service` | open | **不开放** |
| `europepmc.org/reader/PMC1` | open | **不开放** |
| `evil.test/ebi.ac.uk/...` | 不开放 | 不开放 |

## 三、两条队列的处置（一条更正、一条判定不做）

- "合并 `rerun_for_rework` 与 `run_supervisor` 的口子"：查证后第 72 片已完成，
  s77/s78 两篇记录写错了 ⇒ 原地更正，并新增门规则的单点用例（真正可能分叉的是规则，不是调用）。
- "narrow 具名样本与处置账的直接联动"：与 `UNACCOUNTED` 等价，做了就是永不开火的死闸 ⇒ 不做，理由写在这里。

## 四、终局读数（由 `docs/audit/s79/terminal79.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s79/final`，报告产出于提交 `4f0779c`，主树当时 HEAD `86ac866`）：`exitcode=0`、`collected=2621`、`passed=2616`、`skipped=5`、其余终态 `{'skipped': 5}`、用时 `196.9s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s79/final`、`source_commit=a66040520139`
- **同族尺子 `doc_command_census`**：`rc=0`；权威面：90 条 argparse 路径（契约 deprecated 别名不并进权威面，由 alias_unregistered 单独核），15 个组名；只报面（live，可行动）47 处；记录性引述（只数不列名）1021 处 {'CHANGELOG.md': 82, 'docs/audit': 828, 'tests': 65, '.trae': 46}；全量扫描 1398 处，live + record = 1068 处（与减去三档判红面覆盖后的行数同构）；现状面缺陷 0 条：文档与登记表点名的命令都注册着
- **同族回归 `absence_claim_census`**：`rc=0`；能力缺失句（窄档＝判据面）：17 句 = 登记 7 + 豁免 10 + **未处置 0**；被挡在窄档外的 18 句，按轴分开：无缺失谓词 10、无能力名词 5、谈判决/谈口径 3（三档各有常驻用例钉住它非空）；具名样本 8 句、样本问题 0 条
- **两把尺子的 `--self-test`**：`rc=0/0`，合计 **32 条**合成读数全对上（条数由本次运行现数）
- **常驻用例（全文步骤与连接器映射合跑，两个不同文件）**：`pytest tests/test_research_fulltext_step.py tests/test_research_fulltext_fetcher.py tests/test_research_fulltext_live.py -q` → `48 passed in 37.79s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s79/battery79.py` → `rc=0`，合计 KILLED 4 / 其余 0
- **两档分母现读**：宽档 35 句、窄档 17 句（差的 18 句按轴分：无缺失谓词 10、无能力名词 5、谈判决/谈口径 3）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2621 条 / 214 个文件，树 214 个文件 / 2535 个 def，终态 {'passed': 2616, 'skipped': 5}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **具名样本核对**：四档共 8 条，样本问题 0 条；分档 {'no-noun': 5, 'non-claim': 3, 'narrow': 17, 'no-predicate': 10}
- **沿第 71 片那条轴的例行复算**：`external_callers` 对 `commit_approved` / `commit_snapshot` 判 HOLDS，正向对照 `record_dxf_lineage` 判 CONTRADICTED（同一函数换个名字就翻红 ⇒ 探针会开火；第一版这里用的是改口前的旧锚点，读出来是「账文脱钩」而不是「过期」，已更正）
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=86`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `678`；**相对 tag v5.6.0** 的清单：新增 167 个、消失 9 个（这是 25 片的累计漂移，不是本片增量——本片增量看 `chore(sN): 清单再锚` 那两条提交里的文件数）
- **相对 tag 新增的被哈希文件（前 5 个）**：`assets/templates/fact.json`、`docs/architecture/project_boundary.md`、`docs/architecture/state_infrastructure.md`、`docs/architecture/state_inventory.md`、`scripts/absence_claim_census.py`
- **工作树**：`git status --porcelain` 输出 0 行

## 五、下一片入口

1. 多域可抽性：出版商自有 OA 站点仍以 PDF 为主；要做"从引用元数据推真文本源"的第二个域
   （Europe PMC 之外，如 CORE / DOAB 的主机也按前缀接进来）。
2. `rerun_for_rework` 目前只重跑一次；连续失败的重试上限由引擎管，未验多轮形状。
