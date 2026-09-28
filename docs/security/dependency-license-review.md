# 依赖许可证审查（F-DEP-LICENSE，第 92 片起持续）

机器面：`scripts/dependency_license_gate.py`（判档）、`docs/audit/DEPENDENCY_LICENSE_LEDGER.json`
（逐包裁决台账）、常驻牙 `tests/test_dependency_license_gate.py`。
本文只负责**人说的那部分**：为什么某一档要放行、要谁拍、依据是哪份原文。

## 一、为什么要有这一面

CI 的 `license-scan` job 跑的是裸 `pip-licenses`：它只打印表格，**没有可失败的断言**
（第 91 片把它登记成"结构性免跑"时写的就是这个），所以"本仓做过许可证审查"在机器层面
一直没有对应的事实。而仓里明明写过一次判断——`pyproject.toml` 里选 `pypdf` 而不用
`PyMuPDF` 的理由是"后者 AGPL-3.0，与本仓的 Apache-2.0 不兼容"——那是散文，没有任何尺子复查。

本面把这条判断变成判据：闭包内每个包都要落一档；`GPL/AGPL` 家族直接红；
`LGPL` 家族要台账裁决；**三个元数据信号都给不出具体许可证**也算红（"看不见"不等于合规）。

## 二、当前唯一的开放项：`casadi`（LGPL-3.0-or-later）

**它怎么进来的**（本机元数据现读，不靠记忆）：`cadquery` 的 `Requires-Dist` 里有 `casadi`，
且**没有** `extra ==` 标记 ⇒ 属于 `cad` 档的硬依赖，不是选装。

**上游怎么标的**（两份一手读数）：
- PyPI `casadi` 的 `info.license` =
  `GNU Lesser General Public License v3 or later (LGPLv3+)`；
- 它的 classifier 只有 `License :: OSI Approved`（**泛化**，没有具体许可证）。
⇒ 这一格直接决定了取信号的方式：`License-Expression`（PEP 639 的 SPDX 串，最精确）、
`License` 字段、`License ::` classifier 三者**全收**，不给 classifier 优先权。
只看 classifier 的阶梯会把 casadi 读成"未标注"，从而**放过一条 LGPL 依赖**。

**LGPL-3 对"使用它的程序"要求什么**（依据 https://www.gnu.org/licenses/lgpl.html 原文）：
- "使用库的程序"（work that uses the library）与库本身在法律上是分开的；
  原文：*"Defining a subclass of a class defined by the Library is deemed a mode of using an
  interface provided by the Library."* ⇒ 本仓调用它不等于本仓必须以 LGPL 发布；
- 但有**分发义务**：需明示使用了该库并指明其许可证、随 Combined Work 附上
  LGPL 与 GPL 文本、并保证下游能替换该库（动态链接或提供"最小源码"）；
  原文：*"Accompany the Combined Work with a copy of the GNU GPL and this license document."*
- 若**修改库本身**才触发更强的 copyleft（本仓不修改 casadi，只 import 它）。

**要拍的是什么**（我不替人拍）：本仓的发布物是**源码归档 + 可编辑安装**（`SOURCE_MANIFEST` /
`RELEASE_MANIFEST` / `BUNDLE_MANIFEST` / `PROVENANCE`），不是自包含二进制；
"发布时是否已经满足上面三条分发义务"取决于发布形态与随附文件，属法务/属主裁决。
选项与各自后果：
1. `accepted` —— 认定 `cad` 档的发行形态满足 LGPL 义务；要在 `docs/security` 与发布物里
   补"使用了 CasADi（LGPL-3.0-or-later）+ 两个许可证文本 + 替换方式"三件；
2. 把 `cadquery`/`casadi` 从发布档移到"仅本地/仅内部"档（不对外分发）⇒ 义务面消失，
   代价是 `cad.parametric_model` 的成熟度口径要改；
3. 换一个非 LGPL 的优化内核 ⇒ 代价最大，需要重做选型。
**在拍板之前门禁保持红**：台账里那条 `decision` 现在是 `needs-review`，
门禁读到它就报"未裁定"（这一格在真仓库上就是第二把原告，不只在合成语料里）。

## 三、闭包里其余 42 个包的归属（现读，不抄数）

