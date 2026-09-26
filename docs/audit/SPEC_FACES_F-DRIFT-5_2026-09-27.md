# F-DRIFT-5 第 57 片：`drawing_spec` 的身份键补上「源面」（2026-09-26/27）

## 一、要拍的问题

改了 CTQ 的限值、没人重出声明，`truth drift` 与 `truth sweep` 看不看得见？

第 56 片的答案是「看不见」，而且是被一条常驻用例钉住的（当时先按"应该能发现"写断言，它红了，
才改成钉缺席）。本片把这一格闭掉。

## 二、前提复核（改前）

- `drawing_spec` 记录的身份键只有一个：`metadata.spec_sha256`
  （`src/aipd_os/cad/spec_lineage.py:41` 的 `spec_digest` = 声明正文的 canonical JSON 哈希，
  不是文件字节哈希）；
- 漂移侧也只算这一个面：`cli/commands_drift.py` 的 `_spec_signature_resolver()` 原先
  只做 `spec_file_digest(路径)` 与 `spec_sha256` 的比对 ⇒ 文件不动就永远 `in_sync`；
- 返工执行器（`cad/spec_rework.py:84`）已经会按当前 active CTQ 重算，
  所以**"源面算得出"这件事本来就成立**，缺的只是探测侧没用它。

## 三、选型（本轮真实开到的页面）

| 候选 | 出处 | 结论 |
| --- | --- | --- |
| B：两面各与同一条基线比（选中） | Argo CD `docs/operator-manual/architecture.md`（raw master，实际打开）原文：The application controller … **"compares the current, live state against the desired target state"** —— 两侧都现算、状态里只存一份基线 | 存量记录零迁移，第 43~56 片写下的记录照样能判 |
| A：新增一列"源面签名"（`metadata.source_signature`），drift 只比它 | 形状同 Bazel action key / BitBake `STAMPS_DIR`（第 46/51/55 片实读过） | 要同时改两条写入口（生产者 + 返工执行器），且旧记录集体掉进 `no_record_signature`：今天的 `in_sync` 读数被换成"看不见" |
| C：只比源面、丢掉文件面 | — | 会把第 51 片那条"手改产物文件必须被发现"判据降级，直接排除 |

六维：功能匹配度 B 略优（两半各抓一类改动，且都有对侧不开火的对照）；License 无涉（借语义、
不引依赖，未检索到需要引入的 Python 包）；维护活跃度 B 的参照系是 Argo CD/Bazel/BitBake 三家并存；
安全与质量两平；**适配成本 B 明显低**（不动写侧、不迁移数据）。
择一：**借语义、自研实现**——借的是"两侧现算 + 单基线"这条判据形状，
面名/优先级/原因文案都是本仓自己的。

诚实记录：`argo-cd.readthedocs.io/…/diff-strategy/` 返回 **404**；
WebSearch 对该主题只回内容农场（CSDN/51CTO/腾讯云社区），**未采用**；
`mcp__github__get_file_contents` 列 `docs/operator-manual` 后按文件名选中 `architecture.md`，
再 `raw.githubusercontent` 打开取原文。

## 四、形状与判据（每条都有常驻用例，见 §七）

`src/aipd_os/product_truth/drift.py` 的 resolver 协议从「一条 current 比一条 stored」
抬成**一组面**：

```python
@dataclass(frozen=True)
class Face:
    name: str          # "file" / "source" / "input"
    current: str | None
    stored: str | None
    reason: str | None
```

优先级（保守方向从上到下）：**任一面不等 ⇒ `drifted`**（理由点名是哪一面，且把另一面
算不出的话一并留下）→ **没有任何一面有基线 ⇒ `no_record_signature`** →
有基线但当前值算不出 ⇒ `undecidable` → 全部相等 ⇒ `in_sync`。
两个额外的开火点：resolver 交出**空列表** ⇒ `undecidable` 并写明"这把尺子对它不开火，
不算通过"（恒真判据与缺席判据在终端上同形，这一档专门反它）；单面制品由
`_single_face()` 在边界处包成一个 `input` 面，四个既有 resolver 的签名与文案一个字没改。

