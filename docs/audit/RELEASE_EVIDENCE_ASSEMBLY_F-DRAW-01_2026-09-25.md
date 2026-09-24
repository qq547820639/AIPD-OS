# F-DRAW-01 第 14 片：发布证据看得见装配图，并顺带修掉我给状态库加表的坑

这次任务起先只有一句话：让 `aipd release manifest` 知道图纸里有装配图。
做起来先撞到一个更要紧的问题——我上一片的 `--db` 接线把 BOM 表写进了权威状态库。

## 一、两个缺陷，一个比一个严重

### 1.1 `--db` 指错了库，只读操作给状态库加了表（本片先修这个）

第 13 片我写的是 `BomStore(Path(args.db))`。而本仓的口径是：

- `src/aipd_os/bom/store.py:3-5`：「BOM 使用独立库文件……**避免给权威状态库加表**
  （迁移冻结）」；
- `src/aipd_os/cli/commands_manufacturing.py:16`：`_bom_store_path(db) = db.parent/"bom.db"`
  才是产品实际用的换算，`release_manifest.py` 里也另抄了一份同样的表达式。

真跑命令行复现（临时目录，不碰任何开发者库）：

```
BEFORE: state.db tables = 42 | bom tables: []
$ aipd drawing assembly --manifest assembly.json --out assy.dxf --views TOP \
      --db state.db --bom BOM-001 --project rel-proj
rc=2   BOM BOM-001 在 default/default 下不存在
AFTER: tables = 46 | bom tables: ['bom_changes','bom_id_sequences','bom_lines','boms']
```

也就是说：**命令失败了，副作用却留下了**。`BomStore.__init__` 会建库建表，
所以一个「读数量」的只读参数把四张表加进了 Product Truth 的状态库，
正是模块开头写明不能发生的事。修法不是加个 try/finally 回滚，而是把路径换算收成一处：

- 新增 `bom/store.py:bom_store_path(db_path)`（`<目录>/bom.db`），docstring 同时写明
  「只读消费方在构造 `BomStore` 之前必须先确认该文件存在」；
- `commands_manufacturing._bom_store_path`、`release_manifest._collect_bom`、
  `cmd_drawing_assembly` 三处改为走它，删掉各自抄的那份表达式；
- 只读方读不到就报 `bom_db_missing` / rc=2，**不构造 BomStore**，因此不会凭空建库。

夹具也改成走同一个 `bom_store_path`：这样「BOM 到底放哪个文件」一旦被改动，
测试会跟着红，而不是像这次一样测试与命令行各认一个路径、两边都绿。

### 1.2 装配图在发布证据里不存在

`aipd release manifest` 改前只报 `drawing_count`，一张装配图和一张单件图在文档里
长得一样；而装配图特有的 `assembly_issues` 被整个忽略。真跑：

```
drawing_count: 1 | issues kinds: [] | ok/blocking: True False     ← 一张漏零件的图
```

C6 的口径是「总装图 + 零件图」两类都在，两类都缺不动手判。所以补三类判定：

| 判据 | 触发 | blocking |
|---|---|---|
| `assembly_unresolved` | 图纸证据里 `assembly_issues` 非空（球标↔BOM 未闭合） | **是** |
| `assembly_bom_mismatch` | 图上数量取自 BOM A，本份证据核的是 BOM B | **是** |
| `assembly_bom_unverified` | 出图时没接 BOM ⇒ 明细表没有数量列 | 否 |

外加 `evidence.drawings[].kind`（`part` / `assembly`）与
`part_drawing_count` / `assembly_drawing_count` 两个细分计数；
`drawing_count` 的既有含义（总数）**没动**，避免顺手改掉别人在读的字段。

第三类刻意是非阻断：没接 BOM 的装配图仍然成立（球标 + ITEM/PART 都在），
把它判死等于逼用户接一个他还没准备好的 BOM；但必须留一行提示，
否则「这张图的数量是哪来的」没人会被提醒去问。

## 二、判据为什么可机器核

