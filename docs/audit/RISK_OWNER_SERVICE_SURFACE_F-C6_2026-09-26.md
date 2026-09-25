# F-C6 第 37 片：`owner` 能从服务写面进来了（actor ≠ 责任人）

日期：2026-09-26　范围：`src/aipd_os/state/server.py`（`StateService.add_risk`）、
`tests/test_risk_ownership.py`（+5 条）、`CHANGELOG.md`、`README.md`。

## 一、前提：第 35 片留下的那句「需要产品裁决」被自己重新判过一次

第 35 片 §四.4 写的是「服务/HTTP 写面仍未暴露 `owner` 入参——要真填进谁建的，
得先定身份源」。这一条被标成外部裁决项，但拆开看它不是：
**接收一个 owner 字段**不需要身份源，身份源只在「拿它当放行依据」时才需要
（那正是第 34 片决定 C 拒绝做的事）。所以这是自有权责、纯增量、可回退的改动 ⇒ 直接做。
（该纪律与 `feedback-autonomy-mode` 里「重判自己旧的 external 标签」一致。）

普查写面（不截断 `grep -rn "add_risk"`）：
`StateService.add_risk` 是唯一的对外服务写面，它**收下 `actor` 用于授权与审计，
却在往下调 `db.add_risk` 时把整个尾参丢掉**——第 34 片给库层加的 `owner`
因此谁也够不到。RPC 派发是泛化的（`service.call(method, **params)`，`server.py:31`），
所以签名加了参数就自动可达，不需要另开路由。

## 二、修法与一条必须钉住的分离

`StateService.add_risk(..., owner: str | None = None, actor: str | None = None)`，
往下转发 `owner=owner`，并在审计 `after` 里同时记 `owner` 与被谁写的（`actor`）。

决定：**不许把 `actor` 当 `owner` 转发**。库里那条 `actor` 是「谁在调用」，
`owner` 是「谁为这条风险负责」；把前者写进后者，等于用调用者身份替所有人认领风险
——正是 v20/v21/v22 三格迁移在清的那类假归属。这条分离有自己的一对最小对照：
给了 `owner` 必须落库（M2 打这里）、只给 `actor` 时 `owner` 仍是 NULL（M1 打这里）。

## 三、自抓两处

1. 服务层夹具一开始用 `actor="li"` 直调，被真授权拦下
   （`AuthError: unknown user`）——`_authorize` 要求 actor 是注册过并被授予该项目的
   **user id**，不是用户名。改成 `auth_register("u-li", ..., project_id="P-SVC")` 后，
   测试走的才是生产那条授权路径，而不是绕过授权的假绿。
2. 「actor 不渗入 owner」这条断言第一次红，原因不是判据而是夹具：
   它复用了未注册的 `actor="zhang"`。修夹具而不是放宽断言。

## 四、收口读数

| 项 | 读数 |
|----|------|
| 全量用例 | 2238 → **2243**（+5，全在服务写面这一类）；工作树整跑 2238 passed / 2 failed / 3 skipped，两条红只有清单哈希锚点（未重锚，属预期） |
| 变异电池 | `/tmp/slice37-mutations.py` **4 条：杀 4 / 存活 0 / 注入无效 0 / 崩溃式红 0**（M1 actor 当 owner、M2 收下不转发、M3 审计不落 owner、M4 签名退回旧形状）；已知无撤回案例 1 |
| 既有授权面回归 | `tests/test_authorization.py`、`tests/test_mcp_authorization.py` 共 20 条 rc=0 |
| 静态检查 | `mypy src` 0 error；`ruff check src tests state_service` rc=0 |

（签出 attestation 与两道发布门的读数在最后一笔提交里补上。）
