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
| API `write_evidence()` | `source_commit: str \| None = None` | **无默认值** + 同一形状的 `BindPreflightError`（`write_evidence` 定义处与其内第一道校验，行号本轮已漂过两次，故按函数名引） | 本轮新增 `test_api_has_no_anchor_default` 等三条（按函数名引，不引行号：本轮已因加行漂过两次） |
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

新增常驻 6 条（A 面 3 + B 面 3）。电池 `docs/audit/s88/battery88.py` **10 臂 KILLED 10/10**
（第一代 7 臂的读数留在 `battery88.log`，复核交回后加臂那一代在 `battery88-r2.log`，两代不许互换引用），
对照臂 X0 原样全绿，两支被改文件收尾复算 sha 与开局一致
（`release_evidence.py e67ef8e7c4d6`、`doc_command_census.py 3cfcf1b7f613`）。逐臂：

| 臂 | 撤掉的判决 | 被谁抓住 |
| --- | --- | --- |
| X1 | 把签名默认值装回 `\| None = None`（少传参数不再报错） | `test_api_has_no_anchor_default` |
| X2 | 整条锚点校验关掉（`False and`） | `test_api_refuses_a_malformed_anchor_before_any_write` 的 `[None]`/`[""]`/… 五档 |
| X3 | "恰好 40 位"退化成"至少 7 位" | 同条用例的 `[a660405]` 与 `[A660405…]` 两档 |
| X8 | **字符类放宽回大小写通吃**（复核交回后补） | 只有 `[A66040520139405095648461F7144D4F00629924]` 那一档能抓 ⇒ 大写反例的存在理由就是这条臂 |
| X4 | 把快照列接回判据（缺列不再豁免） | `test_the_snapshot_column_is_decoration_not_authority` + 量具自身 `--self-test` + `test_register_entry_that_resolved_again_or_is_uncited_fires` |
| X5 | 刷新时不带旧 note | `test_emit_register_carries_notes_reports_drops_and_refuses` |
| X6 | 目标读不出时照样落盘（拒绝只剩一句话） | 同上（这一臂第一代那版是让被变异体**崩溃**而红，见 §九#6） |
| X9 | 有手写依据却被丢的条目不再报出来 | 同一条用例的 `dropped` 那一节 |
| X10 | 目标不是字典时不拒绝 | 同一条用例的最后一节（原来会抛 `AttributeError`，见 §九#5） |
| X7 | `rule` 常量写错归属档数 | `test_real_repo_register_shares_the_instrument_constants` |

**X3 与 X8 是同一族的两半**：X3 撤"恰好 40 位"，X8 撤"只收小写"——第 86 片那把电池记的
是前一半的腐化路径，本轮复核发现后一半**压根没有牙**（所有夹具锚点都是小写），
所以两半各配一支臂、各配一档反例。

三把**老电池按第 87 片那条要求重跑**（`release_evidence.py` 与 `doc_command_census.py` 都动了）：
`docs/audit/s84/battery84.py` W1–W8 **8/8**、`docs/audit/s86/battery86.py` **X1–X4 4/4**
（第 88 片给它加了 X4「字符类放宽」）、`docs/audit/s87/battery87.py` X1–X7 **7/7**；
三代的日志分别记在 `docs/audit/s86/battery86.log`（第 86 片那一代）与
`docs/audit/s86/battery86-r2.log`（第 88 片重跑那一代）。
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

4. **我自己写的电池只覆盖了我想到的轴**：`battery88.py` 第一代 7 臂全 KILLED，
   看着像"每档判决都有牙"，但锚点字符类那一半**压根没有臂**——因为我全部夹具锚点都是小写，
   "放宽成大写通吃"这种变异我根本没写过。复核件把它找出来之后我才补 X8/X10 与那档反例。
   教训的形状：**"KILLED n/n"里的 n 是自己定的分母，它不等于"覆盖了全部腐化路径"**；
   下一片的电池要按"判据的每个谓词成分"列轴（字符类、量词、锚定位置、大小写、空白），
   而不是按"我改了哪几行"列臂。
5. **行号引用在这一轮漂了三次**（`release_evidence.py:365→367`、`census:687→689`、
   preflight 三条用例 `:321/:332/:346→:326/:339/:356`），每次都靠 grep 重抓才对上。
   已把三处文档改成**按函数名引**并写明原因：同一文件里加行就会挪行号，
   而"去这行看"这种指针的失效是静默的（第 87 片 §八 记过同一形状，本轮是我自己复发）。

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

## 九、复核交回（两件独立只读复核，逐条我重开代码定档）

派件条件写死了"不许跑 pytest、不许跑电池"（当时干净签出那一跑正在进行，
`tests/test_state_perf_gates.py` 那条 5× 比值门在负载下会假红）。
下面每条的"我的判定"都由我亲手重开它引用的文件得出，不是转述。

