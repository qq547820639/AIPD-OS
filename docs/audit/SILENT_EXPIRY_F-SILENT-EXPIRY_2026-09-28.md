# SILENT-EXPIRY F-SILENT-EXPIRY 2026-09-28：第 88 片收的两处"写下去就没人再判"

派这一趟的原因：第 87 片收口时我自己登记了两条"排到下一片"——
一条是 `write_evidence()` 的锚点仍可缺省（第 86 片只关了操作员入口），
一条是登记册里那列 `cited_by` **只写不读**、而登记册自己的 `rule` 文本声称它会触发判决。
两条形状相同：**某个事实被写进产物之后，再没有任何判据回头看它**，
于是"写错了"与"写得对"在终端上完全同形，要到下一轮才被别的东西撞出来。

## 一、这两处各自的代价账（不是推测，都有来处）

- **锚点缺省**：第 52 片与第 62 片各为此多跑一整个全量（约 10 分钟/轮，含重绑与重新出门）。
  机制在 `scripts/release_evidence.py` 的两处 `source_commit or _default_source_commit(repo)`
  （`:154` 清单、`:318` 溯源）：缺省不报错，只是把锚点写成**当时的 HEAD**；
  而锚点是清单**内容**的一部分，所以它要到下一轮绑定比对自记指纹时才显形，
  那时读出来的话是「清单在跑完全量之后被改过」——一句把因果倒过来说的错话。
- **只写不读的列**：代价不是时间而是**说谎的文档**。登记册的 `rule` 原文
  （第 87 片写的）：「`cited_by` 为空或某条现在已能解析时，判据会以『登记册该撤』反向开火」。
  实现里 `load_entry_register`（`scripts/doc_command_census.py:463-482`）只取 `path` 与 `note`，
  反向开火的两个条件都由**语料现算**（`:689` 的 `states`）。
  读者照那句话理解豁免机制，会以为"少写引用 = 会被判"，而真相是"少写判决依据 = 没人管"。

## 二、选型（按最高指令第三节，本轮走例外条款并写明理由）

本轮**不做新的六维对比**，理由要说得出：两片改动都是收紧既有通道的默认值与既有文本的形状，
不引入依赖、不改变模块边界、不新增可执行入口——候选清单里连第二个真实方案都不存在
（"引第三方库"对"把一个默认值删掉"这种改动没有可比性）。
面 ⑤ 本身的选型（lychee / mdBook / markdown-link-check 六维对比与"自研 + 借语义"的决定）
已在第 87 片做完并记在
`docs/audit/RECOMPUTE_ENTRYPOINTS_F-RECOMPUTE-ENTRYPOINTS_2026-09-28.md` §一之二，本轮沿用同一条出处。

## 三、A 面：`write_evidence()` 的锚点必填长什么样

改前三层，改后两层：

| 层 | 改前 | 改后 | 谁在判 |
| --- | --- | --- | --- |
| 操作员入口 `main()` | 缺空串→退 2、非 40 位→退 2（第 86 片） | 不变 | `tests/test_release_evidence_preflight.py:249,266` |
| API `write_evidence()` | `source_commit: str \| None = None` | **无默认值** + 同一形状的 `BindPreflightError`（`:367`/`:382`） | 本轮新增 `:321`/`:332`/`:346` |
| 生成层 `generate_*()` | `or _default_source_commit(repo)` | **有意保留** | 由 A 面用例的注释点名理由 |

保留生成层那半的理由（写进 `tests/test_release_evidence_preflight.py` 分节头）：
`production_release_gate` 的 `source_manifest_zero_diff`（`scripts/production_release_gate.py:414`）
要按"当前这棵树"现算一份清单，再与已入库那份只比 `(path, sha256)`——
它既不写盘也不消费锚点，把必填推到这层只会让那把尺在**没有 tag 的树**（合成语料、镜像仓）上无路可走。

顺序也是判据的一部分：新校验在 `out_dir.mkdir` 之前，所以拒绝不留半个目录。
这条不是新增设计，是第 84 片已经把 `write_evidence` 改成两阶段时钉过的形状
（`test_gate_is_wired_into_write_evidence_before_any_write` 钉"闸在落盘之前"，
本轮 `test_api_refuses_a_malformed_anchor_before_any_write` 用同一个 `out.exists()` 面钉锚点校验）。

## 四、B 面：那一列为什么是"改名"而不是"删掉"或"接回判据"

