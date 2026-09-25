# F-C6 第 29 片：接口清单与契约证据（C6 最后一格零实现，只闭可自查的那一半）

日期：2026-09-25　归属：`industrialize.release_evidence`
上一片：`docs/audit/ECO_DELIVERY_BASELINE_F-C6-ECO_2026-09-25.md`（交付物基线，第 28 片）

## 一、这一格以前为什么是零实现

`scripts/c6_coverage.py` 里「ICD」这一项从第 26 片起就一直挂着 `absent`，note 写着原因
（逐字）：

> 接口控制文档：**按形状就不该由本仓单方产**。…§1.3「Responsibility and Change Authority」
> 与 §3.1.2「Interface Responsibilities」两节的内容只能由**对侧**给；…
> 可自查的那半（接口清单、数据形状、每个接口的定义件版本 + sha256、逐接口用例证据）
> 另出一份《接口清单与契约证据》，**不叫 ICD**（该片尚未做）。

所以这片做的正是「那另一半」，并且**不把它叫 ICD**：文档标题里带着「不是 ICD」，
正文带着 `not_icd_because` 一句理由，另有常驻用例钉住这两处（只改一个标题就想把
它冒充成 ICD，会让用例判红）。档位上「ICD」从 `absent` 升到 `producer`，
与「装配/维护只升装配那一半」是同一形状：**升的是可自查的一半，签署的那半永远不升**。

## 二、选型（本回合真打开过的页面）

| 候选 | 功能匹配度 | License | 维护活跃 | 安全风险 | 代码质量 | 适配成本 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Pact（consumer-driven contract）** `docs.pact.io` | 高（概念正对：契约由消费者测试生成、"验证"= 对 provider **公布过的结果**） | Apache-2.0 | 活跃，有 python 工具链 | 需要 broker/发布链路这套基础设施 | 成熟 | 只面向 HTTP/JSON 交互；本仓四类接口（CLI 命令、JSON Schema、文件格式、MCP 工具）装不进它的 interaction 形状 | **借两条纪律**：每条点名两侧；「未被验证 ≠ 已验证」。不引入 |
| **OpenAPI v3.2.1** | 中（该页自述：语言无关的**接口描述**，但不断言服务端实现） | Apache-2.0 | 现行标准 | — | — | 只覆盖本仓 2 个 HTTP 面 | **借那句边界**：清单不证明对侧真按它实现 |
| **check-jsonschema** | 低-中（把实例对着 schema 验） | 页面标注 **NOASSERTION**（License 不明） | 活跃 | License 不明 ⇒ 不宜进依赖 | — | 新外部 CLI，且无机器可读报告 | 不引入；本仓已有 `jsonschema` 库，够用 |

选定：**本地清单模块，零新依赖**，借上面两处的一个纪律 + 一句边界。理由：
本仓接口面的多数（56/85）是 CLI 命令与文件格式，任何现成契约工具都不覆盖这一类，
而它们恰恰是最需要「定义件 + 取证用例」的地方。

## 三、判据形状

`aipd interfaces` 产出 `aipd.interface_contract.v1`（+ 同名 `.evidence.json` 侧车，
拼法仍走 `cad/evidence.sidecar_path` 那唯一一处）。今天真跑出的分母：

```
85 条接口：{'cli_command': 56, 'mcp_tool': 6, 'json_schema': 5,
            'file_format': 5, 'http_surface': 2, 'egress_consumer': 11}
判定=incomplete（未取证 3、声明了但没人消费 3、定义件缺失 0）
```

每条接口固定带五样东西：**定义件路径 + 当时的 sha256**、**取证用例**、
**这一类一般证到什么**、**证不到什么**、**方向与对侧**。三条形状规矩：

1. **分母一律重算**：CLI 取自 `command_contract.PUBLIC_COMMANDS`；MCP 取自
   `state_service/mcp_server.py` 里 AST 能看到的 `def mcp_*`；schema 清单取
   `assets/schemas/` 目录实况；出网消费者按 `aipd_os.net.http` 的 import 反查。
   抄计数会在改名那天静默漏项（注入 C1 专门演这件事）。