| # | 复核交回 | 我重开代码看到的 | 判定与去向 |
| --- | --- | --- | --- |
| 1 | `write_evidence` 的形状判据含大写，而全部夹具锚点都是小写 ⇒ 把 `[0-9a-fA-F]` 改成 `[0-9a-f]` 或加 `.lower()` 六种坏形状全绿，"逐字落地"那条测不出归一化 | `release_evidence.py:382` 原为 `[0-9a-fA-F]`；`tests/...preflight.py` 三处锚点 `"a"*40`/`"b"*40`/`"c"*40` 确实全小写；`git rev-parse v5.6.0^{commit}` 只印小写，两个读者按逐字相等判（`production_release_gate.py:452` 的 `sc != tag_sha`、`closeout_verifier.py:332,334` 的 `!= pinned`） | **真缺陷，本轮已修**：判据收到 `[0-9a-f]{40}`（CLI 与 API 两支同形），CLI/API 各加一档大写反例，电池补臂 X8（CLI 侧另补 X4） |
| 2 | `test_api_has_no_anchor_default` 里 `assert not out.exists()` 是空断言——`TypeError` 在调用边界就抛了，函数体从没执行，目录当然不存在 | 成立（同 `test_api_writes_the_explicit_anchor_verbatim...` 才会真建目录） | 删掉该行；同一条里留下的 `"source_commit" in str(exc.value)` 改为显式注明它是**唯一**能分辨"删对默认值"与"删错参数"的断言 |
| 3 | `test_the_snapshot_column_is_decoration_not_authority` 只证了"四种写法判决相同"，没证"这一列不被消费"：若某一档把 `startswith("/")` 改成 tracked，四种写法会一起落在"看不见那一行"上而仍然相等 | 成立——`base == []` 使四路相等退化成"没有违规，四次" | 每档加断 `entry_states["dead_registered"] == 1`（把"看得见且被免判"钉成共同前提），并补**分辨性夹具**：在册、引用列完整、语料无对应行的条目必须开火；该形状由 `audit()` 的 `if not states` 分支（`:690`）提供，旧用例那批条目**根本不带这一列**，所以确实分不开"被忽略"与"查到但为空" |
| 4 | `emit_register` 只对**仍在 `dead` 档**的路径带 note；一条死链若因"最后一处命令形态被改写成叙述"而离开 `dead`，它的手写依据就被静默删掉——而这恰是本文件 §八.1 鼓励的写法 | 成立：`by` 只收 `state == "dead"`（`:1099-1101`），`old_notes.get(k, "")` 只对 `by` 里的键生效 | **真缺陷，本轮已修**：返回 `dropped: [{path, note}]`，`main()` 连原文打印；不改判决（该不该撤仍由判据现读）。常驻用例第三节 + 电池 X9 |
| 5 | 拒绝分支只兜住"读不出 JSON"；目标是**能解析但不是字典**（例如一个 JSON 数组）时 `existing.get(...)` 抛 `AttributeError`，退 1 加 traceback，与 docstring 承诺的"整批不写"两套说法 | 成立（`:1104-1109` 只 catch 三个解析异常） | **本轮已修**：加 `isinstance(existing, dict)` 拒绝档；常驻用例第四节 + 电池 X10 |
| 6 | 电池 X6 把拒绝分支删成 `pass` 后，被变异体是在 `existing` 未定义上**崩溃**而红的 ⇒ "拒绝时不许动目标文件"那条断言从没被执行过 | 成立（`except: pass` 之后 `existing.get(...)` 直接抛） | **本轮已改形状**：X6 改成"仍照常落盘"（`existing = {}`），正常返回路径上翻红；崩溃型变异不再充当这条断言的证据 |
| 7 | 归因串 `who[:200]` 把 X4 的第三条被抓用例切掉了，读数无法核对 | 成立（`battery88.py` 原 `[:200]`） | 放宽到 `[:600]` 并写明理由 |
| 8 | 我在 `entry_points()` docstring 里写"五档之和等于总读数由 `--self-test` 钉住"，而同一次提交里我编辑的复核表第 8 行自己判那条是**构造式恒等**（`e_counts[state] += 1` 每行只加一次）⇒ 同一提交两处打架 | 成立（`:672` 的自增排在分支之前；`dead_registered` 是另一格另加） | **本轮已改措辞**：docstring 明说那是"分桶不重不漏的构造式恒等，不是能咬人的牙"，并把"要换成能开火的判据"指向 §九#8/第 89 片 |
| 9 | `REGISTER_RULE` 把「该撤」写成无条件真理，但 git 读不出的树上降级会造出这条红（第 87 片 §九#2 仍未修） | 成立（`entry_points` 的 git 读不出降级在 `doc_command_census.py:536` 记 `tracked`，而 `audit():695` 的条件是"处处都是 tracked"） | 规则文本补两条已知误报与去向，不假装已修 |
| 10 | `test_emit_register_*` 带着惰性夹具参数 `tmp_scope`——`emit_register` 不走被 monkeypatch 的那几张面 | 成立（`emit_register` 只调 `entry_points`，用的是 `ENTRY_FILES`/`ENTRY_DIRS` 名字本身） | 删参数并在 docstring 写明为什么不需要（留着一个"看起来在隔离"的夹具＝给读者一个假的共同前提） |
| 11 | 同源用例 docstring 写"三段说明文字"，实际比五段 | 成立 | 改为五段 |
| 12 | 复核认为 `missing_notes == [DEAD]` 那一档无法分辨"`if not e['note']` 这个过滤被删掉" | **不同意**：过滤删掉后 `missing_notes` 会含全部路径，同一条用例后面的 `again["missing_notes"] == []`（note 已填那一步）必红 | 记录分歧，不再加臂（避免为同一事实写第三处） |
| 13 | `build/bundle_stage/tests/test_release_evidence.py:77` 仍是旧的 5 参调用 | 成立但**不判**：`build/` 被 `.gitignore:16` 排除、`pyproject.toml` 的 `testpaths = ["tests"]` 不收它 ⇒ 不在发布清单也不在收集面 | 不动它（一次构建残留，不是活调用点） |
| 14 | 五段 `what`/`shape_borrowed_from` 原来是内联字面量，"同源"用例只比三份 | 成立 | 提升为 `REGISTER_WHAT` / `REGISTER_SHAPE_BORROWED_FROM` 常量，同源用例与 `emit_register` 的草案各比五份（草案那份也补，否则"两边一致地缺"仍能绿） |

