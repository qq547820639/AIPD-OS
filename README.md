# AIPD Orchestrator v5.3.0

AI全链路产品开发与交付主管：一个对话入口，自主推进理论基础、产品定义、连续附件产品手册、工程CAD、工业化、供应链、EVT/DVT/PVT和生产发布。

## v5.3新增

- **风险 RYG / 外部等待所有者视图**：Supervisor 提供风险红黄绿（RYG）分级与外部等待（blocked_external）的所有者视图，等待外部输入期间继续其他独立工作；
- **确定性可信度 / 人体测量 / 认证模块**：credibility、anthropometry、certification 三个确定性模块，事实与认知一律可追溯、不虚构；
- **视觉审计诚实护栏**：视觉落差评估拒绝为“看起来像”背书，防止视觉意图覆盖安全；
- **命令覆盖一致性测试**：`tests/test_command_coverage.py` 校验声明 / 注册 / 测试三向不变量；
- **SKILL.md v5.3 刷新**：17 个一键命令按工作流分组声明，专业细节集中到 `references/`；
- **17 个一键命令**（`aipd <cmd>`）：`init` / `intake` / `resume` / `status` / `run` / `decide` / `manual plan` / `manual generate` / `cad preflight` / `cad build` / `industrialize` / `validate` / `audit` / `release check` / `test` / `eval` / `package`。

## v5.2新增

- **能力矩阵审计产物**：`aipd audit --repo . --out docs/audit` 生成 `repository_snapshot.json` / `capability_matrix.json` / `capability_matrix.md`，对六大域全部能力按 7 类（fully_implemented / partially_implemented / protocol_only / template_only / external_dependency / not_implemented / not_verifiable）分类并给出证据字段；
- **真实/可插拔模型评测**：`EnvCompletionProvider` 接入 OpenAI 兼容 HTTP 端点（`AIPD_EVAL_MODEL_ENDPOINT/KEY/VERSION`）真实调用；未配置时诚实标记 `external_dependency`，绝不返回伪造输出；
- **干净环境安装修复**：`mcp` 移出 `[full]` 至独立 `server-mcp` extra，Python 3.9 下 `pip install -e ".[full,dev]"` 可成功；CI 安装完整依赖。

## v5.1新增

- **版本真实性审计**：`scripts/audit_repo.py` 生成可再生成的审计报告（`docs/audit/`），校验 git 提交、pyproject 版本、`RELEASE_MANIFEST.json` 逐文件哈希、CI job 与遗留 CAD 冲突；
- **供应链与验证执行器**（`supply_chain/`）：报价、供应商、实验室与分析，配套升级 supplier / mail_rfq / evt_dvt_pvt 适配器；
- **生产发布证据门禁**（`evidence_checks`）：`gdt_covers_ctq`、`ctq_has_inspection`、`drawing_cad_same_revision` 等；
- **WBX-1 黄金样本视觉落差评估**（`visual_audit/golden.py`）；
- **行为评估扩展至 15 项**（`evals.json` v1.2）；
- **16 个一键命令**（`init` / `intake` / `resume` / `status` / `run` / `decide` / `manual plan` / `manual generate` / `cad preflight` / `cad build` / `industrialize` / `validate` / `release check` / `test` / `eval` / `package`），支持 `--json` 模式；
- **提示注入隔离增强**：高风险动作需人工批准。见 `SECURITY.md` / `THREAT_MODEL.md`。

## v5.0新增

- **统一执行层（Execution Router / Tool Adapters）**：按能力选择工具适配器，重试与降级切换，持久化执行记录与证据；
- **CAD C0–C7 统一**：统一成熟度推进（设计意图→生产放行），配合 maturity gate / capability gate / production release gate；
- **手册链自主执行**：连续附件产品手册 + 独立视觉审计；
- **状态服务生产化**：多租户授权、迁移、备份、检查点、追加式审计、健康检查、对象存储、静态加密；
- **Owner Experience 层**：决策卡片与所有者自然语言视图，一键命令（init-project / restore-project / run-supervisor / project-summary / submit-decision / run-manual-chain / run-cad-chain / run-tests / run-evals / build-release）；
- **Evals Runner**：生命周期门禁与质量回归评估；
- **安全**：提示注入隔离（外部内容始终作为数据）、敏感数据打码与显式权限、确定性 SBOM、发布物签名。见 `SECURITY.md` / `THREAT_MODEL.md` / `SBOM.md` / `RELEASE_SIGNING.md`；
- **工程化**：CI（单元/集成/schema/secret 扫描）、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`。

## v4.0新增

- 主管工作队列与生命周期状态机；
- 统一事实、证据、资产谱系、能力注册和成熟度声明；
- 决策策略：只在方向、价值、安全、不可逆投入和放行时询问；
- v3手册链与CAD链作为专业子系统保留；
- 工具能力地板和声明门；
- 后段变更自动回写手册、规格、BOM和CAD；
- 用户成功提示词与手册作为黄金执行轨迹。

理论文档：`references/AIPD-OS-v4.0.docx`。

运行自测：
```bash
python scripts/selftest_v4.py
```
