# F-SUPPLY-03 / F-CLI-01：验证失败的影响传播从无可达路径变成两条真命令

日期：2026-09-24　范围：`AIPD-OS`　停止条件：本文读数均为本机实测；未实测处显式标注。

## 1. 结论

两件事一起修：

1. 登记表 `industrialize.physical_writeback` 声明「测试结果 → 事实主表更新 → BOM/CAD
   影响传播」且 `current_limitation=None`（= 自称完整实现）。实测它在软件上**不可达**。
   现已把它接到两条真命令上，并让"事实主表更新"这句话可核验。
2. 修的过程中量出更大的一条：**8 条在契约、`COMMAND_FUNCS`、SKILL.md 三处都登记为
   PUBLIC 的命令，CLI 解析器从未接线** —— `aipd validation import` 在真实终端上是
   `invalid choice`。这三份内部副本互相核对，所以没有一方能发现"命令根本不存在"。

## 2. 接线前的实测事实

| # | 事实 | 读数（本机） |
|---|---|---|
| 1 | 传播的唯一产品调用点喂的是调用方自带数据 | `tool_adapters/evt_dvt_pvt_adapter.py:73-76`：`facts = input.get("facts") or {}`、`bom = input.get("bom") or []` ⇒ 真实输入下 `bom` 为空，`propagate_impact` 返回 `[]` |
| 2 | 该适配器在仓库里没有任何生产者 | `git grep -l 'validation.import-evt-dvt-pvt' -- .`（排除自身目录）**零命中**；`manual.layout`、`supply.supplier-files` 同样零命中（连测试都不引用） |
| 3 | 产品侧只排产 idea/product 两类能力 | 全仓 `add_work(..., capability_floor=V)` 只有 `supervisor/idea_capabilities.py` 一处来源（10 个 schedule 函数，V 为 `idea.*` / `product.*` 常量）；`scripts/aipd_supervisor.py` 里 `capability_floor` **零命中** |
| 4 | 8 条 PUBLIC 命令不可输入 | 用 `build_parser()` 自省：`COMMAND_FUNCS` 53 条 − 解析器可输入集 = `{issue list, issue resolve, issue show, readiness check, validation import, validation list, validation plan, validation show}` |
| 5 | 现有"命令覆盖率"检查看不见这个洞 | `tests/test_command_coverage.py` 三条断言比的是 契约 ↔ `COMMAND_FUNCS` ↔ 测试引用，全部是内部副本，从未读解析器 |
| 6 | `aipd industrialize --lab-data` 阶段失败仍 exit 0 | 修复前该函数末尾是裸 `return 0`（`ok` 字段恒 `True`），与 `aipd validate` 返回 rc 的纪律不一致 |
| 7 | 既有正向对照证明探针可开火 | 同一 AST 探针读到 `product.derive_insights` 等 7 个 id 在生产者侧出现 ⇒ 第 2/3 条的"零命中"不是扫描器空转 |

第 7 条是必要的：本轮第一版探针因为 `Path.glob("**/*.py")` 漏写 `recursive`
而把所有子包读成零命中，"10 个适配器全部不可达"这个结论当时是假的——
`supply.rfq` 这个已知正例把它暴露了。**否定结论必须先有能开火的正例。**

## 3. 技术选型

本轮是"把已声明能力接到已有实现面 + 修命令接线"，不引入任何新依赖、不改
`pyproject.toml` 依赖面，符合目标里"影响范围明确的局部改动可跳过外部检索"的例外；
下表三个候选都是仓内既有机制的对比，本文不声称查阅过任何未实际打开的外部项目。

| 候选 | 做法 | 功能匹配度 | License | 维护活跃度 | 安全风险 | 代码质量 | 适配成本 |
|---|---|---|---|---|---|---|---|
| A（选定） | 传播函数落在 `supply_chain/impact.py`，由**已可达且已持久化**的 `aipd validation import` 与 `aipd industrialize --lab-data` 调用；stale 判定复用 `deliverables.status` + CAS（`experience/instructions._mark_stale` 同一纪律）；结论写 `impact.<item>` 事实 | 完全匹配声明的三句（事实主表更新 / BOM / CAD 制品） | 无新依赖 | 全部为仓内自有模块 | 无外部面；写操作全部走乐观锁 | 单一函数两处调用，不重复实现 | 中：新增 1 模块 + 2 处接线 |
| B | 只把登记表改成"未接线"并给死适配器加标注 | 不实现声明的能力，只是承认缺陷（目标明确禁止用更窄的方案替代） | — | — | — | 留下 3 个零调用适配器 | 低 |
| C | 让 `validation import` 改走 `ExecutionRouter` + 适配器 | 能顺带救活适配器 | 无新依赖 | router 目前只服务 idea/product 链 | 需引入 work item / run 记录 / 幂等键整套 | 为一条命令引入调度框架 | 高，且能力本身不需要调度层 |

