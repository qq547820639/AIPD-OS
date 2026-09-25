# F-DRAW-01 第 20 片：装配级 STEP 的导出（2026-09-25）

对应 C6 的 **`总装/单件STEP`**：分母逐字取自 `references/production-cad-deliverables.md:3`。
这一项此前已经是 `producer`，但普查映射的 note 里**明写着半个缺口**：

> 单件 STEP 有导出点（backends.py exportType='STEP'）；**装配级 STEP 未导出**——
> assembly.py 只按 manifest 逐件 importStep 再投影，不产总装 STEP 文件。

本片把这一半补上，并把那句 note 换成实际状态。**档位不变（仍 13/1/1）**，
所以这片的价值不在数字，而在把「已交付」这句话里的水分挤掉。

---

## 一、要拍板的事与结论

装配图、爆炸视图、装配步骤文档都有了，但**总装的三维模型**一直没人产：
下游 CAM/PLM 拿到的是散落的零件 STEP + 一张图，装配关系只存在于图与 manifest 里。

结论：`export_assembly_step()` 按 manifest 逐件导入 → 用**声明的 offset** 摆放 → 写出带产品层级的
STEP → **立刻重新导入逐件核对**，对不上就删文件并报错。摆放不引入第二套位置事实
（出图、爆炸视图、总装 STEP 共用同一个 `offset`），这与第 17 片「位移一律由作者声明」同一条纪律。

## 二、实现前实测到的四件事（每一件都改变了实现）

1. **`Assembly.save` 在本版本已 deprecated**（`cadquery/assembly.py:455` 的 docstring 与
   `FutureWarning: save will be removed in the next release`）⇒ 直接调
   `cadquery.occ_impl.exporters.assembly.exportAssembly(assy, path, "default")`，
   它内部走 `toCAF` + `TDataStd_Name` + XCAF（`occ_impl/assembly.py:176`、`exporters/assembly.py:41`）。
2. **`Assembly.add()` 没有 `label` 参数**，只有 `name`/`color`/`metadata`（实测 `TypeError`）⇒
   件号↔几何的对应不能指望多一个「标签」字段。
3. **非 ASCII 零件名被写坏**：`name="支架"` 导出后，STEP 里是
   `PRODUCT('æ¯æ','æ¯æ','',(#57)`（UTF-8 字节被按单字节落盘），而 `name="bracket"` 正常出现 4 次。
   ⇒ 结论：**不宣称 STEP 里的名字可读**。证据里 `step_product_names_readable` 恒 `False` 并带原因，
   件号↔几何的对应只由 `.evidence.json` 承载。
4. **XCAF 子标签读不稳**：本机 OCP 上 `XCAFDoc_ShapeTool` 没有 `GetLabelName`（名字要靠自己
   `TDataStd_Name` 取），`GetComponents_s(root)` 对两件的装配只回 1 个标签；我另写的一版
   `TDF_Label.Child()` 递归直接把解释器 **segfault**（exit 139）。
   ⇒ 结论：**判据不建在 XCAF 遍历上**，改成「回读实体的中心 + 体积多重集逐件比对」——
   这是能稳定量到、且下游真正关心的那一层（几何在不在、摆对没摆对）。
   根产品名与 `IsAssembly=True` 探索时**读到过**，但**没放进证据**：判据既然不建在它上面，
   往侧车里塞一个没人核的字段，等于给读者一个看起来像凭据的东西。

另外踩回一颗旧坑：`Workplane.center()` 只收 (x, y)（第 12 片量过），夹具里写 `center(*xyz)` 直接
`TypeError` ⇒ 改 `Workplane.translate(cq.Vector(...))`（实测能把包围盒中心搬到 (5,0,0)）。

## 三、实现落位

- `src/aipd_os/cad/assembly.py`：`_solid_readings` / `read_back_solids` / `_placement_trsf` /
  `_weighted_center` / `export_assembly_step`（配对就写在 `export_assembly_step` 里，
  只有一个调用点，不为此抽一个只被用一次的函数）。
  校验是**逐件贪心配对**（期望的 (中心, 体积) 一条条从回读池里取走）：取不到就是「这一件没进文件」，
  池子里剩下就是「文件里多出清单没声明的件」；两种都判失败、删文件、抛错。
  中心容差 1e-6、体积容差 1e-6（写后校验不是加工验收，不需要放宽）。
- `src/aipd_os/cad/evidence.py`：新增 `write_evidence_sidecar()`——第三份同形的侧车写入才抽出来，
  前两个产物（装配图、步骤文档）**没**改过来（它们各自还盖别的字段，为改而改会动到已测过的路径）。
- `src/aipd_os/cli/commands_drawing.py` + `commands.py` + `main.py` + `command_contract.py` + `SKILL.md`：
  `aipd drawing assembly-step`（public 命令 50→51），`--manifest/--out/--part` 必填，
  内核缺失走外部任务包，声明不合法 rc=2 且**不留文件**。
- `scripts/c6_coverage.py` 的该项 note 换成实际状态；能力行 `cad.local_native_brep` 的
  `implementation_file`/`unit_test`/`e2e_evidence`/`current_limitation` **同批**改掉（散文不留在旧口径上）。

## 四、常驻用例

`tests/test_cad_assembly_step_export.py` 18 条，四组：忠实性（5）、
拒绝假凭据（6，含三条**故障注入**：回读少一个实体 / 体积被换 / 位置偏 0.2mm ⇒ 都要求报错且文件被删）、
证据侧车（4）、CLI 面（3）。
故障注在「回读结果」这一层而不是注 OCCT：要验的是本仓这道写后校验有没有牙，
不是内核会不会掉件。

