# AIPD-OS 全量基线重审计报告（LATEST HEAD）

> 本报告为 **v5.7 Foundation Closure 的事实基线**。所有命令均在真实环境中执行，
> 输出为真实运行结果；未执行的步骤明确标注 `NOT_RUN` + 原因，绝无虚构 PASS。
> 本审计**只记录事实，不做任何代码修复**；审计期间未改动任何 tracked 文件。

---

## 0. 审计元信息（绑定字段）

| 字段 | 值 |
| --- | --- |
| `source_commit` | `9ded1e85ce38fdf49753259eb49b2f4c15c2cff2`（HEAD，main，working tree clean） |
| `package_version` | `5.6.0`（pyproject.toml `[project].version`） |
| `python_version` | `3.9.6`（仓库 `.venv`，符合 `requires-python = ">=3.9"`） |
| `cadquery_version` | `2.5.2`（`.venv` 内已安装，真实 B-Rep 内核可用） |
| `test_collected` | **601** |
| `test_passed` | **597**（全量回归 `-m "not model_eval"`） |
| `test_failed` | **0** |
| `test_skipped` | **2**（均为 `tests/test_mail_protocol.py`，AIPD_MAILPIT_* 未配置 → HOLD 断言） |
| `test_deselected` | **2**（`model_eval` 标记：`tests/test_evals_runner.py`、`tests/test_model_evals_honesty.py`、`tests/test_evals_ci.py` 中标记项） |
| `generated_at` | `2026-08-12T02:16:49+0800` |
| 运行环境 | macOS（Darwin），repo `.venv`（Python 3.9.6）；未使用 managed python 3.13.12（按指示：仓库有 `.venv` 且 requires-python ≥3.9，采用仓库环境） |

---

## 1. 测试收集

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest --collect-only -q tests
```

真实输出（尾行）：
```
601 tests collected in 6.93s
```

**collected = 601**（含 2 个 `model_eval` 标记项；现有 `docs/audit/pytest-report.json` 记录为 522，见 §8 陈旧性分析）。

---

## 2. 全量回归

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -m "not model_eval" -q
```

真实输出（尾行）：
```
597 passed, 2 skipped, 2 deselected, 351 warnings in 241.60s (0:04:01)
```

| 指标 | 数值 |
| --- | --- |
| passed | **597** |
| failed | **0** |
| skipped | **2**（`test_mail_protocol.py:202/240`，`AIPD_MAILPIT_* 未配置，走 HOLD 断言`） |
| deselected | **2**（model_eval） |
| duration | 241.60s |
| 一致性校验 | 597 + 2 + 2 = 601 = collected ✓ |

说明：351 条 warning 主要来自 cadquery/pyparsing 的 `PyparsingDeprecationWarning`（第三方库告警，非本仓库代码），以及少量本仓库 `scripts/release_evidence.py:198` 的 `jsonschema.__version__` 弃用告警。

---

## 3. 集成测试

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -m integration -q
```

真实输出（尾行）：
```
15 passed, 2 skipped, 584 deselected, 24 warnings in 8.74s
```

**15 passed / 0 failed / 2 skipped**（同 mail_protocol HOLD）。

---

## 4. 集成冒烟

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_integration_smoke.py -q
```

真实输出：`4 passed in 4.21s`

---

## 5. 手工链 E2E

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_manual_chain_e2e.py -q
```

真实输出：`1 passed in 7.58s`

---

## 6. 生产发布门禁

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_production_release_gate.py -q
```

真实输出：`10 passed in 4.95s`

---

