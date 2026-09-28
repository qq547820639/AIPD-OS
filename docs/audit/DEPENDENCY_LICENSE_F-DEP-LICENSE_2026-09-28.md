# 第 92 片：依赖许可证门禁（F-DEP-LICENSE）

量具：`scripts/dependency_license_gate.py`；台账：`docs/audit/DEPENDENCY_LICENSE_LEDGER.json`；
常驻：`tests/test_dependency_license_gate.py`（9 条）+ `--self-test`（5 格）；
电池：`docs/audit/s92/battery92.py`（7 支臂）；裁决文档：`docs/security/dependency-license-review.md`。

## 一、分母与原告（现读，四条命令）

| 读数 | 值 | 怎么来的 |
| --- | --- | --- |
| `pyproject.toml` 声明根 | 13 | `read_declared_roots()` 现读 |
| 闭包内的名字 | 45 | 对已装元数据做 BFS，跳过 `extra ==` 选装 |
| 逐包判到 | 43 | 其中两个名字本平台没装 ⇒ `unresolved` |
| 第三方 `Requires-Dist` 形态 | plain 71 / **extra 409** / 平台标记 11 | 直接遍历 `distributions()` |
| 已装发行包 | 71 个名字 / 72 份元数据（`aipd-os` 有两份） | `installed_index()` |
| 判红条数 | **1** | `casadi`，经 `cadquery` 可达 |

真原告的两份一手读数（不是记忆，也不是子代理转述）：
- 门禁现读 `casadi`：`field='GNU Lesser General Public License v3 or later (LGPLv3+)'`，
  `cls='OSI Approved'`，`expr` 为空 ⇒ 归一后 `lgpl-3.0-or-later`；
- PyPI `casadi` 的 `info.license` 同样是 `GNU Lesser General Public License v3 or later
  (LGPLv3+)`，而它的 classifier 也只有泛化的 `License :: OSI Approved`
  （https://pypi.org/pypi/casadi/json，本轮抓取）。
⇒ 这不是元数据填错的假原告：上游自己就只在 `License` 字段里给出答案。

## 二、选型（AGENTS.md 第三节：要拍的是"用什么实现这道门"）

### 二之一、候选清单（每条带可打开出处与亲验状态）

| 候选 | 出处 | 亲验状态 |
| --- | --- | --- |
| `pip-licenses`：列已装包许可证，带政策开关 | https://pypi.org/pypi/pip-licenses/json | 我本人抓该 JSON 并检索到：`--fail-on`（"Fail (exit with code 1) on the first occurrence of the licenses…"）与 `--allow-only`（"Fail … if none of the package licenses are in…"），`info.license` = **MIT**，运行时依赖 `prettytable>=3.12`（`<3.11` 还要 `tomli`）。本机实测 `find_spec('piplicenses')` 与 `find_spec('prettytable')` 都是 **False** |
| `license-expression`：SPDX 表达式的解析/归一/比较 | 本机已装发行包元数据（`importlib.metadata.metadata('license-expression')`） | 我本人现读：`License: Apache-2.0`、`Summary` 为 "…parse, compare, simplify and normalize license expressions (such as SPDX license expressions) using boolean logic"、`Requires-Dist: boolean.py>=4.0`。它在本机**在装**，但来源是 pip-audit 的传递依赖，我们没声明 |
| `nektos/act`：把 CI 整条跑在本地（第 91 片评估过） | https://github.com/nektos/act | 第 91 片我本人打开过主页（MIT、需 Docker API）。它解决"CI 那侧跑不跑"，不解决"许可证判不判" |
| 自研：stdlib `importlib.metadata` 信号阶梯 + 台账 | 本仓 `scripts/dependency_license_gate.py` | 本片实现，5 格自测 + 7 臂电池 |

未检索到第五个"专做依赖许可证白名单门禁且零依赖"的候选，如实记"未检索到"。

### 二之二、六维对比（只写可核验的结论）

