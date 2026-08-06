# AIPD-OS 版本升级与迁移指南

本文档说明如何把已存在的 AIPD-OS 状态库升级到新版本，以及如何备份、回滚和恢复，
保证停机时间最小、数据不丢失、可回退。

> 当前版本：`5.6.0`。状态库为 SQLite，schema 由 `aipd_os.state.migrations` 管理，
> 备份由 `aipd_os.state.backup.BackupManager` 负责。

## 升级前：备份

任何升级前都应先做一次备份，以便失败时可回退。

```python
from aipd_os.state.backup import BackupManager
bm = BackupManager("path/to/state.db", backup_dir="path/to/backups")
backup_dir = bm.create_backup("path/to/state.db")
# 打印返回的备份目录路径，恢复/回退时使用
print(backup_dir)
```

备份目录包含数据库文件副本 + `manifest.json`（内含 sha256 校验和）。恢复前会校验和一致，
损坏备份会被拒绝恢复。

## 升级步骤

1. 停止旧进程（避免写库期间迁移）。
2. （可选）备份（见上）。
3. 升级安装 AIPD-OS 到新版本。
4. 运行迁移，把 schema 推进到最新：

   ```python
   from aipd_os.state import migrations
   print(migrations.migrate("path/to/state.db"))
   ```

   迁移是**幂等**的：重复执行不会重复应用已记录版本（见 `schema_migrations` 表）。

## 检查当前版本

```bash
python -c "from aipd_os.state import migrations; print(migrations.current_version('path/to/state.db'))"
```

## 回滚（降级）

如新版本有问题，可回滚到目标 schema 版本（会执行每个版本的 `down` 步骤）：

```bash
python -c "from aipd_os.state import migrations; print(migrations.rollback('path/to/state.db', target=0))"
```

> 回滚是破坏性的（会删除对应版本的业务表）。更稳妥的方式是直接从备份恢复（见下）。

## 从备份恢复

```bash
# 命令行：恢复并打印会话续接摘要
aipd resume --db path/to/restored.db --backup path/to/backups/backup_<ts>
# 或从备份恢复数据库
aipd recover --backup path/to/backups/backup_<ts>

# Python
python -c "from aipd_os.state.backup import BackupManager; \
bm=BackupManager('path/to/restored.db'); \
print(bm.restore_backup('path/to/backups/backup_<ts>'))"
```

恢复时会校验 sha256，不一致则拒绝，防止用损坏备份覆盖现有数据。

## 保留策略

备份支持按保留天数清理过期备份：

```python
from aipd_os.state.backup import BackupManager
bm = BackupManager("path/to/state.db", backup_dir="path/to/backups")
removed = bm.retention_prune(retention_days=90)  # 删除 90 天前的备份
```

## 兼容性

- 旧版单项目库（v4 `aipd_store` schema）通过 `migrations/v4_to_v5.py` 迁移到多租户
  多项目 schema，迁移后旧数据（项目/事实/证据/决策/制品/风险/依赖/变更/门禁）均保留。
- 迁移后的库可继续做备份/恢复，恢复后的副本仍可正常执行幂等迁移。

## 新版本注意事项（v5.6）

- 数据库写入使用乐观锁（`version_no`），敏感字段（供应商报价、联系人、实验数据、
  API key 等）透明加密存储。
- 结构化日志默认关闭匿名遥测（`AIPD_TELEMETRY_ENABLED` 未设置时不发送任何数据）。
- 凭据通过 `aipd_os.security.secrets` 注册环境变量引用，日志输出自动脱敏。