## 7. CAD 套件（真实 CadQuery 内核）

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_cad_golden_loop.py tests/test_cad_contract_unify.py -q
```

环境已安装 cadquery 2.5.2（`python -c "import cadquery; print(cadquery.__version__)"` → `2.5.2`），因此 **两条 CAD 套件均真实执行**，无跳过。

真实输出（尾行）：`20 passed, 212 warnings in 17.14s`

---

## 8. 静态检查

### 8.1 ruff

```bash
.venv/bin/ruff check .
```

真实输出：
```
Found 3090 errors.
[*] 311 fixable with the `--fix` option (1662 hidden fixes can be enabled with the `--unsafe-fixes` option).
```
**exit code = 1（FAIL）**

规则分布（前 10）：
| 规则 | 数量 | 说明 |
| --- | --- | --- |
| UP006 | 1109 | `typing.List/Dict` → 内建泛型（存量风格） |
| UP045 | 507 | 风格现代化 |
| E501 | 498 | 行超长（>100） |
| E702 | 303 | 语句同行分号 |
| UP035 | 187 | typing 导入现代化 |
| E701 | 104 | 单行复合语句 |
| W292 | 99 | 缺尾换行 |
| F401 | 76 | 未使用 import |
| I001 | 72 | import 排序 |
| 其他 | ~135 | E401/UP007/UP037/SIM105/UP015/F841 等 |

Top 文件：`scripts/manual_chain.py`(126)、`src/aipd_os/state/db.py`(124)、`scripts/aipd_state.py`(114) 等。

对照：v5.6 基线审计（BASELINE_REPORT.md §基线）记录 ruff **FAIL — 3298 errors**。当前 HEAD 为 **3090 errors**，存量欠债略降（-208），但**仍为 FAIL**。

### 8.2 mypy

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m mypy
```

（mypy 已配置于 pyproject.toml：`python_version="3.9"`, `files=["src","tests"]`，命令有效。）

真实输出（尾行）：
```
Found 138 errors in 53 files (checked 212 source files)
```
**exit code = 1（FAIL）**

样例错误（与基线报告一致的模式）：
- `src/aipd_os/evals_runner/golden_projects.py:193` Path/str 类型冲突（`Incompatible types in assignment ... Path vs str`）
- `tests/test_golden_projects_e2e.py:426/427/504/556/557/590/591/628` Optional 索引 / None union-attr / 变量类型覆盖

对照：v5.6 基线为 mypy **140 errors in 51 files（checked 199）**；当前 **138 errors in 53 files（checked 212）**——错误数略降，但文件范围扩大，仍为 FAIL。

### 8.3 门禁属性

`.github/workflows/ci.yml` 中 **未将 ruff/mypy 作为 CI 门禁**（CI 门禁：unit、integration、schema-validation、maturity-consistency、cad-golden-loop、secret-scan、dependency-audit、license-scan、package-build、audit）。BASELINE_REPORT.md 已明确记录：「静态质量：存量欠债大（ruff 3298 / mypy 140），但均非 CI 门禁，不阻塞现有发布流程」。→ 本次审计维持该判定，但 v5.7 若要收紧质量门禁，此为最大欠债项。

---

## 9. 仓库健康检查（hygiene）

### 9.1 tracked 缓存/pyc 文件（步骤 12）

```bash
git ls-files | grep -E '(^|/)(__pycache__/|\.pytest_cache/|\.mypy_cache/|\.ruff_cache/|.*\.pyc$)'
```

**命中行数 = 0**（预期 0 ✓）。测试运行使用 `PYTHONDONTWRITEBYTECODE=1`，审计结束后 `git status --short` 为空，working tree 无任何污染。

### 9.2 BUNDLE_MANIFEST.json 违禁条目（步骤 13）

```bash
grep -E '\.pytest_cache|__pycache__|\.pyc|\.dist-info|\.venv' BUNDLE_MANIFEST.json
```

⚠️ **命中 4679 行**（grep 计数）。结构化分析（entries 数组共 **5271** 项）：
- `.venv*`：**4670** 项（`.venv-ci/` 等）
- `.pytest_cache`：**9** 项（`.pytest_cache/`、`.pytest_cache/.gitignore`、`.pytest_cache/CACHEDIR.TAG`、`.pytest_cache/README.md`、`.pytest_cache/v/`、`v/cache/lastfailed`、`v/cache/nodeids`、`v/cache/stepwise` 等）
- 合法内容：**592** 项

