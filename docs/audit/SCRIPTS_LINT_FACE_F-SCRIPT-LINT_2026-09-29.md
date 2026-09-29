# `scripts/` 进 lint 面：测量基线棘轮（F-SCRIPT-LINT 第 100 片）

日期：2026-09-29　归属：F-SCRIPT-LINT（第 99 片 `docs/audit/SCRIPTS_LINT_FACE_RULING_2026-09-29.md`
§5.1 已定为 **B**；本轮实施时把 B 的形状改了一次，改动理由在 §二）

## 一、这一片问的两个问题

1. **接哪一面**：CI 的 ruff 门只跑 `ruff check src tests state_service`，`scripts/` 整个不在面上。
   面外有多少债、接进来会不会当场把 CI 判红？
2. **接进来之后怎么保证不再退**：一面只覆盖"零债的那批"的话，剩下的 44 个文件写多少新债都没人看；
   而把整目录并进面又要先偿清 642 条。中间那条路怎么走，且**怎么让它是机器判的而不是文档里的一句话**。

## 二、技术选型（四段）

### 候选清单

1. **B1：ruff 原生 `[tool.ruff.lint.per-file-ignores]`**（配置文件里按 文件×规则码 豁免）。
   出处=本机 `ruff 0.16.1`（`.venv/bin/ruff --version` 现读）+ 我实际跑的两臂：
   临时配置 `/tmp/pfi2/pyproject.toml` 给 `scripts/manual_chain.py` 豁免 `E702`
   ⇒ 该文件命中 **126 → 40**（E702 那 86 条被吞），无豁免时 126。
2. **B2：测量基线 + 棘轮**（本仓既有那一族：消费表 / 根路径名册 / 许可证台账——
   生成件由 `--emit` 现算，判据把今天的测量与登记的基线逐格比）。
3. 外部现成工具：**未检索到**。以"ruff baseline / ratchet / 只判新增"为问法搜到的是教程与
   issue（如 astropy 的 `Ensure compliance with more Ruff rules` #14818，**只按搜索结果标题引用，
   正文未亲验**），没有可引进的 baseline 机制；ruff 侧本身也没有基线概念
   （`--config` 只接受简单 TOML 键值，`lint.per-file-ignores={<table>}` 这种复杂值直接
   `error: invalid value` —— 这是我本轮实测到的 CLI 边界）。

### 六维对比（B1 vs B2）

| 维度 | B1 per-file-ignores | B2 测量基线棘轮 |
| --- | --- | --- |
| 功能匹配度 | **反了**：它要表达的是"这个文件这类问题永远不报"，而我们要的是"这一格只能变少"。同码新增命中一起被吞 | 逐 `(文件, 规则码)` 记数并只许下降，正是问题本身 |
| License 兼容性 | 无新增依赖 | 无新增依赖（只用已装的 ruff 作测量仪） |
| 维护活跃度 | 随 ruff 走（本仓钉 `ruff>=0.4`） | 自家 ~250 行，与同族量具同形 |
| 安全风险 | 无外部执行面 | 只调 `python -m ruff` 读 stdout，不执行被检码 |
| 代码质量 | 零代码 | 与 `ci_surface_census` / `build_forensic_root_register` 同骨架（`measure/audit/emit/render/--self-test`），读者不用学新形状 |
| 适配成本 | ~15 行配置，**但要把"只能变少"补成判据就得再写一个数器，且那个数器必须能绕过豁免**（见下） | 一个新量具 + 一个生成件 + 一个常驻文件（10 条）+ 一支电池（6 臂） |

### 择一决定：**B2（自研，借语义）**，并**摘掉 B1**

