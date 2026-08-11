# AIPD-OS v5.8.1 Re-Audit（Commit 1：问题清单复验 + 审计产物刷新）

> 生成时间：2026-08-12（software-engineer，v5.8.1 Commit 1）
> 本报告是 v5.8.1 的事实基线重审计。所有结论均来自**真实复验**：读代码 + 在
> HEAD `44ce21a` 的干净 worktree 中运行最小复现脚本（`PYTHONDONTWRITEBYTECODE=1
> .venv/bin/python`，仓库 `.venv`，Python 3.9.6 / cadquery 2.5.2）。未执行步骤
> 明确标注，绝无虚构 PASS。
>
> 状态语义：
> - `CONFIRMED` —— 在 HEAD `44ce21a` 复现确认，且修复不在本 Commit 1-2 范围内
>   （后续 Commit 修复，见「修复归属」列）；
> - `RESOLVED` —— 已复现确认，且由本 Commit 1-2 修复（含真实测试证据）；
> - `PARTIALLY_RESOLVED` / `NOT_REPRODUCED` / `SUPERSEDED` —— 按实标注（本轮无）。

---

## 0. 审计元信息

| 字段 | 值 |
| --- | --- |
| HEAD SHA | `44ce21ad1997afa7c92d022139edcd99fa6fc10e`（main，origin/main 同步） |
| package_version | `5.6.0`（pyproject.toml `[project].version`） |
| python / cadquery | 3.9.6（repo `.venv`）/ 2.5.2（真实内核） |
| 复验方式 | 读代码 + `git worktree add`（HEAD 44ce21a 原样）跑最小复现脚本 |
| 本 Commit 修改 | `scripts/release_evidence.py`、`scripts/production_release_gate.py`、`tests/test_repo_hygiene.py`、`docs/audit/audit.json`、`docs/audit/capability_matrix.*`、`docs/audit/repository_snapshot.json`、`BUNDLE_MANIFEST.json`（+ SOURCE/RELEASE 证据随改动刷新，见 §3） |
| 本 Commit 2 修改 | `src/aipd_os/idea/serializers.py`（新）、`src/aipd_os/idea/decomposer.py`、`models.py`、`service.py`、`__init__.py`、`tests/test_idea_decomposer.py`、`tests/test_idea_to_evidence_golden.py` |

---

## 1. 问题清单逐项复验

### A. Idea I0→I1 双 Idea（decomposer.py `_persist` 建新 Idea）

- **Status: CONFIRMED → RESOLVED（Commit 2）**
- 复现（HEAD 44ce21a 原样）：intake 创建 `IDEA-001`（raw）后调用
  `decompose_and_persist`，真实输出：
  ```
  A. double-idea: raw idea_id=IDEA-001, structured idea_id=IDEA-002, total ideas=2
     claims attached to: ['IDEA-002']
  ```
- 根因：`decomposer.py:230-239` `_persist` 无条件 `IdeaService.create` 生成**新**
  Idea，I0（raw）与 I1（structured）是两条记录，身份断裂。
- 修复：Commit 2 新增 `IdeaDecomposer.decompose_existing(idea_id)` —— 对已存在
  Idea 做 `IdeaService.update`（乐观锁），保持 `idea_id/raw_input/created_at`
  不变，Candidate Claims 挂同一 idea。Golden E2E 改走该路径。
- 测试证据：`tests/test_idea_decomposer.py::test_decompose_existing_same_idea_id`
  + `tests/test_idea_to_evidence_golden.py`（decompose 后 idea 数 = 1）。

### B. raw_input 丢失（decomposer.py:232）

- **Status: CONFIRMED → RESOLVED（Commit 2）**
- 复现（HEAD 44ce21a 原样）：
  ```
  B. raw_input preserved? structured.raw_input='' (expect '我想做一个利用 AI 帮助独居老人居家康复的产品')
  ```
- 根因：`_persist` 构造 `Idea(raw_input="")`，用户原始输入未写入。
- 修复：`_persist` / `decompose_existing` 均以 `idea.raw_input` / 入参
  `raw_input` 写入，绝不置空。
- 测试证据：`test_decompose_existing_preserves_raw_input`、
  `test_decompose_and_persist_still_independent_new_idea`。

### C. constraints_json = str(repr)（decomposer.py:236）

- **Status: CONFIRMED → RESOLVED（Commit 2）**
- 复现（HEAD 44ce21a 原样）：
  ```
  C. constraints_json repr? "{'constraints': ['单摄像头即可', '离线可运行']}"
  ```
- 根因：`_persist` 写 `constraints_json=str({"constraints": ...})`（Python repr，
  非 JSON，单引号、无法被 `json.loads` 解析）。
- 修复：Commit 2 新建 `src/aipd_os/idea/serializers.py`：
  `serialize_constraints`（`json.dumps(ensure_ascii=False, sort_keys=True)`）写、
  `parse_constraints`（`json.loads`，旧 repr 用 `ast.literal_eval` 兼容）读；
  decomposer 写、IdeaService 读均走 serializer。新写入永远是合法 JSON。
