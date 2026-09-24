# F-REG-01：能力矩阵的「入口可调用」证据此前是装饰性的

日期：2026-09-24　范围：`AIPD-OS`　本文所有读数为本机实测。

## 1. 结论

`docs/audit/capability_matrix.json` 声称是「含运行时 probe 证据」的能力矩阵，但
`probe.entry_callable` 不参与任何判定、也没有任何门禁要求它为真。结果：78 行里
**11 行**入口解析不到可调用对象，其中 `research.attachment_reading` 还被判成
`fully_implemented`。现在：入口字符串写错的 4 条改对、探针的一处假负修掉、
剩下的 5 条全部是「有意留空的 external 能力」并由常驻门禁逐条声明。

## 2. 修前实测与逐条归类

`entry_callable=false` 的 11 行分三类（此前全挤在同一个 false 里，所以看不出谁在撒谎）：

| 类 | 能力 | 声明的 entry_point | 真实情况 |
|---|---|---|---|
| 标签写错 | `cad.2d_drawings` | `src/aipd_os/cli/commands_drawing.py:cmd_drawing` | 文件路径形态；探针按 `/` 拆候选，拆成 `src`/`aipd_os`/… 全碎 |
| 标签写错 | `cad.text_to_cad` | `cad_adapter` | 裸词，不是模块路径 |
| 标签写错 | `manual.real_image_generation` | `imggen.adapter` | 少包名；且指向模块而非可调用对象 |
| 标签写错 | `research.multi_source_search` | `research.search_papers.selftest` | 该函数**不存在**（真实入口是同模块的 `search_papers`） |
| 探针假负 | `research.attachment_reading`、`research.fulltext_fetch`、`research.multi_source_search` | `research.source_worker.run_source` 等 | 写法正确，但 `scripts/research/*.py` 用顶层 `import _http_runtime`，探针只临时加了 `scripts/` ⇒ 导入失败 |
| 有意留空 | 5 行（`research.standards_regulations`、`research.patents_competitors`、`cad.assembly_constraints`、`cad.continuous_kinematics`、`cad.cae_fatigue`） | `None` | `external_dependency=true`，没有本地入口 |

`probe_classification` 的文档里写明「入口可调用性不作为降级门槛……避免标签老旧大面积误判」：
理由（避免误判）成立，但代价是**错的入口字符串永远不会判红**，于是标签一直烂着。

**而且它已经被测试当成基线钉住了**：`tests/test_cad_drawings2d.py::TestCapabilityDeclaration`
第 313 行原来是 `assert cap.entry_point == "src/aipd_os/cli/commands_drawing.py:cmd_drawing"`
——一条本意是"登记必须指向真实入口"的用例，把探针解析不了的那个错形态当成了期望值。
这条只在改完数据后才暴露（改数据 → 它判红），说明它测的是字符串而不是"能不能取到真身"。
现改为 `getattr(importlib.import_module(mod), attr) is cmd_drawing` +
`probe_entry_callable(...) is True`：与书写形态无关，且钉的是同一个函数对象。

## 3. 技术选型

本轮只动仓内的登记表数据与探针的 `sys.path`，不引入任何依赖，属"影响范围明确的局部
修复"，按目标里的例外条款跳过外部检索（无新组件可比较）。三个仓内做法：

- **A（选定）**：数据改对 + 探针补 `scripts/research` + 常驻门禁（不可解析的入口必须被
  逐条声明；`fully_implemented` 不得压在解析不到的入口上；分母前提与注入反证各一条）。
  代价：门禁依赖 import 真模块，跑起来会带入 cadquery 等重包（实测该文件 1.9s）。
- **B**：只把 `entry_callable` 接进 `probe_classification` 当降级条件。会把"标签写错"
  降级成"能力没实现"——把数据缺陷伪装成能力缺陷，方向错。
- **C**：只改 4 条字符串，不加门禁。下次再写错依旧无人发现。

## 4. 落点

| 位置 | 内容 |
|---|---|
| `src/aipd_os/registry.py` `probe_entry_callable` | 临时 path 同时加 `scripts/` 与 `scripts/research/`；文档写明"否则真入口会被读成不可调用，这一列就失去意义" |
| `src/aipd_os/registry_data.py` | `cad.2d_drawings` → `aipd_os.cli.commands_drawing.cmd_drawing`；`cad.text_to_cad` → `aipd_os.tool_adapters.cad_adapter.CadAdapter`；`manual.real_image_generation` → `aipd_os.imggen.adapter.ImageGenAdapter`；`research.multi_source_search` → `research.search_papers.search_papers` |
| `tests/test_capability_entry_surface.py` | 5 条：逐条声明门禁、`fully_implemented` 不得压空入口（分类现算）、分母前提、注入反证（路径形态与裸词必须读 false，同一能力的正确写法必须读 true）、脚本互引入口不得复发假负 |
| `docs/audit/capability_matrix.{json,md}` | 重生成：`entry_callable=false` 11 → **5**，且这 5 条与声明表逐一对应 |

## 5. 变异对照

| 变异 | 实测 |
|---|---|
| 探针退回只加 `scripts/` | **4 红**（含 `fully_implemented` 那条与分母前提） |
| 把 `cad.2d_drawings` 的入口改回文件路径形态 | **1 红**（逐条声明门禁） |

还原后 13 条（本文件 5 + 矩阵/导出 8）全绿。

## 6. 已知边界

- 分类仍不看 `entry_callable`（本轮没有推翻那个设计，只是让这一列可信）；
- 门禁要求 ≥90% 入口可解析，是"数据整体没烂掉"的底线，不是允许 10% 出错的额度——
  新增行必须走声明表；
- `manual.real_image_generation` 的适配器按自身 limitation 仍是空壳（`external_dependency`），
  本轮只修它入口名字写错，没有声称图像生成能力变强；
- `research.multi_source_search` 的 `external_dependency=False` 与"需网络可用"之间的口径差
  未动（属分类语义问题，另行裁决）。

## 7. 复算入口

```bash
cd /Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
export PATH="$PWD/.venv/bin:$PATH"
python -c "
import json
m=json.load(open('docs/audit/capability_matrix.json'))
rows=[c for d in m['domains'] for c in d['capabilities']]
print([c['id'] for c in rows if not c['probe']['entry_callable']])"   # 期望：5 条，全在声明表里
python -m pytest tests/test_capability_entry_surface.py tests/test_capability_matrix.py -q
python scripts/capability_matrix.py --repo . --out docs/audit
```
