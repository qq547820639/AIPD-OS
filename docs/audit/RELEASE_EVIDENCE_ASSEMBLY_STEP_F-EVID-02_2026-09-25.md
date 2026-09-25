# F-EVID-02 第 22 片：总装 STEP 接进发布就绪证据（`aipd release manifest --assembly-step`）

第 20 片有了生产者（能出总装 STEP 并写后回读），第 21 片把接它进门的那道核对修得有牙
（`FILE_KEYS` 对数组不再形同虚设）。这片把最后一截接上：**发布就绪证据里此前没有总装 STEP
这一格**，C6「总装/单件STEP」只停在普查表的 note 上。

契约给的理由逐字取自 `references/production-cad-deliverables.md:4`：
「**STEP 存在、网格闭合或快照好看均不能单独证明生产可用**」。所以这一格不能只写
「有个 .step、哈希对得上」——那是门禁 `step_assemblies` 已经在做、也只做得到的一件事。

## 一、要拍板的事与结论

写死的 `volume_match: True` 在第 20 片被删掉了（成功路径上硬编码与量出来的值不可区分）。
于是这一格只有一条路：**拿侧车里那两个数自己减**。结论三条——

1. 侧车的话一律**重算**：每件 `volume_mm3` 与 `read_back_volume_mm3` 相减、
   每件 `source_solid_count` 相加对 `solid_count`、`declared_part_count` 对 `parts` 行数、
   侧车写的 `document_sha256` 对眼前这份文件的实际哈希。任一条自相矛盾 ⇒ 阻断并点名，
   不替它盖章（它可能手改过、也可能是别的产物的侧车）。
2. 图与模**只在一对一时才配**：一张装配图对一份总装 STEP 才比球标↔件号集合；
   多张记 `ambiguous_pairing` 不判，没图记 `no_assembly_drawing` 当盲区而不是当失败。
   按名字在多图里猜配对，就是 F-REG-01 那条装饰性接线的老路。
3. **没交就不写这一格**：不给 `--assembly-step` ⇒ `step_assemblies` 与 `assembly_model`
   两个键都不出现。写一个空数组会让门把「没做」读成「做了但是空的」。

## 二、键名为什么不新造

`step_assemblies` 早就在门的 `REQ['C1']` 与 `FILE_KEYS` 里，模板也带着它
（`assets/templates/production_cad_manifest.json:8`）。再造一个 `assembly_model_file`
就是同一件事两个名字——本仓最恨的那种。所以：**文件引用进 `step_assemblies`，
事实进 `assembly_model`**，一格一个职责。
事实格不叫 `assembly_step`：`assembly_steps`（复数）这一格已经是**装配步骤文档**的汇总，
两者挨太近会读错。

## 三、实现落位

- `src/aipd_os/release_manifest.py`：`_assembly_drawings()` + `_collect_assembly_step()`，
  形状照 `_collect_steps` / `_collect_dfm`（没交 ⇒ `{}`；文件在而侧车不在 ⇒ 只写引用并阻断；
  侧车读不出计数 ⇒ 点名并阻断，不折成 0 件）。
- 新增判定 `assembly_step_missing` / `assembly_step_evidence_missing` /
  `assembly_step_evidence_incomplete` / `assembly_step_hash_mismatch` /
  `assembly_step_unverified` / `assembly_model_disagrees_with_itself` /
  `assembly_model_count_disagrees` / `assembly_model_solid_count_disagrees` /
  `assembly_model_drawing_disagree`（都阻断），
  `assembly_model.name_readability`、`coincident_placements`、`not_covered` 只带不判。
- `src/aipd_os/cli/main.py` + `commands_release.py`：`--assembly-step` 一个选项，
  不新增命令（public 命令数不变），prose 里多打两格，取不到仍写「（未取到，不编造）」。
- `scripts/c6_coverage.py` 该项 note、能力行 `industrialize.release_evidence` 的
  `unit_test` / `integration_test` / `e2e_evidence` / `current_limitation` 同批改。
- README：把 `--dfm-doc` 那四行注释挪回 `aipd release manifest` 名下（第 19 片落错了位置，
  它当时长在 `python scripts/c6_coverage.py` 的注释块里），再补 `--assembly-step` 一段。

