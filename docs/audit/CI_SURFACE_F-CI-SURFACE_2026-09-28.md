# 第 91 片：CI 门禁面 ↔ 本地收口链对账（F-CI-SURFACE）

量具：`scripts/ci_surface_census.py`；消费表：`docs/audit/CI_SURFACE_REGISTER.json`；
常驻面：`tests/test_ci_face_gates.py`（ruff / mypy / schema_check 三面）+
`tests/test_ci_surface_census.py`（这把尺自己的牙）。

## 一、起因与分母（现读，不是推测）

第 90 片顺手清掉一条 `E501` 时记下："认证链不跑 CI 的 lint 口径"。本片去补那道门之前，
先把这句话量成一张表——把 `.github/workflows/ci.yml` 的 `run:` 命令逐条抽出来
（命令与 job 都按 workflow 现读，见 `docs/audit/s91/build_ci_surface_register.py`），得：

| 读数 | 值 |
| --- | --- |
| CI 的 job 数 | **17** |
| 会被单独执行的 shell 命令（按文本去重后） | **32** |
| 其中"本地收口链有归宿"的（本轮之前） | **0** |
| 本机 `which gitleaks` / `which act` | 都无 |
| 本机 `find_spec('pip_licenses')` | False；`build`、`pip_audit`、`cadquery` 都在 |

两个具体后果，都是一手复现而不是推断：

1. `ruff check src tests state_service`：第 90 片在 HEAD 复现出 1 条 E501
   （`tests/test_release_evidence_preflight.py:344`，自第 84 片起就在）。
   全量那一跑每次都报 2700+ passed，**没有任何一格读这条命令的结果**。
2. `mypy`：`ci.yml:130` 的注释写着「本地硬基线（ruff 0 / mypy 0）此前在 CI 不设防；
   补 lint job 使之成为门禁」——第 91 片现读是 **24 errors / 20 files**
   （`python -m mypy` → `Found 24 errors in 20 files (checked 478 source files)`）。
   ⇒ 那句话当时可能真成立过，今天不成立；而"补 lint job 使之成为门禁"只对 CI 成立，
   对本仓的收口链不成立。这就是**假叙述住在没人读的位置**的标准形状。

## 二、选型（AGENTS.md 第三节，四段齐全，动手前展示）

要拍的问题是：**用什么机制保证"CI 判的东西"在本地也真被判**。

### 二之一、候选清单（每条带可打开出处与亲验状态）

| 候选 | 出处 | 亲验状态 |
| --- | --- | --- |
| nektos/act：把 GitHub Actions 的 workflow 在本地跑一遍 | https://github.com/nektos/act | 我本人打开该仓库主页：**MIT License**；正文说明它靠 **Docker API** 拉镜像、起隔离环境来复刻 runner |
| pre-commit：框架化管理多语言 pre-commit 钩子 | https://raw.githubusercontent.com/pre-commit/pre-commit/main/README.md | 我本人抓到那句 "A framework for managing and maintaining multi-language pre-commit hooks."；**许可证与安装命令未亲验**（先经 GitHub 页超时，README 现版只剩徽章与外链，没写到那两格）|
| 自研一把"以 workflow 为权威面"的结构对账尺 | 本仓 `scripts/ci_surface_census.py` | 本片实现，四格 `--self-test` 已跑 |
| 只把三条命令抄进常驻用例（不建对账面） | —— | 不需要外部项目；作为"最省事方案"进对比 |

未检索到第四个同类候选（"专门对账 CI job 与本地门禁覆盖面"的开源工具我没找到），
如实写"未检索到"，不补位。

### 二之二、六维对比（只写可核验的结论）

- **功能匹配度**：要的不是"把 CI 跑一遍"，而是"**CI 加了/撤了一道门，本地要知道**"。
  act 执行 workflow，但它不产出"哪些命令本地没人消费"这张表；把 CI 的 13 个 job 全跑一遍
  也要 30 分钟以上，而收口链只有 ~6 分钟。第四个候选（只抄三条命令）解决今天的红，
  解决不了下个月 CI 新加一条时的静默。
- **License 兼容性**：act 是 MIT（我本人读到的徽章与 LICENSE 文件名），与本仓 Apache-2.0 可并存，
  但它是**Go 二进制**，引进来要走"下载可执行文件"这条路——与 CI 里那条 `curl … gitleaks …`
  同一族（我把它判成结构性 CI-only 的理由在这里同样适用于自己）。pre-commit 许可证未亲验，
  不据以决策。自研零新依赖（只用已在 `full` 档声明的 `pyyaml`）。
- **维护活跃度**：act 与 pre-commit 都是活跃项目——**这一条本轮不作为决策依据**，
  因为我没读 release 页，不写具体版本号。
- **安全风险**：act 要求 Docker，而本机 `which docker` 有、`which act` 无；
  要跑得先引入一个能拉起容器的第三方执行面，且 CI 里那些 job 本身 `pip install` 联网装包。
  把联网安装放进认证路径＝给认证加一个不可控依赖面（第 81 片那条 pillow/CVE 的教训同族）。
  自研只读两个文件（workflow + 册子），不执行任何 CI 命令；真正执行的是三条常驻用例。
- **代码质量**：外部工具对 YAML/shell 的解析成熟度高于本尺（本尺的粒度是"一行一条命令"，
  且 `line` 恒 0——见 §四边界 1）。但它们都不表达"消费方是谁"这个概念，接进来仍要自建这张表。
