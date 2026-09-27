# 执行证据的返工执行器（F-REWORK-EVIDENCE，第 71 片，2026-09-27）

产物：`src/aipd_os/supervisor/evidence_rework.py`、`supervisor.rerun_for_rework` 公开口子、
`fact_lineage.evidence_content`（生产者与执行器共用的唯一投影）、
`commands_truth.py` 第二道类别轴、`tests/test_evidence_rework.py`（10 条）、
`docs/audit/s71/battery71.py`（7 臂）、登记表/README/sweep/账本的同批改口。
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `674`。
  本片增量 672 → 674（新实现 `src/aipd_os/supervisor/evidence_rework.py` + 新常驻 `tests/test_evidence_rework.py`，两次 `清单再锚` 提交里各有读数）；脚本现在还会印"相对 tag v5.6.0"的累计漂移 +163 / -9 —— 那是 25 片的总量，**不能当成本片增量读**，第一版我就是把这两个数混成了一个说法。
  这一行最初由脚本印成"本片文件数不变"——那是我从第 70 片脚本复制时留下的**断言文案**，不是现读的差集；已把脚本改成现算差集（见下）。

## 一、缺口为什么挪了一格

第 70 片让证据进入血缘 ⇒ 它能被标 stale；但 `aipd truth rework` 的类别判断只看
`metadata["artifact"]`，证据行没有这个键 ⇒ 仍然"点名拒、不烧 attempts"。
发现者与收口者之间断的这一格，正是第 49/51/52/53 片那条链的第五段。

## 二、这一类的"重算"是什么

不是重算一个数，是**再执行一次同一个工作项**，然后**就地演进这条记录**：

| 引擎/生产面规则 | 本片的取舍 |
| --- | --- |
| 引擎成功时 `bump_version(同一条)` | 执行器绝不另起新行、不自己加版本 |
| 生产面 `cost calc` 换输入另起一版 + 旧版 superseded | 不适用（那是"新一次生产"，返工是"把这条修好"） |
| 正文规则 | 与生产者共用 `evidence_content`，只有一份 |
| 信任 | 按这次独立质量门重定，门没过 ⇒ low（不沿用旧 high） |

四条拒绝：`missing_metadata` / `not_replayable`（对外副作用与不可重试只能人处置）/
`rerun_not_ok`（blocked_external 不算收口）/ `rerun_same_run`。
每一条都必须留下"什么都没改"的读数——拒掉不是失败，stale 留在原处下次扫描还看得见。

## 三、电池抓到的一条死守卫

`evidence_artifact_kind` 里我写了"有 `metadata["artifact"]` 就交回原四支"的让位判断。
注入"把 `artifact` 换成任意别的键"之后 38 条用例全绿 ⇒ 这道判断**永远不开火**：
四类版本记录的 `record_type` 本来就是 `artifact_version`，第二道 `record_type == "evidence"`
已经把它们挡住了。按"造不出只关掉自己的对照 ⇒ 要么删要么写独立存在理由"办：删掉，
并在函数里写明为什么不需要第二道。

## 四、同批改动的镜像（少一处就会出现两套口径）

- `commands_truth.py`：`supported` 清单 + "本执行器只认 …"消息 + 类别轴 `or evidence_artifact_kind(...)`
- `registry_data.py` 两行："四类制品"⇒"五类制品（四类版本记录 + 执行证据）"
- `README.md` 两处同类计数；`product_truth/sweep.py` 模块说明
- `tests/test_dxf_rework.py` / `tests/test_cost_rework.py`：钉死四类清单的两条断言改五类，
  **保留**"quote_batch 仍逐条点名拒、不烧 attempts"那一半
- 账本新增存在式 `EVIDENCE-REWORK-WIRED`（反证 = 执行器在生产面 0 处外部调用点）

## 四之二、全量逮到的一处漏改（我的定点跑与电池都没覆盖它）

第三处钉住"四类制品"的位置是 `tests/test_bom_rework.py:377`——它钉的是
`assert "执行器今天认四类制品" in README.md`，即"README 与登记说的是同一份清单"。
我改了登记表与 README（四→五），也改了另两个文件里钉**类别清单**的断言，
却漏了这一处；而我的定点复算跑的是 `evidence_rework / absence / truth_propagate_cli /
drawing_spec_lineage / supervisor_fact_writeback / architecture_contracts`，
电池跑的是 `evidence_rework / dxf_rework / cost_rework`——**都不含 `test_bom_rework`**，
所以直到干净检出的全量才红。

两件事一起记：
① "改口径要同批改所有钉住它的断言"这条，光靠 grep 关键字不够——
   钉的方式可能是"某个短语在另一个文件里出现"，与被改的键不是同一个字面；
   收口序列里的**全量**才是这条的兜底，定点跑与电池只是加速器，不能替代它。
② 电池与定点跑的覆盖面要写清"没覆盖谁"，否则"7 臂全杀"会给人一种"改完都验过了"的错觉。
   （本轮还把这条读法用在了自己写的读数脚本上：`terminal71.py` 只跑它列出的靶。）

## 五、终局读数（由 `docs/audit/s71/terminal71.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s71/final`，报告产出于提交 `4a61945`，主树当时 HEAD `a194aa7`）：`exitcode=0`、`collected=2587`、`passed=2584`、`skipped=3`、其余终态 `{'skipped': 3}`、用时 `256.1s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s71/final`、`source_commit=a66040520139`
- **本片主角（真仓库终态）**：`rc=0`；语料：84 个能力，带否定词的句子 36 句；账本登记 13 条，未挂锚点 29 句（宽档，只报不判）；能力缺失句（窄档＝判据面）：16 句 = 登记 6 + 豁免 10 + **未处置 0**；判红 0 条：登记的 13 句「仍缺着」现在都还缺着
- **`--self-test`**：`rc=0`，**23 条**合成读数全对上（含存在式登记、去处台账与 `table_ddl` 双向）
- **常驻用例**：`pytest tests/test_evidence_rework.py tests/test_absence_claim_census.py -q` → `36 passed, 24 warnings in 16.94s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s71/battery71.py` → `rc=0`，合计 KILLED 7 / 其余 0
- **两档分母现读**：宽档 36 句、窄档 16 句（差 20 句是谈判决/谈口径的假阳性）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2587 条 / 211 个文件，树 211 个文件 / 2501 个 def，终态 {'passed': 2584, 'skipped': 3}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **本片新档的读数**：`external_callers` 对 `commit_approved` / `commit_snapshot` 判 HOLDS，正向对照 `record_dxf_lineage` 判 CONTRADICTED（同一函数换个名字就翻红 ⇒ 探针会开火；第一版这里用的是改口前的旧锚点，读出来是「账文脱钩」而不是「过期」，已更正）
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=a1`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `674`（本片**文件数不变**，只改内容）
- **工作树**：`git status --porcelain` 输出 0 行

## 六、下一片入口

1. 窄档两个手写词表的自证（被挡掉的 20 句做常驻阴性夹具）。
2. 第 64 片留的 `doc_command_census` 只报面收窄。
3. `supervisor.rerun_for_rework` 目前只在返工路径被调用；把它与 `run_supervisor` 成功分支里
   那三行（router / 质量门 / 血缘）抽成一个共用函数，仍是两处各写一遍的近似——
   等量改名或改语义时两边不会互相报错。
