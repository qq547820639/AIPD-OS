# Tasks — AIPD-OS v5.5 真实闭环、发布可信度与用户体验收口版

> 原则：只做真实代码/测试/CI 修复；外部依赖诚实标 external_dependency/HOLD；fake 只作 contract-test；最终判定依据证据。
> 收尾：全部任务完成后，在最终 HEAD 上重新生成 audit/RELEASE_MANIFEST/SBOM/eval/release，运行全量与 CI 等价检查，提交并推送 origin/main，打 tag。

## Task 1: P0-1 修复 CI 与发布可信度
- [ ] 修正 RELEASE_MANIFEST 生成时序：新增/调整脚本，确保最终代码提交后再刷新 manifest，杜绝“清单哈希与磁盘不一致”。
- [ ] 新增真实集成测试（标记 `integration`），使 CI Integration job 不再空转；或用真实端到端测试填充该 job。
- [ ] 升级 Actions 版本（setup-python@v4→v5 等），消除 Node 20 弃用警告。
- [ ] 增加发布门：仅当必要 job 全部成功才生成正式发布物；处理 dependency-audit 的 CVE（升级/替换或记录 CVE+范围+缓解+复审日期）。
- 验证：干净 clone 后各 CI job（unit/integration/schema/maturity/secret/dependency/license/package/audit/skill）本地等价复现全绿。

## Task 2: P0-2 统一版本与文档
- [ ] 全仓版本统一为 5.5.0：pyproject、`src/aipd_os/__init__.py`、`state/__init__.py`、README、CHANGELOG、QUICKSTART、SKILL、RELEASE_MANIFEST、SBOM、eval report、capability matrix、repository snapshot。
- [ ] 新增 `aipd doctor`（版本/依赖/配置/外部能力/数据库/对象存储/权限）与 `aipd version --verbose`（包版本/Git HEAD/构建时间/矩阵版本/发布清单哈希）。
- [ ] 修复 QUICKSTART 失效命令与版本示例；所有示例命令在干净环境实际运行。
- [ ] 增加 Git tag 与 GitHub Release 发布流程脚本/文档；提供 5 分钟真实入门项目。
- 验证：`aipd doctor`、`aipd version --verbose` 输出正确；版本一致性测试通过。

## Task 3: P0-3 修复手册视觉验收漏洞
- [ ] 修正 `visual_audit/auditor.py` 顶层 passed 逻辑：`requiring_vision=true` 时顶层必须 HOLD/not_verified，绝不 passed。
- [ ] 将 VisualAuditor 与 GoldenGapEvaluator 接入 manual release gate。
- [ ] 手册门同时校验：页面结构/参数真实性/中文/结构一致/人物一致/模块一致/CMF/相机/光线/禁止旧图拼版/黄金样本差异。
- [ ] 补回归测试：视觉后端缺失时断言不能通过。
- 验证：`tests/test_visual_audit.py`（或新增）断言无视觉后端时 passed=False 且顶层 not_verified。

## Task 4: P1-1 Execution Router 与 Supervisor 真实闭环
- [x] 实现真实进度事件、心跳、执行超时、用户取消、可恢复 checkpoint、in-flight 中断恢复。
- [x] 记录实际 duration/token/cost/工具调用；产物存在性/格式/哈希/语义验证；写回 Product Truth 与 Evidence Register。
- [x] stale 产物影响传播；有界自动返工状态机；防无限循环与重复生成。
- [x] 失败时给普通用户明确说明（失败在哪/已保存什么/下一步）；能力地板校验真实 maturity ceiling。
- 验证：新增执行链端到端测试（进度/取消/超时/恢复/写回/返工）。`tests/test_execution_closure.py` 16 项通过；`test_execution_closure.py`+`test_execution_router.py`+`test_supervisor_execution.py`+`test_decision_policy.py`+`test_adapters.py` 共 36 项通过。

## Task 5: P1-2 研究链真实实现
- [ ] 用户附件摄取与安全净化；摘要/全文区分；可获取时下载解析全文。
- [ ] 标准法规/专利/竞品检索接口契约 + 本地测试服务；统一引用；来源/时间/可信度/假设/冲突管理。
- [ ] 写回 Product Truth 与 Evidence Register；证据过期自动标记受影响事实/制品；检索失败保持 not_verified。
- 验证：研究链测试覆盖摄取/净化/全文/引用/过期/失败未验证。

## Task 6: P1-3 连续附件手册链（可替换 ImageGen Provider）
- [x] 定义可替换 Image Generation Provider 接口；前批页面以真实图片字节/后端文件对象传入下一批（非路径字符串）。（`src/aipd_os/imggen/providers.py`）
- [x] 记录请求 ID/模型版本/种子/提示词/附件哈希/生成参数/成本/耗时/返回工件哈希；建立 Anchor Registry 与 Visual Bible。（`providers.py` / `registry.py`）
- [x] 正文主要来自 Product Truth 与内容模型；支持只重建责任页；重建后只重跑受影响页与门；用户预览前后差异并批准。（`scripts/manual_chain.py`）
- [x] 无真实后端时生成外部任务包并 HOLD。
- 验证：`tests/test_imggen_chain.py` 11 项通过；`tests/test_manual_chain_e2e.py` 通过（顶层诚实 HOLD 断言已与 P0-3 诚实门一致）。

