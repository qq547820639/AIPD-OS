# 执行证据的返工执行器（F-REWORK-EVIDENCE，第 71 片，2026-09-27）

产物：`src/aipd_os/supervisor/evidence_rework.py`、`supervisor.rerun_for_rework` 公开口子、
`fact_lineage.evidence_content`（生产者与执行器共用的唯一投影）、
`commands_truth.py` 第二道类别轴、`tests/test_evidence_rework.py`（10 条）、
`docs/audit/s71/battery71.py`（7 臂）、登记表/README/sweep/账本的同批改口。
命令数与三张分母不变；被哈希文件数 +2（新实现 + 新常驻测试）。

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

## 五、终局读数（占位）

## 六、下一片入口

1. 窄档两个手写词表的自证（被挡掉的 20 句做常驻阴性夹具）。
2. 第 64 片留的 `doc_command_census` 只报面收窄。
3. `supervisor.rerun_for_rework` 目前只在返工路径被调用；把它与 `run_supervisor` 成功分支里
   那三行（router / 质量门 / 血缘）抽成一个共用函数，仍是两处各写一遍的近似——
   等量改名或改语义时两边不会互相报错。
