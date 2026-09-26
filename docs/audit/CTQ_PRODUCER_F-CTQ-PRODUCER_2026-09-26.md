# F-CTQ-PRODUCER 第 56 片：`aipd ctq add`——血缘链的头第一次有生产写入点

日期：2026-09-26 · 分支：main · 相关：F-LINEAGE-PROD 第 43 片 / F-REWORK 第 45 片 / F-DRIFT 第 51 片

## 一、要拍的问题

第 43/45/46/51/54 片把 `CTQ → 图纸声明 → DXF` 与「发现漂移 → 落刀 → 返工」接通之后，
一直没人问过一句：**CTQ 本身谁写**。本轮复核的结论是"只有测试写"，
于是链条第二跳在真库里根本没有输入。

## 二、前提复核（生产侧与测试侧分开数）

按「写『无人生产』之前必须两侧各数一遍」的规矩：

```
$ grep -rn 'record_type="ctq"' --include='*.py' src/            # 只有读
src/aipd_os/release_manifest.py:69   truth.query(record_type="ctq")
src/aipd_os/cad/spec_rework.py:84    store.query(record_type="ctq", status="active")
src/aipd_os/cli/commands_drawing.py:86  ↑ 同一个读法
src/aipd_os/cad/spec_from_truth.py:55   （docstring 说明它收这个 query 的返回）
```

测试侧则到处是 `store.add(TruthRecord(record_type="ctq", …))`（11 个文件），
`release_manifest.py:6` 自己也写着「全仓 `ctq`/`gdt` 两个数组只出现在测试夹具里」。
`scripts/` 与 `state_service/` 里没有任何写入形态。⇒ **生产侧 0 个写入点，成立。**

## 三、为什么不复用 PI gate（选型）

`product_intelligence/gate.py:455,476` 只写 `requirement` 与 `feature`；
Feature 模型（`product_intelligence/models.py:507-519`）的字段是
`feature_id / title / description / feature_type / source_requirement_ids / assumptions /
constraints / definition_status / epistemic_status / lifecycle_status`——**一个公差字段都没有**。
让 gate 顺带派生 CTQ 等于由代码发明上下限，那是发明工程要求，不是转译。
外部候选本轮查了 LinkML 的 range/pattern 校验面，**未检索到一手规范页**
（搜索结果全是内容农场），故这条按"未找到"记，不拿它当依据；
落点回到仓内既有形状：属主自述 + 复用 `gate_criteria._derive_trust` 推信任级。

## 四、形状与拒绝面（每条都有常驻用例与电池臂）

- 七个必填：`--feature --drawing-feature --nominal --lower --upper --inspection --by`；
  数值校验只留在 `declare_ctq` 一处（argparse 故意不写 `type=float`），错误文案点名是哪一格；
- 校验：`lower < upper`、`lower ≤ nominal ≤ upper`、认识论态只认 `_derive_trust` 分支的
  `V/C/E/A/U`、空串一律拒；**任一条不满足就一条都不落库**；
- 信任级不自封：`_derive_trust` 三档实测 `A + 无引用 → unverified`、
  `V + 无引用 → medium`、`V + --test-ref → verified`；
- 幂等：同一份声明重跑复用原 `record_id`；**比的是内容不是名字**（改了上下限就是另一份声明）；
- 冲突：同一个 `drawing_feature` 上已有别的 active CTQ ⇒ 点名既有记录并拒，
  因为 `spec_from_truth` 遇到两条抢一个尺寸会把**两条一起撤回**（它不按遍历顺序挑赢家）。

顺手补的一个洞（本轮真跑出来的）：库里 0 条 active CTQ 时
`aipd drawing spec` 旧行为是写一份 `features: []` 的声明 + 落一条 `ctq_refs: []` 的血缘记录
+ `ok:true` 退 0；现在判未收口（退 4，文件与血缘都不写，payload 多一格 `empty_declaration`）。

一处既有断言随之改判：`tests/test_cad_spec_from_truth.py::TestCliProducerAndGate::`
`test_inactive_records_are_not_declared` 原钉的是「库里只剩一条 superseded CTQ 时
写一份 `features: []` 并退 0」，现钉「不写文件、退 4、`empty_declaration` 为真」；
它的原意（作废的 CTQ 不许再往图纸上贴公差）仍然成立，而且更强——文件根本不存在。
这条复算是被干净树跑批抓出来的：第一轮 attestation `1 failed, 2448 passed`，
红的就是它，说明这条旧断言钉的是缺省保证而不是应然。