## Task 7: P1-4 CAD 能力按成熟度真实实现
- [ ] 保留 C0/C1 faceted（≤C1）；实现可替换 CAD 后端适配器契约 + 本地测试服务。
- [ ] C2：真实可编辑参数化 B-Rep（可选 CadQuery 依赖）；未安装内核时 C2 标 external_dependency，绝不越级。
- [ ] C3–C7 依次到真实证据才标 fully；暂未实现标 external_dependency/not_implemented。
- [ ] 实现 CAD 变更到规格/BOM/手册/验证计划的回写链路。
- 验证：maturity-consistency 测试通过；无“faceted 可达 ≥C2”冲突；C2 仅在真实内核可用时标 fully。

## Task 8: P1-5 跨会话恢复
- [ ] 手册批次/附件/Visual Bible/生成任务/返工计划移入统一状态服务/对象存储；DB+对象存储+附件索引一起备份恢复。
- [ ] 恢复摘要含 Product Truth/Evidence/未解决决策/已解决决策/CAD-BOM 修订/附件链/外部等待/失败任务/下一步；多项目按最近活动识别。
- [ ] 恢复后自动继续安全工作；不可逆/安全/成本/发布决策仍需显式批准。
- 验证：“崩溃—重启—恢复—继续”真实端到端测试。

## Task 9: P1-6 供应链与物理验证
- [x] 可插拔邮件连接器（SMTP/IMAP 契约 + 本地测试服务）：RFQ 草稿/批准/发送/Message-ID 线程追踪/收件箱读取/回复关联/附件下载/幂等/重试。
- [x] CSV/JSON/XLSX/PDF 报价解析；供应商/报价/资质/认证持久化；证书过期提醒；EVT/DVT/PVT 导入；失败根因/纠正/回归；物理结果写回。
- [x] 真实报价/制造/测试/认证缺失时保持 HOLD。
- 验证：邮件连接器本地测试；物理环节缺失时状态 HOLD/not_verified。`tests/test_supply_chain.py` 41 项通过。

## Task 10: P1-7 重构 Evals
- [ ] fake provider 改名为 contract-test / deterministic-fixture；其结果不汇入“模型行为通过率”。
- [ ] 报告区分 provider/endpoint/model/model version/是否真实网络调用/prompt hash/token/cost/latency/retry/grader/trace。
- [ ] 真实模型 smoke/integration job（有凭据时运行）；无凭据标 external/skipped。
- [ ] 纯关键词评分升级为结构化输出契约/确定性状态断言/工件断言/DB 状态断言/judge rubric；验证真实副作用；重复试验/稳定性/回归/失败轨迹。
- 验证：eval 报告明确区分 fake fixture 与真实模型；fake 17/17 不描述为真实模型通过率。

## Task 11: P2 所有者 UX
- [x] 自然语言操作闭环：意图解析→影响分析→受影响制品→预计成本/时间→可撤销预览→批准→自动返工→自动验收→更新摘要；同义词/上下文指代/多条件/纠错；无法确定只问一个最关键问题。（`experience/intent_engine.py` / `impact_analysis.py` / `operations.py`）
- [x] 统一 Dashboard/CLI：默认只展示目标/执行/完成/缺口/风险/外部等待/唯一决策/里程碑/变化/可撤销操作；内部标识隐藏；`--json` 与 human 分离；紧凑移动端；进度事件；可取消；失败恢复命令；制品差异；成本耗时变化；无障碍与窄屏测试。（`experience/owner_dashboard.py`，CLI：operate/dashboard/onboard/reset/recover）
- [x] 首次使用引导：一句话建项→立即出第一份结果→展示能力与需外部配置项→引导配置 Provider→示例项目→恢复/重置→CI 实际运行示例命令。（`experience/onboarding.py`）
- 验证：`tests/test_experience.py` 扩展通过；自然语言审批端到端；引导命令可运行。`tests/test_owner_ux.py` 26 项通过；experience+cli+related 58 项通过；`-m "not integration"` 373 通过（4 项为既有版本/manifest 审计失败，属 Task 12 P0-4 范围）；CLI onboard/dashboard/operate 端到端可运行。

## Task 12: P0-4 最终 HEAD 审计与发布
- [ ] 在最终代码提交后重新生成 repository_snapshot / capability_matrix.json|md / RELEASE_MANIFEST / SBOM / eval reports / release package；记录最终 HEAD；工作区 clean；逐文件哈希一致。
- [ ] 运行全量 pytest、集成、Schema、成熟度、secret、pip-audit、license、package、version-truth。
- [ ] 打 Git tag（v5.5.0）并（可行时）创建 GitHub Release；输出签名/哈希/SBOM。
- [ ] 输出最终发布判断 READY/CONDITIONAL/HOLD 及证据。
- 验证：最终 HEAD 上的所有检查全绿；manifest 哈希与磁盘一致；工作区 clean。

# Task Dependencies
- Task 1（P0-1 CI）与 Task 2（P0-2 版本）为 P0 先行，可并行。
- Task 3（P0-3）独立。
- Task 4–10（P1）相互独立，可并行；Task 6 依赖 P0-3 修复。
- Task 11（P2）依赖 Task 4/6 的闭环。
- Task 12（P0-4）依赖全部前序任务，最后执行。