`drawing_spec` 的两面：

- `file`：`spec_file_digest(记录里的 path)` —— 第 51 片那一半，判"手改/删产物"；
- `source`：拿**这条记录自己声明的** `ctq_refs`，从本作用域 active CTQ 里筛出这批，
  重跑 `spec_from_ctq` → `spec_digest`。三条刻意的取舍：
  1. **不吃全作用域 CTQ**：一条记录只覆盖它当初吃进去的那批要求，按全集算会把
     "新增了另一条无关要求"读成每条既有声明都漂了（覆盖率归发布门禁 `gdt_covers_ctq`）；
  2. 上游被停用/删除 ⇒ 算得出、且与基线不等 ⇒ **漂移**，不是不可判；
  3. 重算出缺口 ⇒ 用确定性键 `"ctq-gap:" + spec_digest({"gaps": 排好序的缺口})`，
     同样落**漂移**——折成不可判会让退出码从 4 掉回 0，那是最安静的假绿。
  每轮扫描只读一次 CTQ 表（`nonlocal read` 缓存，miss 用 `None` 哨兵而不是空列表，
  否则"库里真没有"会被当成"已经读过且是空的"）。

## 五、配对实测（同一份生产形状数据，改前树 vs 改后树）

`/tmp/s57/shape.py`：`ProductTruthStore.connect` 挂 `set_trace_callback` 数 SQL，
`dxf_lineage.spec_file_digest` 包一层数文件读；两棵树喂的是**同一个播种函数**
（`spec_from_ctq([该条 CTQ])` + `render_spec_text` + `record_spec_lineage`）。

| 记录数 | 改前（`8d8b396`，第 56 片末） | 改后（本片） |
| --- | --- | --- |
| 5 | SQL=1 文件读=5 扫到=5 `in_sync=5` | SQL=**8** 文件读=5 扫到=5 `in_sync=5` |
| 20 | SQL=1 文件读=20 `in_sync=20` | SQL=8 文件读=20 `in_sync=20` |
| 100 | SQL=1 文件读=100 `in_sync=100` | SQL=8 文件读=100 `in_sync=100` |
| 300 | SQL=1 文件读=300 `in_sync=300` | SQL=8 文件读=300 `in_sync=300` |

多出的 7 条逐条数过（同一探针打印语句原文）：1 条 CTQ `SELECT` + 6 条 schema 引导
（3 × `CREATE TABLE IF NOT EXISTS` + 3 × `PRAGMA table_info`），来自源面第二个
store 实例；**全部是每次扫描的固定开销，不随记录数增长**，所以第 55 片那把
"每记录边际 SQL ≤ 0.1 条"的常驻门禁仍然绿，而它确实能抓住打散缓存的注入（§七 A7）。
文件读次数仍**恰好等于记录数**。

## 六、改判与镜像

1. **第 56 片那条边界断言反转**：`tests/test_truth_ctq_add.py::`
   `test_ctq_change_is_invisible_to_drift_and_sweep` →
   `test_ctq_change_is_visible_to_drift_and_sweep`（同夹具、同改法，期望从"看不见"翻成
   "必须被 drift 点名 + sweep 落刀标 stale"）。
2. **`test_truth_drift.py::test_spec_record_drifts_when_the_file_on_disk_changes` 改判**：
   它的夹具是手写 `{"tolerances": …}`，`ctq_refs` 为空 ⇒ 源面无从重算 ⇒ 整条从 `in_sync`
   变 `undecidable`。本片要钉的"手改文件要被发现"不但没弱，理由还点名了 `file` 面；
   两面各自独立的正例搬进 `tests/test_truth_spec_faces.py`。
3. **第 55 片那副性能夹具的 spec 正文改由生产函数生成**（`scripts/state_perf_gate.py` 与
   `tests/test_state_perf_gates.py` 各一处）：原来手写的 dict 少 `drawing_feature`、
   也不是 `spec_from_ctq` 的产物 ⇒ 源面与基线永不相等，"扫一份一致的库"这个前提就没了。
   这个连带发现正好证明源面有牙。