决定性理由不是工作量而是**可见性**：B1 把债藏进配置——判据若也走同一份配置，就永远数不到被豁免的
命中；要让棘轮数到真数，只能给 ruff 再喂一份"去掉 per-file-ignores 的镜像配置"，
那是**把 pyproject 的规则集抄第二遍**（本仓反复踩过的"一个配置值只认一个来源"）。
所以 B1 的"简单"是假的：它省下 15 行配置，换来一个必须复刻判据的数器。
B2 借的是**同族量具的架构**（生成件 + 双向对账 + 只报不红那一档 + 前提塌不许折成零风险），
不借任何外部实现。第 99 片代价单里写的"B1 先上、B2 补棘轮"这个组合**本轮被实测推翻**，
已把该结论在原文里标注为已废（见 §六）。

### 落地处（每条结论指到它真改的文件）

| 结论 | 落在 |
| --- | --- |
| 面必须真扩到 `scripts/` | `.github/workflows/ci.yml:144`（命令现点名 16 个 0 债文件，544 列） |
| 键不能抄两遍 | `tests/test_ci_face_gates.py`：`SCRIPTS_LINT_FACE` 一份清单 ⇒ `RUFF_CMD` 由它拼 ⇒ `COVERED` 的键与 argv 同源；`test_register_points_here_and_only_here` 里"整串要能在文件里找到"这一格改成**钉 `RUFF_CMD == ci.yml 那条命令`**（派生键不在源文件里出现字面量，钉权威面比钉字符串强） |
| 债只能变少 | `scripts/scripts_lint_ratchet.py` 五档判决 + `docs/audit/SCRIPTS_LINT_BASELINE.json`（生成件，138 格） |
| 豁免不许只涨不消 | 同文件的 `lint面基线该撤` / `lint面文件未覆盖` 两判 |
| 接面这件事本身要被机器核 | 同文件的 `lint面直连清单不同源`：ci.yml 点名的文件集合 == 今天的 0 债集合 |
| 牙 | `tests/test_scripts_lint_ratchet.py` 10 条；`docs/audit/s100/battery100.py` A0 + 6 支撤销臂 **KILLED 6/6** |

## 三、判据与口径

- 分母：**跑真 ruff**（`python -m ruff check --no-cache --output-format concise scripts`），
  不镜像规则集、不 `--isolated`（那会退成默认集——本轮实测默认集对 `a = 1; b = 2`
  **只报 F841 不报 E702**，所以借它数债会少一半）。
- 单位：`(文件, 规则码)` 一格；每格落且只落一档：持平 / 上涨 / 未登记 / 已偿待撤 / 可下调。
  `Σ(五档) == 并集格数` 由常驻用例断，空档也**先显式建键**——`Counter` 里"没有这个键"与
  "这个键是 0"对下游是两件事。
- 只报不红那一档：`可下调`（登记比现实宽松）。它不是原告，但必须在 `outside` 与 `--json` 里露头，
  下一轮 `--emit` 就该把它拧下来。
- 前提塌（退 2，不折成"零债"）：基线读不到 / 基线缺键 / ruff 跑不起来 / 语料一个 `.py` 都没有 /
  ruff 退 1 而我解析出 0 行（那是尺子瞎了）。
  **注意"债全偿完"不算前提塌**：ruff 退 0 + 语料非空 = 合法的空册，`--emit` 会写明"全部 0 债"。
- 终态出口：如果哪天 60 个文件全部 0 债，`lint面直连清单不同源` 允许 ci.yml 退回点名整目录
  （`scripts` 出现在命令里即合规），免得这套尺把自己锁死在"逐个文件名"上。

## 四、读数（一手，2026-09-29）