ruff 侧复核报"本轮新增 246 行最长 95 < 100"，`pyproject.toml:84` 的 `line-length = 100` 我核对过；
两条"未亲验"的读数（面 ⑤ 的 119/8/20 与电池 KILLED 数）都是我自己跑的，见 §三/§十。

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

## 十一、回收签出树之后的复算读数（与 §十 是两代读数，不许互换引用）

`.wt-s88` 已 `git worktree remove --force` 回收，`git worktree list` 只剩主树。
在**只剩主树**的这个状态下重跑门与验签，两步的落盘件与日志都另起文件名
（`-recheck` 后缀），§十 那一代的原件一字不动地留在库里，读者能对照两代。

| 步 | 命令 | 实际读数 |
| --- | --- | --- |
| 复算门 | `production_release_gate.py --release-ready --tag v5.6.0 --test-report docs/audit/pytest-report-v5.6.0.json --json-out docs/audit/s88/gate-recheck.json` | `GATE_RECHECK_RC=0`；`release_ready: True \| 未过: 无 \| 项数: 8` |
| 复算验签 | `closeout_verifier.py --tag v5.6.0 --expect-test ×2 --min-tests 2702 --json docs/audit/s88/closeout-recheck.json` | `CV_RECHECK_RC=0`；`grep -c "✓"` = **11**，末行「全部判据绿」，其中 `worktree_clean：工作树干净` |
| 现场 | `git status --short` | 空（提交 `324308c` 收了门的读数、`b4d44d6` 收了验签的读数） |

这两步为什么值得再跑一遍：回收动作本身会改 `.git/worktrees` 的登记，而
`roster_covers_tree` 与 `worktree_clean` 读的都是"当前这棵树"——
如果哪份取证件是被 `--force` 带走的，红会出现在这里而不是出现在 §十 那一跑。
现在两代读数都是 8/8 与 11/11，说明回收没带走承重件。

## 十二、本文自己的复算入口（面 ⑤ 会扫到，逐条写明怎么重跑）

| 入口 | 在不在库 | 重跑命令 | 预期读数 |
| --- | --- | --- | --- |
| `docs/audit/s88/battery88.py` | 已入库（提交 23877d2） | `.venv/bin/python docs/audit/s88/battery88.py` | `合计 KILLED 10 / 10`，两文件 sha 收尾等于开局 |
| `docs/audit/s86/battery86.py` | 已入库 | `.venv/bin/python docs/audit/s86/battery86.py` | `4 / 4`（第 88 片加了 X4） |
| `docs/audit/s84/battery84.py` | 已入库 | `.venv/bin/python docs/audit/s84/battery84.py` | `8 / 8` |
| `docs/audit/s87/battery87.py` | 已入库 | `.venv/bin/python docs/audit/s87/battery87.py` | `7 / 7` |
| `docs/audit/s88/closeout88.sh` | 已入库 | 只在"重新认证一次"时用；它会绑定并**提交**，不是无副作用的读 | 第一代读数见 §十 |
| `docs/audit/s88/closeout88b.sh` | 已入库 | 同上，第二代专用（报告与工作树都换名） | 第二代读数见 §十三 |

