# 项目边界：AIPD-OS 与 Vencertia 的关系裁决

> 状态：Accepted（v5.10）
> 日期：2026-08-23
> 依据：两仓全量代码审查（9 个并行模块审查 + 跨仓实证比对，全部结论附 file:line 证据并做运行复核）
> 对偶文件：Vencertia 仓 `docs/adr/ADR-015-sister-project-aipd-os.md`

---

## 问题

AIPD-OS 与 Vencertia-Intelligence-Lab（github.com/qq547820639/Vencertia-Intelligence-Lab）由同一作者在同一周期创建，共享"诚实性工程"哲学与相似词汇表。是否应合并为一个项目？是否应整体改造为 SKILL 形态？

## 实证核查结论

1. **零耦合现状**：两仓之间没有任何 import、引用或文档提及。
2. **零代码重复**：全对全 shingle 指纹比对无复制粘贴代码；同名文件相似度 <0.25。
3. **概念同名异物**：decision / evidence / maturity / skill 在两仓语义均不同（见词汇表）。
4. **硬性合并障碍**：
   - Python 版本窗不相容：AIPD `>=3.9,<3.13`（3.9/3.10 是 CI 验证过的契约）vs Vencertia `>=3.11`；
   - 依赖哲学对立：AIPD 的架构原则是"仅 jsonschema、其余全标准库"（LLM 客户端用 urllib 自实现）；Vencertia 域层全量建筑在 pydantic/FastAPI/httpx 上。合并必破 AIPD 的零依赖契约；
   - 存储哲学相反：AIPD 为 21+ 张专用表富关系模型（多租户 + 版本化迁移 + SHA256 冻结 v1），Vencertia 为泛型 entities + event_log 实体存储。共存将产生 decisions/evidence 双真相源；
   - 测试套件物理冲突：同名 `tests/test_cli.py` + 本仓 `tests/__init__.py` 包结构，合并即 pytest import mismatch；Vencertia conftest 顶层依赖 fastapi，本仓零依赖测试环境无法收集。
5. **SKILL 形态核查**：本仓发布链与 SKILL.md 深度耦合（`check_skill_package.py` 强制恰好一个 SKILL.md、`skill_quality_audit.py` 命令覆盖率审计入 CI、`test_command_coverage.py` 解析命令清单、`runtime_preflight.py` 引为架构文件）——SKILL.md 是发布链的校验组件，不能简单删除。Vencertia 是独立产品（FastAPI Web 决策工作台），其引擎核理论可 skill 化但会移除产品面，不予实施。

## 决策矩阵（weighted-scoring，权重 + 评分 1-5）

| 维度 | 权重 | 合并为一仓 | 整体改造为 SKILL | 维持独立+边界规范化 |
|---|---|---|---|---|
| 职责边界清晰度 | 20% | 2 | 4 | 5 |
| 构建发布流程兼容性 | 15% | 2 | 3 | 4 |
| 依赖关系与部署灵活性 | 15% | 2 | 3 | 5 |
| 长期维护成本 | 15% | 2 | 3 | 4 |
| 功能重叠消除收益 | 10% | 3 | 2 | 3 |
| 向后兼容与迁移风险 | 15% | 2 | 2 | 5 |
| 用户价值与调用便利 | 10% | 3 | 3 | 4 |
| **加权总分** | | **2.20** | **2.95** | **4.40** |

敏感性分析：领先 1.45 分（>0.3 阈值），权重 ±10% 波动后排名不变，结论稳健。

## 裁决

**维持独立项目。** 边界规则：

1. **AIPD-OS 拥有**：产品开发执行域——产品定义管线（Idea→Insight→Requirement→Feature→Product Truth）、工程成熟度阶梯（C0–C7）、CAD/BOM/供应链/成本核算、制造准备、签名发布。
2. **Vencertia 拥有**：决策质量域——Claim/Evidence/Belief 贝叶斯管线、预测登记与结算、校准统计（Brier/ECE）、决策台账与复盘。
3. **禁止跨仓代码依赖**：不得互相 import、不得共享源码、不得读取对方数据库。
4. **互操作仅允许文件级显式契约**：未来如需联动（例如本仓 idea 域的 claims 导出到 Vencertia 做校准跟踪），必须通过版本化 JSON 交换格式，并先修订本文件与对偶 ADR。当前**有意不建桥**：本仓 decision 是"Owner 审批工作流条目"，Vencertia PredictionEntry 是"概率预测登记"，语义不同构，强行映射属于伪造集成，违反诚实性原则。

## 词汇消歧表（同名异物）

| 词汇 | 在 AIPD-OS 中 | 在 Vencertia 中 |
|---|---|---|
| decision | Owner 审批队列条目（阻塞工作项，人工裁定） | 效用优化问题对象 + 预测登记（引擎推进） |
| evidence | 文献登记（kind/title/url/quality/summary） | 带权威分级/时效/去重的贝叶斯证据 |
| maturity | C0–C7 工程成熟度阶梯（另有 Idea I0–I3） | 无此概念（最接近的是 calibration 统计校准） |
| skill | Agent Skill 规范形态（本仓即一个 SKILL 包） | V11 提示词资产 Protocol（无写权） |
| audit/event | 变更审计 audit_log（before/after 双写） | 领域事件溯源 event_log |

## 后果与重新评估

- 正向：零依赖契约、版本线（v5.x）、签名发布体系、pytest 套件各自独立完整。
- 代价：4 组功能等价实现平行存在（OpenAI 客户端 urllib vs httpx、指标、mock provider、发布打包），约 500 行，接受。
- 重新评估触发条件：出现第三个同哲学项目且产生真实重复维护负担；两仓间形成真实数据联动需求（按规则 4 建契约）；任一仓部署形态根本变化。

---

## 增补（2026-08-23，同日修订）：合成层 IdeaToLaunch

所有者决策：在两仓之上增设**旗舰合成技能** [IdeaToLaunch](https://github.com/qq547820639/IdeaToLaunch)（模型驱动的 SKILL，零代码），作为**唯一 agent-facing 入口**：它持有"想法 → 决策验证 → 产品落地 → 复盘回流"全链路方法论，本仓与 Vencertia 降级为其执行后端。

本仓配套调整：**根 `SKILL.md` 降级为废弃存根**——description 标注勿加载并指向 IdeaToLaunch，方法论章节移除（唯一维护点收敛到 IdeaToLaunch），仅保留命令清单以维持发布链一致性审计（`skill_quality_audit.py` / `test_command_coverage.py` 依赖该清单）。产品形态（CLI/服务）不受影响。

该合成层与本裁决**兼容而非冲突**：

- 它不建立代码依赖、不读取两仓数据库，仅通过规则 4 允许的文件级契约（IdeaToLaunch 仓 `schemas/handoff_v1.json`）交互——两仓独立性不变；
- 它把**编排**（意图理解、流程组织、接力顺序）交给模型，而本仓的真相核（state/migrations/gate/snapshot/commit/签名发布）保持确定性，不随模型漂移；
- 编排层的"僵化规则降级路线"（S0–S8 阶段机模板化、决策卡片影响档位模型化、硬编码经验文本退役等）记录在 IdeaToLaunch 仓 `docs/architecture.md`，作为后续独立 PR 执行，每项须附回归测试。
