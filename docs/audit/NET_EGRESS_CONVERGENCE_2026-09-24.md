# F-NET-01 · src/ 网络出口收敛到 `aipd_os.net.http`

日期：2026-09-24 ｜ 轮次：本轮（承 F-CAD-01 / F-STATE-05..08 / F-EXEC-01 / F-GATE-01 之后）
状态：**已闭合**（实现 + 常驻用例 + 收敛守卫 + 全量回归 + 静态门禁）

## 1. 结论速览

| 项 | 读数 | 取数方式 |
| --- | --- | --- |
| 迁移前 src/ HTTP 出口调用点 | **9 处 / 7 个模块** | `git grep -n "urlopen" HEAD -- src` + `git grep -n "requests\." HEAD -- src` 现算 || 迁移后 src/ 直连出口 | **1 处**（`net/http.py` 内部） | `tests/test_net_egress_convergence.py` AST 扫描，分母 211 个源文件 |
| `# noqa: S310`（scheme 手工豁免） | 3 → **0**（仅 `net/http.py` 统一实现一次） | 同上扫描 + `grep` |
| src/ 运行时硬依赖 | `jsonschema` 1 个（`requests` 退出核心路径） | `pyproject.toml` `[project.dependencies]` |
| 新增行为契约用例 | 15（`test_net_http.py`，真跑本地 HTTP 服务） | 上一提交 |
| 新增收敛守卫用例 | 8（`test_net_egress_convergence.py`） | 本轮 |
| eval 端点用例改写 | 3 改 + 1 新增（`test_completion_endpoint.py`） | 本轮 |
| 全量回归 | **1385 passed / 0 failed / 3 skipped**（`pytest-report.json` 同源，exit 0） | `pytest -q --json-report` |

## 2. 缺陷本体

同一件事（发一次 HTTP 请求）在 src/ 里有 8 个互不相同的版本，造成的不是抽象的
「不优雅」，而是四类可观察的行为差异：

1. **超时口径**：默认值实测有 **3 种**——60s（`llm` / `imggen` / `visual_audit` /
   两条 eval 路径）、30s（`researchstudio`）、20s（`research_adapter` 的
   `_REQUEST_TIMEOUT_S`）；`imggen` 内部还有一处写死的 `timeout=60` 下载分支。
   同一个「网络挂了」在不同能力里等的时间不一样，降级链（`execution_router`）
   拿到的失败时刻也就不同。
2. **重试语义**：**src/ 的 9 个出口一处都不重试**（实测：`git grep` 这 9 个文件在
   HEAD 上没有 `Retry` / `Retry-After` / 退避 `sleep`；`mail`、`evals/runner`、
   `execution_router` 里的 sleep 属 SMTP 与任务级重试，不是 HTTP 出口）。会处理
   429/`Retry-After` 的只有 `scripts/research/_http_runtime.py` 那一套
   requests+urllib3 策略。于是「端点明确说了稍后再来」在 src/ 侧一律按永久失败上报。
3. **scheme 白名单**：3 处直接 `# noqa: S310` 把「URL 由用户配置所以可信」写成注释
   约定，等于没有校验；其余 6 处连注释都没有，也就是任何 scheme（含 `file:`）都会
   被 `urlopen` 接受。
4. **依赖泄漏**：`requests` 在 `pyproject.toml` 属于 `full` **optional extra**
   （本机实测 `requests==2.32.5` / `urllib3==2.6.3`），但
   `evals_runner/completion.py` 与 `evals/runner.py` 的真实端点路径直接
   `requests.post`。最小安装（只有 `jsonschema`）下这两条路径跑不起来——
   `completion.py` 只能靠 `ImportError` 转成「缺少 requests 依赖」的报错文案兜住，
   把打包问题伪装成环境问题。

## 3. 选型（六维对比）

选型对比。**顺序不合规，如实标注**：`aipd_os.net.http` 与 7 处迁移在上一轮就已落地，
本节是**事后补做**的候选比较（与 F-CAD-01 那轮的同一纪律问题，见 `overview.md`
「纪律更正」条），不写成「当初就先查过」。比较依据如下；联网检索只拿到 SEO 聚合页，
因此**没有**引用任何未实际读到的文档内容（诚实边界见 §7）。

