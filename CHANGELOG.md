# Changelog

## 5.1.0 — 2026-08-06

- **可再生成的版本真实性审计**：`scripts/audit_repo.py` + `docs/audit/`，读取 git 提交、pyproject 版本、Release Manifest 哈希、CI job 与遗留 CAD 冲突，输出机器可读 JSON 报告；
- **统一执行记录字段集**（`unified_record`）：`provider_version` / `token_usage` / `started_at` / `completed_at` / `error_type` / `evidence_ids` / `artifact_ids` 别名，`fallback_from` 降级来源，`project_id` / `capability` / `retry_parent` 持久化；
- **CAD 成熟度术语扫描扩展**至 docs/scripts/templates/examples，并加入 faceted 过度声称防护；
- **生产发布门禁升级为证据门禁**（`evidence_checks`）：`gdt_covers_ctq`、`ctq_has_inspection`、`drawing_cad_same_revision` 等；
- **WBX-1 黄金样本视觉落差评估**（`visual_audit/golden.py`）；
- **供应链与验证执行器**（`supply_chain/`）：quotes / suppliers / lab / analysis，并升级 supplier / mail_rfq / evt_dvt_pvt 适配器；
- **行为评估扩展至 15 项**（`evals.json` v1.2）；
- **16 个一键命令**（init / intake / resume / status / run / decide / manual plan / manual generate / cad preflight / cad build / industrialize / validate / release check / test / eval / package），支持 `--json` 模式；
- **py.typed**：类型标注标记；
- **提示注入隔离增强**：高风险动作需人工批准。

## 5.0.0 — 2026-08-05

- 新增统一执行层（Execution Router / Tool Adapters），按能力选择适配器、重试与降级切换、持久化执行记录与证据；
- 统一 CAD C0–C7 成熟度推进，配合 maturity / capability / production release 门禁；
- 新增手册链自主执行（连续附件手册 + 独立视觉审计）；
- 状态服务生产化：多租户授权、迁移、备份、检查点、追加式审计、健康检查、对象存储与静态加密；
- 新增 Owner Experience 层：决策卡片、所有者自然语言视图与一键命令；
- 新增 Evals Runner：生命周期门禁与质量回归评估；
- 新增安全：提示注入隔离、敏感数据打码与显式权限、确定性 SBOM、发布物签名；
- 工程化：CI 流水线、`SECURITY.md` / `THREAT_MODEL.md` / `SBOM.md` / `RELEASE_SIGNING.md` / `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md` / `QUICKSTART.md` / `docs/architecture.md`。

## 4.0.0 — 2026-08-05

- 从“产品手册+CAD主管”升级为AI全链路产品开发与交付主管；
- 新增S0—S8生命周期、工作队列、能力注册、决策策略和声明门；
- 将用户成功提示词轨迹与合格手册纳入黄金样本；
- 保留并统一编排理论研究、连续附件手册、CAD、工业化和验证子系统；
- 强制变更传播与证据化成熟度声明。