- **不重写图纸侧的判定**：manifest 只把图纸证据里的 `assembly_issues` 逐条搬进
  `issues`，不在这里重算球标绑定（那是 `cad/assembly.bind_bom` 的活）。
- 「数量来自另一张 BOM」这条只在两边都实名时才判；没给 `--bom` 就不凭空造判据。
- 分类靠证据里的 `assembly` 字段，而不是靠文件名——文件名会骗人，
  图纸是不是装配图由出图那一步决定。

## 三、真机读数（临时目录）

```
$ aipd release manifest --db state.db --project rel2 --drawing assy.dxf --bom BOM-001
  drawing_count = 1
  assembly_drawing_count = 1
  part_drawing_count = 0
  无问题项                                                     rc=0

（往 bom.db 的 BOM-001 里加一行 SCREW-77，重出装配图 → 该图 rc=4，随后：）
$ aipd release manifest --db state.db --project rel2 --drawing leak.dxf --bom BOM-001
  [阻断] assembly_unresolved: leak.dxf：装配图有 1 条未收口（球标↔BOM 未闭合），
         第一条：BOM 行 'SCREW-77'（LINE-003，数量 12 pcs）在图上没有球标指它：这张装配图漏了零件
                                                                                     rc=4
$ aipd release manifest --db state.db --project rel2 --drawing assy.dxf --bom BOM-002
  [阻断] assembly_bom_mismatch: assy.dxf：图上的数量取自 BOM BOM-001，本份证据核的是 BOM BOM-002；
         两边不是同一张表，计数一致性不成立
  [阻断] no_bom_lines: BOM 里没有行（bom_id=BOM-002），计数一致性无从谈起              rc=4
```

## 四、用例与变异

- `tests/test_release_manifest.py` +11 条（分类、单件图形状不变、漏零件阻断、
  跨 BOM 阻断、未绑库只作提示、缺 bom.db 不建库）；
- `tests/test_cad_assembly_bom_link.py` +4 条（状态库表集不变、同目录 bom.db 能读到、
  缺库不建库、状态库路径写错即使 bom.db 能读也拒绝）；
- 变异电池 R1-R8（`/tmp/mutate_release_manifest.py`）：**8/8 killed**；
  上一片 17 条复跑仍 **17/17 killed**。
  R7 首轮把目标用例写成了单件图那条（永远走不到 `_check_assembly`，等于空判），
  补了「未绑 BOM 的装配图」这条用例后才真成立——**targeting 也要被检**，
  这是 baseline-先跑绿那道前提第二次抓住我。

N8（上一片的一条幸存）在这一片才被杀掉：去掉状态库存在性检查后，同目录恰好有
bom.db 时会照常出图。新加的 `test_wrong_state_db_path_is_refused_even_if_a_bom_sits_there`
就是照着这个幸存补的。

## 五、边界

- manifest **不重算**球标闭合，只搬运图纸证据里的判定：没有证据 sidecar 的装配图
  走的是既有的 `drawing_evidence_missing`（阻断），不是新判据。
- 仍不判：图纸上的球标数量与 BOM 行的**材料/供应商**一致性（明细表还没取材料列）、
  一张 BOM 对应多张装配图的去重、以及「C6 是否要求装配图必须绑 BOM」——
  最后这条要业务口径，先只记 `assembly_bom_unverified` 提示。
- `approval_status` 仍由属主填，生产者不代为置 approved。

## 六、复算

```bash
cd AIPD-OS
.venv/bin/python -m pytest tests/test_release_manifest.py tests/test_cad_assembly_bom_link.py \
    tests/test_cad_assembly_balloons.py -q                                          # 68 passed
.venv/bin/python -m ruff check src tests                                             # All checks passed
.venv/bin/python -m mypy src tests                                                   # 396 files, no issues
.venv/bin/python /tmp/mutate_release_manifest.py                                     # 8/8 killed
```

电池脚本是临时件；**判据以 §一 的表与 §四 的清单为准**，照表重放即可。
