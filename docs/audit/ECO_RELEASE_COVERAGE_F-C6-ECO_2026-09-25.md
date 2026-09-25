# F-C6-ECO 第 27 片：发布证据读 ECO（带哈希的交付物必须有闭合变更单覆盖）

日期：2026-09-25　归属：`industrialize.change_control` + `industrialize.release_evidence`
上一片：`docs/audit/ECO_CHANGE_ORDER_F-C6-ECO_2026-09-25.md`（ECO 生产者，第 26 片）

## 一、这一片要闭的是哪一格

第 26 片收尾时写下的原话（同一份登记，逐字）：

> **仍未做**：发布门没有「manifest 哈希有差却没有一笔闭合 ECO」这条 fail-closed 判据（下一片）。

第 26 片让 ECO **能产单**，这一片让它**说了不算**：`aipd release manifest` 现在把证据文档里
所有带 `path` + `sha256` 的条目逐个问一遍「这份内容是哪张单带来的，那张单复验过了吗」，
并把答案写进证据文档自己的 `eco` 段；发布门再读这一格。

一句话边界（后面 §三 展开）：这一格证明的是「**内容与某张闭合的单一致**」，
**不证明**「自上次发布以来只改了这些」——后者需要上一版产物清单当基线，本片没做，
所以登记里那条「仍未做」只闭合了一半，另一半留在 §七。

## 二、选型：为什么这片不做外部检索

按工作模式的例外条款主动说明跳过原因：本片**不引入新依赖、不新增数据结构**，
全部动作是把第 26 片已经落地的三张表（`eco_records` / `eco_affected` / `eco_transitions`）
接进第 22/23 片已经落地的证据装配与门禁。要借的模型（状态机、影响清单带哈希、
不许自批）在第 26 片已经做过一轮 OSS 检索并记录在案（那一轮里 frappe 的
`user != doc.get("owner")` 是唯一核到原文的判据，MIL-STD/ISO/ECSS 正文**没读到，因此不引用**）。
本片唯一的新问题是「本机自己的两个部件怎么接线」，答案只在本仓里，所以没有可检索的外部对象。

## 三、判据形状：四种处置、三档覆盖度，刻意不合成一个百分比

`_hashed_artifacts()` 递归走整份证据文档，凡同时带 `path` 与 `sha256` 的节点都算一条交付物
（路径先 `\\`→`/` 再 `posixpath.normpath`，所以 `./x//y.md` 与 `x/y.md` 认成同一个东西）。
**不硬编码**「报告 + 侧车」那两条——今天是 DFM 的两个文件，明天接装配图就是四个；
判据读的东西必须由文档自己声明，否则新增一类交付物会悄悄落在闸外。

对每条交付物四种处置（`_collect_eco`）：

| 处置 | 条件 | 后果 |
| --- | --- | --- |
| `covered` | 有一张 `VERIFIED` 的单，其 `eco_affected` 里指到该路径的那行 `after_sha256` 与实际哈希一致 | 计入覆盖 |
| `eco_change_uncovered` | 有单提到它，但**没有任何一张有效单**的哈希对得上 | **阻断** |
| `eco_change_unverified` | 哈希对得上，但那几张单还活着（`APPROVED`/`IMPLEMENTED`）没走到 `VERIFIED` | **阻断** |
| `undetermined` | 一条单都没提到它 | **不**阻断，只交清单 |

三条不显然的裁决，都写成了常驻用例：

1. **作废的单不许反过来背书内容**。`REJECTED` / `SUPERSEDED` 与还没批的 `DRAFT` /
   `PENDING_REVIEW` 都归入 `uncovered`，不算「等复验」。理由：哈希恰好对得上只说明
   「当初有人这么想过」，用它证明现在的东西是对的，等于拿一张作废的批件签字。
   分档由 `eco.py:51` 的 `VERIFICATION_PENDING` 与 `:54` 的 `DEAD_STATUSES` 两个常量表达，
   并由 `TestTheEndorsementBucketsAreExhaustive` 钉住**四个桶互不相交且并起来 == `ECO_STATUSES`**：
   以后谁加一档状态而没归类，这条立刻判红（变异电池 E12/E13 证它真会开火）。
