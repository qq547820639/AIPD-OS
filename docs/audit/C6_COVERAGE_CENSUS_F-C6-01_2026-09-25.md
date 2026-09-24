# C6 交付物覆盖度普查（新增诊断量具 `scripts/c6_coverage.py`）

日期：2026-09-25　范围：度量面（不改产品行为）
承接：`CAD_ASSEMBLY_PROCESS_F-DRAW-01_2026-09-25.md`（第 16 片）

## 一、为什么先做这个而不是再补一项

第 14/15/16 三片都在补 C6 的零碎项（分清单件图/装配图、材料列、工艺列），但**从来没有一张表
说明 C6 那 15 项各自到哪一步**。后果是可预见的：会继续在已经交付的图纸项上精雕，
而 ICD、装配/维护、ECR/ECO 这三类连落点都没有。所以这一片的产物是**分母 + 档位**，
不是新功能——它决定后面几片做什么。

## 二、落点选择（两条候选，六维里起作用的几条）

| 候选 | 功能匹配 | 维护/风险 | 适配成本 | 判定 |
| --- | --- | --- | --- | --- |
| A. 扩 `scripts/capability_matrix.py`，加一个 C6 维度 | 错配：它答的是「能力有哪四态」（按 registry 行聚合），普查答的是「契约里 15 项各自做到哪一步」——**两套分母** | 它的 JSON schema 已被 `tests/test_capability_matrix.py` 与 `docs/audit/*` 消费，加维度=改契约 | 中-高 | 否 |
| B. 新写 `scripts/c6_coverage.py`（诊断档）+ 常驻用例 | 分母只有一个：契约那一行现算 | 与仓内既有量具同形（`skill_quality_audit.py`、`state_perf_gate.py`、`audit_repo.py` 都是各自独立的脚本，且**都不在能力表里挂行**） | 低 | **选它** |

从 A 借两点：读能力表走 `aipd_os.registry_data`（不另立第二份真相），CLI 形状照
`capability_matrix.py` 的 `--repo/--json`。**不**借它的产物落盘位置：普查不落
`docs/audit/c6_coverage.json`——读数已经由常驻用例钉住，再存一份就是两处会各自漂的副本。

同理，普查工具本身**不登记进能力表**：仓内先例是「产品面登记、质量量具不登记」
（`skill_quality_audit` / `state_perf_gate` / `audit_repo` 都查不到行）。这是选择，不是遗漏。

## 三、三档判据（都可机器核）

- `producer` 有生产者**且**有常驻用例：映射里至少一个 `src/` 下的实现文件 + 至少一个测试文件，
  且那个测试文件里真数得出 `def test_`。
- `checker_only` 只有校验方：`implementation_file` 只指向门禁脚本或模板。
  「手写一份 JSON 把门过去」就落在这一档——**它不等于交付物存在**。
- `absent` 零实现：既没有实现也没有用例。

档位与所列文件互斥性由脚本自己判（标 absent 却列出文件、标 checker_only 却列出 `src/` 落点
都算自相矛盾）。分母漂移两类也算矛盾：契约多一项没映射、映射留一项契约已不要求。

## 四、今天的读数（15 项 = 10 / 2 / 3）

| 项 | 档 | 落点 / 缺口 |
| --- | --- | --- |
| 参数化源模型 | producer | `cad/backends.py` + `tool_adapters/local_brep_adapter.py`（golden loop 15 条用例） |
| 总装/单件STEP | producer | 单件有 `exportType='STEP'`；**总装 STEP 不导出**（`assembly.py` 只逐件 importStep 再投影） |
| 总装图 | producer | `cad/assembly.py`（逐件投影 + 球标 + 六列明细表） |
| 零件图 | producer | `cad/drawings2d.py`（剖视/局部放大/公差/GD&T 框/标题栏） |
| 爆炸图 | **absent** | 全仓只有「未做」这句话 |
| BOM | producer | `bom/{models,store,cost,projection}.py` |
| ICD | **absent** | 词边界查 `ICD`：src/tests/scripts 全 0 命中 |
| 尺寸链 | producer | `cad/stackup.py`（一维；三维/角度/Cpk 未做） |
| GD&T | producer | `cad/gdt.py`（drawn 几何，非 DXF TOLERANCE 语义实体） |
| 材料与工艺 | producer | 两半各一条判据；**多工序路线未建模** |
| DFM/DFA | **checker_only** | 行里只有模板 + 门禁脚本，产品侧没有分析生产者 |
| 装配/维护 | **absent** | 装配说明与维护指引都没有落点 |
| CTQ与检验 | producer | `release_manifest.py` + `cad/spec_from_truth.py`（独立检验计划文档未做） |
| 验证证据 | producer | `release_manifest.py` + `scripts/release_evidence.py`（三源哈希） |
| 版本与ECR/ECO | **checker_only** | 版本有生产者；**ECR/ECO 变更单零实现**（有 changes/decisions 表，没有工程变更单实体） |

## 五、顺带暴露的三处声明缺口（都不在本片修，登记给后续）

