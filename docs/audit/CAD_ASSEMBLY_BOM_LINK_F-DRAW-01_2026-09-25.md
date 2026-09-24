# F-DRAW-01 第 13 片：球标 ↔ BOM 行交叉核对，数量只认 BOM

第 12 片出的装配图明细表只有 ITEM/PART 两列，并在行内写明「数量权威在 BOM，本轮未接线」，
`cad.2d_drawings` 的 limitation 也把「球标↔BOM 行交叉核对」列为未做。本片补那条接线。

## 一、这一片的价值在「怎么对应」，不在「能不能带出数量」

带数量本身是三行代码。真正要定的是**对应关系从哪来**，而本仓对这件事早就有结论：

- `aipd drawing spec` 的注释写着「全程不按名字自动映射，linkage 由需求侧显式写」；
- `supply_chain/impact` 的模块 docstring 写着「匹配只认归一化后的全等（strip + 小写），
  **不做子串猜**——「支架」不得带出「支架座」」。

所以装配侧同一条纪律落地为：manifest 里显式写 `"bom_item": "BRACKET-01"`。
**没写的零件即使与某行 item 完全同名也不算对上**，并且这条要用一条反证用例钉住——
它是这一片最容易「顺手做聪明」的地方，而做聪明的结果是图纸声称了一个作者从没说过的对应。

## 二、候选方案（本轮是既有面上的小接线，未做外部检索；说明理由）

这一片不引入新依赖、不改外部契约，改的是本仓两个模块之间的一条边，属于
「影响范围明确的局部改动」，按用户给的例外条款跳过外部调研。范围内的两个真实选择：

| 选择 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A. 按 `part.name` 归一后匹配 `line.item` | 用户零声明，开箱就能出数量 | 图纸在编对应关系；同名不同件会静默绑错；与本仓两条既有纪律冲突 | 否 |
| B. manifest 声明 `bom_item`（**选中**） | 对应关系可追责；绑不上就是声明错误，能判未收口 | 多一个字段要写 | 采用 |

标识归一函数原本在 `supply_chain/impact.py:37` 有一份私有 `_norm`。第二处要用它的时候
**没有再抄一份**：把它提为 `bom/models.norm_item`（带「不是模糊匹配」的说明），
`impact.py` 改为引用。两处各写一份迟早会各自漂，而这个函数一漂就是「本该判歧义的
被当成匹配」。

## 三、判据为什么可机器核

1. **数量的来源只有一个**：`bind_bom` 只读 `line.quantity` / `line.unit`；
   解析器 `parse_assembly_manifest` 白名单里**没有** `quantity`，所以 manifest 里写了
   也不会进到零件数据。这条原本不显形（见 §五 的 N2），现在由
   `test_manifest_quantity_never_reaches_the_part_record` 直接断言。
2. **两头闭合**：球标找不到行 / 一行有歧义 / 零件没声明 / BOM 有行图上没号 ⇒ 四种都进
   `assembly_issues` ⇒ 命令行退出码 4。
3. **留空不是 0**：绑不上时 `qty is None`，表格里那一格是空串。图纸上 0 与「没核到」
   差一个量级，用例 `test_unbound_part_is_printed_with_an_empty_qty_not_a_zero` 钉住。
4. **画出来了才算数**：`test_bound_quantities_are_actually_drawn_not_only_in_the_evidence`
   从 DXF 的 `TEXT[layer=="TABLECONTENT"]` 里读出 `4 / 2 / pcs / set`，
   不看证据字典——证据里有数量不等于图纸上看得见数量。
5. **没绑 BOM 时长相不变**：列仍是 `["ITEM","PART"]`，`bom` 为 `null`，
   第 12 片的 28 条用例一条都没改判据。

## 四、真机读数（临时目录，非记忆）