```
ruff check --no-cache scripts                     ⇒ 642 条命中 / 60 个文件 / 44 个有债 / 16 个 0 债
scripts/scripts_lint_ratchet.py --emit            ⇒ 138 格 / 642 条 / 60 个文件（其中 0 债 16 个）
scripts/scripts_lint_ratchet.py                   ⇒ rc=0
  语料 60 个 .py（有债 44 / 0 债 16），命中 642 条 / 19 个规则码，基线 138 格，ci.yml 直连 16 个文件
  档位：持平 138 / 上涨 0 / 未登记 0 / 已偿待撤 0 / 可下调 0（求和 138 == 并集 138）
scripts/scripts_lint_ratchet.py --self-test       ⇒ --self-test：9 条合成读数全部对上，rc=0
ruff check <ci.yml 那条命令逐字>                   ⇒ rc=0（19 个参数）
pytest tests/test_scripts_lint_ratchet.py         ⇒ 10 passed
pytest tests/test_ci_face_gates.py tests/test_ci_surface_census.py ⇒ 19 passed（镜像三连同批改过）
mypy                                               ⇒ 0 error
docs/audit/s100/battery100.py                      ⇒ 合计 KILLED 6 / 6，收尾 sha 相等，靶文件债=无
```

## 五、电池教的那一格：债中性

靶文件自己就在被量的面上（`scripts/*.py` 会被 ruff 数）。第一版四支臂写成 `if False and …`，
ruff 把常量条件判成 **SIM223** ⇒ 基线凭空多一格"未登记" ⇒ 那几支臂"被抓住"是**因为夹具变了
而不是因为判据变了**。电池因此多一道别处没有的门：每支臂落笔前后各数一次靶文件命中，
不等就记 BAD-ANCHOR 而不是 KILLED。第一跑实测把 4 支挡成 BAD-ANCHOR（0 支误判 KILLED），
换成债中性的形状（阈值抬到 `want + 999`、比较式自反化 `face == face`、标记名改掉、
`return 2` 换 `pass`）后 6/6 KILLED。

另有两支**如实记录、不收录**的等价变异：
`emit()` 里 `zero` 这个统计量（只进打印，不进任何判决）；`render()` 的 `rowsum`
（只影响人读的那一行，`rows` 由 `buckets` 单独给）。

## 六、代价单里被本轮推翻的一句

`SCRIPTS_LINT_FACE_RULING_2026-09-29.md` §2.2 第 3 点写的是"**先 B1 后 B2**，
B1 借 ruff 的接口语义……必须借 B2 的思路补一条常驻断言"。本轮实测把它改成**只做 B2**：
B1 的豁免语义与"数到真债"这对矛盾不能靠"补一条断言"消掉，只能靠再复刻一份配置，
而复刻配置就是把判据的规则集抄第二遍。该结论已在原文就地标注（不在旧文里追加更正句）。

## 七、还没闭的（不把线下项洗成已做）

- **44 个文件的 642 条债还在**，本面只保证"不再变多"。逐片偿债是长期项；
  三个文件占 295/642（`manual_chain` 126 / `aipd_state` 114 / `aipd_store` 61），
  `manual_chain.py` 一个文件就有 E702 86 条——第一刀该切它。
- **mypy 半边不接**：`mypy scripts` rc=2（模块名撞车，面立不起来），
  `--explicit-package-bases` 后 78 errors / 23 files。这是技术判断，不是待裁项。
- **`EMPTY_EXCEPT` 记号与 ruff 的 `# noqa` 语法对撞**（6 处警告 + `src/` 里 3 处，面内 rc 仍 0）：
  改名要同时动 `tests/test_exception_hygiene.py` 的判据文案与 9 处记号，且与 `SIM105` 的建议互相
  拆台（同一批 try 块两边各说各话）。留给单独一片，本轮不动。
- **债务偿还本身**没做（上面第一条），且 `--emit` 的下调窗口要靠人接着跑：可下调档今天 0 格，
  偿完一片之后才可能出现——那一格的读数不进任何判决，所以它不会自己催。

## 七之二、偿债批次表（第 101 片现算，供第 102 片起直接执行）

分母全部来自 `docs/audit/SCRIPTS_LINT_BASELINE.json`（138 格 / 44 个有债文件 / 642 条命中），
`--diff` 档来自 `python -m ruff check --no-cache scripts --diff`（**不落盘**，rc=1 只表示有建议改动）。