一把尺跑多久的现读值：本轮邻居会话在跑另一棵树的整体验证（宿主 load 23.9），
四把电池的**判决计数没变、时长变了**（s88 约 13 分钟、s84 约 28 分钟，平静时段分别是 8 与 10）。
读数按 `KILLED n/n` 记，不按耗时记——这条是第 84/85 片那条"邻居会话抢 CPU"纪律的又一次兑现。

## 十三、第二代认证读数（收紧形状与牙之后重跑的那一代），含我又一次自红

第二代与第一代的分界是提交 `23877d2`+`c09905e`（复核交回的收紧动的是 `scripts/` 与 `tests/`，
即清单收录的哈希面 ⇒ 第一代那一跑不再描述当前树）。
命令与落盘件由 `docs/audit/s88/closeout88b.sh` 产生，全部另起 `-b` 后缀，第一代的原件一字未动。

| 步 | 实际读数 |
| --- | --- |
| PRECHECK | `2698 passed / 5 skipped / collected 2703 / 634.6s / fp 379613b574ac`（锚点逐字 == tag `a66040520139405095648461f7144d4f00629924`） |
| 脚本内新增的硬断 | `SKIP 面逐条相同：5 条`（本轮把"跳过集合与上一代双向差集为空"从手工核对提成脚本前提） |
| 绑定 | `BIND_RC=0`；回读 `source_commit=a66040520139 test_report=2698p/0f/2703t fp=379613b574ac`；提交 `ecb0182` |
| 门·第一次 | `GATE_RC=2`，`release_ready: False \| 未过: ['workspace_clean'] \| 项数: 8` ⇒ **我自己造成的**：绑定之后、跑门之前我又往 `docs/audit/SILENT_EXPIRY_….md` 追加了 §十二，那份文件当时未提交 |
| 验签·第一次 | `CV_RC=4`，10 格 ✓、唯一 `✗ worktree_clean：工作树有 1 处未提交改动：['M docs/audit/SILENT_EXPIRY_F-SILENT-EXPIRY_2026-09-28.md']` |
| 门·复算 | 提交那一格之后 `GATE2_RC=0`，`release_ready: True \| 未过: 无 \| 项数: 8`（`gate-b2.json`） |
| 验签·复算 | `CV2_RC=0`，11 格全绿，`size_ratchet：名单 2703 条 ≥ 下界 2703`（`closeout-b2.json`） |
| 回收 | `git worktree remove --force .wt-s88b` ⇒ `git worktree list` 只剩主树 |
| 回收后复验 | 门 `8/8`（`gate-b3.json`）＋ 验签 `11 格全绿`（`closeout-b3.json`） |

三次读数都留在库里（`gate-b.json`/`closeout-b.json` 是带红的那一次，`-b2` 是修正后的那一次，
`-b3` 是回收签出树之后的复算），**不删红色原件**：那一次红本身就是
"未跟踪也算脏、门看得见"这条判据的正面证据，也是第 85 片那条纪律我**第三次**复发的记录
（第一次：第 84 片两个自建脚本；第二次：第 86 片 `?? gate.json`；第三次：本轮 §十二）。
为什么这一红不需要重新绑定：`docs/audit/` 整体不在清单里
（`SOURCE_EXCLUDE_PREFIXES`，`release_evidence.py:74`），所以提交取证文档
不牵动清单内容摘要 ⇒ 报告与磁盘清单仍是同一代（`379613b574ac` 两次同源读数可证）。

**两代 collected 的加数账**：第一代 2702 → 第二代 2703，差 1 = 复核后新加的那档
**大写十六进制反例**（`test_api_refuses_a_malformed_anchor_before_any_write[A660405…]`）。
CLI 侧的大写档是 `for` 循环里的一元，不增加 collected，只增加会红的可能性。

## 附：一处口径更正

提交信息 `23877d2` 写的"9 条定档项"按**本轮动了代码的定档项**计（#1/#2/#3/#4/#5/#6/#7/#8/#9/#10/#11
里实际改了实现或判据的那九条），而本表共 14 行——其余三行分别是：#12 我**不同意**复核的判断
（`missing_notes` 那档其实被后面的 `== []` 覆盖，理由见该行）、#13 成立但按判据不属活调用点、
#14 属实现内部改动已并入 #4。提交信息不可改，故把口径差记在这里，免得下一位读者拿"9"去数表行。
