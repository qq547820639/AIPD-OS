# 只报面拆成 live 与 record（F-LIVE-RECORD-SPLIT，第 75 片，2026-09-27）

产物：`scripts/doc_command_census.py`（`RECORD_FILES`/`RECORD_DIR_PREFIXES`/`is_record_path`
+ `report_record_unmatched` + 分目录计数 + `record_bucket_empty`）、
`scripts/absence_claim_census.py`（删一条永不单独开火的冗余守卫）、
`tests/test_doc_command_census.py`（2 条新增、4 条改向）、README、`docs/audit/s75/battery75.py`。

## 一、现读分布（不是估的）

| 文本 | 提及数 | 归桶 |
| --- | --- | --- |
| `docs/audit/` | 820 | record（当轮取证件） |
| `src/` | 333 | live |
| `CHANGELOG.md` | 81 | record |
| `tests/` | 65 | record（含故意写的幻影名） |
| `.trae/` | 46 | record（轮次 spec/checklist） |
| `docs/architecture/` | 22 | live |
| `scripts/` | 20 | live |

拆桶前：只报面 1059 处、未注册名 10 个。拆桶后：live 47 处、未注册名 **0 个**；
record 1012 处（73%）仍逐条列在 `report_record_unmatched` 里。

## 二、这条不变量在拆桶前根本写不出来

`test_live_bucket_has_no_unregistered_commands_in_this_repo` 要求 live 清单为空。
拆之前只能写成"未注册名 ≤ 15"这种废话，因为清单里必然混着测试为了证明判据会开火
而故意写的 `aipd ctq zzz-listy`。**"可见性不降"是这次拆桶的前提**：
record 桶保留名字与位点，只是不再污染可行动清单。

## 三、我这一片自己造成的破坏（记下来，因为它躲过了 `rc`）

删第 74 片那条 `sample_without_home` 守卫时（它永不单独开火：窄档样本若无去处，
`UNACCOUNTED` 已经会红），我用"从注释行切到 `judged =`"做区间删除，多盖住两段循环：
`UNACCOUNTED` 的行发射 + 豁免薄理由/陈旧性检查。后果：

- `absence_claim_census` 的 `rc` **仍是 0**（少产出行不改变判决分支）；
- 是三组常驻用例（partial ledger 不再红、EXEMPT 行不再产生）与 `--self-test` 把它抓回来。

两条规矩：① 删代码按**语义边界**删（整函数/整块），不要"从这行找到那行"；
② 删完必须读 `git diff` 确认只少了想少的东西——`rc=0` 不是证据。
同时承认：那条联动本来就是多余的，写了又删比留着当死守卫好。

## 四、终局读数（由 `docs/audit/s75/terminal75.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s75/final`，报告产出于提交 `34a545a`，主树当时 HEAD `637f5d0`）：`exitcode=0`、`collected=2594`、`passed=2591`、`skipped=3`、其余终态 `{'skipped': 3}`、用时 `213.6s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s75/final`、`source_commit=a66040520139`
- **本片主角 `doc_command_census`**：`rc=0`；权威面：90 条 argparse 路径（契约 deprecated 别名不并进权威面，由 alias_unregistered 单独核），15 个组名；只报面（live，可行动）47 处；记录性引述（只数不列名）1015 处 {'CHANGELOG.md': 82, 'docs/audit': 822, 'tests': 65, '.trae': 46}；全量扫描 1392 处，live + record = 1062 处（与减去三档判红面覆盖后的行数同构）；现状面缺陷 0 条：文档与登记表点名的命令都注册着
- **同族回归 `absence_claim_census`**：`rc=0`；能力缺失句（窄档＝判据面）：17 句 = 登记 7 + 豁免 10 + **未处置 0**；被挡在窄档外的 19 句，按轴分开：无缺失谓词 11、无能力名词 5、谈判决/谈口径 3（三档各有常驻用例钉住它非空）；具名样本 8 句、样本问题 0 条
- **两把尺子的 `--self-test`**：`rc=0/0`，合计 **32 条**合成读数全对上（条数由本次运行现数）
- **常驻用例（两把尺子合跑，两个不同文件）**：`pytest tests/test_doc_command_census.py tests/test_absence_claim_census.py -q` → `47 passed in 22.29s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s75/battery75.py` → `rc=0`，合计 KILLED 4 / 其余 0
- **两档分母现读**：宽档 36 句、窄档 17 句（差的 19 句按轴分：无缺失谓词 11、无能力名词 5、谈判决/谈口径 3）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2594 条 / 211 个文件，树 211 个文件 / 2508 个 def，终态 {'passed': 2591, 'skipped': 3}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **具名样本核对**：四档共 8 条，样本问题 0 条；分档 {'no-noun': 5, 'non-claim': 3, 'narrow': 17, 'no-predicate': 11}
- **沿第 71 片那条轴的例行复算**：`external_callers` 对 `commit_approved` / `commit_snapshot` 判 HOLDS，正向对照 `record_dxf_lineage` 判 CONTRADICTED（同一函数换个名字就翻红 ⇒ 探针会开火；第一版这里用的是改口前的旧锚点，读出来是「账文脱钩」而不是「过期」，已更正）
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=63`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `674`；**相对 tag v5.6.0** 的清单：新增 163 个、消失 9 个（这是 25 片的累计漂移，不是本片增量——本片增量看 `chore(sN): 清单再锚` 那两条提交里的文件数）
- **相对 tag 新增的被哈希文件（前 5 个）**：`assets/templates/fact.json`、`docs/architecture/project_boundary.md`、`docs/architecture/state_infrastructure.md`、`docs/architecture/state_inventory.md`、`scripts/absence_claim_census.py`
- **工作树**：`git status --porcelain` 输出 0 行

**读数脚本又犯了同一族错两次**（已在 `9a1f73a` 之前那一次修掉，这里补记因为它是本节的前置）：
`terminal75.py` 是从 `terminal74.py` 复制的，于是"本片主角"仍在跑上一轮的 `absence_claim_census`、
常驻用例那行仍把同一个测试文件传两遍（`60 passed` 其实是 30 条跑两次）。
第 71/72/74 片已经为这个模式写过三次记忆，这次我把规则落成脚本内的形状：
**每一行都必须显式写出它跑的是哪个脚本、哪几个文件，参数由同一个列表打印**——
不再允许"和上一版一样"的写法。

## 五、下一片入口

1. 第 64 片起挂的两件事还剩一件：窄档词表的"具名样本"已覆盖四档，
   但 `AXIS_SAMPLES` 与 `EXEMPTIONS`/`CLAIMS` 的联动是靠 `UNACCOUNTED` 间接保证的
   ——可以再加一条"每个 narrow 样本都有主"的**显式**断言（不是新守卫，是把间接变直接）。
2. `evidence_rework` 与 CLI 每次新建 `Supervisor`（构造里含建表/迁移），等有性能或并发证据再动。
