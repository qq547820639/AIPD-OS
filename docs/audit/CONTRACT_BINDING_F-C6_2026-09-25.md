# F-C6 第 30 片：契约绑定的判据修正 + 把形状校验接到产物落点（2026-09-25）

这一片起于第 29 片的一条**假阳性**，落在一处**真缺陷**上。记录分两半：
先写清那条判据为什么错、错在哪个方向；再写修了什么样的门、代价量成多少。

## 一、起点：第 29 片把「没人提到这个名字」推成「没人校验这张契约」

第 29 片的 `interface_contract.scan_consumers()` 在 `src|scripts|tests|state_service` 里
按**文件名字面量**反查（例：`project_checkpoint.schema.json`），查不到就报
「这是一张没人校验的契约」。三条同名报告里，两条半是错的：

- `src/aipd_os/scripts/schema_check.py` 真在校验它们，但用的是**命名约定**：
  `name = path.stem.removesuffix(".schema")` → 到 `DATA_DIRS` 里找同名 `<name>.json` →
  `jsonschema.validate(data, schema)`。那句 schema 文件名在 `schema_check.py` 里
  **一个字都没出现过**，按名字反查必然读不到。
- 这个脚本在 CI 里跑着：`.github/workflows/ci.yml:45` 是 `schema-validation` job，
  `:58` 就是 `python -m aipd_os.scripts.schema_check`。
- 现算（`python -m aipd_os.scripts.schema_check`，rc=0）：五份 schema 全部过元校验，
  其中 `cad_contract` / `manual_chain_state` / `project_checkpoint` / `supervisor_project`
  四份**有约定绑定的实例并被真校验**；只有 `fact.schema.json` 落
  `INFO …（跳过数据校验）`。

⇒ 孤儿 **3 份 → 1 份**，理由从「没人引用文件名」换成「**没有任何实例被按它校验过**」。
同一次核对还翻出两件第 29 片没看见的事（见 §二、§三），都比那条假阳性重。

## 二、真缺陷一：同一个形状两处声明，其中一份与数据库权威枚举矛盾

`assets/schemas/project_checkpoint.schema.json` 的 `$defs.fact` 是
`assets/schemas/fact.schema.json` 的**内联副本**，两份已经漂到互相矛盾：

| 位置 | `status.enum` | 其它差异 |
| --- | --- | --- |
| `src/aipd_os/state/db.py:48` `FACT_STATUSES`（**权威**） | `V S C E A P T R U`（9） | — |
| `assets/schemas/fact.schema.json` | 9 值含 `U` | 有 `tolerance`/`version`，`key.minLength=1`，不要求 `fact_id` |
| `project_checkpoint.schema.json` 内联 `$defs.fact` | 8 值**缺 `U`** | 多要求 `fact_id`，少 `tolerance`/`version` |

`U` 不是纸面值：`research/models.py:38 EPISTEMIC_UNKNOWN = "U"`、
`idea/evidence_graph.py:26 UNKNOWN_EPISTEMIC_STATUSES = frozenset({"U", "A"})`、
`product_intelligence/gate_criteria.py:145,372` 都在按 `U` 判定，
`tests/test_truth_evidence_semantics.py:154` 还钉着「`fact.schema.json` 的 enum 必须含 U」。
⇒ 一份从状态库导出的 checkpoint，只要含一条 `U` 事实，就**在本仓自己的契约下非法**。

**三档判据对照**（同一份重建文档，只有判据不同；`/tmp/slice30_arms.txt`）：

| 实例 | ① 内联（现役） | ② 裸 `$ref` | ③ `$ref` + 本地补足（**采用**） |
| --- | --- | --- | --- |
| 现役形状 | 合法 | 合法 | 合法 |
| `status=U` | **非法:enum** | 合法 | 合法 |
| 缺 `fact_id` | 非法:required | **合法（放宽！）** | 非法:required |
| `key=""` | 合法 | **非法:minLength（收紧）** | 非法:minLength |
| 带 `version` | 合法 | 合法 | 合法 |

②那一档就是「单源化顺手把本地多出来的要求丢掉」的样子；采用 ③：

```json
"$defs": {"fact": {"allOf": [{"$ref": "fact.schema.json"}],
                  "type": "object", "required": ["fact_id"],
                  "properties": {"fact_id": {"type": "string"}}}}
```