选定 A，并把"未接线适配器"变成**显式声明表**（`UNREACHABLE_ADAPTERS`）而不是删除：
B 的诚实性 + A 的实现性；新增第四个未声明的死适配器会被
`tests/test_lab_impact_propagation.py::TestNoSilentDeadCapability` 判红。

## 4. 落点

| 位置（写后复读定位） | 内容 |
|---|---|
| `src/aipd_os/supply_chain/impact.py:60` `ImpactReport` | `affected_lines / stale_deliverables / already_stale_deliverables / unresolved_lines / fact_keys / clean`；`stale_deliverables` 只列**本次真正改判**的（重放不得谎报"我又标了一次"） |
| `impact.py:100` 附近 `propagate_lab_impact` | 归一化全等匹配（「支架」不带出「支架座」）→ 行的 `source_deliverable` → CAS 置 `stale`；`released`/`archived` 不改写；关联不到制品进 `unresolved_lines`；结论写/刷 `impact.<item>` 事实（status `P`），**重放只刷新那一条** |
| `src/aipd_os/cli/commands_validation.py:111` `cmd_validation_import` | 导入后对 `result.failing_items` 调传播；`impact` 进 payload；`unresolved` 非空 ⇒ **exit 4** |
| `src/aipd_os/validation/ingestion.py` `IngestionResult.failing_items` | 失败项由导入本身产出（去重、保序），批量 `ingest_files` 合并 |
| `src/aipd_os/cli/commands_cad.py` `cmd_industrialize` | 带 `--lab-data` 且带 `--db` 时传播；缺 `--db` 时如实写 `impact_note`（没库就不传播）；`ok` 与退出码不再恒真（阶段失败或未收口 ⇒ 4） |
| `src/aipd_os/cli/main.py` | 补 `validation` / `issue` / `readiness` 三个 parser 组共 8 条子命令（含 `--stage` choices、`--disposition` choices、`--plan-id`→`plan_id`）；`industrialize` 补 `--project` |
| `src/aipd_os/registry_data.py` | `industrialize.physical_writeback` 重指向 `supply_chain.impact`（分类由 fully → **partially**，边界写明）；`industrialize.evt_dvt_pvt_import` 的 `implementation_file` 里那条不存在的 `tool_adapters/...` 相对路径一并改实 |
| `src/aipd_os/tool_adapters/evt_dvt_pvt_adapter.py` | 注明 `propagated_stale` 只是 payload 回声、真传播在哪、本适配器未被排产 |

## 5. 测试与变异对照

新增 17 条用例（`--collect-only` 实测）：`tests/test_lab_impact_propagation.py` 11 条
（6 行为 + 2 真命令可达 + 3 未接线声明守卫）+ `tests/test_cli_validation_surface.py` 4 条
（全部走 `main(argv)`）+ `tests/test_command_coverage.py` 新增 2 条解析器守卫。

- 行为：命中即改库并写事实；关联不到制品只报告不代造；`released` 不被悄悄改写；
  归一化全等且不做子串；重放零新增事实、零重复标记；无受影响行则不写事实；
- 可达性：`validation import` 与 `industrialize --lab-data` 各一条端到端，
  断言**库里的 deliverable 状态**而不是只看命令自己打印的报告；
- 守卫：解析器面（正向对照 `bom add`/`quote apply`/`outbox drain` 必须在，
  `validation import` 必须在）；适配器面（`UNREACHABLE_ADAPTERS` 声明表 +
  抹掉一条声明必须判红的注入反证）。

变异对照（改真码 → 复跑 → 从备份逐字节还原）：