**判定：BUNDLE_MANIFEST.json 违反预期（预期 0 违禁条目），4679/5271（88.8%）条目为缓存/虚拟环境垃圾。** 该 manifest 声称的 `bundle_sha256`/`entry_count` 与「干净发布物」语义不符，是 v5.7 需要处理的事实项（详见 §10.8）。

### 9.3 pytest-report.json 陈旧性（步骤 14）

现有 `docs/audit/pytest-report.json`：
- `created` = `1786013082.160227` → `2026-08-06T18:44:42`（v5.6 测试提交 d58ab14 前后）
- `summary`：passed 518 / skipped 2 / total 520 / collected 522 / deselected 2
- `environment` = `{}`（不含 commit 信息，无法自证绑定 commit）
- `exitcode` = 0

当前 HEAD 实测：collected **601**、passed **597**、skipped 2、deselected 2。

**判定：pytest-report.json 已陈旧**——落后当前 HEAD 3 个 commit（v5.6.0 tag d58ab14 → 2541be8 → bde17b5 → 9ded1e8），收集数 522 → 601（+79），且报告本身未绑定 source_commit。v5.7 需重新生成并绑定 commit。

### 9.4 审计产物时间线（steps 10/11 交叉验证）

- `scripts/audit_repo.py`：**exit 0**。`release_manifest_verification` hash_matches 384/384（0 mismatch）；`source_manifest_verification` source_commit=`2541be86444ad10a7f8a75c28daa43b1c785b4bd`（**落后 HEAD 1 commit**），hash_matches 384/384。`untracked_or_generated` 仅列出 `.venv`/`build` 内生成物（非 tracked）。
- `scripts/capability_matrix.py --repo . --out docs/audit`：**exit 0**。latest_commit_sha=`9ded1e8…`，total_capabilities=70，fully=35 / partial=26 / external=9（与 v5.6 钉住值一致）。该命令会重写 `docs/audit/capability_matrix.{json,md}`、`repository_snapshot.json`（diff 仅 generated_at/latest_commit_sha 元数据差异）；审计完成后已 `git checkout --` 还原，**未留下任何改动**。

---

## 10. 审计发现（提示词问题逐项初步验证）

> 以下为代码静态初验（非修复）。重点：测试数字与 hygiene 事实已在上文给出；此处定位问题代码与证据。

### 10.1 P0 — MCP Transport Authentication（MCP 传输存在但**完全未认证**）

**证据（修正版）**：MCP 适配器位于 **`state_service/mcp_server.py`**（仓库根目录，非 `src/`；tracked，含于 BUNDLE_MANIFEST，共 4 处提及）。该文件为 FastMCP 薄适配层（118 行），**无任何认证/授权逻辑**：
- 工具函数（`init_project` / `project_summary` / `add_fact` / `propose_decision` / `resolve_decision` / `export_checkpoint`，`mcp_server.py:42-104`）**不含 user/token/bearer 参数**，直接以 `DEFAULT_TENANT` 调用 `StateService` 方法（`mcp_server.py:27,43` 等）；
- `StateService` 构造为 `require_strong_secret=True`（`mcp_server.py:37`，仅保证 secret 强度），但 MCP 路径调用服务方法时**不传 actor** → `_authorize(actor=None)` 直接跳过授权（`server.py:104-107`）；认证形同虚设；
- `DEFAULT_TENANT` 硬编码单一租户（`mcp_server.py:27`），无多租户语义。
- **测试覆盖为零**：`grep -rln "mcp_server\|state_service" tests/ scripts/` → **0 命中**（无任何测试引用该文件）。
- `grep -rn "import mcp\|from mcp" src/ tests/ scripts/` → 0 命中（`mcp` 库仅在 `state_service/requirements.txt` 与 pyproject `server-mcp` extra 声明），因此 `src/` 内确无 MCP 代码——但**不能**推导出「仓库无 MCP 传输」。