| 规则码 | 命中合计 | 形状 | 能不能机械吃 |
| --- | --- | --- | --- |
| E702 | 265 | 多条语句一行（`;`） | 否——要逐行拆，且拆行会移动后续所有行号 |
| E501 | 191 | 超长行 | 否——换行位置要人判（中文注释与 f-string 尤其） |
| E701 | 98 | 复合语句一行（`if x: y()`） | 否 |
| I001 | 28 | import 未排序 | **是**（ruff 自带 fix） |
| E401 | 16 | 一行多个 import | **是** |
| F401 | 13 | 未用 import | **是**，但要逐条看是不是"留着备用"的意图 |
| SIM105 | 5 | 建议 `contextlib.suppress` | 是——**但这一族不许现在动**，见下面第四批 |
| UP045 | 5 | `Optional[X]` → `X \| None` | 是——但 `requires-python >=3.9`，运行期注解要另判 |
| 其余 | 21 | 散在小码 | 逐条 |

集中度：`manual_chain.py` 126 / `aipd_state.py` 114 / `aipd_store.py` 61 = **295/642＝46%**，
后面依次 26 / 25 / 24 / 23 / 18 / 18 / 17。⇒ **机械档一次能吃掉的只有 I001+E401+F401＝57 格（≈9%）**，
`--diff` 实测覆盖 30 个文件、单文件最多 3 个 hunk，大头（E702+E501+E701＝554 格）只能逐行改。

排批（按"改完能不能一把接进 CI"切，不按"哪个文件最脏"切）：

- **第一批（机械）**：I001 / E401 / F401 / UP045。改完把**清零**的文件逐个点名进面（见下面那三条同改）。
  **【第 102 片已做，UP045 留在这里没做】** I001+E401 由 `--select I001,E401 --fix` 一口吃掉
  （现读 "30 fixed, 0 remaining"，26 个文件 +116/−34）；F401 那 13 条**逐条读过再分档**，
  因为它不是机械档：`scripts/aipd_supervisor.py` 的 7 条是**按设计 re-export** 的兼容 wrapper
  （文件头 docstring 第 2 条 + 它列在 `releases/*/RELEASE_MANIFEST`），`--fix` 会把对外表面删掉
  而文件"看起来更干净"。处置取 `__all__` 声明清单而不是逐行 `# noqa: F401`（ruff 对 `__all__`
  里的名字不再报 F401，由该文件随后进 0 债集合现算证实），并补常驻两极
  `tests/test_supervisor_package.py::test_wrapper_declared_surface_is_the_import_block_and_resolves`
  ——注入反证：`__all__` 少写一个名字当场 `FAILED`。其余 6 条是真死的 import，删。
  结果：基线 138 格 / 642 条 ⇒ **89 格 / 584 条**，有债 44 ⇒ **40**，0 债 16 ⇒ **20**，
  `ci.yml:144` 与 `tests/test_ci_face_gates.py` 的清单同批 16 ⇒ 20，棘轮 rc=0。
  主树全量（非认证那一跑）2789 passed / **3 failed**，三条红是"tests 未提交"与"清单未刷"那一族
  已知形状（`test_roster_gap…` + 两条 `*_manifest_hashes_match_disk`）⇒ 行结构改动无行为回归。
  **UP045 没做**：`requires-python >=3.9` 下把 `Optional[X]` 写成 `X | None` 只在注解求值时机上安全，
  这 5 处得逐条看是不是运行期真会被求值（如 pydantic/typing.get_type_hints 路径），不属于"机械档"。
  **一次工具复用失败**：`docs/audit/s100/patch_ci_lint_face.py` 不能再用来加文件——它的一次性锚写的是
  "迁移前的旧命令行"，接完面就永不命中，本轮它 BAD-ANCHOR 且一个字节都没落盘（两阶段闸门按设计拦住）。