1. **两栏皆空的能力行 5 个**：`research.standards_regulations`、`research.patents_competitors`、
   `cad.assembly_constraints`、`cad.continuous_kinematics`、`cad.cae_fatigue`
   ——`implementation_file` 与 `unit_test` 都空，等于一行不可核验的声明。
   与第 16 片补的「BOM 域整域无行」是同一类账。
2. **144 个产品模块没被任何行的 `implementation_file` 点名**（含 `cad/stackup.py`、`cad/gdt.py`
   这种真生产者——`cad.tolerance_chain`/`cad.gdt` 两行反而只写门禁脚本）。
   这条是**信号不是判决**：没点名≠没被测（多数被同域别的用例顺带跑到），
   但「顺着能力表找不到落点」会让下一个人重复劳动。
3. **门禁的 `gdt_covers_ctq` 等只吃证据文档**，所以 `checker_only` 那两档在门面上是绿的。
   普查存在的意义之一就是把这种「门绿着但产品侧没生产者」区分出来。

## 六、自测注入：7/7 条判据都能红

`--self-test` 注入并逐条要求开火（尺子不会红的绿不算证据）：
分母多一项 / 映射留旧项 / 生产者路径不存在 / 档位与所列文件矛盾 /
能力行 id 不存在 / 用例文件里没有 test / 用例路径不存在。
常驻用例 `test_injections_all_make_the_ruler_fire` 直接跑它，所以量具坏在 CI 里就红。

## 七、这一片自己踩的三个坑（都值得记）

1. **映射键与契约原文差一个空格**（写成「总装/单件 STEP」，契约是「总装/单件STEP」）——
   被自己的 `unmapped` + `stale_mapping` 两条同时抓住，rc=4。这正是分母现算的价值：
   手抄的清单连自己的笔误都发现不了。
2. **变量名复用**：`audit()` 里先用 `caps` 装每一项的能力行名，后面的能力表诊断又写 `for cap in caps`
   —— 拿到的是**一串字符串**，`cap.get` 才 `AttributeError`。函数作用域是平的，
   这种复用不会因为分开写两段而安全；已把表侧变量改成 `registry_rows` / `row_cap` 并留注释。
3. **子串噪声差点变成结论**：`grep -i ECO` 命中 107 个文件、`ECR` 命中 15 个，
   一看全是 `SECONDS` / `SECRET` / `TOKEN_TTL_SECON…`；按词边界重查才是 0。
   所以普查的「零实现」判定一律用精确路径/词边界，并在判读里写下这件事，
   免得下一个人拿旧的 grep 数当证据。

## 八、边界：为什么不进发布门禁

今天就有 3 项 `absent`、2 项 `checker_only`。把普查挂进 `production_release_gate` 的
`--release-ready` 会让门**永久红**，而一个永远红的门等于没有门（本仓为 `audit_repo --strict`
的「已知红」已经付过一次解释成本）。所以它是诊断档，且由
`test_census_is_not_wired_into_the_release_gate` 钉住「门禁源码里不许出现 c6_coverage」。
真要挂主线，得先让零实现项变成有落点，或明确「C6 是否要求装配图必须绑 BOM」那一类的业务口径。

## 九、下一片排序建议（按「零实现 + 可数字化 + 不需属主拍板」排）

1. **爆炸图**：CAD 侧可完全数字化（沿装配轴给每个零件一个位移 + 引线与序号，复用第 12 片的
   逐件投影与球标机制），不依赖新事实来源。
2. **装配/维护说明的生产者**：可从 BOM + 明细表 + 检验计划生成结构化装配步骤文档骨架
   （每步引用球标号），但「维护」需要属主给内容 → 拆两半，先做装配步骤那半。
3. **ICD**：需要接口清单这一事实来源（当前仓里没有接口实体），先问属主要不要建，
   不擅自造。`ECR/ECO` 同（涉及审批流程与「AI 不自批」边界）。
4. `DFM/DFA` 从 `checker_only` 升 `producer` 需要一个真分析生产者，暂缓。

## 十、收口读数（commit 后复算）

- 代码+文档：`6cafe91`（9 files，+627/-82）；产物重锚：`f707f62`。
  被哈希面 594 → **596** 个文件（新增的普查脚本与它的常驻用例）。
- 全量常驻用例（带 `AIPD_SOURCE_COMMIT=a66040520139…`）：**1746 passed / 0 failed / 3 skipped**
  （total 1749 = 上一轮 1739 + 本片 10 条）。
- `production_release_gate --release-ready --tag v5.6.0`：**rc=0、8/8、`release_ready: true`**，
  读数 `passed=1746 failed=0 total=1749 source_commit=a66040520139…`。
- `skill_quality_audit` rc=0（0/0）；`state_perf_gate` **PASS**；
  `audit_repo --strict` rc=1 且只剩「tag 未重打的 provenance 锚点」那一条已知 ✗。
- 普查自身：`--self-test` **7/7 注入开火**；正式跑 **rc=0、15 项 = 10 / 2 / 3**；
  `ruff check src tests` 全过、`mypy src tests` 397 files 无 issue。
