# AIPD-OS 能力矩阵（v5.6 Registry 驱动）

- 生成时间：`2026-08-06T18:03:20`
- 仓库：`/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS`
- 默认分支：`main`；HEAD：`0934f84d9d8cae26adfc8a088ba3af2dc58c999b`
- 版本：`5.6.0`
- 能力总数：`70`
- 分类由 Capability Registry + 运行时证据推导，非静态表。

## 分类统计

| 分类 | 数量 | 说明 |
| --- | --- | --- |
| `fully_implemented` | 2 | 完整实现（有真实运行工件与测试证据） |
| `partially_implemented` | 59 | 部分实现（核心路径可用，边界/证据不全） |
| `protocol_only` | 0 | 仅协议/接口（无真实执行） |
| `template_only` | 0 | 仅模板/示例（无真实执行） |
| `external_dependency` | 9 | 依赖外部服务/工具（未配置时诚实等待，不伪造） |
| `not_implemented` | 0 | 未实现 |
| `not_verifiable` | 0 | 无法验证（缺证据/缺环境） |

## 主管执行

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 一句话创建项目 | `partially_implemented` | README.md / SKILL.md | src/aipd_os/cli/commands.py; scripts/aipd_supervisor.py | cmd_intake / Supervisor.run_supervisor | `aipd intake --prompt "<一句话需求>"` | tests/test_cli.py::cmd_intake | 拆分规模受默认工作包模板约束 |
| 自动拆分工作包 | `partially_implemented` | references/work-queue-and-routing.md | scripts/aipd_supervisor.py | Supervisor.plan / Supervisor.run_supervisor | `aipd run --project <id>` | tests/test_supervisor_execution.py |  |
| 依赖排序 | `partially_implemented` | references/work-queue-and-routing.md | scripts/aipd_supervisor.py | Supervisor._next_work | `aipd run --project <id>` | tests/test_supervisor_execution.py |  |
| 真实工具调用 | `partially_implemented` | references/capability-floor-policy.md | src/aipd_os/execution/execution_router.py; tool_adapters/* | ExecutionRouter.execute | `aipd run --project <id>` | tests/test_execution_router.py; tests/test_adapters.py | 主循环真实调用工具，但 research/imggen/cad 等外部适配器在无后端时诚实返回 simulated/external 占位，不真实执行 |
| 重试 | `partially_implemented` | references/supervisor-operating-model.md | src/aipd_os/execution/execution_router.py | ExecutionRouter._bounded_retry | `aipd run --project <id>` | tests/test_execution_router.py | 重试次数为固定有界值 |
| 工具回退 | `partially_implemented` | references/capability-floor-policy.md | src/aipd_os/execution/execution_router.py | ExecutionRouter._fallback | `aipd run --project <id>` | tests/test_execution_router.py |  |
| 工件登记 | `partially_implemented` | references/deliverable-contracts.md | src/aipd_os/execution/runs.py | ExecutionRouter.collect_artifacts | `aipd run --project <id>` | tests/test_execution_router.py |  |
| 事实写回 | `partially_implemented` | references/state-model.md | scripts/aipd_supervisor.py | Supervisor._update_facts | `aipd run --project <id>` | tests/test_supervisor_execution.py | 全库无独立 product_truth/facts 表；主管的 update_facts 仅写 steps_log 字符串标签，未回写结构化事实表 |
| stale传播 | `partially_implemented` | references/supervisor-operating-model.md | scripts/aipd_supervisor.py | Supervisor._mark_stale | `aipd run --project <id>` | tests/test_supervisor_execution.py | 仅写 invalidates 血缘标记，不重建/不重排下游工件 |
| 自动返工 | `partially_implemented` | references/supervisor-operating-model.md | scripts/aipd_supervisor.py | Supervisor._rework | `aipd run --project <id>` | tests/test_supervisor_execution.py | 复用旧工作项重试，不新建独立返工项，且无返工次数上限 |
| 只在必要决策时暂停 | `partially_implemented` | references/decision-policy.md | scripts/aipd_supervisor.py | Supervisor.run_supervisor / aipd run --until-decision | `aipd run --project <id> --until-decision` | tests/test_execution_router.py; tests/test_decision_policy.py |  |

## 理论研究

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 附件读取 | `partially_implemented` | references/research-integration.md | scripts/research/_env.py; src/aipd_os/execution/adapter.py | research.source_worker | `python scripts/research/source_worker.py` | scripts/research/selftest_postprocess.py |  |
| 多源论文检索 | `partially_implemented` | references/research-integration.md | scripts/research/search_papers_by_{arxiv,crossref,dblp,open_alex,openreview,semantic_scholar}.py | search_papers.py | `python scripts/research/search_papers.py --query "..."` | scripts/research/selftest_runtime.py | 需网络/外部源可用 |
| 全文获取 | `partially_implemented` | references/research-integration.md | scripts/research/_http_runtime.py; source_worker.py | source_worker.fetch | `python scripts/research/source_worker.py` | scripts/research/selftest_runtime.py | 各连接器当前仅取摘要，未实现全文获取与全文/摘要区分 |
| 去重排序 | `partially_implemented` | references/research-integration.md | scripts/research/postprocess.py | postprocess.run | `python scripts/research/postprocess.py` | scripts/research/selftest_postprocess.py |  |
| 引用 | `partially_implemented` | references/research-integration.md | scripts/research/postprocess.py | postprocess.attach_citation | `python scripts/research/postprocess.py` | scripts/research/selftest_postprocess.py | 仅后处理附加引用标识，无独立引用生成/引文格式管线 |
| 标准法规 | `external_dependency` | references/research-integration.md |  |  | `` |  | 依赖外部法规库/专业数据源，未接入时诚实等待 |
| 专利和竞品 | `external_dependency` | references/research-integration.md |  |  | `` |  | 依赖外部专利/竞品数据源，未接入时诚实等待 |
| 证据可信度 | `partially_implemented` | references/evidence-policy.md | src/aipd_os/research/credibility.py | credibility.score_evidence | `python scripts/claim_gate.py` | tests/test_credibility.py | 可信度分级为确定性启发式，仍需真实模型/外部核验提升精度 |
| 提示注入隔离 | `partially_implemented` | SECURITY.md / THREAT_MODEL.md | src/aipd_os/security/prompt_injection.py | isolation.sanitize | `aipd eval` | tests/test_prompt_injection.py |  |

## 产品手册

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 理论基础进入规划 | `fully_implemented` | references/manual-chain-workflow.md | scripts/manual_chain.py | manual_chain.cmd_plan_batches | `aipd manual plan` | tests/test_manual_chain_e2e.py |  |
| 先规划，不直接生成全册 | `partially_implemented` | references/manual-chain-workflow.md | scripts/manual_chain.py | cmd_plan_batches / cmd_run_batch | `aipd manual plan && aipd manual generate` | tests/test_manual_chain_e2e.py |  |
| 锚点页 | `partially_implemented` | references/manual-chain-workflow.md | scripts/manual_chain.py | cmd_run_batch(anchors=...) | `aipd manual generate --anchors ...` | tests/test_manual_chain_e2e.py |  |
| 前批页面作为后批附件 | `partially_implemented` | references/manual-chain-workflow.md | scripts/manual_chain.py | cmd_run_batch(prior_batch=...) | `aipd manual generate --prior-batch <id>` | tests/test_manual_chain_e2e.py | 仅收集前批页面路径与 hash 登记入状态，未真实传入图像模型作为附件 |
| Visual Bible | `partially_implemented` | references/manual-chain-workflow.md | scripts/manual_chain.py | cmd_run_batch(visual_bible=...) | `aipd manual generate --visual-bible ...` | tests/test_manual_chain_e2e.py |  |
| 人物一致性 | `partially_implemented` | references/manual-quality-system.md | src/aipd_os/visual_audit/auditor.py | auditor.audit_page | `aipd eval / python -m aipd_os.visual_audit.auditor` | tests/test_visual_golden.py | 依赖视觉/图像后端，无后端时走外部任务包 |
| 产品结构一致性 | `partially_implemented` | references/manual-quality-system.md | src/aipd_os/visual_audit/auditor.py | auditor.audit_page | `aipd eval` | tests/test_visual_golden.py | 依赖视觉后端 |
| CMF一致性 | `partially_implemented` | references/manual-quality-system.md | src/aipd_os/visual_audit/auditor.py | auditor.audit_page | `aipd eval` | tests/test_visual_golden.py | 依赖视觉后端 |
| 真实图像生成 | `external_dependency` | references/image-generation-batch-policy.md | src/aipd_os/imggen/adapter.py | imggen.adapter | `aipd manual generate` | tests/test_imggen.py | imggen 适配器为空壳：即使标 available 也必然抛错，无真实图像模型客户端；未配置后端时向外部任务包诚实降级 |
| 真实中文排版 | `partially_implemented` | references/product-manual-pipeline.md | src/aipd_os/layout/{composer,renderer}.py | layout.compose_pdf | `aipd manual generate` | tests/test_layout.py |  |
| 参数表和曲线 | `partially_implemented` | references/product-manual-pipeline.md | src/aipd_os/layout/renderer.py | renderer.render_table/curve | `aipd manual generate` | tests/test_layout.py |  |
| 失败页局部返工 | `partially_implemented` | references/manual-chain-workflow.md | scripts/manual_chain.py | cmd_run_batch(external_pending/rework) | `aipd manual generate` | tests/test_manual_chain_e2e.py | 仅产出失败页重建计划（rebuild_plan），无据此仅重跑单页的执行入口 |
| PNG、PDF 和 ZIP | `partially_implemented` | references/product-manual-pipeline.md | src/aipd_os/layout/composer.py | layout.build_zip/compose_pdf | `aipd manual generate` | tests/test_layout.py |  |
| 黄金样本语义审核 | `partially_implemented` | references/benchmark-and-golden-sample-policy.md | src/aipd_os/visual_audit/golden.py | golden.audit | `aipd eval` | tests/test_visual_golden.py | 黄金样本仅元数据清单，真实对照 PNG 不在仓库；依赖视觉后端，无后端走外部任务包 |

## CAD与生产图纸

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CAD运行时预检 | `partially_implemented` | references/cad-runtime-acceptance.md | scripts/runtime_preflight.py; scripts/cad_maturity_gate.py | cad_maturity_gate.cmd/preflight | `aipd cad preflight --manifest <m> --target <Cx>` | tests/test_cad_maturity_gate.py |  |
| text-to-cad | `external_dependency` | references/cad-plugin-installation.md | src/aipd_os/tool_adapters/cad_adapter.py | cad_adapter | `aipd cad build` | tests/test_adapters.py | 依赖外部 CAD 内核/插件 |
| 本地原生B-Rep | `partially_implemented` | references/local-cad-fallback.md | src/aipd_os/cad/backends.py; src/aipd_os/tool_adapters/local_brep_adapter.py | aipd_os.cad.backends:get_default_backend | `aipd cad build` | tests/test_cad_golden_loop.py; tests/test_adapters.py | 单零件参数化 B-Rep 由本地 CadQuery 内核实现（C2）；装配/连续运动/CAE/二维图纸/GD&T 仍依赖外部工具，不冒充已完成 |
| Faceted回退 | `partially_implemented` | references/cad-convergence-policy.md | src/aipd_os/tool_adapters/faceted_adapter.py; scripts/faceted_step.py | faceted_adapter | `aipd cad build` | tests/test_adapters.py; tests/maturity_consistency_test.py | 成熟度最高 C1，不可用于正式图纸/量产 |
| 参数化模型 | `partially_implemented` | references/cad-engineering-readiness.md | src/aipd_os/cad/backends.py; src/aipd_os/tool_adapters/local_brep_adapter.py | aipd_os.cad.backends:get_default_backend | `aipd cad build` | tests/test_cad_golden_loop.py | 单零件参数化 B-Rep 由本地 CadQuery 内核实现（C2，需安装 cad extra）；装配/连续运动/CAE/二维图纸/GD&T 仍依赖外部工具，不冒充已完成 |
| 装配约束 | `external_dependency` | references/cad-engineering-readiness.md |  |  | `` |  | 依赖外部 CAD 内核 |
| 连续运动学 | `external_dependency` | references/cad-engineering-readiness.md |  |  | `` |  | 依赖外部仿真/运动学工具 |
| 人体尺寸族 | `partially_implemented` | references/cad-engineering-readiness.md | src/aipd_os/cad/anthropometry.py | anthropometry.get_dimension | `aipd cad build` | tests/test_anthropometry.py | 内置族为常用成年男女/儿童百分位示例，未覆盖全部人群数据库 |
| CAE和疲劳 | `external_dependency` | references/cad-engineering-readiness.md |  |  | `` |  | 依赖外部 CAE/有限元工具 |
| DFM/DFA | `partially_implemented` | references/cad-engineering-readiness.md | templates/cad_engineering_manifest.json; scripts/production_release_gate.py | production_release_gate | `aipd validate --manifest <m>` | tests/test_production_release_gate.py |  |
| 公差链 | `partially_implemented` | references/cad-engineering-readiness.md | scripts/production_release_gate.py | production_release_gate | `aipd validate --manifest <m>` | tests/test_production_release_gate.py |  |
| GD&T | `partially_implemented` | references/cad-engineering-readiness.md | scripts/production_release_gate.py | production_release_gate | `aipd validate --manifest <m>` | tests/test_production_release_gate.py |  |
| 二维图纸 | `external_dependency` | references/production-cad-deliverables.md |  |  | `` |  | 依赖外部 CAD 内核出图 |
| BOM一致性 | `partially_implemented` | references/manual-to-cad-digital-thread.md | scripts/production_release_gate.py | production_release_gate | `aipd validate --manifest <m>` | tests/test_production_release_gate.py |  |
| 检验计划 | `partially_implemented` | references/cad-engineering-readiness.md | scripts/production_release_gate.py | production_release_gate | `aipd validate --manifest <m>` | tests/test_production_release_gate.py |  |
| 生产发布门 | `fully_implemented` | references/gate-model.md | scripts/production_release_gate.py | production_release_gate.main | `aipd validate --manifest <m> --target <level>` | tests/test_production_release_gate.py |  |

## 工业化与验证

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RFQ | `partially_implemented` | references/tool-and-physical-boundaries.md | src/aipd_os/tool_adapters/mail_rfq_adapter.py | mail_rfq_adapter | `aipd industrialize` | tests/test_supply_chain.py | 真实邮件发送依赖外部邮件通道 |
| 邮件执行 | `external_dependency` | references/tool-and-physical-boundaries.md | src/aipd_os/tool_adapters/mail_rfq_adapter.py | mail_rfq_adapter.send | `aipd industrialize` |  | 依赖外部 Gmail/邮件通道，未接入时诚实等待 |
| 报价解析 | `partially_implemented` | references/tool-and-physical-boundaries.md | src/aipd_os/supply_chain/quotes.py | quotes.parse_quote_file | `aipd industrialize --quote <file>` | tests/test_supply_chain.py | 附件格式解析范围有限 |
| 供应商资质 | `partially_implemented` | references/tool-and-physical-boundaries.md | src/aipd_os/supply_chain/suppliers.py | suppliers.register | `aipd industrialize` | tests/test_supply_chain.py | 证书真实性需人工/外部核验 |
| EVT/DVT/PVT数据导入 | `partially_implemented` | references/tool-and-physical-boundaries.md | src/aipd_os/supply_chain/lab.py; tool_adapters/evt_dvt_pvt_adapter.py | lab.import_lab_csv | `aipd industrialize --lab-data <csv>` | tests/test_supply_chain.py | 导入格式范围有限 |
| 测试失败根因 | `partially_implemented` | references/end-to-end-closure-model.md | src/aipd_os/supply_chain/analysis.py | analysis.analyze_stage | `aipd industrialize --lab-data <csv>` | tests/test_supply_chain.py |  |
| 纠正任务 | `partially_implemented` | references/end-to-end-closure-model.md | src/aipd_os/supply_chain/analysis.py | analysis.create_correction_tasks | `aipd industrialize --lab-data <csv>` | tests/test_supply_chain.py |  |
| 实体数据回写 | `partially_implemented` | references/end-to-end-closure-model.md | src/aipd_os/supply_chain/analysis.py | analysis.propagate | `aipd industrialize --lab-data <csv>` | tests/test_supply_chain.py |  |
| 认证状态 | `partially_implemented` | references/quality-and-claim-governance.md | src/aipd_os/supply_chain/certification.py | certification.CertificationRegistry | `aipd industrialize` | tests/test_certification.py | 状态机确定性实现，证书真实性仍需外部权威核验 |

## 跨会话与用户体验

| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 项目持久化 | `partially_implemented` | references/state-model.md | src/aipd_os/state/db.py | AIPDStateDB | `aipd init` | tests/test_state_db.py |  |
| checkpoint | `partially_implemented` | references/state-model.md | src/aipd_os/state/checkpoint.py | checkpoint.save/load | `aipd status` | tests/test_backup_checkpoint.py |  |
| 新会话自动恢复 | `partially_implemented` | references/state-model.md | src/aipd_os/experience/resume_summary.py | resume_summary.build | `aipd resume` | tests/test_experience.py | aipd resume 仅输出恢复摘要，不自动调用 supervisor 继续执行；manual 附件链不在状态库/备份范围内无法恢复 |
| 不重复询问 | `partially_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/resume_summary.py | resume_summary (decisions_to_ask) | `aipd resume` | tests/test_behavior_contracts.py |  |
| 项目摘要 | `partially_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/project_summary.py; views.py | OwnerView.owner_update | `aipd status` | tests/test_experience.py |  |
| 单一决策卡 | `partially_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/decision_card.py | decision_card.build | `aipd status` | tests/test_experience.py |  |
| 自然语言审批 | `partially_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/instructions.py | instructions.parse | `aipd decide` | tests/test_behavior_contracts.py |  |
| 手册预览和版本差异 | `partially_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/artifact_preview.py | artifact_preview | `aipd status` | tests/test_experience.py |  |
| CAD差异 | `partially_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/views.py | OwnerView | `aipd status` | tests/test_experience.py |  |
| BOM差异 | `partially_implemented` | references/manual-to-cad-digital-thread.md | src/aipd_os/experience/views.py | OwnerView | `aipd status` | tests/test_experience.py |  |
| 风险和外部等待视图 | `partially_implemented` | references/interaction-contract-v4.md | src/aipd_os/experience/project_summary.py | project_summary | `aipd status` | tests/test_experience.py |  |

