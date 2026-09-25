# F-C6 第 38 片：服务写面与库层的形参对账

日期：2026-09-26　范围：`src/aipd_os/state/server.py`（三个 `add_*`）、
`tests/test_service_write_surface_parity.py`（新，10 条）、`CHANGELOG.md`。

## 一、这一族的靶子从哪来

第 34-37 片打完「机器默认值冒充归属」之后，同一条轴上还有一句可核的声称：
**多租户状态服务能录 Product Truth**。第 35 片 §四.4 曾把「写面不暴露字段」标成
需要产品裁决——第 37 片重判后先把 `owner` 接上；这一片把普查的轴从「列有没有默认值」
换成「两层同名写入口的形参对不对得上」，用 `inspect.signature` 逐对比较，不截断。

实测结果（改前）：两层同名的写入口 4 个（`add_deliverable`、`add_evidence`、`add_fact`、
`add_risk`），其中三个存在**库层收而服务面不转**的字段：

| 方法 | 缺的字段 | 后果 |
|------|----------|------|
| `add_fact` | `tolerance`、`conditions`、`version` | CTQ 的语义是「目标值 + 公差 + 条件」，多租户这条路上只能录进目标值；第 18/20 片还从 CTQ 生成图纸公差 |
| `add_evidence` | `accessed_at` | 库里写 `accessed_at or ts` ⇒「什么时候拿到的」静默变成「什么时候建的记录」，`list_evidence` 事后无法区分 |
| `add_risk` | `trigger` | 触发条件进不去（第 37 片刚把 `owner` 接上，同一格只差一半） |

同一次普查顺手量到两处**不是**缺陷，记下来免得下次再当靶子：
`add_deliverable` 的创建参数叫 `dtype`、`update_deliverable` 白名单里叫 `type`
（形参名与列名不同，能力不缺）；`id_sequences` 的播种名覆盖不缺
（`next_sequence` 是 `INSERT … ON CONFLICT DO UPDATE`，未知 name 首次调用自行建行）。

## 二、修法与两面判据

三个服务方法补齐形参并按关键字转发（`actor` 保持在末位，位置参数不变 ⇒ 向后兼容）。

判据分两面，各配各的注入，因为**它们互相看不见对方**：

- **行为面**：一次调用把每格都给不同值，逐列断言落盘。
  「形参收下但不转发」这一类（`N1`/`N3`/`N4`）只有这面看得见——签名照样对得上。
  每条都配「把这格从调用里抽掉 ⇒ 该列读回来必须是 NULL（`accessed_at` 那格必须
  不等于哨兵，因为库层对空值兜底 `created_at`）」的最小对照。
- **签名面**：库层每个业务形参都要在服务面同名方法上可见。
  「根本没这个形参」（`N2`/`N5`）只有这面看得见——行为面无法区分「没传」与「没这个参数」。
- **对账面自身**：`assert set(两层同名写入口) == set(COVERED_METHODS)`。
  我不在清单里偷偷少算一个，多了也会当场红。

## 三、三处自抓

1. 服务面调用夹具第一次少传一位：`*args` 是从 `tenant_id` 开始的，我按「项目起步」写 ⇒
   `add_evidence() missing 1 required positional argument: 'title'`。补齐 `("default", "P-SVC", …)`。
2. 第一条注入（`N5`）先做成「服务面新增一个库层不存在的方法」，**存活**——
   那不是漏：这条尺子的射程本来就是两层同名。换成「库层给 `add_fact` 加新形参而
   服务面没跟上」才是真漂移形状，之后 5/5 杀掉。
3. 常驻用例里那句「四个共享写入口」是我手写清单，`test_the_ratchet_...` 第一次就把它
   自己的清单照出来是 4 个（`add_deliverable` 一开始被我漏在射程外）⇒
   把它纳进 `COVERED_METHODS`，而不是把断言放宽。

## 四、这一片没做的事

1. ~~读侧对称面没查~~ —— **同批查完并钉住**：两层同名的读接口 5 个，库层可筛的项
   服务面全可筛（零缺口）。既然今天是零，就把零钉成断言，并加「分母必须是 5」的
   前提（没有可比对象的循环永远绿，那是假绿）；电池 `P1` 用「库层给 `list_facts`
   加筛选参数而服务面没跟上」证明这条尺子会红。
2. **RPC 层没有字段级校验**：新形参经 `service.call(method, **params)` 直达；
   客户端乱传键会 `TypeError`（fail-loud），但没有 schema 化的入参校验。
3. **`add_deliverable` 的 `dtype` 命名不改**：改了要同时动列名与白名单，收益低。

## 五、收口读数

| 项 | 读数 |
|----|------|
| 新增常驻用例 | 12 条（写面 10 + 读侧对称面 2）；全量 2243 → **2253**（工作树整跑 2248 passed / 2 failed / 3 skipped，两条红只有清单哈希锚点，属未重锚预期） |
| 变异电池 | `/tmp/slice38-mutations.py` **6 条：杀 6 / 存活 0 / 注入无效 0 / 崩溃式红 0**，带未注入对照臂；已知无撤回案例 1 |
| 静态检查 | `mypy src` 0 error；`ruff check src tests state_service` rc=0 |

| 签出 attestation | HEAD 干净签出 + `AIPD_SOURCE_COMMIT=<tag SHA>`：**2250 passed / 0 failed / 3 skipped**（2253 收集，8m30s），报告前缀 `2916a14ca08a` 已绑进 `PROVENANCE.test_report` |
| 发布门 | `production_release_gate --release-ready --tag v5.6.0`：**8/8、rc=0、`release_ready: true`**；`audit_repo --strict` rc=1 只剩既有的 tag 锚点判定 |
| 电池重放 | 收尾时在最终树重跑第 38 片 **5/5** 杀掉、字节复算干净 |
| 提交序列 | `b14b7f5`（代码+用例+登记）→ `e99a762`（清单重锚 629 条）→ `ac1e90d`（证据绑签出那一跑）→ 本笔文档 |