**对照**：内置 HTTP/JSON RPC 传输（`src/aipd_os/state/server.py:343-440`）**已认证**：`POST /rpc` 必须携带 `user+token`，否则 401（`server.py:371-408`）；认证 actor 强制覆盖客户端 `actor`（`_inject_actor`，`server.py:410-430`）；授权失败 403；免令牌仅 `PUBLIC_RPC_METHODS = {auth_login, auth_register}`（`server.py:35`）。test_auth.py 4 项 / test_authorization.py 13 项 / test_server_local.py 4 项全部通过。
**判定：P0 确认存在**。MCP 传输（`state_service/mcp_server.py`）未认证、未测试、单租户硬编码，任何 MCP 客户端可无凭证调用全部工具。v5.7 必须为 MCP 层补认证（token/actor 注入/授权），并新增测试（如 `tests/test_mcp_authorization.py`）。

### 10.2 P0 — Tenant Membership（匿名自助注册 + 跨租户授权）

**证据**：`src/aipd_os/state/server.py:114-123`
```python
def auth_register(self, user_id, tenant_id, username, password, project_id=None):
    self.db.ensure_default_tenant(tenant_id)          # 匿名可创建任意租户
    self.auth.register_user(user_id, tenant_id, username, password)
    if project_id is not None:
        self.auth.grant_access(user_id, tenant_id, project_id)  # 匿名可自授项目访问
```
- `auth_register` 属于 `PUBLIC_RPC_METHODS`（免令牌）；调用方**无需认证**即可：任意 `tenant_id` 注册（含创建新租户）、并在同一请求中给自己授予指定 `project_id` 的访问权。
- `db.py:337-343` `has_access` 只查 `user_access` 表，**不校验 `users.tenant_id` 与 `tenant_id` 一致**；`grant_access`（`db.py:330-335`）亦不校验被授权用户的归属租户。→ 用户 A（租户 T1）可被（或自助）持有租户 T2 的授权行。
- `grant_access(actor=None)` 跳过管理员校验（`server.py:134-139`）——HTTP 路径 actor 会被注入，但纯本地 API 路径 `actor=None` 视为系统调用，无身份边界。
**判定：问题存在**。租户成员资格是「授权行驱动」而非「用户归属租户驱动」，且匿名注册入口可自授访问。v5.7 应：注册需引导/邀请或至少校验租户存在与创建权限；`has_access`/`grant_access` 校验 `users.tenant_id` 归属；必要时收紧 `ensure_default_tenant` 的匿名创建。

### 10.3 P0 — Encryption Key（空密钥 fail-open → 明文落库）

**证据**：`src/aipd_os/state/db.py:283`
```python
if self._encryption_key and key in SENSITIVE_KEYS:
    return _json({"__encrypted__": True, "data": encrypt_secret(...)})
```
- `AIPDStateDB(db_path, encryption_key="")` 为默认；`StateService.__init__` 默认 `encryption_key=""`（`server.py:46`）；CLI 默认 `AIPD_ENCRYPTION_KEY` 空（`server.py:453`）。
- 空密钥时，`SENSITIVE_KEYS`（supplier_quote / contact / experiment_data / api_key / credential / secret / token 等）**以明文 JSON 落库**——DB 层为 **fail-open**（与 crypto.py 的 fail-closed 回退策略不一致：`crypto.py:55-58` 明确禁止非安全回退，但 DB 层空密钥直接跳过加密）。
- 解密侧：`db.py:292-295` 遇到 `__encrypted__` 但无 key 时报错（fail-closed），与写入侧语义不对称。
**判定：问题存在**。生产 server 模式若无 `AIPD_ENCRYPTION_KEY`，敏感字段明文存储，违反 at-rest 加密预期。建议 server 模式强制要求 encryption_key（如 `require_strong_secret` 同款 fail-closed），或至少 WARNING + 明确文档。