## 五、真库读数（生产 CLI 自己造出来的库，`/tmp/s56/state2.db`，项目 `CTQ-CHAIN2`）

```
$ aipd drawing spec --db … --project CTQ-CHAIN2 --out spec2.json --json    # 空库
{"command":"drawing spec","ok":false,"ctq_records":0,"declared":0,"gaps":[],
 "empty_declaration":true,"spec":null,"out":null}                          # rc=4，文件不存在
$ aipd ctq add --db … --feature hole_8 --drawing-feature TOP.hole_1 \
      --nominal 8.0 --lower 7.95 --upper 8.05 --inspection CMM --by 潘工 --json
{"ok":true,"record_id":"T-001","created":true,"trust_level":"unverified", …}  # rc=0
$ 同上再跑一次 ⇒ "created":false、record_id 仍是 T-001                      # rc=0
$ 换数值抢同一个 TOP.hole_1 ⇒ rc=2，点名「已经被 CTQ T-001（hole_8，[7.95, 8.05]）认领」
$ aipd drawing spec --out spec2.json
{"ok":true,"declared":1,"lineage":{"record_id":"T-002","ctq_refs":["T-001"],"edges":1}}
$ aipd truth drift ⇒ {"scanned":1,"counts":{"in_sync":1, …}}
```

## 六、一条实测出来的边界（本轮按"应该能发现"写断言，它红了，于是改成钉缺席）

`drawing_spec` 记录的身份键是**声明文件的哈希**（`cli/commands_drift.py:_spec_signature_resolver`
比 `spec_sha256` 与 `spec_file_digest(path)`），所以"改了 CTQ 限值、声明文件没动"这一格
`truth drift` 与 `truth sweep` 都看不见——sweep 甚至退 0（它扫到 1 条、零漂移，
且不许在看不见漂移时顺手标 stale）。那条路上今天只有 `truth propagate --upstream <ctq>` 走得通，
端到端用例就是这么走的：propagate 标 stale + 建任务 → `truth rework --all-pending` 退 0
→ 声明文件按新限值被重写。复合身份键（文件面 + 来源面，旧记录按不可判点名）记为第 57 片。

## 七、变异电池（`/tmp/s56/battery.py` + `battery2.py`，worktree `/tmp/s56w @ 336441e`）

对照臂未注入 `21 passed`（rc=0）。九条臂全部 KILLED、0 存活、0 注入无效：
C1 域内校验、C2 `lower<upper`、C3 信任级自封、C4 尺寸查重、C5 幂等、C6 幂等只看名字、
C7 空声明恢复旧行为、C8 `--by` 给机器缺省、C9 README 镜像缺一条。

两条臂第一轮报"注入无效"，都不是门禁没牙，而是电池自己要修：
- **C2**：把 `lower >= upper` 关掉后，1.5∈[2.0,1.0] 那条夹具被**相邻的域内守卫**顺手挡住
  （两条守卫互相遮蔽）⇒ 补一条退化区间用例（8.0/8.0/8.0，只有 `lower<upper` 看得见）当原告，
  第二轮 KILLED。这正是"冗余守卫要各自有一条只关掉自己的注入"那条规矩。
- **C9**：第一轮的注入改的是行内 feature 名，README 里 needle `aipd ctq add` 还在 ⇒
  测的不是它要测的那格；第二轮改成把命令名本身打错，KILLED。

## 八、终读数

@@FINAL@@

## 九、遗留

- 改一条已声明 CTQ 的限值（revise）与停用/取代（deprecate）今天没有命令：
  端到端用例里的限值变化是走库层 `store.update` 做的，所以"谁在什么时候把 8.05 改成 8.10"
  在 CTQ 这一格**没有审计入口**（图纸声明与 DXF 那两格有）。
- CTQ 变更对 drift/sweep 不可见（§六），修法记为第 57 片（任务 #64）。
- `aipd ctq` 只有 `add` 一个 verb：`main.py` 的 `ctq_sub` 里只挂了 `add_parser("add")`，
  今天要看一个项目的 CTQ 清单只能借 `aipd release manifest`（`doc["ctq"]`）或
  `aipd truth drift` 的读数，没有专门的列表命令。
- 本地开发库 `data/state.db` 刻意未打开，真实存量库里有几条 CTQ 仍未量。