4. **抓到一条镜像缺陷**（与本片无关但被本片暴露）：`registry_data.py` 的
   `product_truth.ctq_declaration.e2e_evidence` 里写的
   `test_declared_ctq_feeds_spec_drift_sweep_and_rework` **在仓库里不存在**
   （第 56 片改名成 `…_propagate_and_rework` 时没同步），已改正并把新用例名登记进去。
5. 扫描成本的三处措辞（架构文档、登记表、README）由"恒为 1 条"改成 §五 的配对读数。
6. 第 55/56 片取证文档里的旧读数各加一行带日期的更正，不改写原文。

## 七、变异电池（`/tmp/s57/battery.py`，worktree `/tmp/s57w`）

对照臂（未注入）rc=0。第一轮 8 条臂：**7 KILLED / 0 SURVIVED / 1 注入无效**。

| 臂 | 注入 | 原告 | 结果 |
| --- | --- | --- | --- |
| A1 | 摘掉源面，退回只比文件 | `test_ctq_limit_change_is_discovered_by_drift_alone` | KILLED |
| A2 | 源面按全作用域 CTQ 算 | `test_unrelated_new_ctq_is_not_drift` | KILLED |
| A3 | 「没有基线」这一档摘掉 | `test_missing_path_is_no_baseline_not_a_pass` | KILLED |
| A4 | 不可判排到漂移前面 | `test_drifted_face_outranks_an_uncomputable_one` | KILLED |
| A5 | 重算出缺口时折成「不可判」 | 原选 `test_deactivated_upstream_ctq_is_drift_not_undecidable` | **注入无效** |
| A6 | resolver 交空列表时当作一致 | `test_resolver_that_returns_no_face_is_undecidable` | KILLED |
| A7 | CTQ 表每条记录读一遍（打散缓存） | `TestDriftScanScaling::test_sql_statements_do_not_grow_per_record` | KILLED |
| A8 | 单面制品的面名写错 | `test_faces_are_a_sequence_protocol_for_single_face_artifacts` | KILLED |

A5 不是门禁没牙，是**电池选错了原告**：那条用例把上游 CTQ 改成 `stale`，于是
`present = []`，而 `spec_from_ctq([])` 的缺口是**空的**（第 56 片刚实测过这一点，
所以才有了 `empty_declaration` 那格）——gap 分支根本没走到。补一条真正踩在 gap 分支上的
用例 `test_recomputed_gap_is_drift_not_undecidable`（上游记录被改坏：去掉 `nominal`
⇒ `ctq_missing_nominal` 缺口 ⇒ 断言 `ctq-gap:` 前缀、理由带"缺口"、`truth drift` 退 4），
并把 A5 的原告换成它，复跑整批：

@@BATTERY2@@

## 八、终读数

@@FINAL@@

## 九、遗留

- `spec_from_ctq` 的缺口键里带 `record_id`，所以"同一条 CTQ 换 id 再来一次"会算作新键；
  这与第 50 片"文件名不进签名"是相反的取舍——缺口身份**是**工程事实，路径不是。未测边界。
- 源面每次扫描多开一个 store 实例（§五 那 6 条 schema 引导）。今天它是常数，
  若以后 resolver 变多，值得换成复用同一个 store；未做，因为没有门禁逼它。
- 上游新增一条 CTQ 时，这条声明"覆盖不全"仍只由发布门禁回答，不由 drift 回答；
  两个判据的分工写在 README 与架构文档里，但**没有一条用例正面钉"门禁会红"**
  （`gdt_covers_ctq` 的既有钉子钉的是声明与 CTQ 一致的场景）。
- 真实存量库 `data/state.db` 刻意未打开，所以"库里现有记录里有多少条没有 `ctq_refs`"
  未测（它们在本片之后会落进 `no_record_signature` 而不是 `in_sync`，读数会变差是好事）。