| 候选 | 功能匹配 | License | 维护活跃度 | 安全 | 代码质量 | 适配成本 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 标准库 `urllib` 自写薄客户端 | 只需 GET/POST + 瞬态重试 + `Retry-After`，够用 | 随 CPython，无新增 | 随 CPython | scheme 白名单可控；无第三方供应链面 | ~170 行，可全量常驻测覆盖 | 低（9 处调用点机械替换） | ✅ **选用** |
| `requests` + urllib3 `Retry` | 连接池/重试/重定向齐全 | Apache-2.0（实测 metadata） | 活跃 | 引入 `certifi`(MPL-2.0) 等传递依赖面 | 成熟 | **需把 optional extra 变成核心硬依赖** | ❌ 与「最小安装」约束冲突，正是本缺陷成因 |
| `httpx` | HTTP/2、超时分解更细 | BSD-3 | 活跃（PyPI 有 0.28.1 页面） | 同上新增供应链面 | 成熟 | 本机**未安装**（实测 `PackageNotFoundError`），需新增依赖 + 全量重写 | ❌ 收益不足以支付新增硬依赖 |
| `tenacity`（重试装饰器）+ 现有 urllib | 只解决重试一项 | MIT | 活跃 | — | — | 本机未安装；只补 1/4 的问题 | ❌ 治不到超时与 scheme 两项 |

借鉴的现成实现：`scripts/research/_http_runtime.py`（仓内既有、基于
requests+urllib3 `Retry`）已经把「只重试瞬态状态、`Retry-After` 支持秒数与
HTTP-date、退避封顶、传输异常立即上抛」这套策略写对了，`aipd_os.net.http`
**沿用同一套语义**，使两条路径行为可比。该模块**保留不动**——它的职责是给第三方
依赖自有的 `requests.Session`（OpenReview 不接受 timeout 入参）挂载策略，只能用
requests 的 adapter 机制，换成标准库反而做不到。

## 4. 实现

`src/aipd_os/net/http.py`（172 行）：

- `check_url()` 在**发请求之前**按 `{http, https}` 白名单拒绝其余 scheme，
  `request()` 入口即调用，取代 3 处 `# noqa: S310` 约定。
- 只对 `RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}` 重试；`URLError` 与
  其他异常立即 `HttpError` 上抛——持续限流的端点不能把进程挂死在循环里。
- `retry_after_seconds()` 双形态解析（秒数 / HTTP-date），退避
  `min(cap, base * 2**(attempt-1))`；`sleep` 可注入，测试里断言实际等待序列
  而不是靠时间猜。
- `DEFAULT_MAX_ATTEMPTS = 1`：**默认不重试**。付费端点（LLM / 图像生成）重复发
  请求等于重复计费，与 `execution_router` 的 `EXTERNAL_SIDE_EFFECT` 不同步重试
  原则一致；只读检索类连接器显式传 `max_attempts=3`。
- `HttpResponse` 冻结数据类，非 2xx 也**带状态码与正文返回**，由调用方判定，
  避免把 404 响应体在出口层丢掉。`MAX_BODY_READ_BYTES = 32MiB` 限制单次读取。

迁移的 7 个模块（`git diff --numstat` 现算：+88 / −92，净 −4 行——出口实现从 7 份
变 1 份，但调用方各自保留状态判定，所以净减有限）：
`llm/client.py`、`research/providers/researchstudio.py`、
`tool_adapters/research_adapter.py`、`imggen/providers.py`、
`visual_audit/providers.py`、`evals/runner.py`、`evals_runner/completion.py`。

## 5. 本轮抓到的假绿与连带修正

写下「收敛完成」之前，这四处是逐条暴露出来的，登记在此以免被当成顺带改动：

1. **桩错对象**：`tests/test_completion_endpoint.py` 打桩 `requests.post`。迁移后
   被测代码根本不再经过 `requests`，桩成为空操作——真实后果是测试把请求发到了
   开发者机器的代理（回溯里出现 `HTTPSConnection('127.0.0.1:7890')` 隧道到
   `example.test`）。修法不是把桩改成 `urlopen`，而是改用**本地真 HTTP 服务**
   （与 `test_net_http.py` 同形），并断言线上真实收到的 `Authorization` 头与
   请求体；用例里显式清空 `*_PROXY` 并设 `no_proxy=*`，保证永不出网。
2. **打桩对象形状不忠实**：`tests/test_adapters.py` 的两个 `FakeResp` 缺
   `getcode()`/`headers`，`read()` 也不接受字节上限，迁移后立刻 `AttributeError`。
   按真实响应形状补齐（同 `tests/test_llm_providers.py`、
   `tests/test_visual_honesty_guardrail.py` 上一轮的补法），**不动生产代码去迁就桩**。
