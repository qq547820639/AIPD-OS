# F-DRAW-01 第 6 片：GD&T 框与基准方案从 CTQ 长出，门禁按「画上去的框」计覆盖

日期：2026-09-24　范围：`src/aipd_os/cad/spec_from_truth.py`（三种声明 + 合并 + 同类冲突）、
`src/aipd_os/cad/gdt.py`（框带 `ctq_ref`）、`src/aipd_os/release_manifest.py`
（`covered_by` 两种凭据 + 去重）、`src/aipd_os/cli/commands_drawing.py`（声明打印 + gdt-only 崩溃修复）、
能力行 `cad.2d_drawings` 与 `industrialize.release_evidence` 行内改写、
`tests/test_cad_spec_from_truth.py` 增 13 条（该文件累计 31 条）。

一句话结论：图纸上的**形位公差框与基准表**不再靠人手写 JSON；门禁 `gdt_covers_ctq`
从此有两种覆盖凭据（尺寸公差 / 特征控制框），并且**同一条需求只计一次**——
最后这条是注入变异才暴露出来的判据空洞，本轮补上了。

## 一、本片做什么、以及为什么跳过外部选型

第 5 片把**尺寸公差**声明接到 Product Truth，但 `gdt` 与 `datums` 两块仍只吃手写 JSON
（能力行当时就写着「GD&T 框与叠加声明仍只吃手写 JSON」）。本片把剩下的这一块接上。

跳过重新检索的理由（按例外条款显式说明）：本片不引入新的外部能力，
几何符号表与「drawn 几何 vs DXF 语义实体」的取舍在第 3 片已经检索并定案
（`docs/audit/CAD_GDT_FRAMES_F-DRAW-01_2026-09-24.md` 记了当时的检索与 404/fetch failed），
声明的形状与契约在第 5 片定案（`spec_from_truth` 与 `--spec` 同形）。
本片改的是**同一份内部契约的表达力**，不是选一个新的库或标准，故不重复六维对比。

## 二、口径

1. **一条记录可以声明三件事**：尺寸合格域（`nominal` + 上下限）、形位公差
   （`metadata.gdt` 列表）、基准字母（`metadata.datum_id`）。三者可以组合出现在同一条记录上；
2. **同特征不同类别不是冲突**：「一条给孔径、一条给同孔位置度」是正常工程实践，
   两片声明合并进同一个 `spec.features[]` 条目，各带各的出处
   （尺寸出处写在条目的 `ctq_ref`，形位出处写在**每个 gdt 条目**里，这样框才答得清自己答的是谁）；
3. **同类重复才是冲突**：两条 CTQ 抢同一尺寸 ⇒ `ctq_duplicate_drawing_feature`；
   两个字母抢同一基准 ⇒ `datum_id_conflict`；同特征上重复同一几何特征 ⇒
   `gdt_characteristic_conflict`。三种一律**两条都撤回**，不留「按遍历顺序挑赢家」；
4. **什么都不声明要点名**：既无上下限、又无 `gdt`、也无 `datum_id` ⇒ `ctq_declares_nothing`，
   不静默产出一张空声明；
5. **覆盖凭据分两种且去重**：`covered_by = "dimension"`（该 CTQ 的尺寸公差真标在图上且数值一致）
   或 `"feature_control_frame"`（该 CTQ 的形位框真画上去且挂在实测特征上）。
   同一条需求两样都命中时只计一条，`dimension` 优先；
6. **形位那一半不越权宣称**：只核「框在图上 + 挂实测特征」，**不**核形位偏差数值——
   本仓还没有形位偏差测量，写出来就是假能力。

## 三、真机端到端读数（临时目录 + 演示库，输出原文）

种子 3 条 CTQ：`T-001` 基准 A（`datum_id: "A"` → `TOP.overall_width`）、
`T-002` 孔位置度（`gdt: [{position, 0.05, diametral, datums:[A]}]` → `TOP.hole_1`）、
`T-003` 孔径（`nominal 8.0 / 7.95–8.05` → `TOP.hole_1`，与 T-002 同特征不同类别）。

```
$ aipd drawing spec --db state.db --project gdt-demo --out spec.json
CTQ 记录 3 条 → 尺寸/形位声明 1 条 + 基准 1 个（default/gdt-demo，只取 status=active）
  基准 A → TOP.overall_width（CTQ T-001）
  TOP.hole_1: +0.05/-0.05（合格域 7.95–8.05）；形位 position 带 0.05 ← CTQ T-002、T-003
已写 /tmp/s6-*/spec.json：可直接 aipd drawing generate --spec /tmp/s6-*/spec.json
spec rc=0
```

