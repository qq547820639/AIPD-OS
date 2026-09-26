# F-LINEAGE-DXF 第 46 片：给「图纸声明 → DXF 制品」补血缘生产者

日期：2026-09-26 归属：Product Truth 血缘链 / CAD 出图命令面
状态：已闭（生产者接线 + 常驻 10 条 + 电池 10 条 + 夹具窗口与输入键两处按实测补漏）
落点：`src/aipd_os/cad/dxf_lineage.py`、`src/aipd_os/cli/commands_drawing.py`
用例：`tests/test_drawing_dxf_lineage.py`

## 一、缺口是怎么量出来的

第 43 片接上 CTQ→图纸声明、第 45 片给声明接上返工执行器之后，链条第三跳仍断着：
`truth_lineage` 里只有 `CTQ → 声明` 这一条边，图纸本身既没有版本记录也没有边。
本轮动手前用 AST 扫 `add_edge` 调用点（`tests/test_drawing_spec_lineage.py::TestProducerRatchet`
那把尺子的判据），`src/aipd_os/` 下登记的生产者是 3 处 PI/truth 侧 + `spec_lineage.py` +
`spec_rework.py`，**没有一处写图纸制品**——这是「第三跳断」的源码证据，不是推测。

后果的形状：改一条 CTQ → `aipd truth propagate` 把声明标 stale、生成返工任务，
而按旧声明画出来的那张 DXF 在库里根本不存在，传播打不到它。读 `--json` 的人看到
「affected 已处理」会把图纸一并当成处理过了。

## 二、制品身份怎么定（本轮实读的三条来源 + 一次实测）

问题：一张 DXF 的「同一版」与「新版」按什么判。

| 候选 | 来处（本轮真实读到的） | 功能匹配度 | License | 维护活跃度 | 安全风险 | 代码质量 | 适配成本 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A 按输出字节哈希（`sha256(dxf)`） | 本仓已有 `evidence.sha256` | 高（实现最省事） | — | — | 无 | — | 零 | **不选**：实测会把时间戳读成一次工程变更（见下） |
| B Bazel 式「动作键 = 输入 + 命令参数」 | Bazel 官方 Glossary 原文：Action Cache 是 "An on-disk cache that stores a mapping of executed actions to the outputs they created"；Action Key 是 "The cache key of an action" | 高：本仓的「出图」正是一个动作（声明 + part/revision/views/scale/sheet） | Apache-2.0 | 活跃 | 无（不引依赖） | 高 | 低：只借判据形状 | **选定** |
| C Reproducible Builds 式「先抹时间戳再比字节」 | reproducible-builds.org §Timestamps：提出 `SOURCE_DATE_EPOCH`；无法改上游时应对产物 "remove the timestamps entirely or to normalize them to a predetermined date and time"（strip-nondeterminism）；也可 libfaketime，但文档自己提示可能打断并行编译 | 中：解决的是「同一动作的两次落盘要可比」，不解决「输入变了要认出来」 | MIT（工具本身） | 活跃 | 无 | 高 | 中：要为 DXF 写一个字段归一化器，且要先确认 ezdxf 是否吃 `SOURCE_DATE_EPOCH`（**本轮未核实**） | 备选：可作为将来「图纸字节也要可比」时的做法 |
| D Nix fixed-output derivation | **本轮未读到**：`nix.dev/concepts` 页面无相关内容、`nixos.org/manual/.../derivations` 重定向后 404 | — | — | — | — | — | — | 不引用（不声称读过） |

实测（`/tmp/s46/bytes_probe.py`，2026-09-26 跑）：同一输入连跑两次 `aipd drawing generate`，
两份 `.dxf` 各 13170 行、**只有 2 行不同**，差的是 `$TDCREATE` / `$TDUPDATE` 那一对儒略日时间戳
（`855ce37c…` vs `d643913f…`）。所以 A 会把「什么都没变」读成「出了一版新图」，
而库里一版图纸对应一次真实工程变更这件事，是第 44/45 片整套返工与发布证据的前提。
选 B：签名 = **全部出图输入**（模型摘要 + 声明内容哈希 + part/revision/views/scale/
sheet/material/剖切/放大），DXF 自己的 sha256 仍写进 `metadata.dxf_sha256` 当**观测**
（图有没有被人动过，靠它判），但不当键。