三个候选，择一：

1. **接回判据**（让它真的承重）：要把"引用位置"变成判决输入，就得先定义
   "同一 path 被三篇文档引用时算一条还是三条"，而判据现读语料已经无条件给出这个答案——
   多这一列只是把同一个事实写两处（第 46 片那类债：注入一支臂杀不掉，因为另一支还兜着）。
2. **整列删掉**：读者要复核某条豁免，得自己去全仓 grep 那个 `/tmp/xxx.py` 被谁点名；
   路标有价值，尤其这 13 条的豁免依据本身就写着"读数抄在哪篇文档的哪一行"。
3. **改名 + 把说明文字收到一处生成**（选了这支）：`cited_by_at_emit_time` 名字自己说清
   "这是生成那一刻的快照"，判决侧不变；`rule`/`what`/两半 semantics/`shape_borrowed_from`
   五段改由 `REGISTER_*` 常量单点生成，常驻用例把磁盘上那本册子与常量**逐字段比**。

选这一支的直接证据：逐字段比这条用例一上线就抓出**另一处同族病**——
磁盘册里的 `rule` 写"面 ⑤ …判**四**种归属"，而代码里的同一句写**五**种。
两份手抄各漂各的，没有任何判据看得见（第 87 片的 §九#4 只抓到了 `cited_by` 那半）。

`emit_register` 顺带补的两条前提（都是它本来就该有而没有的）：
- **按 `path` 带旧 note**：原实现整体覆盖目标文件，重跑一次就把历轮手写的豁免依据抹平。
  本轮实测把 13 条 note 逐字带过（`notes unchanged: True`），并让它自己打印"note 待补 0 条"。
- **目标读不出就不落盘**：半坏的册子若被草案覆盖，会被洗成"有名单、没依据"的豁免，
  而那种状态在判据里是**绿**的（在册即免判）。

## 五、牙：用例与电池

新增常驻 6 条（A 面 3 + B 面 3）。电池 `docs/audit/s88/battery88.py` **7 臂 KILLED 7/7**，
对照臂 X0 原样全绿，两支被改文件收尾复算 sha 与开局一致。逐臂：

| 臂 | 撤掉的判决 | 被谁抓住 |
| --- | --- | --- |
| X1 | 把签名默认值装回 `\| None = None` | `test_api_has_no_anchor_default` |
| X2 | 整条锚点校验关掉（`False and`） | `test_api_refuses_a_malformed_anchor_before_any_write[None]` 与 `[""]` |
| X3 | "恰好 40 位"退化成"至少 7 位" | 同条用例的 `[a660405]` 参数 |
| X4 | 把快照列接回判据（缺列不再豁免） | `test_the_snapshot_column_is_decoration_not_authority` + 量具自身 `--self-test` + `test_register_is_load_bearing_for_the_same_line` |
| X5 | 刷新时不带旧 note | `test_emit_register_carries_notes_and_refuses_an_unparsable_target` |
| X6 | 目标读不出也照样覆盖 | 同条用例的后半 |
| X7 | `rule` 常量写错归属档数 | `test_real_repo_register_shares_the_instrument_constants` |

**X3 是第 86 片 X3 的 API 侧重演**，不是重复：第 86 片那臂撤的是 `main()` 里的形状校验，
撤掉它操作员还能被 API 侧拦住（改后），所以两半各自需要一支。
**X4 是极性反转臂**：它证明"这列不参与判决"这件事本身有牙——
把它接回判据会被三条用例同时翻红，其中一条是量具自己的 `--self-test`。

三把**老电池按第 87 片那条要求重跑**（因为 `release_evidence.py` 与 `doc_command_census.py` 都动了）：
`docs/audit/s84/battery84.py` W1–W8 **8/8**、`docs/audit/s86/battery86.py` X1–X3 **3/3**、
`docs/audit/s87/battery87.py` X1–X7 **7/7**。
第 87 片 §十二 曾预告"第 86 片 X1 的锚点在新形状下必然命中 0、要显式记成臂作废"——
**那条预告本身是错的**：X1 的锚点是 `main()` 里的 `if not a.source_commit:`（`battery86.py:24`），
本轮没动那一行，所以它照旧命中 1、照旧 KILLED。记在这里是因为我一度把这条预告当成前提写进了任务文本。

## 六、本轮我自己的三个错（都靠跑出来才发现，不是读出来）