2. **「被引用」不等于「被验证」**：`verified_by` 用 AST 解析到「文件在 + 符号在 +
   真收得到 test」，解析不到的进 `unverified`。这套自制解析另有一条常驻用例与
   `pytest --collect-only` 的**真读数对齐**（数量必须相等），并配 must-not-fire 一侧：
   真被引用的 `cad_contract.schema.json` 不许躺进孤儿清单——否则「反查消费者」坏掉时
   孤儿清单会整栏膨胀而没人看得出（注入 C2 演这个）。
3. **易变/易假绿的两个洞**：空的 test 文件不算取证（注入 C4）；`proves` 与
   `does_not_prove` 折叠成同一句要判红（注入 C5）——一句「已验证」不算边界。

判定三态与退出码（`verdict_rc`）：**定义件不在盘上 ⇒ 必退 4，与 `--strict` 无关**；
有孤儿契约或未取证行 ⇒ `incomplete`，默认只写进文档，`--strict` 才拦。
不把今天的 3 个孤儿契约做成永远红的硬门（那只会训练人忽略门），
也不把它们折算成通过（那正是本片防的方向）。

## 四、落点

| 位置 | 动作 |
| --- | --- |
| `src/aipd_os/interface_contract.py`（新） | `build` / `write` / `verdict_rc` / `resolve_tests` / `scan_consumers` / `schema_rows` / `cli_rows` / `mcp_rows` / `http_rows` / `egress_rows` / `PROVES` / `FILE_FORMAT_CONTRACTS` |
| `src/aipd_os/cli/commands_release.py` | `cmd_interfaces`（人读输出含三条发现与「为什么不叫 ICD」） |
| `src/aipd_os/cli/main.py`、`command_contract.py` | `interfaces` 公开命令与登记（`--repo` / `--out` / `--strict` / `--json`） |
| `scripts/c6_coverage.py` | 「ICD」档 `absent → producer`（可自查那一半）+ note 换成今天的真读数；`_an_absent_item()` 改为**没有零实现项就当场造一个**（否则这条反证因今天的仓恰好没有 absent 项而失去可红性） |
| `tests/test_c6_coverage.py` | 棘轮 14/0/1 → **15/0/0**、`absent == set()` |
| `tests/test_interface_contract.py`（新） | 18 条（分母重算 5、定义件 2、取证解析 4、孤儿契约 2、退出码 1、CLI 面 4） |
| `SKILL.md` / `README.md` / `registry_data.py` | 公开命令数 55 → 56、命令组清单、能力行 |

## 五、今天这份清单暴露的事实（**本节初稿有一条错的推论，2026-09-25 收口时更正，见下**）

### 初稿说错了什么

初稿写的是：`assets/schemas/` 里三份 schema「全仓没有任何文件按名字引用 ⇒ 这是一张没人校验的契约」。
**前半句是真，后半句是假的。** 假在探针看不见另一种绑定方式：

- `src/aipd_os/scripts/schema_check.py` 不用文件名字面量绑实例，它按**命名约定**绑——
  `name = path.stem.removesuffix(".schema")`，再到 `DATA_DIRS = ("templates", "assets/templates")`
  里找同名 `<name>.json`，找到就 `jsonschema.validate(data, schema)`（`schema_check.py:41,75`）。
  所以那句 schema 文件名在四行代码里**一个字都没出现过**，按名字反查 `.py` 的 `scan_consumers`
  必然读不到它。
- 而这个脚本**在 CI 里跑着**：`.github/workflows/ci.yml:45` 有 `schema-validation` job，
  `:58` 就是 `python -m aipd_os.scripts.schema_check`。
- 现算（2026-09-25，`.venv/bin/python -m aipd_os.scripts.schema_check`，rc=0）：
  **五份 schema 全部过了元校验**，其中 `cad_contract` / `manual_chain_state` /
  `project_checkpoint` / `supervisor_project` **四份有约定绑定的实例并被真校验**
  （`OK assets/templates/<name>.json <- <name>.schema.json`）；
  只有 `fact.schema.json` 落 `INFO … 无同名模板数据文件（跳过数据校验）`。