## 四、常驻用例 23 条（`tests/test_release_manifest_assembly_step.py`）

五组：这一格只在被交时长出（4）、事实来自侧车（5）、自相矛盾一律拒（7）、
图模对账（5）、CLI 面（2）。**总装 STEP 与装配图都走真生产者**
（`export_assembly_step` / `generate_assembly_drawing`），不手写夹具几何。
CLI 两条把基线做到**真能就绪**（有图、有 BOM 行、有 CTQ ⇒ `rc=0`），
才谈得上「0 变 4」；这里踩过一次坑：`create_bom` 的第三个参数是**名字**，
`bom_id` 是生成的，拿字面量当 id 传进 `--bom` 会让读的一方找不到那一版 BOM，
报成 `no_bom_lines`，基线永远不 ok，正反向断言就全成了空话。

## 五、变异电池（`/tmp/slice22-mutations.py`，16 条全开火）

| # | 注入的坏判据 | 开火 |
|---|---|---|
| H1 | 不核「侧车说的是不是眼前这份文件」 | a_sidecar_about_a_different_file_is_named |
| H2 | 不核核对方法 | a_different_verification_method_is_not_accepted |
| H3 | 每件体积不重算 | a_part_whose_two_volumes_disagree_is_refused |
| H4 | 回读实体数不核 | a_part_with_no_read_back_solid_is_refused |
| H5 | `solid_count` 不求和对照 | solid_count_not_equal_to_the_sum_of_parts |
| H6 | 声明件数不核行数 | declared_part_count_not_matching_the_rows |
| H7 | 图模配对不判分歧 | a_balloon_only_on_the_drawing_blocks |
| H8 | 多张装配图也硬配 | two_assembly_drawings_are_not_guessed_at |
| H9 | 没图当「比对过且一致」 | no_assembly_drawing_is_a_blind_spot |
| H10 | 只比号不比名 | a_renamed_balloon_blocks |
| H11 | 名字可读性吞成「可读」 | name_readability_is_carried_verbatim |
| H12 | 「没做的事」抹平 | what_it_does_not_carry_is_not_emptied |
| H13 | 没交参数也长出空数组 | no_argument_writes_neither_key |
| H14 | 文件不存在也写引用 | a_missing_file_is_named_and_writes_nothing |
| H15 | 缺侧车不阻断 | a_step_without_a_sidecar_is_a_blocking_blind_spot |
| H16 | 侧车缺计数就折成 0 件 | a_sidecar_without_counts_is_named_not_folded_to_zero |

H12 第一次跑是**注入无效**（锚点在文件里命中 3 次——`"not_covered": list(...)` 这句
步骤文档、DFM、总装三处都有）。这正是第 19 片 D9、第 20 片 E2 同一颗坑的第三次：
锚点必须落在判据读的那一段，撞车的通用句式要加上下文。补上 `"drawing_check"` 前一行后
16/16 全开火。

## 六、端到端实测（真 CLI、真金样品）

零件仍取仓内金样品 `bracket.step` / `bracket_v2.step`，一份清单两个产物：
`drawing assembly-step` 出 `assy-model.step`（rc=0），`drawing assembly` 出 `assy.dxf`（rc=0），
再 `release manifest` 两次（一次不给 `--assembly-step` 作对照）：

```
step_assemblies = [{'path': 'assy-model.step',
                    'sha256': '6c880fd91710d649…', 'kind': 'assembly'}]
assembly_model.verification        = read_back_matched_multiset
              .declared_part_count = 2      .solid_count = 2
              .parts = [(1, bracket, (0,0,0),  47833.457334 → 47833.457334),
                        (2, plate,   (0,30,18), 57753.457334 → 57753.457334)]
              .drawing_check       = {'status': 'compared', 'drawing': 'assy.dxf',
                                      'agree': True, 'balloons': [1, 2]}
              .name_readability    = readable=True（这次零件名是 ASCII，与第 20 片那趟相反）
对照那次（不给 --assembly-step）：两个键都不出现。
```

