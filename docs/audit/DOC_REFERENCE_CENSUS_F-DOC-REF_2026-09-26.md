# F-DOC-REF 第 41 片：文档写出的 path:line 还指得回代码吗

日期：2026-09-26 归属：文档 ↔ 代码一致性
状态：已闭（现状面 0 条，常驻门禁 + 判据自测 20 条 + 电池 5 条）
量具：`scripts/doc_reference_census.py` 用例：`tests/test_doc_reference_census.py`

## 一、这根轴为什么存在

上一片（第 40 片）收尾时我按"文档引用 ↔ 事实"随手普查了一遍，抓到的第一条真缺陷是
**我自己写下的**：CHANGELOG 第 39 片条目里那句「与同仓 `ts_interface_shape.py`(tree-sitter)
属不同语言面」——本仓没有这个文件，也没有任何 tree-sitter 使用点
（`import ast` 的真实同仓持有者是 `src/aipd_os/interface_contract.py`、
`src/aipd_os/schema_binding.py`）。登记侧写得很像有出处，代码侧根本没有。
一次性更正之后，剩下的问题是：**这条判断能不能常驻**——否则下一轮还会写进去。

## 二、判据（六档，Σ 分类 == 分母是硬断言）

下表取 **`693fa2a` 的干净签出**（145 份文档、3553 处引用）。同一份代码在开发树里读出来
是 multi 429 / missing 134 / resolved 2844 —— 差在开发树多了未跟踪的副本文件，
既让同名简写更容易撞成 multi，也让更多引用"侥幸解析得到"。
**两棵树的现状面都是 0**，所以门禁只钉 `live_defects == 0` 这一格树无关的事实；
档位绝对数只出报表，作断言时只用"读得出来"级门限（multi > 50，两棵树都远高于）。

> **绝对数会随记录自身漂移**（这条是本片写完当天就撞上的）：普查的语料**包含记录它读数的文档**
> ——`CHANGELOG.md` 与 `docs/audit/**` 都在历史面里。于是第 39/40/41 片每写一次收尾留痕，
> 分档绝对数就变一次：本文件第一版记「144 份文档」「开发树 missing 126 / resolved 2829」，
> 复算已漂成 **145 / 134 / 2844**；历史面缺陷数从 §四 记的 116 一路到今天的 138（HEAD）与 122（开发树）。
> 规则由此定下：**参与发布哈希的文件（CHANGELOG/README）只写档位划分、判据取舍与"现状面 0 条"
> 这类树无关事实；带绝对数的快照只写在本文件**（`docs/audit/` 被排除在哈希之外，
> 所以事后更正不会让清单与磁盘打架）。写这张表的下一句话之前先跑 §六 的第一条命令，别复用上一次的数。

| 档 | `693fa2a` 干净签出 | 含义与取舍 |
| --- | --- | --- |
| `resolved` | 3156 | 全路径命中，或模块相对简写按后缀**唯一**命中（`migrations/runner.py` ⇒ `src/aipd_os/state/migrations/runner.py`）；带行号的还要求行号 ≤ 该文件行数 |
| `multi` | 99 | 简写但有多个同名候选 ⇒ **只报不判**：散文里写裸文件名是合法表达，判红等于禁掉一种写法 |
| `missing` | 149 | 全路径、后缀、同名三种解法都试完仍无 ⇒ 现状面判红，历史面只报 |
| `line_beyond_eof` | 13 | 文件在但行号越界 ⇒ 同上分档 |
| `elided` | 61 | 省略写法（`src/...py`）、尖括号占位（`<db>.manual.json`）、裸后缀提法（`.py`） |
| `external` | 75 | 第三方/绝对/站点包内部路径（`ezdxf/…`、`/tmp/…`） |

