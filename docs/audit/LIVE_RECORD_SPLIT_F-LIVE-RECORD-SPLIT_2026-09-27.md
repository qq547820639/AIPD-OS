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

## 四、终局读数（占位）

## 五、下一片入口

1. 第 64 片起挂的两件事还剩一件：窄档词表的"具名样本"已覆盖四档，
   但 `AXIS_SAMPLES` 与 `EXEMPTIONS`/`CLAIMS` 的联动是靠 `UNACCOUNTED` 间接保证的
   ——可以再加一条"每个 narrow 样本都有主"的**显式**断言（不是新守卫，是把间接变直接）。
2. `evidence_rework` 与 CLI 每次新建 `Supervisor`（构造里含建表/迁移），等有性能或并发证据再动。