### 10.4 P0 — Supervisor decisions schema 冲突（tenant 缺列）

**证据**：
- `src/aipd_os/supervisor/supervisor.py:64-70`（supervisor 独立 DB）：
```sql
CREATE TABLE IF NOT EXISTS decisions(
 decision_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, topic TEXT NOT NULL,
 trigger TEXT, recommendation TEXT, options_json TEXT NOT NULL DEFAULT '[]',
 status TEXT NOT NULL DEFAULT 'proposed', choice TEXT, comment TEXT,
 created_at TEXT NOT NULL, resolved_at TEXT);
```
- `src/aipd_os/state/db.py:119-131`（state DB）：
```sql
CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT NOT NULL, project_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
  topic TEXT NOT NULL, trigger TEXT, recommendation TEXT, options_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'proposed', choice TEXT, comment TEXT,
  created_at TEXT NOT NULL, resolved_at TEXT, ...);
```
- 两处同名 `decisions` 表、**不同 schema**：supervisor 版**无 `tenant_id`**（无法多租户隔离），state 版有。二者分属不同 SQLite 文件、无统一模型。
**判定：问题存在（schema 冲突确认）**。supervisor 的 decisions 不受租户作用域约束，与 state 版语义不一致。v5.7 应统一 decisions 契约（含 tenant_id）或明确 supervisor decisions 的租户边界。

### 10.5 P1 — Execution Idempotency Scope（幂等键全局去重）

**证据**：`src/aipd_os/execution/runs.py:256-264`
```python
def find_by_idempotency_key(self, key: str) -> Optional[ExecutionRecord]:
    row = c.execute(
        "SELECT * FROM execution_runs WHERE idempotency_key=? "
        "ORDER BY start_time DESC, rowid DESC LIMIT 1", (key,)).fetchone()
```
- 仅按 `idempotency_key` 查询，**未按 project_id/tenant 作用域过滤**；而 `execution_runs` 表含 `project_id` 列（`runs.py:45,128`）。
- `execution_router.py:104-114` 幂等去重直接调用 `find_by_idempotency_key`。
**判定：问题存在**。同一 idempotency_key 在不同项目/租户间会命中彼此的成功/运行中记录（跨作用域去重），可能返回错误项目的 result 或误判 in_progress。v5.7 应将幂等键唯一性限定为 `(tenant_id, project_id, idempotency_key)`（或键内编码作用域）。

### 10.6 P1 — Research/Truth 语义（verified=已抓取 被写成事实 V）

**证据**：`src/aipd_os/research/models.py:15-17`
```python
# 发现状态：verified=已获取并解析；not_verified=未能获取/未验证；external_pending=等外部回填
STATUS_VERIFIED = "verified"
```
`src/aipd_os/research/writeback.py:53-72`
```python
def write_finding(self, finding):
    if finding.status == STATUS_NOT_VERIFIED:
        return None
    ...
    fact_id = self._db.add_fact(..., status="V", ...)  # V 写入 Product Truth
```
- research 的 `verified` 语义是「**已获取并解析**」（fetch/parse 成功），并非「内容确认为真」；但 `write_finding` 把该状态直接写成 Product Truth fact `status="V"`。
- `assets/schemas/fact.schema.json` 的 status enum（V/S/C/E/A/P/T/R）**无 description**，`V` 含义未定义，语义被隐式等同于「Verified True」。
**判定：语义存疑/需收敛**。fetch 成功 ≠ 事实为真。建议 research 输出区分 `retrieved`（已抓取）与 `confirmed`（已核实），仅后者写事实；或为 fact status 补齐 schema 语义并确保 research 写回不会过度宣称。

### 10.7 P1 — supervisor_claims 死表 + 命名

