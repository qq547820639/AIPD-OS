# 第 106 片：异常卫生门改版（EMPTY_EXCEPT 收回 + SIM105 + 门加宽）

日期：2026-09-29。F 号：F-EXC-HYGIENE。CHANGELOG：v5.67。

## 一、动手前量到的前提（都现算，不抄自述）

- 旧记号 `# noqa: EMPTY_EXCEPT` 全仓 13 行命中里，**代码面 9 处**（`aipd_store.py` ×3、
  `audit_repo.py`、`release_evidence.py` ×2、`quotes.py` ×2、`server.py`），其余 4 行是
  `tests/test_exception_hygiene.py` 判据自己的散文。ruff 对其中 9 处各吐一条
  `Invalid # noqa directive` warning；第 10 条来自 `aipd_supervisor.py:35` 的**散文**
  ——注释里复刻了 `noqa:` 带码的完整指令形状，ruff 把注释当指令解析（教训已写回该注释）。
- SIM105 现读 5 处：`aipd_store.py:194/285/289`、`research/search_papers.py:137`、
  `research/source_worker.py:79`。前三处与 EMPTY_EXCEPT 豁免**同一批 try 块**——
  这就是批次表里 SIM105 挂 blocked 的原因：按 ruff 建议改成 `contextlib.suppress` 后，
  旧判据（只认 only-pass 的 ExceptHandler）看不见新的吞法，豁免记号也没地方放。
- 卫生门的两个既有盲区（CHANGELOG v5.46 那轮自述过）：`scripts` 只扫顶层
  （`research/` 子目录 10 处无记号空吞全隐形）；`SyntaxError` 一律 `continue`
  （解析不了的文件对这道门是隐形的，且与「面上没有吞点」同形）。
- `release_evidence.py:259` 的旧记号是**装饰性的**：那个 handler 体是
  `return "not-installed"`，不是 only-pass，卫生门本就不要求记号——旧记号在那里纯属
  噪声，本轮摘除、理由留散文。

## 二、改法（一句：记号搬家 + 门跟着吞法走）

1. 记号：`# aipd: empty-except - 原因`；判据窗口 = 声明行、其上一行或紧随下一行
   （E501 把长原因挤到上一行的写法合法；隔两行不算，防一条注释盖住嵌套多吞点）。
2. 门加宽：suppress 块（`contextlib.suppress` 与裸 `suppress` 两种导入形）纳入同一道门；
   `scripts` 改递归、`state_service` 入面；解析不了的文件单列第三态判红。
3. 收回臂：代码面（src/aipd_os + scripts 递归 + state_service）再现 `# noqa: EMPTY_EXCEPT`
   即判红。
4. 面读数（改完现读）：**310 文件 / 吞点分母 23（13 only-pass + 10 suppress）/
   无记号 0 / 旧记号 0 / 不可解析 0**。分母下限钉 23：X3 实测把 suppress 判据改瞎后
   分母掉到 13，分母断言当场红——拆吞点缩水与判据致盲从此同形可见。

## 三、常驻用例与必开火控制

`tests/test_exception_hygiene.py` 2 → 14 支。控制 8 支：unmarked except-pass 开火、
unmarked suppress 开火、裸 `suppress` 导入形开火、带记号不开火、下一行记号算数、
隔两行不开豁免、旧记号开收回臂、解析不了文件必须出现在第三态（不许伪装成
「面上没有吞点」）。

## 四、变异电池（docs/audit/s106/battery106.py，6 臂全 KILLED）

基线 14/14；X1 记号窗口放行 / X2 收回臂致盲 / X3 suppress 看不见 / X4 旧记号真回代码面
（收回臂真开火，双红：no_unmarked + old_marker）/ X5 静默跳过回潮 / X6 扫描面塌缩。
每臂观察面是 **FAILED 用例集合**（不是退码），红错地方记 WRONG-REASON。
日志：`battery106-run.log`；收尾 sha 与开跑前逐字节相同。

## 五、连锁面

- `source_worker.py` 偿清 E501+SIM105 成为第 22 个 0 债文件，棘轮的对账格当场点名
  「直连清单不同源」，已接进 ci.yml 与 `tests/test_ci_face_gates.py::SCRIPTS_LINT_FACE`
  两处镜像；`CI_SURFACE_REGISTER.json` 的 ruff 命令串同步。
- `SCRIPTS_LINT_BASELINE.json` 重发：86 格持平（命中 580→576；`aipd_store.py`
  E701 15→12 下调；SIM105 三格摘除；`source_worker.py` E501 1 格收账）。
- ruff Invalid noqa warning：10 → 0（整面现读）。

## 六、复算入口

```bash
cd AIPD-OS
.venv/bin/python -m pytest -q tests/test_exception_hygiene.py        # 14 passed
.venv/bin/python scripts/scripts_lint_ratchet.py                     # 86/86 持平，直连 22
.venv/bin/python -m ruff check --no-cache src tests scripts state_service 2>&1 | grep -c '^warning'  # 0
.venv/bin/python -B docs/audit/s106/battery106.py                    # KILLED 6/0/0
```

## 七、认证流水账（含第一代作废）

- 第一代（锚 `4d2b623` 后、`c51a721` 的树）：全量 2815p/4f——4 条红全是
  `test_forensic_scripts_root` 一族：`closeout106.sh` 在名册末次 emit 之后才入库。
  排障时又踩深一层：`build_forensic_root_register.py` **不带 `--emit` 只审不写**，
  且两种模式的输出长得一样（都是"归属/缺陷"读数）——连跑两次"重发"名册都没动，
  靠 `facts()` 与名册求差（inside 81 vs register 80）才定位。带 `--emit` 重发
  81 条后 13/13 绿（`d6995da`）。第一代报告随 `.wt-s106` 重建作废，
  尾巴留档 `run-s106-gen1-tail.log`。
- 第二代（`d6995da` 树，2819p/0f/5s 全绿）**作废在收口 precheck**：报告 `source_commit`
  钉的是实测 HEAD 而不是 tag——worktree 全量必须带 `AIPD_SOURCE_COMMIT=<tag SHA>` 起跑，
  这道发令旗只活在跑 pytest 的那行命令里，不在收口 .sh 内（已补进脚本头）。
- 第三代（同一 `d6995da` 树 + 环境变量重跑）：2819 passed / 0 failed / 5 skipped，
  collected 2824 > 下界 2812，fp ca85567b0bf1；SKIP 面逐条相同（5 条）；
  BIND_RC=0（一次绑定两旗齐给）、GATE_RC=0（release_ready=True，8/8）、CV_RC=0 全绿；
  B 臂（全部提交落库后复跑门 + 验签）GATE_B_RC=0 / CV_B_RC=0（`gate-b.json`、
  `closeout-b.json`）。尾巴 `run-s106-gen3-tail.log`、链上全程 `closeout106-chain.log`。