出图（`--views TOP --spec spec.json`，`rc=0`）关键行：

```
公差：声明 1 项、落到图上 1 处（无声明则不写任何公差）
  GD&T 框 TOP→TOP.hole_1：⌖|⌀0.05|A（挂点 [-30.0, -0.0]，来自实测）
```

`release manifest` 产出的覆盖记录（`covered_by` 现形）：

```
gdt = [
  {"feature": "孔直径",   "drawing_feature": "TOP.hole_1", "ctq_record_id": "T-003",
   "covered_by": "dimension",              "tolerance": {"upper": 0.05, "lower": -0.05},
   "nominal": 8.0},
  {"feature": "孔位置度", "drawing_feature": "TOP.hole_1", "ctq_record_id": "T-002",
   "covered_by": "feature_control_frame",  "frame": "⌖|⌀0.05|A"}
]
```

对照的一极（把基准写成**不带任何合格域**的纯 CTQ）：`production_release_gate --target C5`
实跑 `rc=2`，读数原文

```
gdt_covers_ctq -> False | ctq features not covered by gdt: ['基准A面']
ctq_has_inspection -> False | ctq items lacking inspection: ['基准A面']
```

本片**判定这是正确行为**并写进口径：基准角色不是待检特性，门禁不该为它开绿灯；
要同时表达「它是基准」与「它自己有公差」，就把 `datum_id` 写在带合格域的那条记录上
（用例 `test_one_record_can_be_a_datum_and_a_size_requirement` 钉住组合路径）。

## 四、落点

| 位置 | 做了什么 |
| --- | --- |
| `src/aipd_os/cad/spec_from_truth.py:71` | `_entry(target)`：同一图纸特征只有一条声明（合并点） |
| `src/aipd_os/cad/spec_from_truth.py:77` | `_drop_if_empty`：撤回后不留空壳条目 |
| `src/aipd_os/cad/spec_from_truth.py:101` | `ctq_declares_nothing`：三样都没声明要点名 |
| `src/aipd_os/cad/spec_from_truth.py:110` | `datum_id_conflict`：字母撞车时两条都撤回 |
| `src/aipd_os/cad/spec_from_truth.py:124` | `gdt_characteristic_conflict`：同特征重复同一几何特征 |
| `src/aipd_os/cad/spec_from_truth.py:135` | 形位声明写入时带条目级 `ctq_ref` |
| `src/aipd_os/cad/spec_from_truth.py:157` | `ctq_duplicate_drawing_feature`：尺寸撞车时撤回双方 |
| `src/aipd_os/cad/gdt.py:175` | 框带 `ctq_ref`（条目级优先，退回声明级，手写声明留空不硬凑） |
| `src/aipd_os/release_manifest.py:148` | 尺寸覆盖记 `covered_by="dimension"` |
| `src/aipd_os/release_manifest.py:154` | 遍历图上真画出来的框作为第二种覆盖凭据 |
| `src/aipd_os/release_manifest.py:172` | 框覆盖记 `covered_by="feature_control_frame"` + `frame` 原文 |
| `src/aipd_os/cli/commands_drawing.py` | `drawing spec` 打印基准表 + 合并声明 + 多出处（并修掉只有形位时 `KeyError: 'tolerance'` 的崩溃） |

## 五、用例与变异（7 条变异，1 条先幸存后补杀）

`tests/test_cad_spec_from_truth.py` 新增 13 条，分 3 类：
`TestGdtAndDatumsFromCtq`（9）、`TestDatumAndSizeOnOneRecord`（2）、
`TestOneRequirementCountsOnce`（1，注入反证补出来的）。

| 变异 | 结果 | 杀于 |
| --- | --- | --- |
| P1 基准字母冲突时保留先来的 | 杀 | `test_two_records_claiming_one_datum_letter_produce_neither` |
| P2 只声明形位的记录被判「什么都没声明」 | 杀（8 条） | `test_a_gdt_only_ctq_declares_a_frame_without_inventing_a_size` 等 |
| P3 形位条目不带引用 | 杀（5 条） | `test_the_drawn_frame_records_which_ctq_it_answers` 等 |
| P4 同特征重复尺寸时后来的覆盖先来的 | 杀 | `test_two_ctqs_claiming_one_dimension_produce_neither` |
| P5 门禁不再认形位框为覆盖 | 杀 | `test_a_gdt_only_ctq_is_covered_by_the_frame_for_the_gate` |
| **P6 同一条需求被尺寸与框各计一次** | **首轮幸存 ⇒ 补用例后杀** | `test_a_record_covered_by_both_a_dimension_and_a_frame_counts_once` |
| P7 框的引用只认声明级、不认条目级 | 杀（3 条） | `test_a_pure_datum_ctq_is_covered_once_its_datum_role_is_used_by_a_frame` 等 |

