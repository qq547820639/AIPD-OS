# F-DRAW-01 第 5 片：公差声明的生产者——CTQ → 图纸 spec，并用实测值反查合格域

日期：2026-09-24　范围：新增 `src/aipd_os/cad/spec_from_truth.py`、
`src/aipd_os/cli/commands_drawing.py` 的 `cmd_drawing_spec` 与合格域未收口判定、
`src/aipd_os/cad/drawings2d.py`（`limits` 契约 + `spec_limit_issues`）、
`src/aipd_os/release_manifest.py`（每条 gdt 回写 `ctq_record_id`）、
CLI 面（`aipd drawing spec`）、能力行 `cad.2d_drawings` 与 `industrialize.release_evidence` 行内改写、
新增常驻用例 `tests/test_cad_spec_from_truth.py`（18 条）。

一句话结论：图纸的公差声明从「人手写一份 JSON、再手抄 `ctq_ref`」变成
**产品从需求侧（Product Truth 的 CTQ）自己长出来**；并且补上一条**不由 CTQ 自证**的判据——
投影实测值落在 CTQ 的绝对合格域内吗。这一片在真机跑通时**当场抓到一个真实不一致**
（黄金件孔实测 Ø8，我给的 CTQ 写的是 5.95–6.05 ⇒ 判未收口），不是纸面能力。

## 一、为什么要做这一片（缺口是量出来的，不是猜的）

第 1 片的 docstring 与能力行都写着：声明入口「只吃 JSON 文件（`--spec`），
未与 Product Truth 打通：CTQ 溯源靠人工写 `ctq_ref`、无自动映射」。
把这句话展开成一个可判定的问题：门禁 `gdt_covers_ctq` 的两条输入
（「图上画了公差」与「spec 里 `ctq_ref` 指向某条 CTQ」）**都出自同一个人手写的同一个文件**，
所以它实际考的是「人抄得对不对」，而不是「产品有没有把要求传到图纸」。
第 4 片之后图纸侧已经能画、能量、能判叠加与剖视，缺的正是这一头接线。

## 二、选型与检索（诚实记录取到了什么、没取到什么）