3. **自家新代码违反本仓异常卫生门禁**：`net/http.py` 的
   `except ValueError: pass` 被 `tests/test_exception_hygiene.py` 判红。改为嵌套
   `try`（多格式解析回退不该写成空吞），顺带删掉 `if when is None` 这条不可达分支
   ——`parsedate_to_datetime` 对坏输入是抛 `ValueError`，不会返回 `None`。
4. **守卫本身可能是假绿**：AST 扫描如果 `src` 路径解析错、扫到空目录，同样返回
   「0 违规」。故 `scan_src()` 与读数一起返回分母，用例断言 `scanned > 150`
   （实测 211，且断言 `net/http.py` 确实在枚举内被排除）；另用 5 条合成源码
   逐形态注入验证探针会开火（`urllib.request.urlopen`、`from ... import urlopen`、
   `requests.get/post/Session`、仅 `import requests`），再用 1 条「注释里提到
   urlopen + 合规调用」样例证明文本匹配会产生的假阳性不在判据里。

## 6. 验证

- `tests/test_net_egress_convergence.py` 8 passed；`tests/test_net_http.py` 15 passed；
  `tests/test_completion_endpoint.py` 8 passed；`tests/test_adapters.py` +
  `tests/test_llm_providers.py` 31 passed。
- 全量：**1385 passed / 0 failed / 3 skipped**（exit 0，`docs/audit/pytest-report.json`
  同源）。中途曾有 2 条 `test_packaging.py` 的 manifest 哈希项判红——它们钉的是
  「清单与磁盘一致」，改了 src/ 就必然红，重锚方式见 §9 末尾
  （`SOURCE_MANIFEST` / `RELEASE_MANIFEST` 生成命令），**不是**回归；重锚后复跑转绿。
- 静态：`ruff check src tests state_service` 0；`mypy` 0 error（365 files）。
- 本轮新增的 `eval` 端点用例在真服务上断言 429 命中次数 `== 1`，把「付费端点
  不自动重试」从意图变成机器读数。

## 7. 诚实边界

- 本轮**没有**对任何真实外部端点发起请求。全部 HTTP 证据来自
  `127.0.0.1` 上的本地 `HTTPServer`。真实模型端点/图像端点的行为仍属
  `external_dependency`，需要 owner 配 key 后实测。
- 联网检索只得到聚合站与博客页（关键词见 §3），**未**读取 `httpx`、
  `tenacity`、`urllib3` 的源码或官方文档正文；因此本文件的第三方结论只来自两类
  可复核证据：本机 `importlib.metadata`（版本 / License / requires-python）与
  `pyproject.toml` 的 extra 归属。维护活跃度一列是这类包常识级别的定性判断，
  未附实测证据，不作依据使用。
- `FakeResp` 双桩仍然存在（`test_adapters.py`）。它们现在形状忠实，但忠实度靠人
  盯；后续新增出口用例的默认做法应是本地真服务，而不是继续加桩。

## 8. 遗留（未在本轮做）

| 项 | 现状 | 判断 |
| --- | --- | --- |
| `scripts/research/_http_runtime.py` 仍用 requests | 保留 | 要给第三方自有 `Session` 挂 adapter，标准库做不到；不是同类重复 |
| `aipd doctor` 依赖清单仍把 `requests` 当运行时依赖探测 | 仍探测，缺失只报 `missing` | src/ 已不依赖它，文案宜改标「scripts 连接器专用」。属可选依赖口径，留待与 optional-extra 文档一起改 |
| `mail/` 的 SMTP 出口（`smtplib`/`SSLContext`） | 未收敛 | 不是 HTTP 语义（无状态码/`Retry-After`），强套 `net.http` 反而丢真；另登记 |
| `evals_runner/completion.py` 用 `cast(str, ...)` 未校验 content 类型 | 保留原行为 | `llm/client.py` 有 `isinstance` 校验；两处口径统一属改进项，非缺陷 |
| 连接复用（keep-alive 连接池） | 未做 | stdlib `urllib` 每请求一连接。当前调用频次（每能力一次）不需要，若进入高频抓取再评估 |

## 9. 复算入口