| 变异 | 实测 |
|---|---|
| M1 传播只写报告、删掉 `db.update_deliverable(...)` | **4 红**（3 条单元 + 1 条 CLI 端到端）。附带价值：第一版 CLI 用例只断言了报告字段，M1 竟不判红 —— 断言已按"必须读库"补强后 M1 才开火 |
| M2 去掉 `released/archived` 保护分支 | **1 红**（`test_released_deliverable_is_never_silently_staled`） |
| M3 `_record_fact` 永远走 insert（不刷新） | **2 红**，报错正是 `UNIQUE constraint failed: facts…key, facts.version` |
| 解析器未接线（本轮接线前的自然状态） | 守卫**2 红**（`test_every_registered_command_is_parseable` + 正向对照），接线后转绿 |

## 6. 已知边界与未做

- 匹配只在 BOM 行 `item` 一层，不沿 `parent_item` 向上/向下推，也不读 CAD 模型；
- `unresolved` 只报告，不自动创建 deliverable（造出来就是假证据）；
- `product_truth/PropagationEngine` 仍是 0 调用点：本条走的是 deliverable + fact 这条
  已经接线、且有 CAS 的路，没有把返工预算（`backoff_until`）那套引进来；
- 10 个适配器里 3 个连测试都不引用（`manual.layout` / `supply.supplier-files` /
  `validation.import-evt-dvt-pvt`），本轮只把它们**写进声明表**使其可见，
  没有删除，也没有把它们接进 router（删除属破坏性动作，留给属主裁决）；
- 就绪度对"已解决 Issue 但结果仍 FAIL"的项目照旧判 FAIL —— 处置 Issue 不等于复验，
  这条已由用例钉住。

## 7. 复算入口

```bash
cd /Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
export PATH="$PWD/.venv/bin:$PATH"
# 8 条命令是否真能输入（解析器自省，无需跑命令）
python - <<'PY'
import argparse
from aipd_os.cli.main import build_parser
from aipd_os.cli.commands import COMMAND_FUNCS
a = [x for x in build_parser()._actions if isinstance(x, argparse._SubParsersAction)][0]
reachable = set(a.choices)
for name, sp in a.choices.items():
    for act in sp._actions:
        if isinstance(act, argparse._SubParsersAction):
            reachable |= {f"{name} {v}" for v in act.choices}
print(sorted(set(COMMAND_FUNCS) - reachable - {"usage"}))   # 期望：[]
PY
python -m pytest tests/test_lab_impact_propagation.py tests/test_cli_validation_surface.py \
  tests/test_command_coverage.py tests/test_capability_matrix.py -q
python scripts/capability_matrix.py --repo . --out docs/audit

# 一条真链（临时库）
D=$(mktemp -d); python -m aipd_os.cli.main init --db "$D/state.db" --project P-1 --name 支架 --goal 量产 >/dev/null
python -m aipd_os.cli.main bom add --db "$D/state.db" --project P-1 --part 支架
printf 'stage,test_item,sample_id,result,pass_fail,notes\ndvt,支架,S1,0.4,fail,拉力不足\n' > "$D/lab.csv"
python -m aipd_os.cli.main validation import --db "$D/state.db" --project P-1 --stage dvt --file "$D/lab.csv"
python -m aipd_os.cli.main issue list --db "$D/state.db" --project P-1
python -m aipd_os.cli.main readiness check --db "$D/state.db" --project P-1; echo "rc=$?"
```

本轮把上面最后那段（A/B 两个临时库）实际跑过，读数原文：

- 解析器自省：`missing: []`（53 条注册命令全部可输入）；
- A）BOM 行不带 `--deliverable`：`影响传播：受影响 BOM 行 1，置 stale 制品 0，
  关联不到制品的行 1` + `⇒ 有受影响行挂不到制品上（补 --deliverable 后重跑即可收口）`，
  `rc=4`；
- B）另一临时库、BOM 行 `--deliverable DEL-001`：`置 stale 制品 1，关联不到制品的行 0`，
  `rc=0`；`issue list` 读到 `共 1 个 Issue`；`readiness check rc=1`
  （结果仍是那条 FAIL，处置 Issue 不等于复验）；
- 库里：`facts` 有 `impact.支架|P`，`deliverables` 有 `DEL-001|stale`。
