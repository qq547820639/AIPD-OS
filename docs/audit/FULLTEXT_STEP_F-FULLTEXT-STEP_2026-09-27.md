# 全文获取的消费者（F-FULLTEXT-STEP，第 76 片，2026-09-27）

产物：`scripts/research/fetch_fulltexts.py`（新步骤）、
`scripts/research/search_papers_by_open_alex.py`（带出 `is_oa`/`oa_url`/`oa_license`）、
`tests/test_research_fulltext_step.py`（6 条）、`tests/test_research_fulltext_fetcher.py`（4 条）、
`scripts/absence_claim_census.py`（`duplicate_claim_id` 前提 + 账本换条 + 具名样本改指）、
登记表 `research.fulltext_fetch` 该行、README、`docs/audit/s76/battery76.py`。

## 一、这一步只做连接器侧的两件事

1. **这条记录有没有合法的开放副本**：只用来源自己返回的字段（OpenAlex `is_oa`+`oa_url`、
   arXiv 按 id 推官方 PDF 直链、其余来源只认已有的 `oa_url`）。
2. **该用哪个 URL 去取**：取不到就报"没标开放副本"，**不去 scrape 出版商页面**。

下载、编码判定、缓存、SHA-256、access 分类全部复用库里那份
`src/aipd_os/research/fulltext.py`（它本来就写着诚实契约：非法 UTF-8 字节 = 拿不到）。

## 二、为什么之前接不上：连接器把答案丢了

OpenAlex 的响应里有 `open_access` 与 `best_oa_location`，连接器映射时**两个都没取**，
所以记录里只剩 DOI。这不是"少一个字段"，是让下游只剩两种坏选择：猜 URL（可能撞 robots、
可能只拿到付费墙 HTML）或者永远报"没有开放副本"。

## 三、选型（零新依赖优先）

| 候选 | 功能 | 依赖/条款 | 结论 |
| --- | --- | --- | --- |
| OpenAlex `best_oa_location` | 开放副本地址 + license | CC0 数据、无 key、我们已是六源之一 | **选它** |
| Unpaywall | 同上 | 要 email 参数、非商用条款、新外部依赖 | 不选：字段等价 |
| Semantic Scholar `openAccessPdf` | 同上 | 部分字段要 key | 不选：收益不抵依赖 |
| 抓出版商页面 | — | 版权/robots 边界，库里实现本身拒绝 | 不做 |

## 四、两处我自己造的缺陷（都被自己的闸抓回）

1. `s[:i] + 新条目 + s[j:]` 里 `j < i`，四块登记被复制。重复 id 不改判决、`rc` 仍 0
   ⇒ 加 `duplicate_claim_id` 前提 + 守卫用例（账本不许有僵尸条目）。
2. `--offline` 用例第一版钉"没拿到全文"，T4 臂摘掉 offline 判断后仍绿
   （真下载 PDF 也判 restricted ⇒ 两种因果同一读数）。改钉原因：离线**不许构造下载器**。

## 五、终局读数（由 `docs/audit/s76/terminal76.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s76/final`，报告产出于提交 `000d093`，主树当时 HEAD `5874a98`）：`exitcode=0`、`collected=2605`、`passed=2602`、`skipped=3`、其余终态 `{'skipped': 3}`、用时 `320.3s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s76/final`、`source_commit=a66040520139`
- **同族尺子 `doc_command_census`**：`rc=0`；权威面：90 条 argparse 路径（契约 deprecated 别名不并进权威面，由 alias_unregistered 单独核），15 个组名；只报面（live，可行动）47 处；记录性引述（只数不列名）1018 处 {'CHANGELOG.md': 82, 'docs/audit': 825, 'tests': 65, '.trae': 46}；全量扫描 1395 处，live + record = 1065 处（与减去三档判红面覆盖后的行数同构）；现状面缺陷 0 条：文档与登记表点名的命令都注册着
- **同族回归 `absence_claim_census`**：`rc=0`；能力缺失句（窄档＝判据面）：17 句 = 登记 7 + 豁免 10 + **未处置 0**；被挡在窄档外的 18 句，按轴分开：无缺失谓词 10、无能力名词 5、谈判决/谈口径 3（三档各有常驻用例钉住它非空）；具名样本 8 句、样本问题 0 条
- **两把尺子的 `--self-test`**：`rc=0/0`，合计 **32 条**合成读数全对上（条数由本次运行现数）
- **常驻用例（全文步骤与连接器映射合跑，两个不同文件）**：`pytest tests/test_research_fulltext_step.py tests/test_research_fulltext_fetcher.py -q` → `48 passed in 45.91s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s76/battery76.py` → `rc=0`，合计 KILLED 5 / 其余 0
- **两档分母现读**：宽档 35 句、窄档 17 句（差的 18 句按轴分：无缺失谓词 10、无能力名词 5、谈判决/谈口径 3）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2605 条 / 213 个文件，树 213 个文件 / 2519 个 def，终态 {'passed': 2602, 'skipped': 3}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **具名样本核对**：四档共 8 条，样本问题 0 条；分档 {'no-noun': 5, 'non-claim': 3, 'narrow': 17, 'no-predicate': 10}
- **沿第 71 片那条轴的例行复算**：`external_callers` 对 `commit_approved` / `commit_snapshot` 判 HOLDS，正向对照 `record_dxf_lineage` 判 CONTRADICTED（同一函数换个名字就翻红 ⇒ 探针会开火；第一版这里用的是改口前的旧锚点，读出来是「账文脱钩」而不是「过期」，已更正）
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=58`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `677`；**相对 tag v5.6.0** 的清单：新增 166 个、消失 9 个（这是 25 片的累计漂移，不是本片增量——本片增量看 `chore(sN): 清单再锚` 那两条提交里的文件数）
- **相对 tag 新增的被哈希文件（前 5 个）**：`assets/templates/fact.json`、`docs/architecture/project_boundary.md`、`docs/architecture/state_infrastructure.md`、`docs/architecture/state_inventory.md`、`scripts/absence_claim_census.py`
- **工作树**：`git status --porcelain` 输出 0 行

**本节之外还要记两笔（都是自己的工具咬自己）**：
① 第 69 片我给读数脚本加的 `pip-audit` 环境守卫**自己会误拒**——它起 `bash -lc`，
登录 shell 重读 profile 把调用方 export 的 PATH 洗掉，于是明明装着 pip-audit 也报"没有"。
一把只会误拒的守卫比没有守卫更糟：它会把"跑不动"伪装成"环境不对"。改成进程内 `shutil.which`。
② 读数脚本的小节编号又是从上一轮复制的（本篇是 §五，脚本找 §四 ⇒ 拒写）。
这是同一族错的第 5 次，规则已经写进记忆：**复制脚本后逐行问"这句话这一轮是谁算出来的"**。

## 六、下一片入口

1. 联网端到端仍需在能出网的环境跑一次（本机测试全部注入 getter，离线不下载）；
   这一步的 `e2e_evidence` 已按"联网跑通即拿到正文；离线模式只登记可取性"写清，不假装已在线验过。
2. 第 64 片留的 `doc_command_census` 只报面收窄已完成；剩两件：narrow 具名样本与处置账的**直接**联动、
   `rerun_for_rework` 与 `run_supervisor` 的共用口子进一步合并。