净效果只有两条，且都是有意的：**收 `U`**（与权威对齐）+ **拒空 `key`**（继承 `minLength`）。
今天真语料的读数：全仓 **0 条** fact 文档（`assets/templates/project_checkpoint.json` 的
`facts` 是空数组；`tests/fixtures/golden_projects/*/project.json` 里的 `facts` 是
`{"params": …}`，另一种语义）⇒ **两档 0 处翻转**，明写「今天无差」而**不是**「两条等价」，
必开火对照交给合成实例（`tests/test_schema_check.py::TestCheckpointContractSemantics` 三条：
U 合法 / 缺 `fact_id` 非法 / 空 `key` 非法）。

## 三、真缺陷二：落点只判存在，从不核形状

- `scripts/outcome_acceptance.py:22`：`exists(root,'state/project_checkpoint.json')`，
  而 `exists()` 只要求 `is_file() and st_size>0`。
- `scripts/quality_gate.py:22` 的 `REQ`：按 deliverable **类型名**在不在判
  （现抽：`REQ` 共 40 个类型，**只有 `project_checkpoint` 一个有同名契约**），
  而 `deliverables` 表带 `path` 列（`src/aipd_os/state/db.py:156`）⇒ 形状门有明确落点、
  爆炸半径 = 1 类。另两个 exists-only 落点 `cad/inspection_report.json`、
  `release/production_approval.json` **没有**同名契约（记事实，不算形状洞）。

**修前的门今天会怎么判**（旧码签出实测，三例同一份 G9 世界）：

| checkpoint 落点 | 旧 `quality_gate` | 新 `quality_gate` |
| --- | --- | --- |
| 合规文件 | `pass=true` | `pass=true`（`shape_findings=[]`） |
| 形状坏（缺 `fact_id`） | **`pass=true`** | 红：`invalid`，点名 `fact_id` |
| 文件根本不存在 | **`pass=true`** | 红：`missing` |
| 没填 `path` | `pass=true` | 红：`path_missing` |
| 文件不是 JSON | `pass=true` | 红：`unreadable`（与 `invalid` 分开） |

五态分开是因为下一步动作各不同：`invalid` 是「改坏了」，`unreadable` 是「核不了」，
`missing`/`path_missing` 是「标了交付却没东西可核」，`no_schema` 是「这形状今天没契约」。
**后四种都不许被读成通过。**

## 四、判据形状：四条规矩，每条都有电池注入对着

1. **绑定规则从真校验器里现抽**（`schema_binding.binding_dirs()` 用 AST 读
   `schema_check.DATA_DIRS`）。抄一份常量就是第二个会漂移的镜像；
   抽不到（脚本不在、常量改名）⇒ `binding_blind`，是**盲区**不是「没有绑定」。
2. **枚举的第四源是数据库**（`fact_status_authority()` AST 读 `FACT_STATUSES`）。
   两份 schema 互比只能证明抄得一样；权威读不到 ⇒ `authority_readable=False`
   且差集留空，明写「不知道」。
3. **量具不进自己的分母**——三个面都被实测咬过：
   ① `egress_consumer` 把 `interface_contract.py` 自己数成一个消费者（它的 `PROVES`
   文案里写着 `aipd_os.net.http`）；② 补了断言之后**分母从 11 涨到 12**——
   常驻用例里那句 `aipd_os.net.http` 也算一次引用（`INSTRUMENT_FILES` 由此而来）；
   ③ 同一个文件点了 `manual_chain_state.schema.json` 这个名字，就被当成
   「这张契约被某个消费方验过」⇒ 取证那一面也排除量具自己。
   排除表本身有常驻用例钉「表里每个路径必须真在盘上」，防它随改名腐化。
4. **七个轴逐轴单独钉判定**（`verdict_of()`）。前两版把判定写成 `build()` 里一长串
   `or`，测的时候只能整体断 `incomplete`——电池把「删掉某一格」的两条注入**放过去了**
   （因为别的轴本来就脏）。拆成逐轴参数之后，每一格都有自己那一发必须开火的注入。

## 五、落点（改了哪些文件）

- 新：`src/aipd_os/schema_binding.py`（绑定/解析/权威/落点四组判据的唯一出处）、
  `assets/templates/fact.json`（把 `fact.schema.json` 从「从没被按它校验过」里拉出来）、
  `tests/test_quality_gate_shape.py`（两个门的常驻用例）。