1. **一次 Edit 吃掉了 CHANGELOG 的 v5.48 标题行**：我把新条目"插在 v5.48 之前"写成了
   以 v5.48 的标题行为锚点、`new_string` 里却没重贴那一行 ⇒ v5.48 的正文头上无标题、
   两条目被并成一条。`grep -n "v5.48" CHANGELOG.md` 只剩我自己引自己的两句才发现。
   这正是记忆里那条"大块 Edit 漏掉尾巴会留下结构残件"的又一实例，
   而 `tests/test_changelog_integrity.py` 这类门禁当时**没跑**——它只判结构完整性，
   标题行丢失后结构仍是合法列表，所以这道门禁本来就看不见这个错（不是漏跑，是判据不覆盖）。
2. **抄分母的病又犯一次**：给 `entry_points()` docstring 写"104/5/18 已漂成 119/8/20"时，
   后半个数是我这一轮跑出来的、前半个是第 87 片跑出来的——**同一句话里两种时效混排**，
   读者会以为两句都可现读。已在同一句里给两个数各挂轮次标签，并把"当前值一律 `--json` 现读"
   写成独立一句而不是形容词。
3. **收口脚本 `git add -f` 指到没落盘的路径**：派生自第 86 片脚本时，我把
   `cp "$X/gate.log" docs/audit/s88/` 这一步在"提交门的读数"那节漏掉了，
   却留着 `git add -f docs/audit/s88/gate.log`——`git add` 对不存在的路径会报错，
   而这一节的退码没被收进任何判据。`bash -n` 过、`grep -c 's86\|s87'` 归零都拦不住它，
   只有逐行读 `git add` 的目标是否存在才看得见。修法：把 `bind.log`/`gate.log`
   的 `cp` 放在同一节第一条。

## 七、镜像面（同轮必须一起改的那几张）

| 面 | 位置 | 本轮动作 |
| --- | --- | --- |
| 模块 docstring 退码段 | `scripts/release_evidence.py:24-28` | 加"第 88 片把同一半闸放到 `write_evidence()`" |
| `--source-commit` 的 help | `scripts/release_evidence.py:424-427` | 原文写"默认为当前 HEAD"，已改成"必填…不默认成当前 HEAD" |
| 生成入口叙述 | `docs/audit/release_evidence_notes.md:9` | 补 API 侧形状与"生成层为何保留默认" |
| 第 86 片取证文档的遗留项 | `docs/audit/ANCHOR_REQUIRED_F-ANCHOR-REQUIRED_2026-09-28.md:74` | 原句"API 仍可传 `None`"标为**已由第 88 片闭合**，并写清保留的那半是哪一层 |
| 登记册五段说明 | `REGISTER_*` 常量 ↔ `docs/audit/RECOMPUTE_ENTRYPOINT_REGISTER.json` | 由 `--emit-register` 生成、由常驻用例逐字段比 |
| 面 ⑤ 的 README 块 | `README.md:512` 起那一整块 | 分母改指 `--json` 键；补快照列降级与 `--emit-register` 的两条新前提 |
| 第 87 片取证文档 §八.3/§八.5/§九#3/#4/#8 | `RECOMPUTE_ENTRYPOINTS_…_2026-09-28.md` | 闭合两条、更正三处失效行号引用 |
| 失效配方 | `docs/audit/RELEASE_FIX_PLAN_2026-08-14.md:59` | 字面量 `--source-commit HEAD` → tag SHA 现读，并注明原文意图 |
| v5.48 条目内的旧读数 | `CHANGELOG.md:1003,1014` | 144/122 更正为 143/127 并指回 §六；"不是抄的，现读"改成带轮次的历史读数 |

## 八、残留与未做

1. **`--emit-register` 仍不解决"同一 path 被多篇文档引用"的取舍**：快照列按去重后的
   path 聚合，引用行号全列在一格里。要做成"每处引用单独一行"得先定聚合键，留给第 89 片。
2. **note 的信息量仍没有判据**：常驻用例只保证非空。要判"有没有信息量"就得结构化
   （有没有 `F-…`、有没有文件名、有没有数字），而那种判据对措辞过敏——第 87 片已记同一理由。
3. **`generate_*` 的默认值还在**：这是设计选择（§三），但**没有判据钉住"它不该被写进产物"**。
   今天唯一的保护是"要写产物就得走 `write_evidence`/`main`"这个约定。
   第 89 片候选：一条 AST 判据——`generate_source_manifest` 的返回值若被任何
   非 `write_evidence` 的调用点直接 `json.dump` 到 `SOURCE_MANIFEST.json`，判红。