- **第二批**：`manual_chain.py` 的 E702 86 条（本片 §七 已点名为第一刀）——先决条件是"这个文件有没有
  被任何常驻工具按 `file:line` 钉住"，拆行会把后面的行号整体下移；派了只读普查，读数回来才动手。
- **第三批**：E501 的 191 条按文件收（`aipd_store.py` 29 条最多）。
- **第四批（挡住，不许顺手做）**：`SIM105` 与 `# noqa: EMPTY_EXCEPT` 那 5 处同一批 try 块
  （`scripts/aipd_store.py:194/285/289` 等）——照 ruff 改就要删 `except …: pass`，连带把豁免记号一起
  没地方放；只删记号保留 `pass` 则 `tests/test_exception_hygiene.py:66` 立刻红。
  这一批的前置是"记号改名"那件事（§七 第三条），顺序错了就是两边轮流红。

**每一批都必须同批改的三条镜像**（第 100 片实测过"少改一条会怎样"）：
文件债清零 ⇒ ① `scripts/scripts_lint_ratchet.py --emit` 把登记值拧下来（否则那一格落进
「已偿待撤」**判红**）；② `.github/workflows/ci.yml:144` 那条命令把这个文件**点名加进去**
（否则「lint面直连清单不同源」判红）；③ `tests/test_ci_face_gates.py` 的 `SCRIPTS_LINT_FACE`
清单同步——那里 `RUFF_CMD` 是由清单拼出来的，改一处就两处同源，**不许在第二处再抄一遍命令串**
（第 100 片写过两版字面量，实测 `KeyError`）。

## 八、认证读数（一手，2026-09-29 收口后填）

干净签出 `.wt-s100`（绝对路径、仓库**外**）在 `28b507a` 上跑全量：
**2790 passed / 5 skipped / 0 failed，collected 2795，398.5s，exitcode=0**，
报告自带清单指纹 `8fa29399bddf`（日志 `docs/audit/s100/run-s100.log`）。

`bash docs/audit/s100/closeout100.sh` 一次跑通，四道退码 `BIND=0 GATE=0 CV=0`（逐项见
`closeout100.log`、`gate100.log`、`closeout.json`、`gate.json`）：

| 步 | 现读 |
| --- | --- |
| 硬前提 | `PRECHECK OK: 2790 passed / 5 skipped / collected 2795 / 398.5s`；跳过面与上一代**逐条相同 5 条** |
| 一次绑定（两旗同给） | `BIND_RC=0`，回读 `source_commit=a66040520139`、`test_report=2790p/0f/2795t`、`fp=8fa29399bddf` ⇒ 提交 `721e1d4` |
| 发布门 | `GATE_RC=0`，`release_ready True / 未过 无 / 项数 8` |
| 门读数先入库 | `GATE_COMMIT_RC=0` ⇒ `ee0c5c8`（未跟踪也算脏，所以取证件排在验签之前） |
| 收尾验签 | `CV_RC=0`，**11 格全绿**，含 `size_ratchet：名单 2795 条 ≥ 下界 2795`、`roster_covers_tree：树 225 文件 / 2700 个 def ↔ 报告 225 文件 / 2795 条，双向差集为空` ⇒ `c01dce2` |

签出回收（`git worktree remove --force` ⇒ `git worktree list` 只剩主树）后 B 档复跑：
`GATE_B_RC=0 / 8 项全过`、`CV_B_RC=0 / 11 格全绿`，复跑当时 `git status --short` **0 行**
（`gate-b.json`、`closeout-b.json`、`gate100-b.log`、`closeout100-b.log`）。