- 改：`src/aipd_os/scripts/schema_check.py`（UNBOUND 具名并报失败、`UNBOUND_EXEMPT`
  具名豁免、跨文件 `$ref` 用 `referencing` 解析、元校验按各文件自己声明的方言）；
  `assets/schemas/project_checkpoint.schema.json`（`$defs.fact` 单源化）；
  `src/aipd_os/interface_contract.py`（绑定判据、落点轴、权威轴、逐轴判定、`INSTRUMENT_FILES`）；
  `scripts/quality_gate.py`（`--root`、`contracted_types()` 现算、`shape_findings()` 五态）、
  `scripts/outcome_acceptance.py`（`checkpoint_shape` 字段 + 形状进合取）；
  `src/aipd_os/cli/commands_release.py`（七个轴的读数）；
  `src/aipd_os/cli/command_contract.py`（删掉那句停在「当前为 29」的过期注释，
  改成说明为什么**不写死数字**）；镜像：`registry_data.py`、`scripts/c6_coverage.py`、
  `README.md`、`CHANGELOG.md`。

## 六、选型（本回合真打开/真跑过的东西）

- **引擎 A：`jsonschema` 4.25.1 + `referencing` 0.36.2**（本机已装，均 MIT）。
  跨文件 `$ref` 用 `referencing.Registry(retrieve=…)` +
  `Draft202012Validator(schema, registry=reg)`（本机实测可用）。
  同一台机器上 `jsonschema.RefResolver` 会打弃用警告（4.18 起），**不用它**；
  本机 `jsonschema/__main__.py:4` 的 `DeprecationWarning` 原文把 CLI 需求指向
  `check-jsonschema`——这条是这一格该借的方向，不是该装的包。
- **候选 B：`check-jsonschema`**（经 GitHub MCP 真读 `README.md`，commit `0494aa7`）：
  jsonschema 之上的 CLI + pre-commit hook，本地/远程 schemafile、远程自动缓存、
  `pipx`/`brew` 安装、示例 rev 0.38.2。功能匹配、维护活跃；但**未安装、需装包，
  门与 CI 不能依赖外部进程**，且它底层就是同一个 jsonschema ⇒ 复用不了引擎，
  只借它「把 schema→实例的绑定写成可声明的东西」这个形状（本仓按习惯做成
  「约定 + AST 现抽」，不做手抄映射表）。
  它的 mapping 配置文件的**具体选项名本轮没查到**（readthedocs 一个 URL 404、
  PyPI 页要 JS），所以这里不引用它的选项名。
- 候选 C `fastjsonschema`：本轮**没有**读它的文档，不作评价。
- 元校验的方言：五份契约都写 `$schema: 2020-12`。实测两档在**现役五份上都是 ok**
  （0 处翻红），但**不等价**：`prefixItems: 5`、`unevaluatedProperties: "x"` 两类
  在 Draft7 元校验下放行、在 2020-12 下报红——这两条已作为注入进电池/用例。

## 七、端到端实测（提交后的树）

```
$ .venv/bin/python -m aipd_os.scripts.schema_check
[schema-check] OK   cad_contract.schema.json (schema)
[schema-check] OK   assets/templates/cad_contract.json <- cad_contract.schema.json
[schema-check] OK   fact.schema.json (schema)
[schema-check] OK   assets/templates/fact.json <- fact.schema.json
... 五份全 OK
[schema-check] 全部通过                                              rc=0

$ aipd interfaces --repo . --out /tmp/ic30/b.json
  85 条接口：{'cli_command': 56, 'mcp_tool': 6, 'json_schema': 5, 'file_format': 5,
             'http_surface': 2, 'egress_consumer': 11}
  判定=incomplete（未取证 2、没有实例被按它校验的契约 0、绑定读不到 0、
                  只判存在的落点 0、形状副本与权威不一致 0、权威读不到 0、定义件缺失 0）   rc=0

$ aipd interfaces --repo . --out … --strict                            rc=4
```

## 八、这一片没做的事

1. `unverified` 剩 2 条：`manual_chain_state.schema.json` 与
   `supervisor_project.schema.json` 今天没有任何**消费方**用例点它们
   （两份都有实例被按约定校验过，但没有真读过它们的测试）。前一条在第 30 片里
   从「已被取证」**改回**「未取证」——那是 §四 第 3 条的第三个面：量具自己的用例
   点了这个名字，排除之后就不该再算成别人验过它。
2. **`contracts_without_instance` 的判据仍只看模板**：校验的是 `assets/templates/*.json`
   这类形状样本，不是真产物落盘文件；真产物的形状由 §四 的门负责，两边口径不同是刻意的。
3. `interfaces` 还没接进 `aipd release check`，发布门也不读它的 `verdict`（属主裁决，
   与第 27/28 片「门读 ECO 但口径不同」同族）。