面划分：**现状面** = `README.md`、`SKILL.md`、`docs/architecture|contracts`、`references/`
⇒ 判红；**历史面** = `CHANGELOG.md`、`docs/audit/**` ⇒ 只报不判。
这条取舍借自同类工具 dsh-doc-guard 的「现状核对时忽略历史 changelog 行」——
历史记录是当时的事实，改写等于篡改记录；但**豁免名单本身要被核**，
否则把 README 划进"历史"就等价于关掉门禁（注入 D3 专打这一格）。

## 三、判据自己被推翻的三次（都是尺子造数，不是文档造数）

第一版普查报「514 条 missing / 活文档 97 条」，**全是假的**：它把 CLI 示例操作数
（`out/bracket.dxf`）、第三方内部路径、省略写法、模块简写一律当缺陷。逐条修：

1. **扩展名表里有 `dxf` ⇒ `ezdxf/entities/polygon.py:212` 被切成两段**
   （第一段就是 `ezdxf`，因为 `…xf` 结尾命中 `dxf`）。修法：整段必须以扩展名结尾
   `(?![A-Za-z0-9])` + 左侧不许接词字符。
2. **表里有 `sql` ⇒ `aipd_state.sqlite` 被读成一条 `aipd_state.sql` 引用**（同一根因的第二形态）。
3. **点号前不限词 ⇒ `.py`、`.manual.json` 这类裸后缀提法被当成路径**；
   `<db>.manual.json` 这类占位写法同理。修法：点号前至少一个词字符，
   且带 `<`/`>`/`...` 或以 `.` 开头的一律进 `elided`。

修完现状面从 6 条降到 0 条，其中还有一条是**文档写法本身该改**：
`references/local-cad-fallback.md` 写 `cad/model.py` 指的是**用户项目里生成的文件**，
不是本仓源码 ⇒ 改成 `<项目目录>/cad/model.py`，让写法与含义一致（而不是给判据开后门）。

另有一条过程事实要记：我为 sqlite 那条写的合成语料，原句里**又字面写了**
`aipd_state.sql`，于是"控制没立住"其实是语料自指——控制本身要先能开火再谈信它。

## 四、性能一次、口径一次

首版每条解析不到的引用都去 `rglob` 扫盘 ⇒ 常驻用例 **99.6s**。改为整仓文件清单读一次并缓存
（排除 `.git/.venv/__pycache__/.mypy_cache/.pytest_cache/releases`）：`audit` 1.8s、整个用例 2.5s。
副作用要说清：缓存把 `__pycache__`/`.pytest_cache` 移出了可解析集，历史面读数从 114 变 116 —
**这是收紧，不是漂移**；现状面仍 0 条，判红档不受影响。
（114/116 是**当时那一棵树**的读数，按 §二 的漂移规则不再往下追，今天的数见 §七。）

## 五、撤改电池（`/tmp/s41/battery.py`，5 条：杀 5 / 存活 0 / 注入无效 0 / 崩溃式红 0）

对照臂（未注入）rc=0 先立；每条注入后按**被改的那个文件**比 sha 还原。

| 注入 | 半径 |
| --- | --- |
| D1 文档形态改回裸相对名 | `test_live_docs_have_no_dead_code_references` |
| D2 去掉扩展名的 token 结尾约束 | 同上 + `test_instrument_self_test_runs_and_is_green` |
| D3 把 README 划进历史豁免名单 | `test_history_face_cannot_swallow_the_live_face`、`test_instrument_self_test_runs_and_is_green` |
| D4 关掉模块相对后缀解析 | 6 条（含 Σ/非空转/JSON 同源） |
| D5 关掉代码块跳过 | `test_live_docs_have_no_dead_code_references`、`test_instrument_self_test_runs_and_is_green` |

D5 第一次是**注入无效**：我把 `continue` 关在了"围栏翻转行"上，真正的跳过在下一句
`if fence: continue`，所以"存活"是假读数。同时暴露判据缺一支自己的对照——
`aipd …` 行规则与代码块规则是两条冗余防线，只测其一等于没测：
补了一段**不以 `aipd` 开头**的 JSON 代码块进合成语料，重瞄后 D5 才真开火。
D4 一开始只报"抓住 0 条 rc=1"，是电池的半径解析只收 `FAILED` 不收 `ERROR`（夹具期错误）——
读数为 0 的"杀掉"不是证据，先修记分再谈结论。