- 测试证据：`test_constraints_json_roundtrip`、`test_parse_constraints_legacy_repr_compatible`、
  `test_decompose_existing_persist_writes_real_json_constraints`。

### D. maturity 任一 relation → I2（maturity.py `evaluate`）

- **Status: CONFIRMED（修复归属 Commit 3/5）**
- 复现（HEAD 44ce21a 原样）：给 structured idea 挂一条 **pending + inconclusive**
  关系（既非 reviewed 也非 supports），`IdeaMaturity.evaluate` 输出：
  ```
  D. maturity (structured idea, pending inconclusive relation): I2
  ```
- 根因：`maturity.py:49-54` `has_real_evidence = any(get_claim_evidence(...))`，
  只要有**任意** relation（含 inconclusive / pending / rejected）即判 I2，
  不看 relation_type 语义、不看 review_status。
- 本轮不改（属于 Commit 3 lifecycle/maturity 分离 + Commit 5 保守 I2 的修复范围）。

### E. pending 不检查 review_status

- **Status: CONFIRMED（修复归属 Commit 4/5）**
- 复现：与 D 同一脚本——`review_status="pending"` 的关系被
  `maturity.evaluate` 当作已确认证据计入 I2；`EvidenceGraph` 的
  `get_supporting_evidence` 也只按 `relation_type` 过滤，不看 review_status。
- 根因：relation 默认 `review_status="pending"`（evidence_relations.py:44），但
  maturity / graph 查询均未过滤 pending/rejected。
- 本轮不改。

### F. classify_relation 有 sources → supports（research_provider.py:188-201）

- **Status: CONFIRMED（修复归属 Commit 5）**
- 复现（HEAD 44ce21a 原样）：
  ```
  F. classify_relation(result with sources but no declared relation) -> supports
  ```
- 根因：`classify_relation` 在结果未显式声明 `evidence_relation` 时，只要有
  `sources` 就默认 `supports`——「检索到来源」≠「该来源支持该 claim」。
- 本轮不改。

### G. INSERT OR REPLACE（evidence_relations.py:180）

- **Status: CONFIRMED（修复归属 Commit 7）**
- 复现（HEAD 44ce21a 原样）：对同一 `relation_id` 连续 add 两次：
  ```
  G. after first add: REL-001 version_no = 1 review_status = pending
  G. after REPLACE with same id: version_no = 1 (>=2 expected; history destroyed)
  ```
- 根因：`add` 用 `INSERT OR REPLACE`——主键/唯一键冲突时**删除旧行再插入**，
  `version_no` 复位、变更历史丢失、乐观锁语义被绕过。
- 本轮不改。

### H. `_next_id` scan-max 并发 race（service.py）

- **Status: CONFIRMED（修复归属 Commit 7）**
- 复现（HEAD 44ce21a 原样，8 线程并发 `IdeaService.create`）：
  ```
  H. 8 concurrent creates -> ids: ['IDEA-001', 'IDEA-002', 'IDEA-003'] errors: 5
  H. unique ids: 3 | total rows: 3
  ```
- 根因：`IdeaService._next_id` / `ClaimService._next_id` /
  `EvidenceRelationService._next_id` 均为「SELECT 全部 id → max+1」，无原子
  分配；并发下多个线程算出同一 id，5/8 写失败（PK 冲突）。
- 本轮不改。

### I. migration v1 `from .db import SCHEMA` 未冻结（migrations.py:14）

- **Status: CONFIRMED（修复归属 Commit 8）**
- 复验：`migrations.py:15` `from .db import SCHEMA as V1_INITIAL_SCHEMA`，
  v1 的 `"up": [V1_INITIAL_SCHEMA]` 直接引用**活 schema 常量**。`db.py SCHEMA`
  当前已含 v5.8 新增的 `ideas/claims/claim_evidence_relations` 表
  （db.py:242 起）——即「v1 迁移」的内容随代码演进而变化，不是冻结的历史快照；
  未来给 `db.SCHEMA` 加列会悄悄改变 v1 迁移行为，无法精确复现历史 v1 库。
- 本轮不改。

### J. audit.json 陈旧（绑定旧 commit 0934f84）

- **Status: CONFIRMED → RESOLVED（Commit 1）**
- 复验：改动前 `docs/audit/audit.json` 的 `latest_commit_sha` 为 `0934f84...`
  （旧 commit），与 HEAD `44ce21a` 不符；capability_matrix / repository_snapshot
  同样陈旧。
- 修复：重新生成（见 §2），现绑定 HEAD `44ce21a`，`source_manifest_verification.
  hash_mismatch_count == 0`。

### K. BUNDLE_MANIFEST bundle_path 为开发机绝对路径（Commit 1 新增复现项）

- **Status: CONFIRMED → RESOLVED（Commit 1）**
- 复验：改动前 `BUNDLE_MANIFEST.json` 的 `bundle_path` 为
  `/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS/build/release/aipd-os-5.6.0.zip`
  ——不可 relocatable。