**「出图参数」那一半起初是漏的，收口前实测复现出来的**（`/tmp/s46/sig_gap.py`）：
同一 `--out`、同一参数，分别用仓库里两个真不同的 STEP
（`releases/golden-projects/B-cad-engineering-change/bracket.step` 摘要 `4efdb74a…`、
`bracket_v2.step` 摘要 `09fe94e0…`）各出一次图——
* 修之前：两次落库的 `inputs=` 前缀**一模一样**（`30599f43…`），图纸记录数 1，
  也就是**两张图被记成一版**；
* 修之后：记录数 2、签名分别是 `29c694b8…` / `22f16d04…`。
模型摘要的取法（`model_input_digest`）：给了 `--step`/`--native` 按源文件内容摘要；
都没给则按内置黄金模型的 `{name, parameters}` 规范哈希——那是「同一个输入」的
可复算定义，不是文件名。

## 三、四条判据

1. **传播第三跳到得了**：`声明记录 → 图纸记录` 的 `affects` 边写进 `truth_lineage`，
   `PropagationEngine.on_upstream_changed(ctq)` 的 `affected` 同时含声明与图纸，
   两条各自生成返工任务。
2. **幂等按输入**：同输入重跑 ⇒ 同一条记录（`created=False`）；换声明 ⇒ 另起一版。
3. **同一产物路径只留一版有效**：新版落下时把旧版 `set_status(superseded)`——
   否则一张图改十次就有十条永久下游，一次改 CTQ 会把历史版本全打成待返工。
   `superseded` 在第 44 片之后的发布证据里是「可见但不算未收口」。
4. **看不见的不写成没有**：上游连不上（手写 spec / 当时 `drawing spec` 没带 `--db`）⇒
   记录照写、`edges=0` 且 `upstream_reason` 点名原因；没给 `--db` ⇒ 明说的跳过、
   图照出、返回 0；血缘写失败 ⇒ 判未收口，`--json` 的 `ok=false` 与退码 4 同向
   （与第 43 片同一条纪律：机器面和终端面不许各说一套）。

## 四、撤改电池（`/tmp/s46/battery.py`，10 条：杀 10 / 存活 0 / 注入无效 0）

对照臂（未注入）rc=0 先立。靶：`test_drawing_dxf_lineage.py` +
`test_drawing_spec_lineage.py` + `test_truth_rework_cli.py`。

| 注入 | 结果 | 半径 |
| --- | --- | --- |
| E1 给了 `--db` 也不登记（`if db_arg:` → `if False:`） | KILLED | 6 条（含第三跳、幂等、换版、零边、失败判未收口、库缺失） |
| E2 没给 `--db` 时静默（跳过原因置 None） | KILLED | `test_no_db_is_a_stated_skip_not_a_silent_one` |
| E3 新版落下不标旧版 superseded | KILLED | `test_changed_declaration_starts_a_new_version_and_supersedes_old` |
| E4 输入签名不吃声明内容 | KILLED（第二次） | 同上一条 |
| E5 血缘写失败但不改 `ok` | KILLED | `test_lineage_failure_holds_the_command_and_agrees_with_ok` |
| E6 连不上上游时不写原因 | KILLED | `test_hand_written_spec_records_the_drawing_with_zero_edges` |
| E7 状态库读不到当成「没有血缘」 | KILLED | `test_missing_database_is_not_read_as_no_lineage` |
| E8 键改成吃 DXF 字节 | KILLED | `test_same_inputs_hit_one_record_and_stay_idempotent` |
| E9 键里抽掉模型摘要 | KILLED | `test_a_different_model_starts_a_new_version_not_a_reuse` |
| E10 键里抽掉 material/剖切/放大 | KILLED | `test_signature_covers_every_declared_input` |