## 六、复算入口

```
.venv/bin/python scripts/doc_reference_census.py            # 现状面 0 条 ⇒ rc=0
.venv/bin/python scripts/doc_reference_census.py --self-test # 20 条合成读数
.venv/bin/python -m pytest tests/test_doc_reference_census.py -q   # 2.5s
```

## 七、终读数（工作树干净后跑）

收尾链：`5b6f023`（文档改写）→ `2e3e9f6`（两份清单重锚）→ 全量 → `dcb61e6`（绑证据）→
`2e53931`（报告入库）→ 门禁。

- **全量**：**2285 passed / 3 skipped / 0 failed**，791.56s，跑在 `2e3e9f6` 的
  `git worktree` 干净签出里（`PYTHONPATH` 指向该签出的 `src`，
  `AIPD_SOURCE_COMMIT` = tag SHA）。报告 sha256 `6960f647ad1c4f7d…`，
  已入库 `docs/audit/pytest-report-v5.6.0.json` 并绑进 `PROVENANCE.test_report`
  （passed 2285 / failed 0 / total 2288）。上一片同规模用例 477.60s，本轮 791.56s ——
  并行会话把机器压到 load 21，**性能比门禁未被拖红**（阈值 5×，见 §附）。
- **普查终读数（同一棵树 `2e3e9f6`）**：145 份文档 / 3555 处引用，
  `resolved` 3158 / `missing` 149 / `multi` 99 / `external` 75 / `elided` 61 /
  `line_beyond_eof` 13；Σ 分类 = 3555 = 分母 ✓；**现状面 0 条**、历史面 138 条（只报不判）。
  与 §二 表（基准 `693fa2a`）差的那 2 处引用，就是 §二 那段漂移说明的现场复现：
  从 `693fa2a` 到 `2e3e9f6` 之间我只改了两份文档，分母就从 3553 涨到 3555。
- **`production_release_gate --release-ready --tag v5.6.0`**：**8/8 PASS，rc=0**
  （`workspace_clean`、`commit_matches_head`、`source_manifest_zero_diff`、
  `bundle_manifest_zero_diff`、`test_numbers_from_report`、`signature_verifiable`、
  `no_secrets`、`no_unacknowledged_cve`）。
- **`audit_repo --strict`**：rc=1，**唯一一条 ✗** 是按设计保留的 tag 锚点项
  （`Provenance source commit mismatch: manifest=a66040520139… vs HEAD=2e5393154c18…`）；
  两份清单的 `hash_mismatch_count` 均为 0、`mismatches` 均为空。

## 附、本片学到的一条（进用户级记忆）

判据的语料**包含记录它读数的文档**时，绝对数不能写进参与发布哈希的文件：
`CHANGELOG.md` 在历史面里，所以往它写"读成 missing 149 / multi 99"这种句子，
下一次编辑文档就会让它自己变假——而且**假得很安静**（没有任何红会亮）。
处置：哈希文件只写树无关事实（档位划分、"现状面 0 条"），
绝对数只写进 `docs/audit/`（被排除在哈希外、可事后更正），并给表格标明它是**哪个提交的树**。

## 九、第 103 片：现状面不许写裸行钉，历史面把"漂"报出来

**触发**（第 102 片量的，全读数见 `docs/audit/LINE_PIN_BLINDSPOT_MEASURED_2026-09-29.md`）：
本尺对行号只有一条判据 `line > 文件行数`。文件变长时旧行号仍然"合法"，于是漂移完全静默——
现读 `docs/audit/v5.4/phase4-manual-chain-audit.md:59-63` 钉的三处已经差约 47 行，四轮门禁全绿。

**这一片加的三面**（`scripts/doc_reference_census.py`）：