⇒ 正确的读法是：孤儿契约 **3 份 → 1 份**（只剩 `fact.schema.json`），而且它的理由是
「**没有任何实例被按它校验过**」，不是「没人引用这个文件名」。
判据本身要改（第 30 片）：绑定目录用 AST 从 `schema_check.py` **现抽**，不抄常量表——
抄一份就是再造一个会漂移的镜像。

### 初稿里那条站得住的，以及一条更重的

- 站得住：`project_checkpoint` 的**落点**只判存在、从不核形状。
  `scripts/outcome_acceptance.py:22` 是 `exists(root,'state/project_checkpoint.json')`，
  而 `exists()` 只要求 `is_file() and st_size>0`；`scripts/quality_gate.py:22` 的 `REQ['G9']`
  按 deliverable **类型名**在不在判（现抽：`REQ` 共 40 个类型，**只有 `project_checkpoint` 一个有同名 schema**，
  而 `deliverables` 表带 `path` 列，见 `src/aipd_os/state/db.py:156`）
  ⇒ 形状门有明确落点，且爆炸半径就是 1 类。字段改坏了两道门照样绿。
- 更重的一条（收口时才发现，留给第 30 片当主判据）：**同一个「事实」形状在两处定义，而且已经漂移，
  其中一份与数据库权威枚举矛盾**。权威是 `src/aipd_os/state/db.py:48`
  `FACT_STATUSES = {"V","S","C","E","A","P","T","R","U"}`（9 值，含 `U`）；
  `assets/schemas/fact.schema.json` 的 `status.enum` 同样含 `U`，
  且 `tests/test_truth_evidence_semantics.py:154` 有常驻用例钉住「必须包含 U」；
  而 `assets/schemas/project_checkpoint.schema.json` 的**内联** `$defs.fact`
  `status.enum` **只有 8 值、缺 `U`**，另外多要求 `fact_id`、少 `tolerance`/`version`。
  `U` 不是纸面值：`src/aipd_os/research/models.py:38` `EPISTEMIC_UNKNOWN = "U"`，
  `src/aipd_os/idea/evidence_graph.py:188`、`src/aipd_os/product_intelligence/gate_criteria.py:145,372`
  都在按 `U` 判定 ⇒ 一份从状态库导出的 checkpoint 只要含一条 `U` 事实，就**在本项目自己的契约下非法**。
  今天的语料读数：全仓 **0 条**真 fact 文档（`assets/templates/project_checkpoint.json` 的
  `facts` 是空数组；`tests/fixtures/golden_projects/*/project.json` 的 `facts` 是 `{'params': …}`，
  另一种语义），所以两档判据**今天 0 翻转**——这说的是「今天无差」，**不是**「两条判据等价」。

本片只做清单与判据，不顺手把上面两条接进门——第 30 片专做这两条（判据修正 + 落点形状门 +
`enum` 拿 `FACT_STATUSES` 当边界对象核对）。另记一处小的文档漂移：
`command_contract.py:301` 的注释 `EXPECTED_PUBLIC_COUNT = len(PUBLIC_COMMANDS)  # 当前为 29`
与实际 56 早已不符；常量本身是自算的，所以没有实害，注释留待第 30 片顺手改。

## 六、端到端实测

> 下面是**当时的真读数，原样保留**（含那三条 `[发现]` 的文字）。三条发现里
> 「按名字引用不到」是真的，「⇒ 没人校验的契约」是错的推论——见 §五 更正。
> 判据修正与它应得的读法在第 30 片；这份产物今天重跑仍然是下面这些数。


