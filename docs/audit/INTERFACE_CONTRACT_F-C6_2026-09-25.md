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

## 五、今天这份清单暴露的事实（不是本片的活，逐条登记）

`assets/schemas/` 里三份 schema **全仓没有任何文件按名字引用**：
`manual_chain_state.schema.json`、`project_checkpoint.schema.json`、
`supervisor_project.schema.json`。

它们不是没人碰的名字，而是**碰的是文件、不是契约**（逐条核过，2026-09-25）：

- `project_checkpoint`：`scripts/quality_gate.py:33` 的 G9 要求这个交付物**在**，
  `scripts/outcome_acceptance.py:22` 只 `exists(root,'state/project_checkpoint.json')`
  ——**存在性有门、内容不合形没人管**：字段改坏了两道门照样绿。这才是「没人引用 schema」
  的实际后果，也是这张清单最该被读出来的一条。
- `manual_chain_state`、`supervisor_project`：除普查与能力表的自述文字外，
  `src/`、`scripts/`、`tests/`、`state_service/` 里没有任何引用点。

本片只做清单与判据，不顺手给它们接校验方——接谁、怎么接是各自的范围决定，
硬接会把这片变成一次跨模块重构。（另记一处小的文档漂移：
`command_contract.py:301` 的注释 `EXPECTED_PUBLIC_COUNT = len(PUBLIC_COMMANDS)  # 当前为 29`
与实际 56 早已不符；常量本身是自算的，所以没有实害，注释留待下轮顺手改。）

## 六、端到端实测

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

1. **三份孤儿 schema 没有接校验方**（§五）。
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

（全量、电池、被哈希面、门与重锚见下方补记。）