2. **盲区不折算成违规**。本仓没有「上一版发布产物清单」可比，一条单没提到某文件时，
   **不知道**它有没有被改过。判成合格是假绿，判成违规是把「没登记」当成「改了没提单」。
3. **有单却没全覆盖只敢说 `partial`**。路径写法不一致、漏算一个侧车，都会让
   「全部交付物都有闭合单」这句话变成假话，所以 `coverage` 分三档
   `complete` / `partial` / `incomplete`，一张单都没有时整格 `undetermined` 并带
   `why=no_change_orders_in_scope`。

### 生产者与门禁的口径**刻意不同**

| 读数 | `aipd release manifest`（生产者） | `production_release_gate`（门） |
| --- | --- | --- |
| `complete` | 无 eco 问题项 | 通过 |
| `incomplete` / `unreadable` | 逐条**阻断**问题项 | 不通过，detail 点名 |
| `undetermined` / `partial`（有盲区） | **不**阻断，只写清单 | **不通过** |
| 整格缺失（老文档） | 不会出现（生产者总写） | 不通过，`no eco section` |

理由：生产者的 `rc` 管「这份证据有没有说错话」，门管「这句话够不够格用来签字」。
「不知道改没改」在第一栏是一句诚实的自述，在第二栏不能读成「核过了，没问题」——
这与门里 `ctq/gdt not both lists present` 那一族既有的 fail-closed 口径同构。

**收紧的代价是现算的，不是估的**：这道门既有口径是「任何一档 `evidence_checks` 失败即整体
`rc=2`，不看 `--target`」（`production_release_gate.py:751-753`），所以加一格判据 =
所有过门的夹具都得补齐这一格。首跑全量 4 条红：`test_cli.py::test_validate_minimal_manifest`
与 `::test_release_check_on_minimal_repo`（这两份"最小清单"本来就带齐了 ctq/gdt/owner/timestamp
的 fail-closed 数据，注释写着「缺失即失败，不得空真通过」，补 `eco` 是跟着既有约定走）、
`test_packaging.py` 的两条 `*_manifest_hashes_match_disk`（产物清单还没重锚，属预期，
收尾按重锚配方闭）。合计 3 个夹具文件、4 处清单补齐。

## 四、落点

| 位置 | 动作 |
| --- | --- |
| `src/aipd_os/release_manifest.py:594` | `_hashed_artifacts()`：递归收带哈希条目，路径归一，同路径首次出现为准 |
| `src/aipd_os/release_manifest.py:615` | `_collect_eco()`：四处置 + 三档 `coverage` + `open_orders` 点名 + `claimed_not_shipped` |
| `src/aipd_os/release_manifest.py:812` | 装配处 `doc.update(_collect_eco(db, tenant, project, _hashed_artifacts(doc), issues))` |
| `src/aipd_os/change_orders/eco.py:51,54` | `VERIFICATION_PENDING` / `DEAD_STATUSES` 两个分档常量 |
| `src/aipd_os/cli/commands_release.py:99` | `release manifest` 的人读输出多一行 `eco 覆盖=…`（含四个计数） |
| `scripts/production_release_gate.py:302-330` | 新证据判据 `change_control_closes_deliverables`（C6），四支各一条出口 |
| `tests/test_release_manifest_eco_coverage.py` | 20 条常驻用例（含 3 条真文档过真门的子进程用例） |
| `tests/test_production_release_gate.py` | +5 条：`complete` / 缺格 / `incomplete` 点名 / 盲区 / `partial` |
| `scripts/c6_coverage.py`、`src/aipd_os/registry_data.py` | 镜像同步（note 与两行能力卡） |

## 五、常驻用例怎么分组

- `TestBlindUntilAnyOrderExists`（2）：零张单 ⇒ `undetermined` + 清单等于全部带哈希条目，
  且条目集合**由文档算出**（不是硬编码两条）；