```
$ aipd interfaces --repo . --out /tmp/…/interfaces.json
接口清单与契约证据：/tmp/…/interfaces.json（+ 同名 .evidence.json 侧车）
  85 条接口：{'cli_command': 56, 'mcp_tool': 6, 'json_schema': 5, 'file_format': 5,
             'http_surface': 2, 'egress_consumer': 11}
  判定=incomplete（未取证 3、声明了但没人消费 3、定义件缺失 0）
    [发现] 全仓没有任何文件按名字引用 manual_chain_state.schema.json ⇒ 这是一张没人校验的契约
    [发现] 全仓没有任何文件按名字引用 project_checkpoint.schema.json ⇒ 这是一张没人校验的契约
    [发现] 全仓没有任何文件按名字引用 supervisor_project.schema.json ⇒ 这是一张没人校验的契约
  为什么这份东西不叫 ICD：ICD 的「责任与变更授权」「接口职责」两节只能由对侧给；
             本仓单方产它等于伪造签署（NASA SE Handbook 附录 L 实读，2026-09-25）   rc=0

$ aipd interfaces --repo . --out … --strict        # 同一份文档，只换档位
  --strict：判定不是 complete，按不放行退出                                          rc=4
```

侧车与文档的一致性由用例核：`document_sha256` 必须等于落盘那份的现算哈希，
侧车名必须等于「产物全名 + `.evidence.json`」。

## 七、这一片没做的事

1. **契约的校验覆盖率没被核**（§五 更正后的读法）：五份 schema 里 4 份由
   `schema_check.py` 按命名约定绑实例并真校验，只有 `fact.schema.json` 落
   `INFO …（跳过数据校验）`——本片既没给缺实例的那份补实例，也没把「INFO 跳过」
   变成一条具名盲区；这两件都留给第 30 片。
2. **接口清单不进发布门**：它今天是**产物**，不是判据；要不要让
   `production_release_gate` 读它的 `verdict`，得先定「C6 是否要求接口零缺口」，
   那是属主裁决（与第 27/28 片「门读 ECO 但口径不同」同一族问题）。
3. **`egress_consumer` 只到「谁 import 了出网点」这一层**，没有逐端点列 URL/超时/重试策略
   （各 provider 模块里形状不同，逐个抽出来会变成一次跨模块整理）。
4. **MCP 工具面没有对端一致性证明**（那需要 MCP 客户端侧的契约，即 Pact 那一半，
   本仓给不了）。
5. `interfaces` 命令本身没接进 `aipd release check`。
6. **产物刻意不提交进仓根**：`interface-contract.json` 由命令现取（与 `aipd release manifest`
   同一口径）。提交进仓库就等于再造一个「声明了但没人刷新」的东西——发布链里那份必须每轮重锚
   的 `SOURCE_MANIFEST` 已经够贵了。

## 八、收口读数