- 修复：`scripts/release_evidence.py::generate_bundle_manifest` 改为写相对路径
  （相对 repo_root，缺省 CWD，统一 `/` 分隔）；`production_release_gate` 的
  bundle 定位同步解析相对路径。重新生成后：
  ```
  bundle_path = build/release/aipd-os-5.6.0.zip
  ```
- 测试证据：`test_bundle_manifest_is_relocatable`。

### L. test_repo_hygiene 直接跑 git ls-files，无 .git 时不可运行（Commit 1 新增复现项）

- **Status: CONFIRMED → RESOLVED（Commit 1）**
- 复验：`tests/test_repo_hygiene.py` 原实现 `_tracked_files` 无条件
  `git -C <repo> ls-files`（check=True）——GitHub source ZIP 无 `.git` 时
  直接抛错，测试无法运行。
- 修复：支持两种模式——有 `.git` 验证 git ls-files；无 `.git`（archive 模式）
  遍历当前 source tree 验证无 `__pycache__/*.pyc/.pytest_cache/.mypy_cache/
  .ruff_cache/.venv`（跳过生成的打包元数据目录），并显式标注 archive mode。
- 测试证据：`test_tracked_sources_contain_no_cache_garbage`（双模式）、
  `test_source_archive_hygiene_without_git`（迷你无 .git source tree）、
  `test_archive_mode_hygiene_passes_on_repo`。

---

## 2. 审计产物刷新（绑定当前 HEAD）

真实命令与结果：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/audit_repo.py --repo . --json-out docs/audit/audit.json
# latest_commit_sha: 44ce21ad1997afa7c92d022139edcd99fa6fc10e
# source_manifest hash_mismatch_count: 0

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/capability_matrix.py --repo . --out docs/audit
# repository_snapshot.json latest_commit_sha: 44ce21ad1997afa7c92d022139edcd99fa6fc10e
# capability_matrix.json  latest_commit_sha: 44ce21ad1997afa7c92d022139edcd99fa6fc10e
#                         version: 5.6.0 | total_capabilities: 70
```

历史报告（V5_7_FOUNDATION_CLOSURE.md、RE_AUDIT_LATEST_HEAD.md 等）**不改**，
属 Historical。

---

## 3. 发布证据刷新说明

本 Commit 修改了 3 个 tracked 文件（release_evidence.py、production_release_gate.py、
test_repo_hygiene.py），`tests/test_packaging.py` 要求根级
`SOURCE_MANIFEST.json` / `RELEASE_MANIFEST.json` 与磁盘逐文件哈希一致，因此随
改动同步刷新（与 44ce21a 刷新 README 证据同惯例）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/release_evidence.py --repo . --out . \
  --version 5.6.0 --bundle build/release/aipd-os-5.6.0.zip \
  --source-commit 5055ab1950678a40e7f8b6aa684960e6f35616a0 \
  --test-report .pytest/lastreport.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/regenerate_release_manifest.py --version 5.6.0
# RELEASE_MANIFEST.json 已刷新：439 个文件，version=5.6.0
```

- `SOURCE_MANIFEST.json` / `PROVENANCE.json` 保持既有 release anchor
  `5055ab1`（与 44ce21a 同惯例），仅刷新受影响文件的哈希。
- `BUNDLE_MANIFEST.json`：`bundle_path` 已改为相对路径
  `build/release/aipd-os-5.6.0.zip`；`bundle` 保留文件名；
  bundle 本体未重建（重建属发布动作，不在本阶段）。
- `releases/` 已公开产物未修改。

---

## 4. 复验命令汇总（全部真实执行）

| 复验 | 方式 | 结果 |
| --- | --- | --- |
| A/B/C 双 Idea + raw_input + repr | worktree(44ce21a) 脚本 | CONFIRMED（输出见上） |
| D/E 任意 relation→I2 + pending 不查 | worktree(44ce21a) 脚本 | CONFIRMED（I2） |
| F sources→supports | worktree(44ce21a) 脚本 | CONFIRMED（supports） |
| G INSERT OR REPLACE 复位版本 | worktree(44ce21a) 脚本 | CONFIRMED（version 1→1） |
| H _next_id 并发 race | worktree(44ce21a) 8 线程 | CONFIRMED（3 唯一 / 5 错） |
| I migration v1 未冻结 | 读代码 | CONFIRMED |
| J audit.json 陈旧 | 读 JSON | CONFIRMED → RESOLVED |
| K bundle_path 绝对路径 | 读 JSON | CONFIRMED → RESOLVED |
| L hygiene 无 .git 不可跑 | 读代码 | CONFIRMED → RESOLVED |

---

## 5. 结论

- 主理人已复现的 10 项问题全部 **CONFIRMED**（无一 NOT_REPRODUCED / SUPERSEDED）。
- 其中 A/B/C（Commit 2）与 J/K/L（Commit 1）已 **RESOLVED**，其余
  D/E/F/G/H/I 为后续 Commit（3/4/5/7/8）修复范围，本报告如实记录为 CONFIRMED。
- 审计产物（audit.json / capability_matrix / repository_snapshot）已绑定 HEAD
  `44ce21a`；发布证据 relocatable + 双模式 hygiene 由新增测试守护。