| 候选 | 结论 |
| --- | --- |
| **A 借 QIF（ISO 23952）的 characteristic 数据形状**：标称值 + 上下限 + 显式几何关联 | 形状完全对口，但检索只命中 [qifstandards.org](https://qifstandards.org/) 与博客级材料（[BS ISO 23952:2020 条目页](https://www.antpedia.com/standard/1023128328-7.html) 等），**未找到可 pip 安装的 Python SDK，官方 SDK 源码本轮未读** ⇒ 只借形状（必须有显式 linkage、必须有标称值），不引实现、不宣称符合标准 |
| **B 走 STEP AP242 PMI 语义关联** | 检索命中的是厂商帮助页（PTC Creo、Autodesk Fusion），且 Autodesk 那页 **WebFetch 取回的是 JS 引导壳、正文未获得**；本轮不作依据。长期正确，但要把产出物从 DXF 换成 STEP，且本环境无法核验渲染 ⇒ 不在本片 |
| **C（选定）本仓原生桥**：CTQ `TruthRecord` → `--spec` 已接受的那份 dict 形状，新增 `aipd drawing spec` | 精确对上现存契约（`resolve_spec_tolerances` 只读 `features[].{feature,tolerance,ctq_ref}`），零新依赖，复用既有 Product Truth 读路径与退出码语义，适配成本最低 |

补充：**未检索到**「纯 Python、把 PLM 侧特性直接转成 2D 图纸公差声明」的成熟轮子；
实现为本仓自写，形状借 A，接口沿用本仓既有 spec。

## 三、口径（六条，全部写成用例）

1. **只认显式关联**：CTQ 必须写 `metadata.drawing_feature`（形如 `TOP.hole_1`）。
   **不按名字、不按直径相近去猜**——特征名叫 `hole_Ø6` 而图上有四个孔的场合，猜就是标错尺寸
   （用例 `test_no_drawing_feature_is_a_gap_not_a_name_match` 同时断言 spec 文本里
   不得出现任何 `TOP.hole` 猜测结果）；
2. **必须有标称值才换算**：缺 `nominal` 时不拿「图纸实测值」当标称（那是让被检对象给自己定基准），
   也不折算成 0 偏差 ⇒ 点名 `ctq_missing_limit_value`；
3. **脏值不当数用**：`"6.0"` 这种字符串一律按「没给」处理（`_num` 拒 `bool` 与非数值类型），
   不顺手 `float()` 一个可能是别名的值；
4. **不自相矛盾**：同一图纸特征被两条 CTQ 认领 ⇒ **两条都不产出**并点名
   （保留先来的那条＝按遍历顺序挑一个赢家，同样是猜）；上下限颠倒只点名不调头；
5. **绝对合格域随行、且由几何侧反查**：spec 条目带 `limits{min,max,nominal}`，出图时拿
   **投影实测值**比它 ⇒ 不一致判 `ctq_window_violation`、进 `spec_limit_issues`、
   命令未收口（退出码 4）。边界值算落在域内（`CTQ_WINDOW_TOL = 1e-6`）；
   手写 spec 不带 `limits` 时**不新增任何判定**，旧路径行为逐字不变；
   也**绝不**从总宽的 CTQ 反推 `global_tolerance`——那会把一条要求贴满每一条未声明的尺寸；
6. **半成品不落盘**：`drawing spec` 只要还有 gap 就**不写文件**并返回 4。
   一份「看着能用、其实漏标」的声明比没有声明更危险，因为下游只看有没有 `--spec`。

## 四、真机端到端读数（临时目录，黄金件，一条都不是从记忆里抄的）

种子库 3 条 CTQ：`T-001` 孔（写了 linkage、nominal 6.0、域 5.95–6.05）、
`T-002` 板长（100.0 / 99.9–100.1）、`T-003` 装配面（**故意不写 linkage**）。

```
$ aipd drawing spec --db state.db --project demo-bracket --out spec.json
CTQ 记录 3 条 → 声明 2 条（default/demo-bracket，只取 status=active）
  TOP.hole_1: +0.05/-0.05（合格域 5.95–6.05）← CTQ T-001
  TOP.overall_width: +0.1/-0.1（合格域 99.9–100.1）← CTQ T-002
  未收口：ctq_missing_drawing_feature — CTQ 装配面 没写 metadata.drawing_feature，…
未写 /tmp/chain-*/spec.json：1 条 CTQ 还挂不上图纸，补齐后重跑。
rc=4
```

补上 `T-003` 的 linkage（`TOP.overall_height`，50.0 / 49.9–50.1）后：

```
$ aipd drawing spec … --out spec.json          → 声明 3 条，rc=0
$ aipd drawing generate --part GOLD-BRACKET --views FRONT,TOP --spec spec.json
公差：声明 3 项、落到图上 3 处（无声明则不写任何公差）
  合格域未收口：TOP.hole_1 实测 8 不在 CTQ 的 5.95–6.05 内（CTQ T-001）
rc=4
```

⇒ **这一条就是本片要抓的真实缺陷**：黄金件的孔是 Ø8，需求侧写的 CTQ 是 Ø6 的域。
把 `T-001` 改成 8.0 / 7.95–8.05 之后同一命令 `rc=0`，证据里
`spec_limit_issues: []`、`tolerance_applied: 3`、三条尺寸的 `ctq_ref` 分别是
`T-001/T-002/T-003`（`TOP.hole_1 value 8.0 tol {'upper': 0.05, 'lower': -0.05}`）。
同一次运行里「公差叠加 TOP：不可判定（insufficient_data）」仍照常报出——
尺寸链各段没声明就是没声明，本片不拿 CTQ 去补链上的洞。

链级验收（用例 `test_the_whole_chain_needs_no_hand_written_spec_to_pass_the_gate`）：
DB 播种 → `drawing spec` → `generate_drawing` → `build_release_manifest` →
**真跑** `production_release_gate.py --target C5`，`gdt_covers_ctq` 判绿，
且证据里每条 gdt 带 `ctq_record_id`（只说「匹配上了」不可审计）。

## 五、落点（行号由脚本现算后复读确认）

| 位置 | 做了什么 |
| --- | --- |
| `src/aipd_os/cad/spec_from_truth.py:37` | `ctq_gap`：结构化缺口（kind / record_id / detail / blocking） |
| `src/aipd_os/cad/spec_from_truth.py:42` | `_num`：只认真数，`bool` 与字符串按「没给」处理 |
| `src/aipd_os/cad/spec_from_truth.py:49` | `spec_from_ctq`：CTQ → 与手写 `--spec` 同形状的声明 + 缺口清单 |
| `src/aipd_os/cad/spec_from_truth.py:76` | 重复认领时**连先来的也撤回**（不留「按顺序挑赢家」） |
| `src/aipd_os/cad/spec_from_truth.py:105` | 条目带绝对合格域 `limits{min,max,nominal}` |
| `src/aipd_os/cad/drawings2d.py:99` | `CTQ_WINDOW_TOL = 1e-6`：边界与离散化噪声容差 |
| `src/aipd_os/cad/drawings2d.py:695` | `_declared_limits`：spec 的可选绝对域校验（缺 min/max 即报错，不推断） |
| `src/aipd_os/cad/drawings2d.py:764` | 实测值落在域外 ⇒ `ctq_window_violation`（带 measured/min/max/ctq_ref） |
| `src/aipd_os/cad/drawings2d.py:773` | 证据新字段 `spec_limit_issues` |
| `src/aipd_os/cli/commands_drawing.py:68` | `cmd_drawing_spec`：只取 `status="active"`，有缺口不写盘并返回 4 |
| `src/aipd_os/cli/commands_drawing.py:215` | 打印「合格域未收口：… 实测 … 不在 …」 |
| `src/aipd_os/cli/commands_drawing.py:223` | `limit_issues` 进入未收口集合 ⇒ 退出码 4 |
| `src/aipd_os/cli/main.py:247` | `aipd drawing spec --db --tenant --project --out --json` |
| `src/aipd_os/release_manifest.py:148` | 每条 gdt 回写 `ctq_record_id` |
| `src/aipd_os/registry_data.py` | `cad.2d_drawings`：`unit_test` 补本片用例、`input_output` 与限制改写（声明已有生产者，GD&T/叠加仍手写）；`industrialize.release_evidence`：`ctq_ref` 不再全靠人工、判责分面 |

一处踩坑（值得留在案上）：给 `cad.2d_drawings` 的 `implementation_file` / `entry_point`
改成「; 」分隔的多值后，`tests/test_cad_drawings2d.py::TestCapabilityDeclaration` 立刻判红——
该守卫要求这两个字段是**单一可解析目标**（`rpartition(".")` + `importlib` + `is_file()`），
多值登记等于把探针解析不了的写法当基线（正是 F-REG-01 当年钉过的错）。已回退单值；
多文件面由 `unit_test` 与命令契约表覆盖。

## 六、用例与变异（8 条变异全部被杀）

`tests/test_cad_spec_from_truth.py` 18 条，分三类：
`TestSpecGrowsFromCtq`（9）、`TestMeasuredGeometryAgainstTheCtqWindow`（4）、
`TestCliProducerAndGate`（5）。

| 变异 | 结果 | 杀于 |
| --- | --- | --- |
| N1 缺 linkage 时按 `feature` 名字猜映射 | 2 失败 | `test_no_drawing_feature_is_a_gap_not_a_name_match`、`test_a_gap_holds_the_command_and_writes_nothing` |
| N2 缺标称值按 0 折算 | 2 失败 | `test_missing_nominal_is_not_filled_with_the_measured_value` |
| N3 脏值一律 `float()` 硬转 | 1 失败 | `test_string_limits_count_as_missing_not_coerced` |
| N4 重复认领保留先来的 | 1 失败 | `test_two_ctqs_claiming_one_dimension_produce_neither` |
| N5 上下限颠倒自动调头 | 1 失败 | `test_inverted_limits_are_named_not_swapped` |
| N6 出图时不做合格域反查 | 2 失败 | `test_measured_outside_the_ctq_window_is_a_violation`、`test_a_window_violation_holds_the_drawing_command` |
| N7 有缺口也照样写盘 | 1 失败 | `test_a_gap_holds_the_command_and_writes_nothing` |
| N8 不区分 `status`（作废 CTQ 也声明） | 1 失败 | `test_inactive_records_are_not_declared` |

三个源文件还原后与原件**逐字节相同**。另：命令面守卫
`tests/test_skill_command_surface.py`（总数 + 逐条点名 + 注入反证）在新命令加入后仍绿，
说明 SKILL 的「主线共 45 个」与契约表同源。

## 七、边界（还没做，别当已交付）

- **只自动长尺寸公差声明**：GD&T 框（`gdt`）与一维叠加用的声明**仍是手写 JSON**，
  CTQ 侧没有形位公差的权威字段；
- **linkage 由需求侧显式写**：本片做的是「把 `metadata.drawing_feature` 翻译成 `ctq_ref`」，
  不是「自动找出该挂哪条尺寸」——自动映射仍是要么靠名字（不诚实）、要么靠几何匹配
  （需要特征识别）的独立问题；
- `ctq_window_violation` 只对**有实测值的尺寸类声明**开火（总体宽/高、孔径）；
  形位特征没有独立实测值可比（图纸侧只画框不测形位偏差），所以那条判据今天**不覆盖 GD&T**；
- 合格域比较是**单尺寸独立比较**，不做装配级（多尺寸联合）判定；
- CTQ 记录里的 `inspection_method` 由 `release_manifest` 侧核（`ctq_has_inspection`），
  本片不重复判；
- 图纸侧仍未做：剖切符号 A-A/阶梯剖、局部放大、爆炸图、装配图；
  `audit_repo --strict` 的发布锚点、版本号双轨制仍属属主的真实发布动作。

## 八、复算

```bash
cd AIPD-OS
.venv/bin/python -m pytest tests/test_cad_spec_from_truth.py tests/test_release_manifest.py -q
.venv/bin/python -m ruff check src tests state_service
.venv/bin/python -m mypy src tests
TMP=$(mktemp -d)   # 种子库 + 三条 CTQ + 出图，见本文第四节的原文
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/production_release_gate.py \
  --release-ready --tag v5.6.0 --json-out /tmp/gate.json
```

## 九、收尾读数

（本节在全量与门禁跑完后按**实际输出**填写，不用记忆值。）