- `TestAClosedOrderCovers`（3）：`VERIFIED` + 哈希对上才算覆盖；侧车是一条**独立**声明
  （只给报告提单 ⇒ 整格只能 `partial`）；路径写法归一；
- `TestChangedWithoutAnOrderIsBlocking`（3）：哈希对不上 ⇒ 阻断项自己带 `blocking=True`
  （不许由别的格子的红代它作证）；被否的、被替代的各一条；
- `TestUnverifiedChangeIsBlocking`（2）：`IMPLEMENTED` / `APPROVED` 都阻断，且 `open_orders`
  点名到 eco_id 与当前状态；
- `TestClaimsThatShipNothing`（1）：单里声明了但本次没发的对象进 `claimed_not_shipped`，不判违规；
- `TestTheCriterionIsNotDecorative`（3）：把单推到 `VERIFIED` 才解掉阻断；复验后再改一次文件
  又判红；`eco` 段能过 JSON 落盘回读；
- `TestTheEndorsementBucketsAreExhaustive`（2）：分档穷尽 + 作废档是终态且与等复验档不相交；
- `TestTheGateReadsIt`（3）：**真证据文档交子进程跑真门**——盲区在生产者不阻断但在门不通过、
  全覆盖时门读 `2/2` 通过、复验后动手门又判红。断言只落在这一条判据自己的 `passed`/`detail`，
  不借整份文档的总体裁决（那份临时文档本来就因缺图纸/CTQ 而红，见 §六 末）。

夹具里两条是踩过才知道写的：`_walk_to()` 现在**到不了目标状态就抛**（它曾把「推到 REJECTED」
静默走成「推到 VERIFIED」，于是断言变绿而它以为自己在测被否的单）；`TestTheGateReadsIt` 每步
都显式 `_build()` 重刷盘上那份——门读的是文件，不是内存，`_cover_all()` 内部那次 `_build`
发生在建单**之前**，直接读旧文件会得到 `undetermined`。

## 六、端到端实测（真命令行，一次走完红→绿→红→绿）

夹具：`/tmp/eco27/state.db`（migration v19 的三张表）+ 金样品 `bracket.step` 出的真 DFM 报告。
两份带哈希的交付物**取自证据文档本身**，不是手抄：

```
dfm.md                 5f26d020eb8d433b…
dfm.md.evidence.json   a697df6b0ff708b1…
```

```
===== ① 一张单都没有 =====
$ aipd release manifest --db $DB --project $P --dfm-doc $DOC --out $EV
  eco 覆盖=undetermined 单=0 条 / 交付物=2 条：已闭合 0、无有效单 0、待复验 0、无单可判 2
  [阻断] no_ctq: Product Truth 里没有 active 的 ctq 记录；门禁 gdt_covers_ctq / ctq_has_inspection 都会 fail-closed
  [阻断] no_drawings: 没有传入任何图纸：图纸侧产不出 gdt，发布就绪不成立
  [阻断] bom_db_missing: BOM 库不存在：/tmp/eco27/bom.db（--db 是状态库，BOM 取同目录的 bom.db）
  ↳ rc=4
  eco ⟶ {"coverage": "undetermined", "covered": 0, "uncovered": [], "unverified": [],
         "undetermined": ["dfm.md", "dfm.md.evidence.json"], "by_status": {}}
```

零条 eco 问题项：门那一侧会拦，生产者这一侧不拦（§三 那条口径差的实物）。