**证据**：`src/aipd_os/supervisor/supervisor.py:60-63`
```sql
CREATE TABLE IF NOT EXISTS supervisor_claims(
 claim_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, claim TEXT NOT NULL,
 allowed INTEGER NOT NULL, evidence_json TEXT NOT NULL DEFAULT '[]',
 reason TEXT, created_at TEXT NOT NULL);
```
全仓 grep `supervisor_claims`：**仅此一处 CREATE TABLE**，src/tests/scripts 无任何 INSERT/SELECT —— **死表**；且列名 `claim` 与 Product Truth / research evidence 概念混用。
**判定：问题存在（命名/清理项）**。v5.7 应删除或落地该表，并统一「claim / evidence / truth」词汇。

### 10.8 其它事实项（新发现）

- **BUNDLE_MANIFEST 污染**（§9.2）：4679/5271 条目为 `.pytest_cache`/`.venv*` 垃圾。发布产物 manifest 需重建。
- **audit_repo source_commit 落后**：`SOURCE_MANIFEST.json` 钉住 `2541be8`，落后 HEAD 1 commit；`docs/audit/audit.json` generated_at=2026-08-06（落后 6 天）。
- **pytest-report.json 陈旧**（§9.3），且不绑定 commit。
- 未发现 `NOT_RUN` 项：任务列出的 15 条命令全部真实执行（schema_check、audit_repo、capability_matrix、CAD 套件均存在且可运行）。

---

## 11. 结论（v5.7 基线判定）

| 维度 | 结果 |
| --- | --- |
| 测试（全量回归） | ✅ **597 passed / 0 failed / 2 skipped / 2 deselected**（601 collected） |
| 集成/冒烟/E2E/发布门禁 | ✅ 15 / 4 / 1 / 10 passed |
| CAD（真实内核） | ✅ 20 passed（cadquery 2.5.2） |
| schema_check | ✅ 全部通过（exit 0） |
| 审计脚本 | ✅ audit_repo / capability_matrix exit 0（产物已还原） |
| repository hygiene（tracked） | ✅ 0 命中 |
| BUNDLE_MANIFEST 违禁条目 | ❌ 4679/5271（.pytest_cache + .venv*） |
| pytest-report.json | ❌ 陈旧（522→601 collected，落后 3 commits，未绑定 commit） |
| ruff | ❌ 3090 errors（exit 1；基线 3298，略降，非 CI 门禁） |
| mypy | ❌ 138 errors in 53 files（exit 1；基线 140/51，略降，非 CI 门禁） |
| P0 初验（MCP auth / tenant membership / encryption key / supervisor schema） | ⚠️ 4/4 均有问题：MCP 传输（state_service/mcp_server.py）未认证未测试；其余见 §10.2-10.4 |
| P1 初验（idempotency scope / research truth / supervisor_claims） | ⚠️ 3/3 均有问题（§10.5-10.7） |

**总体**：运行时/测试基线**健康**（601 collected、597 passed、0 failed；所有门禁套件通过）；但**发布产物与安全契约存在明确缺口**（BUNDLE_MANIFEST 污染、pytest-report 陈旧、encryption-key fail-open、tenant 自助注册/跨租户授权、supervisor decisions 无 tenant、幂等键跨作用域、research truth 语义过宣称、supervisor_claims 死表），以及**静态质量存量欠债**（ruff 3090 / mypy 138，非门禁）。以上构成 v5.7 Foundation Closure 必须回填的事实基线。

---

## 附录 A：全部命令执行清单