**E4 首版存活，是一次有用的反证**：只把签名里的 `spec_sha256` 置 None 时全绿——
身份键 `content` 里声明哈希写了**两遍**（`inputs=<签名前 16 位>` 与 `← spec <声明哈希前 16 位>`），
关掉一处另一处仍会翻版。补成同时关掉两处才翻红。这条结构事实记在这里：
「换声明才另起一版」在实现上是双保险，不是单点；要改这个键的人得同时知道两处。
E8 则是对 §二 那条选择的正向证明：把键换成按字节，幂等用例真的会红。
E9/E10 是补完输入键之后新立的两支：各自抽掉一类输入，只打中对应那一条用例——
说明这些输入是**真在键上**，不是碰巧和别的字段一起变。

## 五、本轮自己踩到的一处夹具错（差点造成一条恒真用例）

新用例最初把 CTQ 写成 `nominal 6.0 / 5.95–6.05`（这是第一处），而 golden 支架 TOP 视图四个孔
**实测直径全部 8.0mm**（`generate_drawing` 直接量，`/tmp/s46/probe3.log`）。
于是每次出图都因 `ctq_window_violation` 返回 4：`test_third_hop…` 与幂等用例红，
而 `test_lineage_failure_holds_the_command_and_agrees_with_ok` **看着是绿的**——
它断言 rc==4，可这个 4 来自公差窗口而不是它要验的 `lineage_error`。
按实测把窗口改成 8.0 / 7.95–8.05 后，那条用例的 4 才归因到血缘写失败。
这也是本轮把「测试夹具的合格域必须来自实测几何」写进注释的原因。

第二处是自家人抓自家事：签名初版只吃「声明 + 六个参数」，把「出图参数」写窄了，**模型本身不在键里**。这条不是被用例发现的，是收口前专门去复现「同一命令还能不能被另一个模型复用」时发现的（见 §二 末），补完才补上 E9/E10 两支注入。

## 六、镜像同步清单（改公开命令能力行的固定一圈）

`src/aipd_os/registry_data.py` 两行（`product_truth.impact_propagation`：生产者由两改三、
写明第三跳到得了 + DXF 仍无执行器；`cad.2d_drawings`：`--db` 血缘 opt-in 与其边界）；
`README.md` 命令速查补 `drawing generate … --db`；`docs/architecture/truth_architecture.md`
§二 现状段改写；`tests/test_drawing_spec_lineage.py::TestProducerRatchet` 登记
`dxf_lineage.py`；输入键的适用域另由 `test_signature_covers_every_declared_input` 钉（每个输入单独变都要翻签名，全同必须稳定）；`docs/audit/capability_matrix.{md,json}` + `repository_snapshot.json`
由 `scripts/capability_matrix.py --pin-commit <tag SHA>` 重生成。
顺带清掉登记里一处上一轮拼接残留：「血缘边的生产者今天有两个」被写了两遍。

## 七、仍然没接上的（是读数，不是完成度）

- **BOM / 成本那一支没有血缘生产者**：`add_edge` 调用点普查里仍没有它们。
- **DXF 这一跳只有边、没有返工执行器**：`spec_rework.artifact_kind` 只认 `drawing_spec`，
  落到 `drawing_dxf` 的任务仍走「烧 attempts 之前逐条点名拒掉」那条路——
  这是刻意保持可见的缺口，不是漏接。
- 图纸被外部 CAD 改动后重新出图会命中同一条记录（签名相同）而只更新 `dxf_sha256` 观测，
  本轮不做「磁盘图与记录不符」的常驻判定。

## 八、复算入口

```bash
cd /Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
PYTHONPATH=src:scripts .venv/bin/python -m pytest tests/test_drawing_dxf_lineage.py \
  tests/test_drawing_spec_lineage.py tests/test_truth_rework_cli.py -q
.venv/bin/python /tmp/s46/battery.py          # 电池（10 条）
.venv/bin/python /tmp/s46/bytes_probe.py      # DXF 字节漂移实测
.venv/bin/python /tmp/s46/sig_gap.py          # 换模型是否复用同一条记录（修前后各跑一遍）
.venv/bin/ruff check src tests
```

## 九、终读数