```
===== ② 提了单，但 dfm.md 的哈希写错（sidecar 写对）=====
$ aipd eco create --db $DB --project $P --title dfm 报告改版 --creator 张三 --reason 补孔周留肉判据
ECO-001｜ECO｜DRAFT｜dfm 报告改版（创建人 张三）                                              rc=0
$ aipd eco affected ... --id ECO-001 --object-id dfm.md --change UPDATE \
    --before-sha256 aaaa…(64) --after-sha256 bbbb…(64) --actor 张三
ECO-001 影响清单第 1 行：UPDATE doc/dfm.md                                                    rc=0
$ aipd eco affected ... --object-id dfm.md.evidence.json --after-sha256 a697df6b… --actor 张三
ECO-001 影响清单第 2 行：UPDATE doc/dfm.md.evidence.json                                      rc=0
$ aipd eco transition --id ECO-001 --to PENDING_REVIEW --actor 张三   ⇒ ECO-001 → PENDING_REVIEW      rc=0
$ aipd eco transition --id ECO-001 --to APPROVED        --actor 李四   ⇒ ECO-001 → APPROVED（批准人 李四） rc=0
$ aipd eco transition --id ECO-001 --to IMPLEMENTED     --actor 李四   ⇒ ECO-001 → IMPLEMENTED         rc=0
$ aipd eco transition --id ECO-001 --to VERIFIED        --actor 王五   ⇒ ECO-001 → VERIFIED            rc=0

$ aipd release manifest --db $DB --project $P --dfm-doc $DOC --out $EV
  eco 覆盖=incomplete 单=1 条 / 交付物=2 条：已闭合 1、无有效单 1、待复验 0、无单可判 0
  [阻断] eco_change_uncovered: dfm.md 的实际哈希 5f26d020eb8d… 没有任何**有效**（VERIFIED）变更单覆盖：
         ECO-001(VERIFIED) 声称 bbbbbbbbbbbb…。改了内容却没有对应的闭合变更单
  ↳ rc=4        # 三条老问题项还在，这里只列 eco 那一支
  eco ⟶ {"coverage": "incomplete", "covered": 1, "uncovered": ["dfm.md"], "unverified": [],
         "undetermined": [], "by_status": {"VERIFIED": 1}}
```

一张已复验的单**没有**替写错的哈希背书：`covered=1` 与 `uncovered=[dfm.md]` 同时成立，
说明判定是逐条的，不看「有没有单」而看「这条内容的这个哈希有没有单」。

```
===== ③ 补一张写对了的单，只推到 APPROVED =====
$ aipd eco create ... --title dfm.md 哈希纠错 --creator 张三 --reason ECO-001 写错哈希
ECO-002｜ECO｜DRAFT｜dfm.md 哈希纠错（创建人 张三）                                            rc=0
$ aipd eco affected ... --id ECO-002 --object-id dfm.md --after-sha256 5f26d020eb8d… --actor 张三
ECO-002 影响清单第 1 行：UPDATE doc/dfm.md                                                    rc=0
$ aipd eco transition --id ECO-002 --to APPROVED --actor 李四    ⇒ ECO-002 → APPROVED（批准人 李四） rc=0
$ aipd eco show --db $DB --project $P --open
ECO-002｜ECO｜APPROVED｜dfm.md 哈希纠错                                                        rc=0

$ aipd release manifest --db $DB --project $P --dfm-doc $DOC --out $EV
  eco 覆盖=incomplete 单=2 条 / 交付物=2 条：已闭合 1、无有效单 0、待复验 1、无单可判 0
  [阻断] eco_change_unverified: dfm.md 的内容与单 ['ECO-002'] 的 after_sha256 一致，
         但那些单还没到 VERIFIED（现状态 ['APPROVED']）：未复验的变更不该进发布
  ↳ rc=4
  eco ⟶ {"coverage": "incomplete", "covered": 1, "uncovered": [], "unverified": ["dfm.md"],
         "undetermined": [], "by_status": {"VERIFIED": 1, "APPROVED": 1}}
```

**批了不等于复验了**：这一支的 `open_orders` 点名到 `ECO-002 / APPROVED`，
看得出差哪一张卡住发布，而不是只得到一个数。