- **适配成本**：act ⇒ 装二进制 + 起容器 + 改 job 以适配本地（`.[full,dev]` 那类安装要在容器里重跑）；
  pre-commit ⇒ 只在 **commit 那一刻**、且**只在装了钩子的那个克隆**里生效——
  本机实测 `.git/hooks/` 里没有 `pre-commit`（只有 `post-checkout`、`post-commit` 两个非 sample 钩子），
  而本仓的判定发生在 commit **之后**（清单/证据/门/验签），钩子跑不到那一层；
  自研 ⇒ 一个脚本 + 一份册子 + 一个常驻文件，与第 60 片那把尺同形状，成本已被验证过一次。

### 二之三、择一决定：**借语义自研**

选"自研结构对账尺 + 三条命令接进常驻"。**借的是 act 的一个观点**：
以 workflow 文件为唯一权威面，本地**不复制一份命令清单**（复制一份就会漂一次）。
这一点不是口号——消费表的键一律由 `ci_commands()` 从 ci.yml 现读生成，
生成脚本 `docs/audit/s91/build_ci_surface_register.py` 里只写**子串规则**；
任何一条命令没被唯一接住就整批不落盘（本轮它真的拦下一次：
`python -c "import cadquery as cq; …"` 一开始没有规则接它）。
不引 act 的理由如上；不用 pre-commit 的理由是**执行时机与 enforcement 面都不对**。

### 二之四、落地处（每条结论指到它实际改动的文件）

- "CI 每条命令都要有归宿" ⇒ `scripts/ci_surface_census.py:audit()` 的
  `CI面无人守` / `CI面空头委托` / `CI面免跑没理由` / `消费表该撤` 四档判决；
- "权威面只有一个" ⇒ `docs/audit/s91/build_ci_surface_register.py`（现读生成）+
  `tests/test_ci_surface_census.py::test_commands_are_read_from_the_workflow_not_from_a_copy`
  （册子里每条命令必须逐字出现在 ci.yml 里，且比较前同样折 `\` 续行）；
- "免跑不许变成后门" ⇒ `kind: ci-only` 必须带 `why`，否则判红
  （`tests/test_ci_face_gates.py::test_register_points_here_and_only_here` 与
  `--self-test` 第三格各钉一端）；
- "登记面 ↔ 执行面也要互点" ⇒ `tests/test_ci_face_gates.py`（量具只核到文件级，
  "这个文件到底跑了哪几条命令"只能在这里钉）；
- 三条命令真跑 ⇒ `tests/test_ci_face_gates.py` 的 `test_ruff_face_is_clean` /
  `test_mypy_face_is_clean` / `test_schema_check_face_is_clean`（缺工具 `pytest.skip`，
  不把"未覆盖"报成绿）。

## 三、分类依据（13 条"结构性免跑"逐条给因）

* 安装与解包（`python -m pip install --upgrade …`、六种 `pip install -e ".[…]"`、
  `pip install pip-audit/pip-licenses/build`、`curl … gitleaks …`、`tar -xzf …`）：
  要联网装包或往 `/usr/local/bin` 写文件。后者是**共享状态动作**，不属自决范围，
  所以不是"我没想到"，是"我不该在收口链里做"。
* `gitleaks detect`：本机无该二进制（实测 `which gitleaks`），且它扫提交历史，
  而收口链跑在 detached worktree 上——历史面不在这一格。
* `python -m build`：会往 `dist/` 落产物，而收口链硬要求工作树干净
  （`closeout_verifier` 的 `worktree_clean` 无豁免路径）。打包一致性另由
  `tests/test_packaging.py` 在本地判，那一格已登记。
* `pip-licenses`：**这条最值钱**——它根本没有可失败的断言（只把许可证打印出来，退出码恒 0），
  把它当门禁是假承诺。登记成免跑并写明理由，比假装它被覆盖了诚实。

19 条"已接住"里，`-m pytest` 系（10 条）一律记在 `scripts/closeout_verifier.py` 名下，
理由是现读的：本地全量那一跑是**无标记的超集**（collected 2726，`integration` 打标的
21 条都在名单里，5 条 skipped 是 smtp/imap/arxiv/pmc 这类真网络项，不是 CAD——
`cadquery` 本机在盘且 28 条 CAD 用例都真跑了）。"谁跑遍了整棵树"由
`roster_covers_tree` 那一格证，不是由我在文档里说。

## 四、已知边界（写清是哪一种）

1. `line` 恒为 0：PyYAML 的 `safe_load` 不带行号，判据要靠 `compose` 才拿得到标记。
   违规行因此按 **job 名 + 命令文本**定位（消息里带 `CI 的 'lint' job`）。
   属"本轮没做"，不是机制限制。
2. 命令文本按"一行一条"切，不看 shell 的 `&&`/`||` 与 `for` 循环：
   `a && b` 会被当成一条。今天 CI 里没有这种写法（实测 32 条里 0 条含 `&&`），
   所以不咬现状；CI 若改用 `&&`，本尺会把它当一个整体命令要求登记，不会静默漏判。
3. "consumed" 的判据是**归宿存在且有效**（文件在、`tests/` 下的还要求真有用例），
   不是"逐字复现 CI 的执行环境"。例：`python scripts/audit_repo.py --json-out …`
   记给 `tests/test_audit_repo.py`——同一份判据在进程内跑，落盘那一份不是新判据。
   这一格是刻意的粒度选择，写在这里以免下一轮把它读成"等价执行"。
4. CI 是否真的在跑、跑成什么颜色：未验证。本机 `gh auth status` 报
   "You are not logged into any GitHub hosts" ⇒ 拿不到 Actions 的历史。
   属**机制限制 + 线下项**（要真人登录）；本片的判据不依赖那一面——
   我以本地逐字复现 CI 命令代替（ruff/mypy/schema_check 三条都亲手跑过，读数见 §一）。
