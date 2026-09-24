# AIPD-OS 能力矩阵（v5.6 Registry 驱动）

- 生成时间：`2026-09-25T03:34:44`
- 仓库：`/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS`
- 默认分支：`main`；HEAD：`46515d7f0abfe40959687609d3250fa08d5f453c`
- 版本：`5.6.0`
- 能力总数：`80`
- 分类由 Capability Registry + 运行时证据推导，非静态表。

## 分类统计

| 分类 | 数量 | 说明 |
| --- | --- | --- |
| `fully_implemented` | 35 | 完整实现（有真实运行工件与测试证据） |
| `partially_implemented` | 32 | 部分实现（核心路径可用，边界/证据不全） |
| `protocol_only` | 0 | 仅协议/接口（无真实执行） |
| `template_only` | 0 | 仅模板/示例（无真实执行） |
| `external_dependency` | 13 | 依赖外部服务/工具（未配置时诚实等待，不伪造） |
| `not_implemented` | 0 | 未实现 |
| `not_verifiable` | 0 | 无法验证（缺证据/缺环境） |

## 主管执行

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 一句话创建项目 | `partially_implemented` | README.md / SKILL.md | src/aipd_os/cli/commands.py; scripts/aipd_supervisor.py | aipd_os.cli.commands:cmd_intake | `aipd intake --prompt "<一句话需求>"` | tests/test_cli.py::cmd_intake | 拆分规模受默认工作包模板约束 |
| 自动拆分工作包 | `fully_implemented` | references/work-queue-and-routing.md | scripts/aipd_supervisor.py | aipd_supervisor.Supervisor.run_supervisor | `aipd run --project <id>` | tests/test_supervisor_execution.py |  |
| 依赖排序 | `fully_implemented` | references/work-queue-and-routing.md | scripts/aipd_supervisor.py | aipd_supervisor.Supervisor.next_work | `aipd run --project <id>` | tests/test_supervisor_execution.py |  |
| 真实工具调用 | `partially_implemented` | references/capability-floor-policy.md | src/aipd_os/execution/execution_router.py; tool_adapters/* | aipd_os.execution.execution_router.ExecutionRouter.run | `aipd run --project <id>` | tests/test_execution_router.py; tests/test_adapters.py | 主循环真实调用工具，但 research/imggen/cad 等外部适配器在无后端时诚实返回 simulated/external 占位，不真实执行 |
| 重试 | `partially_implemented` | references/supervisor-operating-model.md | src/aipd_os/execution/execution_router.py | aipd_os.execution.execution_router.ExecutionRouter.run | `aipd run --project <id>` | tests/test_execution_router.py | 重试次数为固定有界值 |
| 工具回退 | `fully_implemented` | references/capability-floor-policy.md | src/aipd_os/execution/execution_router.py | aipd_os.execution.execution_router.ExecutionRouter._try_fallback | `aipd run --project <id>` | tests/test_execution_router.py |  |
| 工件登记 | `fully_implemented` | references/deliverable-contracts.md | src/aipd_os/execution/runs.py | aipd_os.execution.runs.RunStore | `aipd run --project <id>` | tests/test_execution_router.py |  |
| 事实写回 | `partially_implemented` | references/state-model.md | scripts/aipd_supervisor.py | aipd_supervisor.Supervisor._register_outputs | `aipd run --project <id>` | tests/test_supervisor_execution.py | 全库无独立 product_truth/facts 表；主管的 update_facts 仅写 steps_log 字符串标签，未回写结构化事实表 |
| stale传播 | `partially_implemented` | references/supervisor-operating-model.md | scripts/aipd_supervisor.py | aipd_supervisor.Supervisor._mark_stale | `aipd run --project <id>` | tests/test_supervisor_execution.py | 仅写 invalidates 血缘标记，不重建/不重排下游工件 |
| 自动返工 | `partially_implemented` | references/supervisor-operating-model.md | scripts/aipd_supervisor.py | aipd_supervisor.Supervisor.run_supervisor | `aipd run --project <id>` | tests/test_supervisor_execution.py | 复用旧工作项重试，不新建独立返工项，且无返工次数上限 |
| 只在必要决策时暂停 | `fully_implemented` | references/decision-policy.md | scripts/aipd_supervisor.py | aipd_supervisor.Supervisor.run_supervisor | `aipd run --project <id> --until-decision` | tests/test_execution_router.py; tests/test_decision_policy.py |  |

## 产品事实

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 事实失效传播与有界返工 | `partially_implemented` | docs/architecture/truth_architecture.md | src/aipd_os/cli/commands_truth.py | aipd_os.cli.commands_truth.cmd_truth_propagate | `aipd truth propagate --db <state.db> --project <p> --upstream <id>` | tests/test_truth_propagate_cli.py; tests/test_product_truth_propagation.py; tests/test_product_truth_scoping.py | 只接了「传播」这半条链：返工的执行 PropagationEngine.run_rework 在 src/ 里仍是 0 调用点，因为没有真实返工执行器——引擎自身在无执行器时只判 blocked（其 refusing fake success 分支），本仓刻意不提供一条永远不会成功的命令，该缺口由 tests/test_truth_propagate_cli.py::TestUnwiredHalfStaysVisible 钉成断言，接上执行器那一轮必须连同该断言极性一起改判；血缘边目前也只有 product_intelligence/gate.commit_snapshot 会写（PI 需求 -> truth 记录），CTQ/图纸/BOM 之间没有生产者，所以链条更长的那一段今天传播不到；任务号按整表分配（task_id 是全局主键，按 tenant/project 作用域取 max 会让两个项目各自算出同一个 RW-001 并撞唯一约束，本轮跨项目实跑撞到），但读-算-插之间没加锁，多进程并发仍可能撞号，本仓按单写者假设运行；与主管侧 supervisor.auto_rework 是两套机制：那边复用工作项重试且无上限，这边是 truth 侧带 attempts/max_attempts/backoff 的有界返工 |

## 理论研究

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 附件读取 | `fully_implemented` | references/research-integration.md | scripts/research/_env.py; src/aipd_os/execution/adapter.py | research.source_worker.run_source | `python scripts/research/source_worker.py` | scripts/research/selftest_postprocess.py |  |
| 多源论文检索 | `partially_implemented` | references/research-integration.md | scripts/research/search_papers_by_{arxiv,crossref,dblp,open_alex,openreview,semantic_scholar}.py | research.search_papers.search_papers | `python scripts/research/search_papers.py --query "..."` | scripts/research/selftest_runtime.py | 需网络/外部源可用 |
| 全文获取 | `partially_implemented` | references/research-integration.md | scripts/research/_http_runtime.py; source_worker.py | research.source_worker.run_source | `python scripts/research/source_worker.py` | scripts/research/selftest_runtime.py | 各连接器当前仅取摘要，未实现全文获取与全文/摘要区分 |
| 去重排序 | `fully_implemented` | references/research-integration.md | scripts/research/postprocess.py | research.postprocess.dedup | `python scripts/research/postprocess.py` | scripts/research/selftest_postprocess.py |  |
| 引用 | `partially_implemented` | references/research-integration.md | scripts/research/postprocess.py | research.postprocess.dedup | `python scripts/research/postprocess.py` | scripts/research/selftest_postprocess.py | 仅后处理附加引用标识，无独立引用生成/引文格式管线 |
| 标准法规 | `external_dependency` | references/research-integration.md |  |  | `` |  | 依赖外部法规库/专业数据源，未接入时诚实等待 |
| 专利和竞品 | `external_dependency` | references/research-integration.md |  |  | `` |  | 依赖外部专利/竞品数据源，未接入时诚实等待 |
| 证据可信度 | `partially_implemented` | references/evidence-policy.md | src/aipd_os/research/credibility.py | aipd_os.research.credibility.score_evidence | `python scripts/claim_gate.py` | tests/test_credibility.py | 可信度分级为确定性启发式，仍需真实模型/外部核验提升精度 |
| 提示注入隔离 | `fully_implemented` | SECURITY.md / THREAT_MODEL.md | src/aipd_os/security/prompt_injection.py | aipd_os.security.prompt_injection.sanitize_external_content | `aipd eval` | tests/test_prompt_injection.py |  |

## 产品手册

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 理论基础进入规划 | `fully_implemented` | references/manual-chain-workflow.md | scripts/manual_chain.py | manual_chain.cmd_plan_batches | `aipd manual plan` | tests/test_manual_chain_e2e.py |  |
| 先规划，不直接生成全册 | `fully_implemented` | references/manual-chain-workflow.md | scripts/manual_chain.py | manual_chain.cmd_plan_batches | `aipd manual plan && aipd manual generate` | tests/test_manual_chain_e2e.py |  |
| 锚点页 | `fully_implemented` | references/manual-chain-workflow.md | scripts/manual_chain.py | manual_chain.cmd_run_batch | `aipd manual generate --anchors ...` | tests/test_manual_chain_e2e.py |  |
| 前批页面作为后批附件 | `partially_implemented` | references/manual-chain-workflow.md | scripts/manual_chain.py | manual_chain.cmd_run_batch | `aipd manual generate --prior-batch <id>` | tests/test_manual_chain_e2e.py | 仅收集前批页面路径与 hash 登记入状态，未真实传入图像模型作为附件 |
| Visual Bible | `fully_implemented` | references/manual-chain-workflow.md | scripts/manual_chain.py | manual_chain.cmd_run_batch | `aipd manual generate --visual-bible ...` | tests/test_manual_chain_e2e.py |  |
| 人物一致性 | `partially_implemented` | references/manual-quality-system.md | src/aipd_os/visual_audit/auditor.py | aipd_os.visual_audit.auditor.VisualAuditor | `aipd eval / python -m aipd_os.visual_audit.auditor` | tests/test_visual_golden.py | 依赖视觉/图像后端，无后端时走外部任务包 |
| 产品结构一致性 | `partially_implemented` | references/manual-quality-system.md | src/aipd_os/visual_audit/auditor.py | aipd_os.visual_audit.auditor.VisualAuditor | `aipd eval` | tests/test_visual_golden.py | 依赖视觉后端 |
| CMF一致性 | `partially_implemented` | references/manual-quality-system.md | src/aipd_os/visual_audit/auditor.py | aipd_os.visual_audit.auditor.VisualAuditor | `aipd eval` | tests/test_visual_golden.py | 依赖视觉后端 |
| 真实图像生成 | `external_dependency` | references/image-generation-batch-policy.md | src/aipd_os/imggen/adapter.py | aipd_os.imggen.adapter.ImageGenAdapter | `aipd manual generate` | tests/test_imggen.py | imggen 适配器为空壳：即使标 available 也必然抛错，无真实图像模型客户端；未配置后端时向外部任务包诚实降级 |
| 真实中文排版 | `fully_implemented` | references/product-manual-pipeline.md | src/aipd_os/layout/{composer,renderer}.py | aipd_os.layout.composer.compose_pdf | `aipd manual generate` | tests/test_layout.py |  |
| 参数表和曲线 | `fully_implemented` | references/product-manual-pipeline.md | src/aipd_os/layout/renderer.py | aipd_os.layout.renderer.render_page | `aipd manual generate` | tests/test_layout.py |  |
| 失败页局部返工 | `partially_implemented` | references/manual-chain-workflow.md | scripts/manual_chain.py | manual_chain.cmd_run_batch | `aipd manual generate` | tests/test_manual_chain_e2e.py | 仅产出失败页重建计划（rebuild_plan），无据此仅重跑单页的执行入口 |
| PNG、PDF 和 ZIP | `fully_implemented` | references/product-manual-pipeline.md | src/aipd_os/layout/composer.py | aipd_os.layout.composer.build_zip | `aipd manual generate` | tests/test_layout.py |  |
| 黄金样本语义审核 | `partially_implemented` | references/benchmark-and-golden-sample-policy.md | src/aipd_os/visual_audit/golden.py | aipd_os.visual_audit.golden.GoldenGapEvaluator | `aipd eval` | tests/test_visual_golden.py | 黄金样本仅元数据清单，真实对照 PNG 不在仓库；依赖视觉后端，无后端走外部任务包 |

## CAD与生产图纸

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CAD运行时预检 | `fully_implemented` | references/cad-runtime-acceptance.md | scripts/runtime_preflight.py; scripts/cad_maturity_gate.py | cad_maturity_gate.main | `aipd cad preflight --manifest <m> --target <Cx>` | tests/test_cad_maturity_gate.py |  |
| text-to-cad | `external_dependency` | references/cad-plugin-installation.md | src/aipd_os/tool_adapters/cad_adapter.py | aipd_os.tool_adapters.cad_adapter.CadAdapter | `aipd cad build` | tests/test_adapters.py | 依赖外部 CAD 内核/插件 |
| 本地原生B-Rep | `partially_implemented` | references/local-cad-fallback.md | src/aipd_os/cad/backends.py; src/aipd_os/tool_adapters/local_brep_adapter.py | aipd_os.cad.backends:get_default_backend | `aipd cad build` | tests/test_cad_golden_loop.py; tests/test_adapters.py | 单零件参数化 B-Rep 由本地 CadQuery 内核实现（C2）；装配建模/连续运动/CAE/形位校验 仍依赖外部工具，不冒充已完成（二维的装配图与形位框已本地出图，见 cad.2d_drawings） |
| Faceted回退 | `partially_implemented` | references/cad-convergence-policy.md | src/aipd_os/tool_adapters/faceted_adapter.py; scripts/faceted_step.py | aipd_os.tool_adapters.faceted_adapter.FacetedAdapter | `aipd cad build` | tests/test_adapters.py; tests/maturity_consistency_test.py | 成熟度最高 C1，不可用于正式图纸/量产 |
| 参数化模型 | `partially_implemented` | references/cad-engineering-readiness.md | src/aipd_os/cad/backends.py; src/aipd_os/tool_adapters/local_brep_adapter.py | aipd_os.cad.backends:get_default_backend | `aipd cad build` | tests/test_cad_golden_loop.py | 单零件参数化 B-Rep 由本地 CadQuery 内核实现（C2，需安装 cad extra）；装配建模/连续运动/CAE/形位校验 仍依赖外部工具，不冒充已完成（二维的装配图与形位框已本地出图，见 cad.2d_drawings） |
| 装配约束 | `external_dependency` | references/cad-engineering-readiness.md |  |  | `` |  | 依赖外部 CAD 内核 |
| 连续运动学 | `external_dependency` | references/cad-engineering-readiness.md |  |  | `` |  | 依赖外部仿真/运动学工具 |
| 人体尺寸族 | `partially_implemented` | references/cad-engineering-readiness.md | src/aipd_os/cad/anthropometry.py | aipd_os.cad.anthropometry.get_dimension | `aipd cad build` | tests/test_anthropometry.py | 内置族为常用成年男女/儿童百分位示例，未覆盖全部人群数据库 |
| CAE和疲劳 | `external_dependency` | references/cad-engineering-readiness.md |  |  | `` |  | 依赖外部 CAE/有限元工具 |
| DFM/DFA | `fully_implemented` | references/cad-engineering-readiness.md | templates/cad_engineering_manifest.json; scripts/production_release_gate.py | production_release_gate.main | `aipd validate --manifest <m>` | tests/test_production_release_gate.py |  |
| 公差链 | `fully_implemented` | references/cad-engineering-readiness.md | scripts/production_release_gate.py | production_release_gate.main | `aipd validate --manifest <m>` | tests/test_production_release_gate.py |  |
| GD&T | `fully_implemented` | references/cad-engineering-readiness.md | scripts/production_release_gate.py | production_release_gate.main | `aipd validate --manifest <m>` | tests/test_production_release_gate.py |  |
| 二维图纸 | `partially_implemented` | references/production-cad-deliverables.md | src/aipd_os/cad/drawings2d.py; src/aipd_os/cad/assembly.py | aipd_os.cli.commands_drawing.cmd_drawing | `aipd drawing generate` | tests/test_cad_drawings2d.py; tests/test_cad_drawings_chain_tolerance.py; tests/test_cad_stackup.py; tests/test_cad_gdt_frames.py; tests/test_cad_section_views.py; tests/test_cad_spec_from_truth.py; tests/test_cad_gdt_deviation.py; tests/test_cad_section_symbols.py; tests/test_cad_detail_views.py; tests/test_cad_assembly_balloons.py | 出图为 DXF 三视图 + 投影测量的总体尺寸/孔径 + 由实测孔心排出的尺寸链（闭合差写进 dimension_chain_check）；公差只能来自 --spec 声明，未声明则不写任何公差，声明落空会判未收口（退出码 4）。隐藏线用逐点射线遮挡判定，相切轮廓（如孔筒壁正视图）只判出一侧（tests/test_cad_drawings2d.py::TestTangencyLimit 钉住现状并写明翻转条件）。一维公差叠加已给出「各段公差带之和 vs 封闭环公差带」的自相矛盾判定（缺任何一环声明即判不可判定，不按 0 折算，也不猜功能限值），但三维/角度叠加与统计分布（Cpk）未做。GD&T 特征控制框（FCF）可按声明绘制并回读：分格框线 + 每格 TEXT + 引线，挂点取实测特征圆心，基准解析不了/特征不存在/类型不认识一律判未收口而不是画半截框；位置度类框已能**数值核对**：声明带 basic（理论精确位置）时拿投影实测圆心算偏差，超带判 position_deviation_exceeded 并退出码 4，没给 basic 则点名 position_basic_missing 而不拿实测当理论；形状/方向类（平面度/垂直度等）需要整面采样，本仓不做，一律标 verified=presence_only 不假称核过。但用的是 drawn 几何而非 DXF TOLERANCE 语义实体——其 content 转义码本轮未找到权威来源核实，故不宣称在各查看器里渲染一致。剖视已能真做（半空间布尔切割 + 剖面材料区量积 + DXF HATCH 填充，切不到材料/边界接不成闭合环/含内环都如实报且不静默填错多边形，切不到材料还判未收口（退出码 4））；剖切符号（母视图上的剖切线 + 指向保留侧的短划 + 两端字母 + 剖面标题 A-A）已按「剖切平面在母视图投影面上的交线」算出并真画，空剖视不编号也不画符号；局部放大图已能出（--detail TOP@(-30,0)/12=2：放大圆与母视图**已判定可见/隐藏**的折线做解析式二维裁剪，母视图上画裁剪圈 + 编号，放大图按「全局比例 × 倍数」画并带 DETAIL n 与比例标题；尺寸只从母视图继承测点落在圆内的那些且保留原名（inherited_from），总尺寸与以零件边缘为锚的链段一律不带入；圆内没有图线即判未收口（退出码 4）且不编号不画圈；它是母视图几何的放大而非重新投影，故母视图的可见/隐藏判定与相切边界原样带过去，母视图允许是剖视但材料区不参与裁剪（从剖视放大的图有线无剖面线），形位框仍只贴在母视图上（框按视图前缀名解析），同一处公差在母视图与放大图各印一次只算一条覆盖凭据）；未做阶梯剖/旋转剖；仍未实现：爆炸图与装配约束/配合；尺寸公差声明已有生产者：`aipd drawing spec` 把 Product Truth 里 status=active 的 CTQ 转成 --spec 那份 JSON（必须显式写 metadata.drawing_feature 与 nominal，缺则点名不产出、且缺口未收口时不写文件），出图时还会拿投影实测值反查 CTQ 的绝对合格域（落在域外判 ctq_window_violation 并退出码 4）；GD&T 形位框与基准方案也已能从同一条记录长出（metadata.gdt / metadata.datum_id，同一个特征上「一条给尺寸、一条给形位」合并成一条声明、同类重复则两条都撤回）；仍只吃手写 JSON 的是尺寸链各段与 global_tolerance（CTQ 上一般没有分段要求），且全程不按名字自动映射；装配图已能出（`aipd drawing assembly` 吃装配清单：**逐件投影**而非合并投影，故每条折线天然知道自己属于哪个零件；球标编号只认 manifest 里作者声明的 balloon，缺号/重号/写 0/零件重名/STEP 读不到一律 rc=2，不按遍历顺序发号；引线挂在实测投影质心上，零件沿投影方向叠着时点名列出「球标落在视图上同一个位置」的告警；明细表由 ezdxf TablePainter 画，只含 ITEM/PART 两列——数量权威在 BOM，本轮未接线故不印任何猜测值；包络投影重叠只作告警，不是干涉判定，本轮不做实体求交；装配视图上拒绝 --section/--detail，因为裁剪会打散按零件归属的折线）；未做：球标↔BOM 行交叉核对（BomLine 无件号字段）、爆炸图与装配约束/配合；剖视的阶梯剖/旋转剖未做，放大图不做重新投影与局部剖，故 C6 生产图纸包整体仍不成立。需安装 cad extra（cadquery/OCP + ezdxf）；未安装时 CLI 返回 HOLD 外部任务包，不外推出图。 |
| BOM一致性 | `fully_implemented` | references/manual-to-cad-digital-thread.md | scripts/production_release_gate.py | production_release_gate.main | `aipd validate --manifest <m>` | tests/test_production_release_gate.py |  |
| 检验计划 | `fully_implemented` | references/cad-engineering-readiness.md | scripts/production_release_gate.py | production_release_gate.main | `aipd validate --manifest <m>` | tests/test_production_release_gate.py |  |
| 生产发布门 | `fully_implemented` | references/gate-model.md | scripts/production_release_gate.py | production_release_gate.main | `aipd validate --manifest <m> --target <level>` | tests/test_production_release_gate.py |  |

## 工业化与验证

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RFQ | `partially_implemented` | references/tool-and-physical-boundaries.md | src/aipd_os/tool_adapters/mail_rfq_adapter.py | aipd_os.tool_adapters.mail_rfq_adapter.MailRfqAdapter | `aipd industrialize` | tests/test_supply_chain.py | 真实邮件发送依赖外部邮件通道 |
| 邮件执行 | `external_dependency` | references/tool-and-physical-boundaries.md | src/aipd_os/execution/side_effects.py; src/aipd_os/tool_adapters/mail_rfq_adapter.py | aipd_os.execution.side_effects.rfq_send_handler | `aipd outbox drain` | tests/test_outbox_rfq_wiring.py | 真实投递仍依赖外部 SMTP/Gmail 通道，未配置时诚实 external_blocked；投递由 outbox 事件 + dispatcher 驱动（aipd outbox drain）；同一内容的重驱动按内容幂等拦截，结果未知（transient/tool_error）的失败挂起等人工核对，不自动重发 |
| 发布就绪证据装配 | `partially_implemented` | references/production-cad-deliverables.md | src/aipd_os/release_manifest.py | aipd_os.cli.commands_release.cmd_release_manifest | `aipd release manifest` | tests/test_release_manifest.py; tests/test_cad_spec_from_truth.py | 覆盖凭据分两档并写进 covered_by/verified：尺寸数值一致（dimension）或形位框真画上且挂实测特征（feature_control_frame，verified=deviation 表示位置度偏差已数值核对、presence_only 表示只证到存在）；位置度超带的框**不给**计覆盖并落一条阻断问题。只做证据装配与显式溯源：每条 gdt 覆盖都带 covered_by（dimension 或 feature_control_frame）与 ctq_record_id，形位框按「真画上去了 + 挂在实测特征上」计入覆盖，**不**声称核过形位偏差数值（本仓还不测形位偏差）；同一条需求被尺寸与框同时命中时只计一次。图纸特征与 CTQ 的对应关系可由 aipd drawing spec 从 metadata.drawing_feature 生成 ctq_ref（仍不按名字自动映射，linkage 由需求侧显式写），证据里的每条 gdt 都回写 ctq_record_id 指明是对着哪条记录成立的；模型侧只支持从 STEP 数实体，读不到就不写 model_part_count（不折算成 0）；approval_status 由属主填、缺省 unapproved，生产者不代为置 approved；版本不一致只如实记录不对齐；GD&T 形位公差框已可绘制（见 cad.2d_drawings），但叠加/形位声明的自动生成仍未接入；尺寸实测值是否落在 CTQ 合格域内由图纸侧判（cad.2d_drawings 的 spec_limit_issues），本模块不重复判。 |
| 报价解析 | `partially_implemented` | references/tool-and-physical-boundaries.md | src/aipd_os/supply_chain/quotes.py | aipd_os.supply_chain.quotes.normalize_quote | `aipd industrialize --quote <file>` | tests/test_supply_chain.py | 附件格式解析范围有限；解析本身不动钱，落到 BOM 由 industrialize.quote_to_bom_cost 承担 |
| 报价→BOM→成本闭环 | `partially_implemented` | references/tool-and-physical-boundaries.md; docs/audit/QUOTE_BOM_COST_F-SUPPLY-01_2026-09-24.md | src/aipd_os/supply_chain/apply.py; src/aipd_os/cli/commands_supply.py | aipd_os.supply_chain.apply.apply_quotes_to_bom | `aipd quote apply --db <state.db> --file <quotes.csv>` | tests/test_quote_to_cost_chain.py | 报价文件表头无币种列，币种必须由 --currency 显式声明并逐行核对；draft/superseded 报价与作废行一律拒绝改价；跨币种折算未实现 |
| 供应商资质 | `partially_implemented` | references/tool-and-physical-boundaries.md | src/aipd_os/supply_chain/suppliers.py | aipd_os.supply_chain.suppliers.SupplierRegistry | `aipd industrialize` | tests/test_supply_chain.py | 证书真实性需人工/外部核验 |
| EVT/DVT/PVT数据导入 | `partially_implemented` | references/tool-and-physical-boundaries.md | src/aipd_os/supply_chain/lab.py; src/aipd_os/validation/ingestion.py | aipd_os.supply_chain.lab.import_lab_csv | `aipd validation import --db <state.db> --project <p> --stage dvt --file <csv>（或 aipd industrialize --lab-data <csv>）` | tests/test_supply_chain.py; tests/test_validation_ingestion.py | 导入格式范围有限（PDF/DOCX 报告走 external_blocked 不虚构）；tool_adapters 里的 ValidationDataAdapter 未被产品侧排产，产品面是这两条命令 |
| 测试失败根因 | `fully_implemented` | references/end-to-end-closure-model.md | src/aipd_os/supply_chain/analysis.py | aipd_os.supply_chain.analysis.analyze_stage | `aipd industrialize --lab-data <csv>` | tests/test_supply_chain.py |  |
| 纠正任务 | `fully_implemented` | references/end-to-end-closure-model.md | src/aipd_os/supply_chain/analysis.py | aipd_os.supply_chain.analysis.create_correction_tasks | `aipd industrialize --lab-data <csv>` | tests/test_supply_chain.py |  |
| 实体数据回写 | `partially_implemented` | references/end-to-end-closure-model.md; docs/audit/LAB_IMPACT_PROPAGATION_F-SUPPLY-03_2026-09-24.md | src/aipd_os/supply_chain/impact.py; src/aipd_os/cli/commands_validation.py | aipd_os.supply_chain.impact.propagate_lab_impact | `aipd validation import --db <state.db> --project <p> --stage dvt --file <lab.csv>` | tests/test_lab_impact_propagation.py | 匹配按 BOM 行 item 归一化全等，不做子串或父子链推断；未关联 deliverable 的行只如实报告 unresolved（不代造制品），此时命令 exit 4 不静默通过；released/archived 制品不被回溯改写，返工范围由人决定；product_truth 的失效传播已从 aipd truth propagate / aipd truth tasks 可达（见 product_truth.impact_propagation），但返工的执行 run_rework 仍是 0 调用点；本条走的是 deliverable+fact 这条已接线的路 |
| 认证状态 | `partially_implemented` | references/quality-and-claim-governance.md | src/aipd_os/supply_chain/certification.py | aipd_os.supply_chain.certification.CertificationRegistry | `aipd industrialize` | tests/test_certification.py | 状态机确定性实现，证书真实性仍需外部权威核验 |

## 跨会话与用户体验

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 项目持久化 | `fully_implemented` | references/state-model.md | src/aipd_os/state/db.py | aipd_os.state.db.AIPDStateDB | `aipd init` | tests/test_state_db.py |  |
| checkpoint | `fully_implemented` | references/state-model.md | src/aipd_os/state/checkpoint.py | aipd_os.state.checkpoint.CheckpointManager | `aipd status` | tests/test_backup_checkpoint.py |  |
| 新会话自动恢复 | `partially_implemented` | references/state-model.md | src/aipd_os/experience/resume_summary.py | aipd_os.experience.resume_summary.build_resume_summary | `aipd resume` | tests/test_experience.py | aipd resume 仅输出恢复摘要，不自动调用 supervisor 继续执行；manual 附件链不在状态库/备份范围内无法恢复 |
| 不重复询问 | `fully_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/resume_summary.py | aipd_os.experience.resume_summary.build_resume_summary | `aipd resume` | tests/test_behavior_contracts.py |  |
| 项目摘要 | `fully_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/project_summary.py; views.py | aipd_os.experience.views.OwnerView | `aipd status` | tests/test_experience.py |  |
| 单一决策卡 | `fully_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/decision_card.py | aipd_os.experience.decision_card.build_decision_card | `aipd status` | tests/test_experience.py |  |
| 自然语言审批 | `fully_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/instructions.py | aipd_os.experience.instructions.parse_instruction | `aipd decide` | tests/test_behavior_contracts.py |  |
| 手册预览和版本差异 | `fully_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/artifact_preview.py | aipd_os.experience.artifact_preview.artifact_preview | `aipd status` | tests/test_experience.py |  |
| CAD差异 | `fully_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/views.py | aipd_os.experience.views.OwnerView | `aipd status` | tests/test_experience.py |  |
| BOM差异 | `fully_implemented` | references/manual-to-cad-digital-thread.md | src/aipd_os/experience/views.py | aipd_os.experience.views.OwnerView | `aipd status` | tests/test_experience.py |  |
| 风险和外部等待视图 | `fully_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/project_summary.py | aipd_os.experience.project_summary.build_project_summary | `aipd status` | tests/test_experience.py |  |

## 产品智能

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 推导洞察候选 | `external_dependency` | docs/architecture/idea_evidence_architecture.md; docs/audit/V5_9_1_RE_AUDIT_MATRIX.md | src/aipd_os/tool_adapters/product_adapters.py; src/aipd_os/product_intelligence/provider.py | aipd_os.tool_adapters.product_adapters.ProductDeriveInsightsAdapter | `aipd run（Supervisor S2 product.derive_insights）` | tests/test_product_definition_integrity.py; tests/test_product_intelligence.py | 生产 Provider 未接入；未配置时 discover.available=False -> probe EXTERNAL_DEPENDENCY，execute 写外部任务包（诚实不伪造） |
| 识别机会候选 | `external_dependency` | docs/architecture/idea_evidence_architecture.md; docs/audit/V5_9_1_RE_AUDIT_MATRIX.md | src/aipd_os/tool_adapters/product_adapters.py; src/aipd_os/product_intelligence/provider.py | aipd_os.tool_adapters.product_adapters.ProductIdentifyOpportunityAdapter | `aipd run（Supervisor S2 product.identify_opportunity）` | tests/test_product_definition_integrity.py | 生产 Provider 未接入；未配置时诚实 EXTERNAL_DEPENDENCY |
| 推导产品原则候选 | `external_dependency` | docs/architecture/idea_evidence_architecture.md; docs/audit/V5_9_1_RE_AUDIT_MATRIX.md | src/aipd_os/tool_adapters/product_adapters.py; src/aipd_os/product_intelligence/provider.py | aipd_os.tool_adapters.product_adapters.ProductDerivePrinciplesAdapter | `aipd run（Supervisor S2 product.derive_principles）` | tests/test_product_definition_integrity.py | 生产 Provider 未接入；未配置时诚实 EXTERNAL_DEPENDENCY |
| 推导需求候选 | `external_dependency` | docs/architecture/idea_evidence_architecture.md; docs/audit/V5_9_1_RE_AUDIT_MATRIX.md | src/aipd_os/tool_adapters/product_adapters.py; src/aipd_os/product_intelligence/provider.py | aipd_os.tool_adapters.product_adapters.ProductDeriveRequirementsAdapter | `aipd run（Supervisor S2 product.derive_requirements）` | tests/test_product_definition_integrity.py | 生产 Provider 未接入；未配置时诚实 EXTERNAL_DEPENDENCY |
| 推导功能候选 | `external_dependency` | docs/architecture/idea_evidence_architecture.md; docs/audit/V5_9_1_RE_AUDIT_MATRIX.md | src/aipd_os/tool_adapters/product_adapters.py; src/aipd_os/product_intelligence/provider.py | aipd_os.tool_adapters.product_adapters.ProductDeriveFeaturesAdapter | `aipd run（Supervisor S2 product.derive_features）` | tests/test_product_definition_integrity.py | 生产 Provider 未接入；未配置时诚实 EXTERNAL_DEPENDENCY |
| 冻结产品定义快照 | `fully_implemented` | docs/audit/V5_9_1_RE_AUDIT_MATRIX.md | src/aipd_os/product_intelligence/snapshot.py; src/aipd_os/tool_adapters/product_adapters.py | aipd_os.tool_adapters.product_adapters.ProductCreateSnapshotAdapter | `aipd run（Supervisor S2 product.create_snapshot）` | tests/test_product_definition_integrity.py |  |
| 产品定义门禁 | `partially_implemented` | docs/audit/V5_9_1_RE_AUDIT_MATRIX.md | src/aipd_os/product_intelligence/gate.py; src/aipd_os/tool_adapters/product_adapters.py | aipd_os.tool_adapters.product_adapters.ProductDefinitionGateAdapter | `aipd product gate --db state.db --project p1` | tests/test_product_definition_integrity.py | 确定性本地评估（LLM 只可解释不可决定 READY）；生产 Provider 不影响 Gate 可用性 |