```
===== ④ 把 ECO-002 推到 VERIFIED =====
$ aipd eco transition --id ECO-002 --to PENDING_REVIEW --actor 张三
eco transition：ECO-002：APPROVED → PENDING_REVIEW 不是合法转移（可去：['IMPLEMENTED', 'SUPERSEDED']）  rc=4
$ aipd eco transition --id ECO-002 --to APPROVED --actor 李四
eco transition：ECO-002：APPROVED → APPROVED 不是合法转移（可去：['IMPLEMENTED', 'SUPERSEDED']）        rc=4
$ aipd eco transition --id ECO-002 --to IMPLEMENTED --actor 李四   ⇒ ECO-002 → IMPLEMENTED  rc=0
$ aipd eco transition --id ECO-002 --to VERIFIED --actor 王五      ⇒ ECO-002 → VERIFIED     rc=0

$ aipd release manifest --db $DB --project $P --dfm-doc $DOC --out $EV
  eco 覆盖=complete 单=2 条 / 交付物=2 条：已闭合 2、无有效单 0、待复验 0、无单可判 0        rc=4
  eco ⟶ {"coverage": "complete", "covered": 2, "uncovered": [], "unverified": [],
         "undetermined": [], "by_status": {"VERIFIED": 2}}
```

头两条 `rc=4` 是脚本按主干路径重放前两步撞出来的，**原样留着**：状态机不接受回退，
也不接受原地重放。这一轮的 `rc=4` 全部来自别的格子（缺 CTQ、缺图纸、缺 BOM 库），
eco 那一支已经没有问题项了。

```
===== ⑤ 复验之后又动了 dfm.md 一行 =====
（$DOC 追加一行 ⇒ 实际哈希变成 ed96a55ef5f638c4…）
$ aipd release manifest --db $DB --project $P --dfm-doc $DOC --out $EV
  eco 覆盖=incomplete 单=2 条 / 交付物=2 条：已闭合 1、无有效单 1、待复验 0、无单可判 0
  [阻断] eco_change_uncovered: dfm.md 的实际哈希 ed96a55ef5f6… 没有任何**有效**（VERIFIED）变更单覆盖：
         ECO-001(VERIFIED) 声称 bbbbbbbbbbbb…；ECO-002(VERIFIED) 声称 5f26d020eb8d…。改了内容却没有对应的闭合变更单
  ↳ rc=4

$ aipd validate --manifest $EV --target C6      # 门读同一格
{
  "check": "change_control_closes_deliverables",
  "level": "C6",
  "passed": false,
  "detail": "coverage=incomplete; 缺闭合单或未复验: ['dfm.md']"
}
```

detail 里把**两张单各自声称什么**都印出来了——差在哪一目了然，不必再去开库查。

```
===== ⑥ 补一张覆盖新哈希的单，门这一侧转绿 =====
$ aipd eco create ... --title dfm.md 追加一句 --creator 张三           ⇒ ECO-003  rc=0
$ aipd eco affected ... --id ECO-003 --object-id dfm.md \
    --before-sha256 5f26d020eb8d… --after-sha256 ed96a55ef5f6… --actor 张三       rc=0
$ aipd eco transition --id ECO-003 --to {PENDING_REVIEW,APPROVED,IMPLEMENTED,VERIFIED}
    张三 → 李四 → 李四（带 --evidence-ref release v5.7.1 --effective-at 2026-09-25T00:00:00+00:00）
    → 王五（带 --evidence-ref 复验记录 R-2）                                        全部 rc=0

$ aipd release manifest --db $DB --project $P --dfm-doc $DOC --out $EV
  eco ⟶ {"coverage": "complete", "covered": 2, "artifacts": 2, "uncovered": [], "unverified": [],
         "undetermined": [], "by_status": {"VERIFIED": 3}}
$ aipd validate --manifest $EV --target C6
{
  "check": "change_control_closes_deliverables",
  "level": "C6",
  "passed": true,
  "detail": "coverage=complete; 2/2 条带哈希交付物由 VERIFIED 单逐条对上 after_sha256"
}
```

两处**不许读过头**：⑥ 的 `aipd release manifest` 仍 `rc=4`，`aipd validate` 的
`passed` 仍是 `false`、`achieved` 仍是 `null` —— 因为这份临时文档本来就缺图纸、缺 CTQ、
缺 BOM 库（`drawing_cad_same_revision` / `bom_matches_model` / `gdt_covers_ctq` /
`ctq_has_inspection` 四条各自都红）。本片能主张的是：**这一条判据的读数跟着
`eco` 段动了**（红→绿，且 detail 由点名路径变成 2/2 对上），不是「这份文档可以放行了」。
常驻用例 `TestTheGateReadsIt` 同样只断这一条判据自己的 `passed`/`detail`。