- **功能匹配度**：`pip-licenses` 的两个开关是**政策形状**的成熟答案（allow-list / deny-list），
  但它作用在"许可证名字符串"上，而本仓的真问题恰在"名字从哪个元数据字段来"
  （casadi 只有 `License` 字段有答案，classifier 是泛化的）⇒ 拿它仍需自建阶梯；
  `license-expression` 提供的是 SPDX 布尔解析（`OR`/`AND`/`WITH`、`~`、`+`），比本片手写的
  "顶层 `OR`／`AND` 一层切分"完整，但本片实测语料里带括号/异常式的是 **0 例**，
  且我刻意把无法解析的表达式判成 `unknown-license`（红）而不是悄悄放行。
- **License 兼容性**：MIT（pip-licenses）与 Apache-2.0（license-expression）与本仓 Apache-2.0
  都并存，许可面不构成排除理由；`act` 是 Go 二进制，引进来要下载可执行文件（同一格里
  我把 CI 那条 `curl … gitleaks` 判成结构性 CI-only，理由对自家长相也成立）。
- **维护活跃度**：三者都活跃，但**具体版本与更新日期本轮未亲验**，不作为决策依据。
- **安全风险 / 覆盖面**：决定性一条——`ci.yml:56` 的 `schema-validation` job 只跑
  `pip install -e .`（无 `prettytable`、无 `license-expression`）。若门禁依赖未声明的第三方，
  它在那条 job 上只会 SKIP；**一道永远 SKIP 的门等于没有门**，而这正是本片在修的病
  （`license-scan` 那条裸 `pip-licenses` 就是这个形状：没有可失败断言）。
- **代码质量**：外部工具的 SPDX 正规化强于本尺（本尺只处理一层 `OR`/`AND`，带括号就判红），
  但本尺的判据核心不在解析而在**台账与两极**（`accepted` 才转绿、`needs-review` 继续红、
  forbidden 不许被台账吞）——那一层没有任何现成工具替我们做。
- **适配成本**：`pip-licenses` ⇒ 要新增 dev 依赖并在收口链里保证它装上（否则退化成 SKIP）；
  `license-expression` ⇒ 要把它写进 `pyproject` 声明（多一条真运行时依赖，为一层表达式解析不值）；
  自研 ⇒ 零新依赖，代价是 SPDX 词表要自己维护（`ALIASES`/`LICENSE_FAMILY` 两张表），
  而这两张表本身被常驻用例与电池管着。

### 二之三、择一决定：**自研 + 借语义**

选"stdlib 信号阶梯 + 台账"。**借 `pip-licenses` 的政策形状**：allow-list（本仓的
`LICENSE_FAMILY` 档位表）＋ deny-list 优先级（`forbidden` 压过台账）；
**借 `license-expression` 的形状约定**：许可证 id 用 SPDX 风格（`Apache-2.0`、
`LGPL-3.0-or-later`），台账里的串与现读值同一词表，才能做"逐字相等"对账。
不直接引两者的理由见六维第 4 条（永远 SKIP 的门）与第 6 条（判据核心在台账不在解析）。
若将来要支持括号表达式／`deprecated` SPDX 别名，再把 `license-expression` 写进 dev 档并替换
`parse_expression` 的内部实现——**接口形状不变，判据不变**，这条替换路径写在 §四边界 3。

### 二之四、落地处

- "CI 有 `license-scan` 但没人判它" ⇒ 门禁本体 `scripts/dependency_license_gate.py:audit()`
  的七档与 `main()` 的 0/4/2；
- "三信号全收、classifier 不优先" ⇒ `signals_of()` + `ALIASES` 里
  `"osi approved": ""` 那一条（泛化不算标注）；电池 **B2** 撤它就红；
- "`OR`/`AND` 不能拍平" ⇒ `parse_expression()` + `classify_branches()`；电池 **B3** 把它改回
  `any(...)` 即红（`test_or_branch_is_usable_but_and_pair_is_not`）；