```bash
cd /Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
# 迁移前出口分布（读数应为 9 处调用点 / 7 个模块）
git grep -n "urlopen" HEAD -- src | grep -v "net/http.py"
git grep -n "requests\." HEAD -- src | grep -v "net/http.py"
# 收敛守卫（含分母与注入反证）
.venv/bin/python -m pytest tests/test_net_egress_convergence.py tests/test_net_http.py -q
# 行为契约（真服务：鉴权头上线、429 不重试、连不上必报错）
.venv/bin/python -m pytest tests/test_completion_endpoint.py tests/test_adapters.py -q
# 静态门禁
.venv/bin/ruff check src tests state_service && .venv/bin/mypy
# 清单重锚（§6 那 2 条红了才需要；source_commit 仍锚在 v5.6.0 的提交上，
# 不移动 tag、不重签名、不 push）
.venv/bin/python scripts/release_evidence.py --source-commit "$(git rev-parse 'v5.6.0^{commit}')" \
  --test-report docs/audit/pytest-report-v5.6.0.json
.venv/bin/python scripts/regenerate_release_manifest.py
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/production_release_gate.py --release-ready --tag v5.6.0
```

## 10. F-REL-01：收尾时量出来的第二个缺陷（发布证据读的是可变文件）

本轮按流程重生成 `PROVENANCE.json` 之后，`production_release_gate` 从 8/8 掉到
7/8，红项是 `test_numbers_from_report`：

```
test_report source_commit a7fa402… != a660405… (tag v5.6.0): report STALE, cannot gate release
```

判据没错，**证据链的写法**有问题：`PROVENANCE.test_report` 记录的是
`docs/audit/pytest-report.json` 这个**每轮都会被覆盖**的路径。它上一次被解析时里面
恰好还是 v5.6.0 时代的那份报告（`generated_at` 2026-08-13、1096 passed、
`source_commit = a660405`），于是 8/8 成立；而本轮把新跑的 1385 写进同一路径后，
「v5.6.0 的发布证据」就变成了一份比 tag 新的树的测试结果——**要么判红，要么假绿**，
取决于重生成证据的时机。这不是本轮引入的，是它一直没被触碰。

修法（不改门禁、不动 tag、不重签名）：

1. 从 git 历史取回与旧 `PROVENANCE` 所记 sha256 **逐字节相同**的那份报告
   （`git show 7971545:docs/audit/pytest-report.json` →
   `sha256=4e4f70223bb8…49a8`，1096 passed / 1099，`source_commit=a660405`），
   归档为不可变路径 `docs/audit/pytest-report-v5.6.0.json`；
2. `release_evidence.py --test-report` 改指该归档件 ⇒ 发布证据重新只描述 v5.6.0 自己；
3. 每轮的 `docs/audit/pytest-report.json` 保留为**轮级**证据，与发布证据不再共用路径。

读法约束（写给下一轮，也纠正上一轮容易误读的一行）：
`production_release_gate --release-ready --tag v5.6.0` 的 8/8 **认证的是 tag 那一棵树的
测试结果（1096 例）**，不是本轮 1385 例；本轮这棵树的证据是「全量 1385 passed / 0 failed
+ ruff 0 + mypy 0（365 文件）+ 性能门 PASS」。二者不可互换引用。
另测得：`--release-ready` 不带 `--tag` 时锚点取 HEAD，而报告是在上一个提交上跑的，
`report STALE` 必红——所以**轮内不存在 8/8 的合法路径**，8/8 只在从 tag 检出跑测试时成立。
不要用 `AIPD_SOURCE_COMMIT` 把报告钉到 tag 上（`tests/conftest.py` 的该环境变量是发布流程
入口，在本轮用它等于用未发布的树冒充已发布提交，与黄金工件不重锚是同一条纪律）。

收尾读数（本轮，全部现场复算）：

| 门禁 | 读数 |
| --- | --- |
| `production_release_gate --release-ready --tag v5.6.0` | **8/8，exit 0**（认证 v5.6.0） |
| 全量 `pytest -q --json-report` | **1385 passed / 0 failed / 3 skipped**（collected 1388） |
| `state_perf_gate` | **PASS**：嵌套事务边际 23.6µs、批处理比 0.0456 ≤ 0.34 |
| `skill_quality_audit` | 0 警告 0 失败，exit 0 |
| ruff / mypy | 0 / 0（365 文件） |
| 工作树 | `git status --short` 空；提交未 push、tag 未动 |