| 项 | 读数 |
| --- | --- |
| 全量用例 | 2056 → **2074** 条（+18，全在 `tests/test_interface_contract.py`）。收口把两件事**合成一跑**：带 `AIPD_SOURCE_COMMIT=tag` 的锚定跑同时当干净全量跑用 ⇒ `2071 passed / 0 failed / 3 skipped`（总 2074），315.27s |
| 首跑（重锚之前） | `2 failed, 2069 passed, 3 skipped`（260.26s）——红的正是 `tests/test_packaging.py::test_release_manifest_hashes_match_disk` 与 `::test_source_manifest_hashes_match_disk`，属预期，随重锚闭 |
| 命令面漏提交（**本片真正的事故**） | `3ab466a` 提交时 `src/aipd_os/cli/commands.py` 的镜像行没进暂存区，而同一次提交里的 `main.py:385` 用 `COMMAND_FUNCS["interfaces"]` 取函数 ⇒ **HEAD 上任何 `aipd` 调用都 KeyError**。在 `3ab466a` 的干净签出（`git worktree add /tmp/headcheck 3ab466a` + `PYTHONPATH` 指签出树，避开 editable 指回工作树）里实测：`build_parser()` 抛 `KeyError: 'interfaces'`；`test_command_coverage.py + test_interface_contract.py + test_cli.py` **28 failed / 25 passed**。之前那次「全量绿」是在**带着这行的工作树**上跑的，不是提交后的树。修法是修向前进 `3d096c4`，不 amend |
| 被哈希面 | 614 → **616**（`src/aipd_os/interface_contract.py` + `tests/test_interface_contract.py`），`SOURCE_MANIFEST` 与磁盘逐条一致（`hash_mismatch_count: 0`） |
| `PROVENANCE.test_report` | `2071 passed / 0 failed`，报告 `docs/audit/pytest-report-v5.6.0.json`（`sha256=bc9ccd439e5e…`）；`source_commit = a66040520139…`（tag，按既有裁决不重锚到 HEAD） |
| 发布门 `--release-ready --tag` | **8/8 绿**，`release_ready: true`，rc=0（在产物提交 `cf7f573` 之后的干净树上跑，`git status --short` 空） |
| `audit_repo --strict` | rc=1，唯一 ✗ 仍是那条既有裁决红：`Provenance source commit mismatch: manifest=a66040520139… vs HEAD=cf7f573c3285…` |
| ruff（CI 范围 `src tests state_service`） | All checks passed! |
| mypy（`src tests`） | Success: no issues found in **417** source files（+2：`interface_contract.py` 与其用例） |
| C6 普查 | 15 项 = **有生产者 15 / 只有校验方 0 / 零实现 0**（档位不变）；`--self-test` **7/7 条注入都被抓住** |
| 变异电池 | 本片 `/tmp/slice29-mutations.py` **12 条：杀 12 / 活 0 / 注入无效 0**；同树复跑第 27 片 **17/17**、第 28 片 **15/15**（上一片记录过锚点会随改形腐化，这次三条电池都在最终树上重跑，无一「注入无效」） |
| 端到端 | §六 那两条命令在提交后的树上重跑，读数见下节的漂移说明 |

### 收口重跑发现的两处读数漂移（都是量具自己的问题，登记给第 30 片）

`aipd interfaces --repo . --out …` 在提交后的树上重跑得 **86 条 / egress 12**，
不是 §六 当初记的 85 / 11。差的那一条是 **`src/aipd_os/interface_contract.py` 自己被算成了出网消费者**：
`egress_rows()` 的排除条件只有 `if not r.endswith("net/http.py")`，而本模块
`PROVES["egress_consumer"]` 的文案里写着「唯一出网点 `aipd_os.net.http`」——
**量具的描述文本把它自己送进了自己的分母**。同族第二处：`egress_consumer` 12 条里有 3 条是
`tests/…`（`test_net_http.py`、`test_net_egress_convergence.py`、`test_completion_endpoint.py`），
与 9 条生产模块混在同一个 kind 里数，「产品侧有几个消费者」这句话因此读不出来。
两处与 §五 那条错推论同源：**按字面量反查**看不见约定绑定，也会看见不该算进去的自引用。

### 这一片该被怎么读

§五 初稿把「按文件名反查不到」推成「没人校验的契约」，**是错的**；收口时才发现
`schema_check.py` 按命名约定绑实例并真跑校验，而且挂在 CI 上。孤儿从 3 份更正为 1 份
（只剩 `fact.schema.json`，理由是「没有实例被按它校验过」），并翻出一条更重的：
`project_checkpoint.schema.json` 的内联 `$defs.fact` 与权威枚举
`src/aipd_os/state/db.py:48 FACT_STATUSES`（含 `U`）矛盾。两处都在第 30 片闭。

### 第 30 片的前置实测（不属于本片读数，只是把代价先量了）

形状门若接进落点，代价是**今天 0 处翻转**：全仓按「八个必需键里命中 ≥6」筛 checkpoint 文档，
只有 1 份真文档 `assets/templates/project_checkpoint.json`（`facts` 是空数组，
现役内联档与 `$ref`+补足档都判合法）；另一处命中是 schema 文件自己的 `properties`，
属筛法的假阳性，已排除。三档判据对同一份重建文档的对照表在《第 30 片》文档里。