| # | 命令 | 结果摘要 | Exit |
| --- | --- | --- | --- |
| 1 | `pytest --collect-only -q tests` | 601 tests collected in 6.93s | 0 |
| 2 | `pytest tests/ -m "not model_eval" -q` | 597 passed, 2 skipped, 2 deselected, 241.60s | 0 |
| 3 | `pytest tests/ -m integration -q` | 15 passed, 2 skipped, 584 deselected, 8.74s | 0 |
| 4 | `pytest tests/test_integration_smoke.py -q` | 4 passed in 4.21s | 0 |
| 5 | `pytest tests/test_manual_chain_e2e.py -q` | 1 passed in 7.58s | 0 |
| 6 | `pytest tests/test_production_release_gate.py -q` | 10 passed in 4.95s | 0 |
| 7 | `pytest tests/test_cad_golden_loop.py tests/test_cad_contract_unify.py -q` | 20 passed in 17.14s（cadquery 2.5.2） | 0 |
| 8a | `ruff check .` | **3090 errors**（exit 1） | 1 |
| 8b | `python -m mypy` | **138 errors in 53 files**（checked 212） | 1 |
| 9 | `python -m aipd_os.scripts.schema_check` | 全部通过（5 个 schema OK） | 0 |
| 10 | `python scripts/audit_repo.py --repo .` | OK；release/source manifest hash 384/384（source_commit=2541be8） | 0 |
| 11 | `python scripts/capability_matrix.py --repo . --out docs/audit` | OK；fully=35/partial=26/ext=9；产物已还原 | 0 |
| 12 | `git ls-files | grep -E '(^|/)(__pycache__/|\.pytest_cache/|\.mypy_cache/|\.ruff_cache/|.*\.pyc$)'` | **0 命中** | 0 |
| 13 | `grep BUNDLE_MANIFEST.json`（.pytest_cache/__pycache__/*.pyc/*.dist-info/.venv*） | **4679 命中**（4670 .venv* + 9 .pytest_cache） | 0 |
| 14 | pytest-report.json 陈旧性 | 陈旧：created 2026-08-06，522 collected vs 当前 601 | — |
| 15 | 版本探测 | python 3.9.6（.venv）/ cadquery 2.5.2 / managed python 3.13.12（未使用） | — |

## 附录 B：NOT_RUN 说明

无。任务列出的全部命令均已真实执行；报告内无 PASS 冒充。

---

## 附录 C：v5.8 增量审计（Commit 9-16 之后，software-engineer-2）

本附录记录 v5.8 Idea & Evidence Foundation（Commit 9-16）之后的增量事实；
历史报告正文保持 v5.7 结论不变。

### C.1 全量回归（最新 HEAD 工作树）

| 命令 | 结果 |
|---|---|
| `pytest tests/ -m "not model_eval" --json-report ...` | **684+ 通过**（Commit 9-11 后 684；Commit 12-16 后全量数字以 pytest-report.json 为准） |
| Commit 9-11 新测试（idea/claim/evidence graph） | 27 passed |
| Commit 12-16 新测试（decomposer/research integration/truth projection/golden E2E） | 27 passed |

### C.2 新增域（Idea / Claim / EvidenceRelation）

- `src/aipd_os/idea/`：models / service / maturity / decomposer / projections /
  claims / claim_service / evidence_relations / evidence_graph / research_provider。
- 表：`ideas`（migration v2）、`claims`（v3）、`claim_evidence_relations`（v4）；
  db.py SCHEMA 同步幂等 CREATE；migrate/rollback 测试覆盖。
- 全部写操作 tenant+project scoped / audited / versioned。

### C.3 诚实性护栏（v5.8 新增）

- Candidate Claim 默认 epistemic_status=A/U，绝不默认 V；
- IdeaDecomposer 无 provider → CAPABILITY_UNAVAILABLE（不写 DB）；schema 失败 → FAILED_VALIDATION；
- ResearchIntegration 无 provider/无结果 → external_blocked（不写 evidence）；
- claim↔evidence relation 跨 tenant/project link 拒绝；
- relation 的 evidence_id 必须真实存在于 canonical evidence 表（无 fake evidence）；
- ResearchStudio 检查：/Volumes/Extra/CodeProj/ 下**不存在** → 仅 Provider contract + capability 注册骨架；
- golden fixture 标注 EPISTEMIC_NOTE（非真实医学/研究结论）。

### C.4 遗留

- 静态质量（ruff/mypy）存量欠债非本批范围（v5.7 报告 §静态质量）。