全部由命令现场产出（记录于 2026-09-26；被背书的树 = HEAD `53e4876`，
attestation worktree 检出 `bbc74d6`）。本文件在 `docs/audit/` 下、不参与发布哈希，
所以绝对数写在这里而不写进 CHANGELOG。

| 项 | 读数 | 产出命令 |
| --- | --- | --- |
| 本片常驻用例 | 10 passed（11.97s） | `pytest tests/test_drawing_dxf_lineage.py -q` |
| 邻接面（血缘／返工／命令面／C6／能力矩阵） | 71 passed | 上面那个文件 + `test_drawing_spec_lineage` `test_truth_rework_cli` `test_truth_propagate_cli` `test_command_surface_census` `test_c6_coverage` `test_capability_matrix` 一起跑 |
| 变异电池 | 10 条：杀 10 / 存活 0 / 注入无效 0；对照臂 rc=0 | `.venv/bin/python /tmp/s46/battery.py` |
| 撞键复现（补漏前后各一遍） | 修前记录数 **1**、两次 `inputs=30599f43…` 相同；修后 **2** 条（`29c694b8…` / `22f16d04…`） | `.venv/bin/python /tmp/s46/sig_gap.py` |
| DXF 字节漂移 | 同输入两次：13170 行 / 仅 2 行不同（`$TDCREATE`、`$TDUPDATE`），sha 前缀 `855ce37c…` vs `d643913f…` | `.venv/bin/python /tmp/s46/bytes_probe.py` |
| 全量复算（背书用） | **2326 passed / 3 skipped / 0 failed**，215.06s，total 2329 | 干净 worktree `/tmp/s46b` @`bbc74d6`，带 `AIPD_SOURCE_COMMIT=<tag>` 与 `--json-report` |
| 全量复算（过程读数，不背书） | 2324 passed / 3 skipped / 0 failed，290.62s | 补漏前那一遍 @`cef8bb0` |
| 发布清单 | `RELEASE_MANIFEST.json` 642 个文件（640 → 642，version 5.6.0） | `scripts/regenerate_release_manifest.py` |
| 溯源锚 | `SOURCE_MANIFEST`/`PROVENANCE` 的 `source_commit` = `a66040520139…`（tag SHA，**不跟 HEAD**）；`test_report.present=true`、`total=2329`、`passed=2326`、`failed=0`，报告 sha256 `3e94b016ffe92124…` | `scripts/release_evidence.py --source-commit <tag> --test-report docs/audit/pytest-report-v5.6.0.json` |
| 生产发布门禁 | `rc=0`、`release_ready=true`、8/8 checks `passed=true`（含 `test_numbers_from_report`、`signature_verifiable`、`no_secrets`、`no_unacknowledged_cve`） | `PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/production_release_gate.py --release-ready --tag v5.6.0` |
| 严格审计 | `rc=1`，`✗` **恰好 1 条**：`Provenance source commit mismatch: manifest=a66040520139… vs HEAD=53e48760060a…`（按设计：清单钉 tag、树在往前走）。该量具不输出 `✓`（`✓` 计数 0 是它的形状，不等于"没有通过项"） | `scripts/audit_repo.py --strict` |
| 文档引用普查 | 文档 150 份 / 代码引用 3654 处 / **现状面缺陷 0 条** / 历史面 128 条（只报不判） | `scripts/doc_reference_census.py` |
| 命令面真调 | 已注册 67 条全部在 `cli` 档、低于 cli 档 0 条（本片只给既有命令加参数，命令数与手写分母不动） | `scripts/command_surface_census.py` |
| SKILL 自审 | 0 警告 0 失败 | `scripts/skill_quality_audit.py` |
| lint | `ruff check src tests` → All checks passed | — |

**没跑的那部分（不是通过，是没跑）**：没有用任何外部 CAD 查看器打开新生成的 DXF 验渲染；
`drawing_dxf` 的返工执行器与 BOM/成本的血缘生产者都还没接（§七）；
`--json` 的 `lineage_skipped` 字段没有单独的机器面断言（终端面文案有断言）。