4. **本轮新量到的一条同名双旗**（不在本片动，理由写在 CHANGELOG v5.49 末段）：
   锚点环境变量有两个名字——`tests/conftest.py:54` 读 `AIPD_SOURCE_COMMIT`，
   `tests/test_golden_projects_e2e.py:75` 读 `AIPD_PIN_COMMIT`，
   而全仓没有任何配方或文档设置后者（唯一命中是 `tests/test_golden_isolation.py:68`
   用 `"deadbeef"` 当夹具值）⇒ 黄金项目产物的"锚定最终 tag"在真实发布路径上从未生效。
   已排进第 89 片任务 #20 第⑨条。

## 九、复核交回（独立视角，逐条我自己重验后才落表）

（待两个复核件交回后填：每条含它的探针读数、我重开代码后的判定，以及是否升格为第 89 片条目。）

## 十、终局读数（全部由 `docs/audit/s88/closeout88.sh` 现场产生）

| 步 | 命令 | 实际读数 |
| --- | --- | --- |
| 0 | 脚本内 `PRECHECK` | `2697 passed / 5 skipped / collected 2702 / 676.8s / fp 9d912fcbf7d0`（报告锚点逐字 == `git rev-parse v5.6.0^{commit}` = `a66040520139405095648461f7144d4f00629924`；报告自记指纹与 `release_fingerprint.py SOURCE_MANIFEST.json` 同为 `9d912fcbf7d0…`） |
| 1 | `release_evidence.py --source-commit --test-report`（一次绑定） | `BIND_RC=0`；回读 `source_commit=a66040520139 test_report=2697p/0f/2702t fp=9d912fcbf7d0`；提交 `5ac551c` |
| 2 | `production_release_gate.py --release-ready --tag v5.6.0` | `GATE_RC=0`；`release_ready: True \| 未过: 无 \| 项数: 8` |
| 3 | `closeout_verifier.py --tag v5.6.0 --expect-test ×2 --min-tests 2702` | `CV_RC=0`；11 格全绿：`report_bound_to_provenance`（报告 sha256 `7a6a10590bbe` 与 PROVENANCE 一致）、`counts_counted_from_roster`、`terminal_clean`、`roster_covers_tree`（树 218 文件 / 2608 个 def ↔ 报告 218 文件 / 2702 条，双向差集为空）、`pinned_source_binding`（`a660405…` 是 HEAD `ba51b7ff` 的祖先）、`content_parity_measured`（2 条清单哈希用例 passed）、`report_fingerprint_recorded`、`report_fingerprint_matches_disk`、`worktree_clean`、`plaintiffs_measured`（2 条本轮原告）、`size_ratchet`（2702 ≥ 2702） |
| 4 | `git worktree remove --force .wt-s88` | `git worktree list` 只剩主树（当时 HEAD `7d294bd`），目录 `No such file or directory` |

三条读数要单独说一句，否则容易被当成"绿就是绿"：

- **`collected` 从 2692 涨到 2702 的加数账**：本片新增 6 个 `def test_`
  （preflight 3、census 3），其中参数化那条把 1 个 def 摊成 5 个 case ⇒ 净 +10。
  `--min-tests` 因此取**本轮现读的 2702**，而"必须严格大于上一轮下界 2692"这一步
  写在脚本的 `PRECHECK` 里（`assert s["collected"] > prior`），不是靠我记住上一轮的数——
  这样"本片新增用例根本没跑到"仍会红。
- **跳过面没有缩**：本轮 5 条 skip 与上一轮那份**逐条相同**（两个方向的差集都为空），
  所以 `FAIL=0` 这次确实意味着"同一覆盖面"，不是把某档换成了 skip。
- **`environment` 那一格仍是 `{}`**：`pytest-json-report 1.5.0` 读 `config._metadata`
  而 `pytest-metadata ≥3.0` 写 `config.stash`，所以这份报告的该键恒空（已知量具缺陷，
  不在本片范围，已单独记在项目记忆）。绑定不消费它。

回收后再复验一次（证明取证件没被回收动作带走）：命令与读数见 §十一，
本节写在这里只为了给"回收前"的读数留位——§十一 的读数是**换树之后**重跑门与验签得到的，
两节不许互换引用。