`allowed 42 / forbidden 0 / unresolved 2 / declared-missing 1 / out-of-closure 28`（逐包读数由
`--json` 的 `rows` 与 `buckets` 给，本文不抄绝对数——第 87 片起这条是硬规矩）。
其中三个值得点名：
- `certifi` / `pathspec` / `pytest-metadata` 是 **MPL-2.0**：文件级 copyleft，
  本仓不修改它们的文件 ⇒ 政策上直接允许，不需要逐包裁决；
- `cryptography` 是 `Apache-2.0 OR BSD-3-Clause` 双许可 ⇒ 任一分支可用即放行，
  这也是为什么解析必须保留 `OR`/`AND` 结构（`MIT AND LGPL-2.1` 不能因为含 MIT 就变绿）；
- `mcp`（`server-mcp` 档）在当前环境装不上 ⇒ 它的许可证**从没被看过**，
  这条缺口写在 `DECLARED_NOT_INSTALLED` 里并要理由；新出现的装不上依赖没登记就判红。

## 四、已知边界

1. 读的是**当前环境里已装发行包的元数据**，不是 lockfile/解析器：换平台（`sys_platform` 标记的
   依赖被装上）时覆盖面会变，未装的计入 `unresolved` 只报不判。
2. 环境标记一律取并集（不解析 `python_version < "3.11"` 之类），但 `extra ==` 一律跳过：
   本环境 480 条第三方 requires 里 409 条是选装，展开它们会让分母从 45 涨到 169、
   其中 117 个从未安装 ⇒ 判据会被"未安装"淹没，那不是保守是失聪。
3. 带括号的 SPDX 表达式（`A OR (B AND C)`）不解析 ⇒ 该包落 `unknown-license` 判红，
   逼人来登记台账，不静默放行。
4. ~~上游元数据标错许可证时本面看不见（它读的是上游自述）；真要防这一格得比对
   打包内的 `LICENSE` 文件正文——挂在下一片的入口清单里。~~
   **第 93 片已把这一格接上**（正文面见 §五），剩下的看不见面写在 §五 末尾两条。

## 五、正文面（第 93 片加的第二个读入面）

上面 1-4 条的判断只读**上游自述**（元数据三信号）。第 93 片起，门禁还会打开 wheel 里
打包的许可证文件正文（只认 `*.dist-info/**` 下的 `LICENSE*` / `COPYING*`）对一次账：
正文断言的档位比元数据**更严** ⇒ 判红 `许可证正文与元数据打架`。

现读（2026-09-29，本机环境；分母由 `python docs/audit/s93/probe93_license_bodies.py` 自报）：
闭包内 43 个已装包读到 48 个 dist-info 正文文件；37 个可与元数据比档，1 个没有正文
（`casadi`——它只打包了 58 份 vendored 第三方许可证，自己的 LGPL 正文**不在轮子里**），
5 个头部认不出（certifi / multimethod / nlopt / pillow / typing-extensions），
8 个正文里提及了比元数据更严的家族。**今天 0 条判红是正文面报的**：这一面是防御性加严，
牙齿在常驻用例与变异电池里，不在真语料上。把防御性改动报成活缺陷，下一轮就无从判断
还剩多少真风险，所以这一句必须写在这里。

两格**属主该看一眼**的只报档（本面按边界不判红，理由见取证文档 §四边界 2）：

- `nlopt`：元数据 MIT，正文提及 `LGPL-3.0-or-later` —— 那是它 bundled 的 NLopt C 库。
  若链接方式是把 LGPL 代码静态编进产物，义务形状与 §二 的 casadi 同类（动态链接 vs 静态内嵌）。
- `cadquery-ocp`：元数据 Apache-2.0，`LICENSES_bundled`（698KB）逐条列了它捆绑组件的
  许可证，含 GPL/LGPL/AGPL 名字。这一格要不要升级为待裁项，取决于「vendored 组件的许可证
  算不算本依赖的许可证」这条口径——属主拍。

同名多份元数据记录：`aipd-os` 在本机有两份（wheel 的 `.venv/.../aipd_os-5.6.0.dist-info` +
遗留 `src/aipd_os.egg-info`）。现在两份档位一致所以不判红，只把「重复安装记录」变成可见事实；
清掉遗留 egg-info 是属主动作（删文件不可逆），不在量具的自主范围。

本面仍然看不见的两格（写清楚，别让"加了正文面"读成"许可证面已经闭环"）：
① 正文里**提及**的更严第三方（bundled 列举、quoted 全文）一律只报不红，
② 头部窗口（前 8 个非空行）之外没有标题行的短声明落"认不出"，也只报。