4. 逐端点的出网明细（URL/超时/重试）仍没有；`egress_consumer` 只到「谁 import 了出网点」。
5. `quality_gate` 的形状门按**同名词干**配契约；deliverable 类型名与契约文件名不同的
   那 39 类今天仍没有契约可配（要补的是契约，不是门的规则）。

## 九、收口读数

| 项 | 读数 |
| --- | --- |
| 全量用例 | 2074 → **2121** 条（+47：`test_interface_contract` 18→41、`test_schema_check` 3→16、新增 `test_quality_gate_shape` 11）。收口跑（提交 `b6c2a32` 之后、带 `AIPD_SOURCE_COMMIT=tag`）：**2118 passed / 0 failed / 3 skipped**，156.41s |
| 中间两轮 | 第一轮（重锚前）`2 failed, 2116 passed`——红的正是 `test_packaging.py` 那两条哈希对照；第二轮（只刷了 `RELEASE_MANIFEST`、`SOURCE_MANIFEST` 还没重算）`1 failed`——这条不是回归，是**清单生成顺序**：`SOURCE_MANIFEST` 只由 `release_evidence.py` 产，`regenerate_release_manifest.py` 只刷 `RELEASE_MANIFEST` |
| 命令面漏提交这一族 | 本片**没有再犯**，并补了第 29 片缺的那一步：代码提交之后另开 `git worktree add /tmp/s30head HEAD`，用 `PYTHONPATH` 指到签出树（避开 editable 装回指工作树）重跑全量 ⇒ **2118 passed / 0 failed / 3 skipped**，rc=0，126.34s，并先断 `aipd_os.__file__` 真的落在 `/tmp/s30head/src/…` 再采信这个读数 |
| 被哈希面 | 616 → **619**（`src/aipd_os/schema_binding.py`、`tests/test_quality_gate_shape.py`、`assets/templates/fact.json`），`SOURCE_MANIFEST` 与磁盘逐条一致（`test_packaging` 8 passed） |
| `PROVENANCE.test_report` | `2118 passed / 0 failed / 总 2121`，报告 `docs/audit/pytest-report-v5.6.0.json`（`sha256=ea50b195d379…`）；`source_commit = a66040520139…`（tag） |
| 发布门 `--release-ready --tag` | **8/8 绿**，`release_ready: true`，rc=0（在 `7994516` 的干净树上） |
| `audit_repo --strict` | rc=1，唯一 ✗ 仍是既有裁决那条 tag 锚点红（`manifest=a66040520139… vs HEAD=7994516afbda…`） |
| ruff（CI 范围 `src tests state_service`） | All checks passed!（`scripts/` 里那条 E501 是本片之前就存在的旧债，未顺手改） |
| mypy（`src tests`） | Success: no issues found in **419** source files（+2：`schema_binding.py` 与其用例） |
| C6 普查 | 15 项 = **15 / 0 / 0**（档位不变，note 换成本片的真读数）；`--self-test` **7/7** |
| 变异电池 | 本片 `/tmp/slice30-mutations.py` **21 条：杀 21 / 活 0 / 注入无效 0**。同树复跑：第 29 片 **12/12**（其 C6 锚因本片把判定拆成 `verdict_of()` 而重指）、第 27 片 **17/17**、第 28 片 **15/15** |
| 电池放走过的注入（记下来） | 第一轮 17 条里 **F5 与 H4 存活**，两条同因：断言被别的合取项救活。F5 是整体断 `verdict == incomplete`，而 `unverified` 本来就非空；H4 是 `digital_thread_complete` 的其余六个产物在夹具里根本不存在，形状判据删掉它照样 False。修法不是加断言而是**把判定抽成 `verdict_of()` 逐轴参数**（七轴各一发必须开火）与**把夹具铺满**（六件产物先建，让形状成为唯一变量）。之后新增 F9 也是同一族：取证那一面被量具自己的用例喂。这正是「复合门的每一条子句都要有自己的最小对」在本仓的第三次落地 |

## 十、这一片怎么被复核

```
.venv/bin/python -m aipd_os.scripts.schema_check              # 五份契约 OK，rc=0
.venv/bin/python -m pytest tests/test_schema_check.py \
    tests/test_interface_contract.py tests/test_quality_gate_shape.py
.venv/bin/python /tmp/slice30-mutations.py                     # 21/21
aipd interfaces --repo . --out /tmp/ic30/b.json                # 85 条，七轴读数见 §七
