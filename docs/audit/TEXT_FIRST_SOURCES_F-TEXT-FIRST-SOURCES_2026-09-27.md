# 真文本源优先，策略判定挪到下载之前（F-TEXT-FIRST-SOURCES，第 78 片，2026-09-27）

产物：`scripts/research/fetch_fulltexts.py`（`_pmcid_of`、PMC 优先的 `pick_target`、
`sniff_bytes` 认 XML、`xml_to_text`、下载前的 `classify_access`、`not_open_*` 结论词、
`force_fetch`）、`scripts/research/search_papers_by_open_alex.py`（带出 `ids.pmc`）、
`src/aipd_os/research/fulltext.py`（白名单加 Europe PMC 两个主机 + 边界注释）、
`tests/test_research_fulltext_step.py`（+5）、`tests/test_research_fulltext_live.py`（+1）、
登记表与 README、矩阵重生成。

## 一、先探再动手

Europe PMC REST `/{PMCID}/fullTextXML`：OA 条目 200 + `application/xml`（JATS 正文），
非 OA 的 PMC8581587 → 500，带版本号写法 → 404。结论：这条路径**不需要 PDF 抽取器**就能拿到文本，
所以它应当排在 PDF 直链之前，而不是当备选。

## 二、"没正文"的一半原因是连接器丢了字段

OpenAlex 的 `ids.pmc` 一直在返回，第 76/77 片的映射没取。没有 PMC id 就只能看见 PDF 副本，
于是撞上第 77 片那个死路（能下载、被许可、没有抽取器 ⇒ 零正文）。

## 三、策略判定前移

旧顺序：下载 → 交给库分类 → 库判 restricted 时**根本不调 getter**，于是我们已经白下一次，
而 `outcome` 还留着 `extracted_xml`。新顺序：先 `classify_access()`，不开放就不发起请求；
真去取（`force_fetch`）而结果仍不开放时，结论词写成 `not_open_restricted`。

## 四、白名单的边界

加进 `OPEN_ACCESS_DOMAINS` 的是 `ebi.ac.uk` 与 `europepmc.org`，注释写明这份信任的依据
（Europe PMC 只对 OA 收藏返回全文）以及"我们只构造 `/webservices/rest/{PMCID}/fullTextXML`
这一种 URL"；两条常驻用例分别钉住"只构造这一种路径"和"没有顺手放进别的站"。

## 五、在线读数（`AIPD_RESEARCH_INTEGRATION=1`）

| 目标 | kind | outcome | chars | access |
| --- | --- | --- | --- | --- |
| PMC12900525 JATS | xml | extracted_xml | 37970 | open |
| arXiv 2401.04398 PDF | pdf | extracted_pdf | 80991 | open |
| 由 europepmc 链接反推 PMC8783953 | xml | extracted_xml | 16136 | open |

## 五之二、电池第一版也抓到一条不结实的控制

V3（把策略判定改成"永远开放"）第一版**存活**：我的"策略前移"用例喂的是**根本没有开放副本**的记录，
那种情况在 `pick_target` 就返回空 URL 了，压根走不到策略判定那一行。
补一条"挑出了 URL 但域名不在白名单"的用例（断言 `calls == []`）之后 V3 才死。
**控制要打在它声称要防的那一行上**——这条规矩这一轮又用了一次（前一例是第 77 片的 strip 闸）。
最终 `docs/audit/s78/battery78.py` **6 臂杀 6 活 0**。

## 六、终局读数（由 `docs/audit/s78/terminal78.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s78/final`，报告产出于提交 `f97997f`，主树当时 HEAD `fb384cf`）：`exitcode=0`、`collected=2620`、`passed=2615`、`skipped=5`、其余终态 `{'skipped': 5}`、用时 `229.2s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s78/final`、`source_commit=a66040520139`
- **本片主角之一 `doc_command_census`**：`rc=0`；权威面：90 条 argparse 路径（契约 deprecated 别名不并进权威面，由 alias_unregistered 单独核），15 个组名；只报面（live，可行动）47 处；记录性引述（只数不列名）1020 处 {'CHANGELOG.md': 82, 'docs/audit': 827, 'tests': 65, '.trae': 46}；全量扫描 1397 处，live + record = 1067 处（与减去三档判红面覆盖后的行数同构）；现状面缺陷 0 条：文档与登记表点名的命令都注册着
- **同族回归 `absence_claim_census`**：`rc=0`；能力缺失句（窄档＝判据面）：17 句 = 登记 7 + 豁免 10 + **未处置 0**；被挡在窄档外的 18 句，按轴分开：无缺失谓词 10、无能力名词 5、谈判决/谈口径 3（三档各有常驻用例钉住它非空）；具名样本 8 句、样本问题 0 条
- **两把尺子的 `--self-test`**：`rc=0/0`，合计 **32 条**合成读数全对上（条数由本次运行现数）
- **常驻用例（全文步骤与连接器映射合跑，两个不同文件）**：`pytest tests/test_research_fulltext_step.py tests/test_research_fulltext_fetcher.py tests/test_research_fulltext_live.py -q` → `48 passed in 27.66s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s78/battery78.py` → `rc=0`，合计 KILLED 6 / 其余 0
- **两档分母现读**：宽档 35 句、窄档 17 句（差的 18 句按轴分：无缺失谓词 10、无能力名词 5、谈判决/谈口径 3）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2620 条 / 214 个文件，树 214 个文件 / 2534 个 def，终态 {'passed': 2615, 'skipped': 5}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **具名样本核对**：四档共 8 条，样本问题 0 条；分档 {'no-noun': 5, 'non-claim': 3, 'narrow': 17, 'no-predicate': 10}
- **沿第 71 片那条轴的例行复算**：`external_callers` 对 `commit_approved` / `commit_snapshot` 判 HOLDS，正向对照 `record_dxf_lineage` 判 CONTRADICTED（同一函数换个名字就翻红 ⇒ 探针会开火；第一版这里用的是改口前的旧锚点，读出来是「账文脱钩」而不是「过期」，已更正）
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=fb`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `678`；**相对 tag v5.6.0** 的清单：新增 167 个、消失 9 个（这是 25 片的累计漂移，不是本片增量——本片增量看 `chore(sN): 清单再锚` 那两条提交里的文件数）
- **相对 tag 新增的被哈希文件（前 5 个）**：`assets/templates/fact.json`、`docs/architecture/project_boundary.md`、`docs/architecture/state_infrastructure.md`、`docs/architecture/state_inventory.md`、`scripts/absence_claim_census.py`
- **工作树**：`git status --porcelain` 输出 0 行

## 七、下一片入口

1. 白名单是主机级的，构造边界靠我们的代码自律；更硬的做法是让 `classify_access`
   接受"路径前缀"级信任（需要改库的签名与既有用例）。
2. §第 77 片两件仍未做：narrow 具名样本与处置账的直接联动、`rerun_for_rework` 与
   `run_supervisor` 共用口子合并。