两趟对照值得单独记：**同一条 `name_readability` 在 ASCII 命名下真为 `true`**，
说明第 20 片那条「不宣称可读」不是永远为假的一行字，而是跟着文件走的事实。

**这一趟还顺带撞出一个缺陷**（不是本片要修的东西，另立一条）：
第一次跑时产物叫 `assy.step` 与 `assy.dxf`，两者的证据文件都拼成 `assy.evidence.json`
⇒ 出图把总装 STEP 的侧车顶掉了，`release manifest` 于是报
`assembly_step_evidence_incomplete`。详见
`docs/audit/EVIDENCE_SIDECAR_PATH_COLLISION_F-EVID-03_2026-09-25.md`。
本片改成不同干名（`assy-model.step` / `assy.dxf`）后按预期通过——**绕开不是修掉**，
所以那条单独立项。

## 七、这一片没做的事

- 没把 `step_assemblies` / `assembly_model` 提进 `REQ['C6']`：一提就成了「每个 C6 包都必须
  有一份总装 STEP」，单件产品没这一层，那是假前提；要阻断得先有「本产品是装配体」这一事实，
  本仓还没有它（装配清单是产物侧的声明，不是产品侧的分类）。
- 多张装配图 / 多份子装配 STEP 的配对：只记 `ambiguous_pairing`，不自动配对也不报错。
- 单件 STEP 的逐件哈希进证据：`parts[].source_step_sha256` 在侧车里已有，
  这一格没往发布文档抬（抬过去就得为它建一条「单件文件是否还在」的判据，那是另一片）。
- 没做 STEP 与 BOM 的行数对账：`bom_line_count` 与 `model_part_count` 那条既有判定
  吃的是 `--model` 的实体数，换成总装的**声明件数**是口径变更，得先定
  「一行 BOM 对一件零件还是一个实体」，本仓不猜。
- 侧车路径同干名相顶（§六 末）**没修**，另立 F-EVID-03。

## 八、收尾读数（落盘后由量具复算，不是计划）

提交：`be67189`（代码 + 文档）→ 本文件所在那次文档提交 → 发布工件重锚在其间。

| 量具 | 读数 |
|---|---|
| 全量 pytest（`docs/audit/pytest-report-v5.6.0.json`） | **1890 passed / 0 failed / 3 skipped**（共 1893；上一片收尾 1867/0/3=1870，本片 +23 条用例） |
| `PROVENANCE.json` | `test_report.{passed:1890, failed:0, total:1893, source_commit:a66040520139…}` |
| `SOURCE_MANIFEST.json` | 被哈希面 **603 → 604**（与上一轮逐项求差，新增就是 `tests/test_release_manifest_assembly_step.py`） |
| `production_release_gate --release-ready --tag v5.6.0` | rc=0，`release_ready: true`，8 项检查、未通过列表为空 |
| `ruff check src tests state_service` | rc=0（与 CI 同口径，`scripts/` 不在本仓 lint 面内） |
| `mypy` | rc=0，405 files no issues |
| `scripts/c6_coverage.py --self-test` | 7/7；档位仍 **13 / 1 / 1**（这一格是「已 producer 的那项接进证据」，不升档） |
| 变异电池 `/tmp/slice22-mutations.py` | 16 条：杀掉 16 / 存活 0 / 注入无效 0 |
| `audit_repo.py --strict` | rc=1，1 个 ✗（Provenance 锚点与 HEAD 之差，真发版前按设计为红） |

## 九、下一片候选（供排序，不代表已决定）

1. **F-EVID-03 侧车同干名相顶**（本片端到端撞出来的，已立案带修法选项）：
   先做「写入方拒绝顶掉别人的 `document`」那条止血，再数消费方决定要不要改成带后缀的侧书名；
2. `assembly_model` 与 BOM 的行数对账（要先定「一行 BOM 对一件零件还是一个实体」）；
3. **ICD**：普查里唯一仍 `absent` 的一项，卡在「接口清单的事实来源」要属主给；
4. **版本与ECR/ECO**：唯一仍 `checker_only` 的一项，变更单是流程与审批事实；
5. DFM 侧两件可继续做深的：沿面法向射线与插入方向计数（数据源已是 manifest 的 `explode`）。