- "台账不许自我放行" ⇒ `audit()` 的 `依赖许可证未裁定 …decision!=accepted` 与 `台账越权放行`
  两笔；电池 **B4**/**B5**；
- "看不见要签字" ⇒ `DECLARED_NOT_INSTALLED` + `声明的依赖没查过`；电池 **B6**；
- "未装的不算合规也不算红" ⇒ `unresolved` 只报；电池 **B7**；
- 三个选项与法务要拍的那一格 ⇒ `docs/security/dependency-license-review.md` §二
  与台账里那条 `needs-review`（**门禁今天保持红**）。

## 三、为什么这一片结束时门是红的（以及怎么让它合法地变绿）

这不是没收尾：`casadi` 的 LGPL-3 分发义务是否已被本仓发布形态满足，是**人的裁决**
（AGENTS.md §一停工条件 2：法务裁决类，线下项）。本片做的就是把"这个问题存在、谁拍、
拍完写在哪"钉成机器可见：台账 `decision` 从 `needs-review` 改成 `accepted`
 ⇒ 门禁与 `tests/test_dependency_license_gate.py::test_casadi_stays_red_until_a_human_adjudicates_it`
同时要求更新，转绿必须是**一次显式的决定**，不能是判据松动或条目挂上去。
本轮唯一由我自决的是口径：LGPL 归 `review`（不放行也不禁），MPL-2.0 归 `allowed`
（文件级 copyleft，本仓不改其文件；三条依赖 certifi/pathspec/pytest-metadata 走这一档）。

## 四、已知边界

1. 读的是当前环境**已装**发行包，不是 lockfile／解析器：换平台时覆盖面会变。
2. `extra ==` 的 requires 一律跳过；环境标记一律取并集不解析（保守，代价是闭包里含 dev 档的
   传递依赖，如 `pathspec`）。
3. 带括号的 SPDX 表达式与 `WITH` 例外不解析 ⇒ 该包落 `unknown-license` 判红；
   真要支持，替换 `parse_expression()` 内部为 `license-expression`，判据与接口不动。
4. 上游把许可证标错时本面看不见（读的是上游自述）。下一步可选：比对 wheel 内 `LICENSE` 文件正文
   （`importlib.metadata.files()` 拿得到路径），把"元数据说 MIT、打包文件是 AGPL"这种不一致
   也做成一格判红。挂到第 93 片入口。

## 五、认证读数（这一代一次跑通）

| 项 | 读数 |
| --- | --- |
| 干净全量（worktree `.wt-s92` @ `b541f3c`） | **2740 passed / 5 skipped / collected 2745**，396.3s，`exitcode=0` |
| 用例数增量 | 2736 → 2745，恰为本片新增的 9 条常驻用例（`--min-tests 2745` 由报告现取） |
| 报告自记清单指纹 | `71078cdade00…` == 磁盘 `SOURCE_MANIFEST.json`（绑定前后各核一次） |
| 被哈希文件数 | 688 → **691**，差集现算＝新增三条且零删除：门禁本体、它的常驻用例、`docs/security/dependency-license-review.md`（**这条顺带核实了 `docs/security/` 参与哈希**，只有 `docs/audit/` 被整体排除 ⇒ 裁决文档必须在最后一次 `release_evidence.py` 之前定稿，本轮就是这个顺序） |
| 发布门 | 8/8、`release_ready=True`、`GATE_RC=0` |
| 收尾验签 | 11/11、`CV_RC=0`；回收 worktree 后复算 `-b` 亦 11/11、`CVB_RC=0` |
| 门禁本身 | 闭包 45 名 / 逐包 43 / `allowed 42`、`forbidden 0`、`unresolved 2`、`declared-missing 1`、`out-of-closure 28`；**判红 1 条 = casadi/LGPL-3.0-or-later，台账 `needs-review`** |
| 自测与电池 | `--self-test` 5 格；`docs/audit/s92/battery92.py` **7/7 KILLED**、退 0；第 91 片电池 8/8、第 90 片 13/13、第 89 片 15/15、第 87 片 7/7 同批复跑仍全绿 |

上一片那两条"收口顺序"的教训这一片照做且都生效：跑批期间**不写仓库**（所以 `workspace_clean`
一次过），`-b` 复算**先入库再跑**（所以 `worktree_clean` 一次过）。