P6 是本片最有价值的一条：**现有全部常驻用例在注入「覆盖计数虚高」后仍然全绿**。
覆盖类门禁最常见的失效方式就是把同一件事数两遍，而这恰好是没人写断言的地方。
补了去重断言（并规定 `dimension` 优先）之后，同一注入立刻被杀。
三个源文件还原后与原件逐字节相同。

## 六、边界

- **形位偏差没有实测值**：框的覆盖凭据只到「画上去了 + 挂在实测特征上」。
  真正的形位偏差测量（平面度、位置度实测）本仓没有，因此这条判据**不**声称验证了形位达成；
- **纯基准 CTQ 会被判未覆盖**（见第三节），这是判定而不是缺陷，但如果需求侧希望基准也进
  覆盖率口径，需要先在 Product Truth 里给「基准」一个独立记录类型
  （`TRUTH_TYPES` 是闭集，本片**没有**为了演示方便去改这个共享枚举）；
- 尺寸链各段与 `global_tolerance` 仍只吃手写声明——CTQ 一般不给分段要求，
  生产者也不从封闭环反推全局公差（第 5 片口径保留）；
- 基准字母之间的**层级关系**（第一/第二基准顺序对框的影响）按声明原样透传，不做推导；
- 图纸侧仍未做：剖切符号 A-A/阶梯剖、局部放大、爆炸图、装配图；
  发布锚点与版本号双轨制仍属属主的真实发布动作。

## 七、复算

```bash
cd AIPD-OS
.venv/bin/python -m pytest tests/test_cad_spec_from_truth.py tests/test_release_manifest.py \
  tests/test_cad_gdt_frames.py -q
.venv/bin/python -m ruff check src tests state_service
.venv/bin/python -m mypy src tests
# 真机三命令序列（种子库 → drawing spec → drawing generate → release manifest → gate）
# 见本文第三节；跑门禁须带 PATH="$PWD/.venv/bin:$PATH"
```

## 八、收尾读数（全部来自本轮实跑输出，非记忆）

- 提交：实现 `9032280`（CAD: grow GD&T frames and the datum scheme from CTQ, credit frames
  as coverage）、产物重锚 `2606191`（Release artifacts: re-anchor manifests after the
  GD&T-from-truth slice），本节所在提交是本轮第三个；
- `regenerate_release_manifest.py --version 5.6.0` → **586 个文件**（与上一轮持平：本片只改
  已跟踪文件，没有新增被跟踪文件；新增的审计文档在 `docs/audit/` 下，两份清单整体排除该前缀）；
- `release_evidence.py --bundle releases/aipd-os-5.6.0.zip --version 5.6.0
  --test-report docs/audit/pytest-report-v5.6.0.json
  --source-commit a66040520139405095648461f7144d4f00629924` → 重写
  `SOURCE_MANIFEST / BUNDLE_MANIFEST / PROVENANCE`；bundle 未重建、未重签、tag 未动；
- 重锚前全量：**1569 passed / 2 failed / 3 skipped**，两条失败只仍是
  `tests/test_packaging.py::test_release_manifest_hashes_match_disk` 与
  `::test_source_manifest_hashes_match_disk`（改了 `src/` 后的预期红，收尾时重算）；
- 重锚后全量：**1571 passed / 0 failed / 3 skipped**（119.09s），报告落
  `docs/audit/pytest-report.json`；
- `production_release_gate --release-ready --tag v5.6.0`：**rc=0，release_ready true，
  8/8 全绿**（`workspace_clean: clean`、`commit_matches_head`、两份清单 `zero diff`、
  `test_numbers_from_report` 读数 `passed=1096 failed=0 total=1099 source_commit=a660405…`、
  `Ed25519 signature verified`、无密钥、CVE 无未承认项）；
- `skill_quality_audit`：**0 项警告 0 项失败**；`state_perf_gate`：**PASS**（空闲单跑）。
- 本轮自伤一处并当场清掉：把门禁的 `--json-out` 写到了仓库根（`.gate6.json`），
  会让下一条 `workspace_clean` 判红——读数取完立即 `rm` 并复核 `git status --short` 为空。
  教训与既有偏好同源：**产物落点必须在仓库外**（`/tmp/...`），别让判据去收拾脚本的临时文件。
- 未做且有意不做：不 `git push`、不动 tag、不重建 bundle、不重签、不放宽任何共享门禁；
  `audit_repo --strict` 仍按设计判红（锚点在 tag 而非 HEAD），留给属主的真实发布闭合。