| 面 | 形状 | 为什么这样切 |
| --- | --- | --- |
| `bare-line-pin`（判红，只作用于现状面） | 现状面文档里出现 `` `path.py:123` `` ⇒ 缺陷，要求写成 `path.py::符号` | 历史面**不能**判：那行号是当时的盘，判红等于逼我改写取证件（那比假绿更糟） |
| `symbol-resolved` / `symbol-missing` | `路径::符号`（支持 `类.方法` 限定）按 AST 找定义区间；找不到 ⇒ 判红档 | 仓内已有 178 处这种写法（CHANGELOG/取证文档在用）⇒ 这是把既存惯例接上判据，不是发明新语法 |
| `drift`（只报不判） | 带行号的引用分三档：还在符号区间 / 已离开 / 这句没点名符号；三档求和必须等于带行号引用数 | 第三档必须存在：没有可核符号的钉是"看不见"，不许折进"没漂" |

**本片真语料读数**（树 `docs/audit/s103/drc_live.json`，改文档之前那一跑）：
现状面裸行钉 **11 处**，全在 `docs/architecture/truth_architecture.md`；
逐条按 AST 求出宿主符号后换成符号锚，换完现状面 **0 条**；
`symbol-resolved 178+11`、`symbol-missing 12`（12 条全在历史面 ⇒ 只报）、
`bare-line-pin 0`；漂移档 `checked 792 = ok 50 + suspect 94 + unhinted 648`。

**三处"判据自己救回来"的现场**（都不是先写对再跑的）：

1. **一条常驻控制一直开着火而没人发现**：旧那条「历史面缺陷不进现状判红」拿 `"40"` 去比
   `live_defects`，而 `Ref.key()` 第三格在有行号时是 `int` ⇒ 类型不同，`not in` 恒真，
   这条控制**从来没开过火**。修法是先归一成字符串键（`_live_keys`）再比，
   并把"现状面缺陷"那格从**条数**改成**集合**（条数会被"多算一条/少算一条"互相抵消，
   集合要逐条对上）。电池 X5 那一臂（键里丢掉行号）现在能被抓住。
2. **Σ 闭合这种"结构上不可能破"的判据，抽成函数才有牙**：写在 `audit()` 里的一行 `if`
   在任何可达输入上都不会触发，于是"把它改成永不成立"的变异必然存活（电池 X3 第一跑就 SURVIVED）。
   抽成 `_drift_problem()` 之后，自测直接喂两把字典（闭合 ⇒ 沉默、少一档 ⇒ 开火），
   同一支臂改成"少加一档"就 KILLED。**推论**：不变量类判据要连"能被喂进不平衡输入"一起设计，
   否则它只是给未来编辑者的一句注释。
3. **符号锚会把文档里写错的意图暴露出来**——本次是好事也是提醒：
   `truth_architecture.md` 有一句写 `` `commands_truth.py:543 cmd_truth_ctq_list` ``，
   而我按行号算出的宿主是 `cmd_truth_ctq_deprecate`（该函数在 :531，`:570` 才是 list）。
   **以文档点名的符号为准**（`::cmd_truth_ctq_list`），行号只是当时飘了；
   第一版我错按行号取了宿主符号，把这句话的意思改坏了，随即改回。这正是换符号锚想买的东西：
   意图与位置分开，位置可以过期，意图不能被打错。

**电池**：`docs/audit/s103/battery103.py`，A0 + 6 臂 **KILLED 6/6**（含债中性门与理由门，
靶文件在 CI 的 ruff 面上，所以变异形状一律避免常量条件；收尾 sha 与开跑前相同）。
`--self-test` 现报 25 条合成读数全立住（条数只以该行自报为准，本文与 README 都不抄它）。
另外本片顺手补了一把新尺：`tests/test_unreachable_code.py`（函数体顶层 `return` 之后还挂语句 ⇒ 判红；
ruff/mypy 都不抓这一形，而本尺自己的 `resolve()` 里就躺着五条这样的残句——已删，
且删前后同一棵树逐条 klass 全等，5936 处引用一个读数没变）。