## 五、变异电池（`/tmp/slice20-mutations.py`，16 条全开火）

| # | 注入的坏判据 | 开火的用例 |
|---|---|---|
| E1 | 写完不做回读校验 | dropped_solid…（并报「已删除」） |
| E2 | 校验只比中心、不比体积 | a_wrong_volume_in_the_written_file_is_caught |
| E3 | 位置容差放宽到 0.5mm | a_half_millimetre_placement_error_is_caught |
| E4 | 校验没过也把文件留在盘上 | dropped_solid… |
| E5 | 读不出实体的零件照收 | empty_solid_step_is_refused |
| E6 | 多实体件只取第一个实体 | multi_solid_part_is_counted_by_volume |
| E7 | 假装零件名在 STEP 里可读 | part_names_are_not_claimed_readable |
| E8 | 两件同位不报了 | two_parts_in_the_same_place_are_reported |
| E9 | `solid_count` 抄成声明件数 | multi_solid… |
| E10 | 文档哈希抄成清单哈希 | sidecar_next_to_the_step_with_both_hashes |
| E11 | 侧车写到别的后缀 | 同上 |
| E12 | 不再声明自己没做什么 | sidecar_says_what_the_assembly_step_does_not_carry |
| E13 | CLI 把拒绝当成成功 | cli_broken_part_step_is_rc2_not_a_hollow_file |
| E14 | 体积容差给到天量 | a_wrong_volume… |
| E15 | 证据里只留一个体积数（读者无从复算） | volumes_survive_the_round_trip_per_part |
| E16 | 校验拿期望值当实测值（循环自证） | dropped_solid… + a_wrong_volume…（红 2 条） |

三处「电池自己」的读数值得记：

1. E3 首轮**存活**——用例把扰动写成 0.5mm 正好压在放宽后的容差边界上（`< 0.5` 对 0.5 仍为假），
   改成 0.2mm 才把 1e-6 与 0.5 两档分开。
2. E2 的锚点第一次凭记忆写、命中 0 次，被「命中必须恰好 1 次」判为**注入无效**而不是通过。
3. E15 是后补的：补完之后重跑，锚点命中 0 次（同一批里我把重复的 `expected_volume_mm3`
   字段删掉了，E15 的锚点里有那一行）——**又是判为无效而不是通过**，改锚点重跑才拿到「杀掉」。
   第 19 片 D9 的教训这片提前消化了：写后校验这道新判据是**先补三条故障注入用例、再跑电池**。

**一条开不了火的注入（记下来，别当没发生）**：最早 E16 写的是「聚合出来的
`max_volume_deviation_mm3` 硬编码成 0」，**存活**。原因是成功路径上偏差本来就是 0，
硬编码 0 和量出来的 0 在证据里长得一模一样，没有任何断言能分开它们。
处置是**把那个聚合值连同 `volume_match` 布尔一起从证据里删掉**，只留每件两个数
（源体积、回读体积），让读者自己减；换上来的是现在这条 E16（循环自证），它开火并红 2 条。

## 六、端到端实测（真几何，不是夹具里的方块）

零件取仓库里自带的金样品：`releases/golden-projects/B-cad-engineering-change/bracket.step`
与 `bracket_v2.step`（带孔支架，两件体积只差一个孔的 9920mm³）。清单两份偏移
`(0,0,0)` / `(0,30,18)`，命令与读数：

```
aipd drawing assembly-step --manifest assy.json --out assy.step \
    --part ASSY-BRKT-01 --revision R20
→ 声明 2 件、回读 2 个实体，逐件位置与体积已核对；rc=0
→ assy.step 145818 字节、assy.evidence.json 2396 字节，cadquery 2.5.2
```

**不经本仓代码的独立核对**（另起进程，`STEPControl_Reader` + `BRepGProp` + `Bnd_Box` 直接量）：

| 实体 | 源件体积 | 总装里回读体积 | 期望 bbox 中心 | 实测 bbox 中心 |
|---|---|---|---|---|
| 支架 | 47833.457334 | 47833.457334 | (0, 0, 0) | (0, 0, 0) |
| 压板 | 57753.457334 | 57753.457334 | (0, 30, 18) | (0, 30, 18) |

⇒ 声明的偏移**真的进了文件**，孔几何（两件体积正好差一个孔的 9920mm³）原样带过去。
STEP 里有 6 条 `PRODUCT(`：总装根 `ASSY-BRKT-01` 两条、每件两条（一条名字、一条 `名字_part`），
产品层级是真写出来了。同一份文本里那四条名字是 `PRODUCT('M-CM-%M-BM-^N...` 这类 mojibake
（`cat -v` 原样），把 §二.3 的「非 ASCII 名字被写坏」在真产物上复核了一遍：
`step_product_names_readable=false` 不是推测，是这份文件的事实。

## 七、这一片没做的事

- 装配约束/配合与子装配层级（manifest 是平表，本仓也不建约束对象）；
- 让非 ASCII 零件名在 STEP 里可读：那是 OCCT 侧的编码问题，本仓的处置是**改判据 + 在证据里明写**，
  不假装解决；真要解决得先定「件号用什么字符集」的规矩（属主的事）；
- XCAF 子标签的结构化读回（本机 API 不稳，见 §二.4）；
- 总装 STEP 的几何质量检查（干涉/间隙仍不做实体求交，与第 17 片同一条边界）。