```
$ aipd drawing assembly --manifest assembly.json --out assy.dxf --part ASSY-1 --views TOP \
      --db state.db --bom BOM-001 --project assy-proj
已出装配图：/tmp/aipd-bom-AQ03/assy.dxf（A3 1:1.0，2 个零件 / 1 个视图）
  ASSY_TOP    包络 40.0x65.0mm 实线 16 条 / 虚线 0 条（分段按零件归属：16 段）
        1 支架           可见折线 8 条 / 隐藏 0 条 挂点 (0, 0)
        2 压板           可见折线 8 条 / 隐藏 0 条 挂点 (0, 45)
      球标 2 个，包络投影重叠 0.0mm²
明细表：2 行，列 ['ITEM', 'PART', 'QTY', 'UNIT']，绘制方式 ezdxf.addons.tablepainter
  数量与单位来自 BOM BOM-001（2 行）；对应关系靠 manifest 的 bom_item 声明，不按零件名字猜
  没有做的事：干涉检查（只报包络投影重叠，不做实体求交）、爆炸图/装配约束、明细表材料列（材料在 BOM 行上，尚未取用）。
rc=0
```

往 BOM 里再塞一行图上没有的 `SCREW-77` 之后：

```
  装配未收口：BOM 行 'SCREW-77'（LINE-003，数量 12 pcs）在图上没有球标指它：这张装配图漏了零件
rc=4
```

**这一段命令行又抓到一个缺陷**：`--bom BOM-999`（编号写错）当时被当成「空 BOM」，
输出是逐条「球标 1/2 声明的行在 BOM 里找不到」——听起来像内容对不上，实际是
**根本没读到那张表**。两句话的处置完全不同（改编号 vs 改 BOM 内容），所以补了
「那张 BOM 必须真在，否则当场 rc=2」。顺带钉住另一件事：`BomStore(path)` 会在给定
路径上 `mkdir` 并建表，所以 `--db` 的 `is_file` 检查必须在构造之前，
命令行不许在写错的路径上凭空造一个数据库。

## 五、用例与变异（14 条变异，两条首轮幸存）

`tests/test_cad_assembly_bom_link.py` 20 条。变异表（`/tmp/mutate_bom_link.py`，
先跑 baseline 绿、node id 失效单独报 INVALID-TEST-ID）：

| 变异 | 结果 |
|---|---|
| N1 没声明的零件按名字匹配 | 杀掉 |
| N2 解析器把 manifest 的 quantity 带进零件数据 | **首轮幸存** → 补断言后杀掉 |
| N3 归一全等改成子串包含 | 杀掉 |
| N4 BOM 多行不再报（只核对图纸一侧） | 杀掉 |
| N5 找不到行时数量写 0 | 杀掉 |
| N6 歧义时取第一行 | 杀掉 |
| N7 `--db` 单独给也放行 | 杀掉 |
| N8 去掉「库文件不存在」的检查 | **首轮幸存** → 补断言后杀掉 |
| N9 列不生长（绑定结果不印） | 杀掉 |
| N10 绑定问题算了但不并进 hold 集合 | 杀掉 |
| N11 大小写/空格差异被判成不同 item | 杀掉 |
| N12 `bom_item` 写空串被放过 | 杀掉 |
| N13 不再检查那张 BOM 真在 | 杀掉 |
| N14 表格画了但数量单元格跳过 | 杀掉 |

两条幸存各自说明一件事：

- **N2 是等价变异**：因为解析器本来就不读 `quantity`，「改从 manifest 取数量」在使用点
  根本注入不进去。这不是测试太弱，而是这条规矩**不显形**——所以把它写成对解析边界的
  直接断言，守卫才真的存在。
- **N8 被新代码掩盖**：加了「BOM 必须真在」之后，去掉「库文件不存在」的检查仍然返回
  rc=2（`BomStore` 会自己建库，然后 `get_bom` 读不到 ⇒ 同一支另一条分支兜住）。
  rc 一样，但**副作用不一样**：那条分支会在写错的路径上建出一个数据库文件。
  补 `assert not ghost.exists()` 之后杀掉。教训：只断言退出码的用例，会把
  「判对了但顺手干了别的」读成通过。

## 六、边界（不要当成已具备）

- 明细表仍**不含材料列**，尽管 `BomLine.material` 一直有值——取用它是下一小步，
  本轮不顺手扩面，避免「一次改动同时改判据和扩输出」。
- 绑定要求 **一对一**：同一个 item 在 BOM 里出现两次即判歧义并留空。
  真实的 BOM 允许同一 item 多行（不同供应商/不同阶段），那种情形本仓今天怎么合并
  还没有权威口径，所以不猜。