## 七、这一片没做的事

1. **没有上一版产物清单当基线** ⇒ 只能证明「内容与某张闭合单一致」，
   不能证明「自上次锚定发布以来**只**改了这些」。要闭这条，得把上一次发布的
   `SOURCE_MANIFEST` 文件清单存成本次的比对基准（登记为后续项）。
2. **`undetermined` 的成因没细分**：「新文件、从没提过单」与「老文件、动了没提单」
   在这一格里长得一样。有基线才能分开。
3. **署名没有身份源**（第 26 片就记着，本片没改）：`actor` 是不是某个真人，机器验不了。
4. **`gates.approved_by DEFAULT 'AI-internal'`**（`src/aipd_os/state/migrations/schema.py:173`，
   同一句形状在 `src/aipd_os/state/db.py:222` 又出现一次）
   那个「不写审批人也算 AI 批过」的形状仍在，属主裁；ECO 侧刻意没复刻它。
5. **门只看 `eco` 段，不重算哈希**：门没有第二个真值源，它信生产者写进文档的那份读数
   （与 `file_openable` 那类自己重算的判据不同）。要防的是「侧车/文档被手改」——
   那一层由 `SOURCE_MANIFEST` 哈希与 `audit_repo --strict` 管，不在这一格。
6. **ECO 不联动失效传播**：一张 `VERIFIED` 的单不会让尺寸链/成本/Product Truth 快照失效。

## 八、收口读数

| 项 | 读数 |
| --- | --- |
| 全量用例 | 2003 → **2028** 条（新增 25：生产者侧 20 + 门侧 5）；首跑 `4 failed, 2021 passed, 3 skipped`，补齐 2 处 `test_cli.py` 夹具后剩 2 条红＝产物清单还没重锚（预期，收尾按重锚配方闭） |
| ruff（CI 范围 `src tests state_service`） | All checks passed |
| ruff（`scripts/production_release_gate.py`，不在 CI 范围） | 9 条，与 `git show HEAD:` 同一份的 9 条同数 ⇒ 本片**未新增** lint 债 |
| mypy（`src tests`） | Success: no issues found in 413 source files |
| C6 普查 | `scripts/c6_coverage.py` 15 项 = 有生产者 14 / 只有校验方 0 / 零实现 1（档位不变，note 与用例数更新）；`--self-test` 7/7 条注入被抓 |
| 变异电池 | `/tmp/slice27-mutations.py` **17 条：杀 17 / 活 0 / 注入无效 0**（每条先跑对照组） |
| 端到端 | 真命令行走完红→绿→红→绿六步（§六逐字），门侧读数由子进程真跑 `aipd validate` 取得 |
| 发布门 `--release-ready --tag` | 见文末重锚补记 |
| 重锚 | 见文末重锚补记 |

### 变异电池的两处自我修正

- 原 E2 的锚点是 `living = [... not in DEAD_STATUSES]`。判据改成
  「只有 `APPROVED`/`IMPLEMENTED` 算等复验」之后，那条锚命中 0 次 ⇒ 电池自己报
  「注入无效」而不是「杀掉」——这正是把 `rc∈{4,5}` 且无失败行判成无效的用处。
  锚换成现役那行、目标用例补上 `SUPERSEDED` 那条，才真的开火。
- 第一轮给门侧想过两条注入：把 `coverage == 'complete'` 放宽成 `'complete' in str(coverage)`、
  把「缺 `coverage` 键」的分支短路。两条都**行为等价**（能走到那一支的 `coverage` 只有
  `complete`；短路后仍由 `else` 判红），换了也是化妆，故按第 26 片 G19 的教训丢掉，
  换成四条真会翻转读数的（不点名 / 盲区读成通过 / 缺格读成通过 / 键名接错）。
