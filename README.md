# AIPD Orchestrator v5.0.0

AI全链路产品开发与交付主管：一个对话入口，自主推进理论基础、产品定义、连续附件产品手册、工程CAD、工业化、供应链、EVT/DVT/PVT和生产发布。

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