**B 档第一跑被判红过一次，如实记**：那版把 `--json-out`/`--json` 直接写进
`docs/audit/s100/`（树内），于是 `✗ worktree_clean：工作树有 1 处未提交改动：
['?? docs/audit/s100/gate-b.json']`（`CV_RC=4`，其余 10 格仍绿）。这是**量具把自己的产物
写进被它检查的树**（同一形状第 99 片已记过一次），不是发布状态变了：改成一落树外、
读完后才 `cp` 入库，同一棵 HEAD 立刻 `rc=0`。取证件面本轮无新增 `.py`/`.sh`，
名册重 emit 后仍是 **73 条**且与已提交版本逐字节相同。

## 九、第 102 片认证读数（一手，2026-09-29）

机械档那一跑一次通过：干净签出 `.wt-s102`（绝对路径、仓库**外**）在 `d411350` 上跑全量
⇒ **2792 passed / 5 skipped / 0 failed，collected 2797，exitcode=0**，报告自记清单指纹
`44b85d697b46`（日志 `docs/audit/s102/run-s102.log`）。

`bash docs/audit/s102/closeout102.sh` 四道退码 `BIND=0 GATE=0 CV=0`：

| 步 | 现读 |
| --- | --- |
| 硬前提 | `PRECHECK OK` + `SKIP 面逐条相同：5 条`（与上一代双向差集为空） |
| 一次绑定（两旗同给） | `BIND_RC=0`，回读 `source_commit=a66040520139`、`2792p/0f/2797t` ⇒ 提交 `64b5bbc` |
| 发布门 | `GATE_RC=0`，`release_ready True / 未过 无 / 项数 8` |
| 收尾验签 | `CV_RC=0`、**11 格全绿**，含 `roster_covers_tree：树 225 文件 / 2702 个 def ↔ 报告 225 文件 / 2797 条，双向差集为空`、`size_ratchet：名单 2797 条 ≥ 下界 2797`、`plaintiffs_measured：3 条本轮原告都在名单里且 passed`（`test_supervisor_package` / `test_ci_face_gates` / `test_scripts_lint_ratchet`） |
| 回收后 B 档 | `git worktree remove --force` ⇒ `git worktree list` 只剩主树；复跑 `GATE_B_RC=0 / 8 项全过`、`CV_B_RC=0 / 11 格全绿`，复验当时 `git status --short` **0 行**（JSON 落树外再 `cp` 入库，第 100 片那条自伤没重犯） |

绑定报告的 sha `81e3b15059d3` 与 `PROVENANCE.test_report.sha256` 逐字相同 ⇒ 签出删掉后证据仍在
树内可复算。链后只动 `docs/audit/`（`run-s102.log`、`gate-b.json`、`closeout-b.json`、两份 `-b`
日志、`drc.json` 与行钉分母那篇），被哈希的四面一字未动 ⇒ 没有第二代。

链后复算：`scripts/scripts_lint_ratchet.py` rc=0（语料 60 / 有债 40 / 0 债 20 / 基线 89 格 /
`ci.yml` 直连 20，"现状面缺陷 0 条"）；取证名册仍 **76 条**（本轮 `docs/audit` 没新增 `.py`/`.sh`）。

## 十、第 102 片顺手量出来的一条尺子盲区（不在本面，另片处理）

改 `scripts/` 行结构之前查"有没有人按行号引用它们"，撞出 `doc_reference_census` 只判
`line > EOF`；用**它自己的** `LIVE`/`HISTORY` 作用域现算：live 面裸行钉 **11 处**（全在
`docs/architecture/truth_architecture.md`，逐条 `resolved`）、history 面 **974 处**（其中 246 条
是它自己认定的历史面缺陷，只报不判）。我第一版用自写的 `rglob(basename)` 数出"live 面 0 处"
还把 `state/db.py:1073` 读成越界——那是我的临时尺撞了同名文件，不是语料缺陷。
分母、下一刀形状与那条"借判据要连解析面一起借"的更正全部落在
`docs/audit/LINE_PIN_BLINDSPOT_MEASURED_2026-09-29.md`，任务表里第 103 片入口按它更正过。