- 只读 `bom_lines`，不改 BOM：图纸侧没有任何写 BOM 的路径。
- 干涉检查、爆炸图、装配约束/照旧未做（第 12 片的记录仍然成立）。
- C6 生产图纸包整体仍不成立。

## 七、复算

```bash
cd AIPD-OS
.venv/bin/python -m pytest tests/test_cad_assembly_bom_link.py -q          # 20 passed
.venv/bin/python -m pytest tests/test_cad_assembly_balloons.py -q          # 28 passed（判据未改）
.venv/bin/python -m pytest tests/test_cad_*.py tests/test_bom.py \
    tests/test_lab_impact_propagation.py tests/test_supply_chain.py \
    tests/test_import_cycles.py -q                                          # 317 passed
.venv/bin/python -m ruff check src tests                                    # All checks passed
.venv/bin/python -m mypy src tests                                          # 396 files, no issues
.venv/bin/python /tmp/mutate_bom_link.py                                    # 14/14 killed
.venv/bin/python /tmp/mutate_assembly.py                                    # 12/12 killed（上一片不回归）
```

> 两个电池脚本都在 `/tmp`，是临时件、跑完即删；**变异清单以 §五 与上一片 §六 的表为准**
> （每条都写了改哪一行、改成什么、该红哪条用例），照表重放即可，不依赖那个文件还在。
> 复算时值得照抄的是脚本那三条前提：先跑 baseline 绿、node id 失效单独报
> INVALID-TEST-ID、还原后逐文件比对内容一致。

命令行造库与造图：见 §四（临时目录，跑完删；不碰任何开发者数据库）。

## 八、收尾读数（全部来自本轮实跑输出，非记忆）

- 新用例 **20 条**；第 12 片的 28 条一条没改判据（`--db/--bom` 不给时形状完全不变）。
- 受影响面合跑（`tests/test_cad_*.py tests/test_bom.py
  tests/test_lab_impact_propagation.py tests/test_supply_chain.py
  tests/test_import_cycles.py`）：**317 passed**。
- 全量：**1689 passed / 0 failed / 3 skipped（总 1692）**。
- `ruff check src tests`：All checks passed；`mypy src tests`：
  **Success: no issues found in 396 source files**（上轮 395）。
- 变异：本片 **14 条，首轮 N2/N8 幸存**，各补一条断言后 **14/14 killed**；
  第 12 片的 12 条复跑仍 **12/12 killed**（无回归）。
- `RELEASE_MANIFEST.json` / `SOURCE_MANIFEST.json` 各 **594 个文件**（+新测试文件），
  `SOURCE_MANIFEST.source_commit` 仍是 `a66040520139…`（v5.6.0 那个提交），没跟着 HEAD 漂。
- `production_release_gate --release-ready --tag v5.6.0`：**8/8 全绿，release_ready true**，
  `test_numbers_from_report | passed=1689 failed=0 total=1692 source_commit=a66040520139…`。
  第一次出报告时漏了 `AIPD_SOURCE_COMMIT`，PROVENANCE 落成 HEAD（`47781a9`）——
  门禁会判 report STALE，是**读数字**时抓到的，重跑并重新盖章。
- `skill_quality_audit`：rc=0，**0 项警告 0 项失败**；`state_perf_gate`：rc=0，**性能门禁 PASS**。
- `audit_repo --strict`：**rc=1**，唯一一条
  `✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=9c5fb7252035…`
  ——发布锚点在 tag 上而 HEAD 已前进，按设计判红；改绿要移 tag + 重签，属业主侧动作。
- 提交：`24abaa7` 实现 → `47781a9` 文档 → `9c5fb72` 发布件。
  本文档 §八 里最初把实现提交写成 `5af3500`，那是 amend 前的孤儿哈希（对象还在但不从分支可达），
  已改指 `24abaa7`。
- 未做且有意不做：不 push、不移 tag、不重建 bundle、不重签、不放宽任何共享门禁。
  临时目录（含造出来的 BOM 库与 DXF）跑完即删；全程没碰开发者/共享数据库。
