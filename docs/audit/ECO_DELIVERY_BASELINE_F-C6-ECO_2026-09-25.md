# F-C6-ECO 第 28 片：上一版交付物清单当基线（把「没单提到」拆成两种结论）

日期：2026-09-25　归属：`industrialize.change_control` + `industrialize.release_evidence`
上一片：`docs/audit/ECO_RELEASE_COVERAGE_F-C6-ECO_2026-09-25.md`（发布证据读 ECO，第 27 片）

## 一、这一片闭的是哪半句

第 27 片收尾写着（同一份登记，逐字）：

> **仍未做**：没有上一版产物清单当基线，所以只证明「内容与某张闭合单一致」，
> 不证明「自上次发布以来只改了这些」；没被任何单提到的文件记 undetermined（盲区）而不是违规。

那一格 `undetermined` 之所以只能是盲区，是因为**两种完全不同的事实长得一样**：

- 这个文件这轮**没动过**（本来就不需要变更单）；
- 这个文件**动了却没提单**（正是最需要拦的那一种）。

手里没有「上一版」的时候，任何一侧的断言都是编的。本片把「上一版」变成一件可落盘、可比对的
东西，于是那一栏一分为三：`unchanged_since_baseline`（**证明没改**，不需要单）、
`since_baseline.added / modified`（改了或新增却没闭合单 ⇒ **阻断**）、
`since_baseline.removed`（上一版有、这版没交 ⇒ 必须由一张 `VERIFIED` 的 `REMOVE` 单认领，否则**阻断**）。

## 二、选型：真读过的两份外部材料，与一条否掉「整仓差集」的实测

规则要求动手前做成熟实现检索并让结论真的影响决策，所以这一节只写**实际打开过的页面**
（均于 2026-09-25 访问），以及一次本仓自己的测量。

| 候选 | 功能匹配度 | License | 维护/活跃 | 安全风险 | 代码质量 | 适配成本 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **A. SLSA provenance 的「既有输入 vs 产物」两栏模型**（`slsa.dev/provenance` 实读） | 高：正是「先声明上一版是什么，再声明这次交了什么」的形状；该页写明 v1 已把旧的 `materials` 换成 `resolvedDependencies`（"unordered collection of artifacts needed at build time"），每条 `ResourceDescriptor` 带 name + 摘要表 | Community Specification License 1.0（该页自述） | 规范文档明写 v1.1、站点横幅已标 v1.2 ⇒ 活跃 | 无第三方代码可引入 | 模型清晰，但字段面向**构建过程**，本仓的产物是工程交付物不是构建输出 | 全套 attestation 结构（builder/predicate/invocation）用不上 | **借形状，不引依赖**：基线文件 = `{kind, release, source_commit, artifacts{path→{sha256, semantic_sha256, volatile_dropped}}}`，一条自述式的 `kind` 版本号 |
| **B. Apache Maven `artifact:compare`**（`maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html` 实读） | 中-高：它比的是「本次构建 vs 仓库里那一份参考构建」，参考由坐标解析而非手抄路径；且把 `<ignore>` 做成一等参数、`<fail>` 默认 true | Apache-2.0（ASF 项目） | 页面版本 3.7.0，Maven 官方插件 | 需要 Java/Maven 生态 | 高 | 本仓是纯 Python + CAD 交付物，装不进 Maven 生命周期 | **借两条判断**：① 每次都会变的东西必须**显式声明**，不能被当成内容差异；② 差集判据默认应当 fail（`<fail>` true）。不引入 |
| **C. 整仓文件差集**（拿 tag 上的 `SOURCE_MANIFEST.json` 与今天的比） | 看着最匹配：清单格式现成、零新代码 | 本仓自有 | — | — | — | — | **实测否掉**：`git show <tag>:SOURCE_MANIFEST.json` 与今天的清单做差，得 **新增 101 / 删除 9 / 内容变 82**（本轮现算，命令见 §六），而 v19 之后一张单都没有。把它们全要求成「有闭合变更单覆盖」，唯一变绿的办法是补写一百多张事后变更单——那是造证据。⇒ 基线**作用域缩到本次发布真正交出的带哈希交付物**（生产者本来就算得出来），整仓那条路只在 §七 记为未做 |

选定：**A 的两栏形状 + B 的两条判断，本地实现，零新依赖**；作用域按实测收到交付物级。

## 三、判据形状与被刻意排除的做法

1. **易变字段是白名单，不是 ignore 列表**。`delivery_baseline.VOLATILE_FIELDS`
   只含四个时间/访问类键名（`generated_at` / `accessed` / `accessed_at` / `generated_at_utc`），
   按**整名**匹配，不做前缀或通配。理由：一个能吞任意键的 ignore 列表就是关掉判据的开关。
   两侧都有常驻用例钉住：只换 `generated_at` ⇒ 语义摘要不变；改一条真结论 ⇒ 必须变；
   `created` 这种**没声明过**的近似名 ⇒ 一律算内容。
2. **只对 JSON 生效**。报告体是 Markdown、STEP/DXF 是文本/二进制，没有可声明的字段名 ⇒
   语义摘要 = 原始哈希，**不假装能省什么**。
3. **剔了哪些位置要交出去**：`volatile_dropped` 给出 `/document/generated_at`、
   `/runs[0]/accessed` 这样的路径，不是一句「省了两处」。
4. **`unchanged` 的优先级排在最前**：一条交付物若基线证明没改，即使单里有一条哈希对不上的
   声明也判「没改」——文件字节与上次一致是最强证据，那张单是错的文书，不是这次的风险。
   这条排序写在判据里并由 `test_a_closed_order_clears_the_baseline_violation` 钉住
   （它同时证明：改了的那条走单，没改的那条走基线，两桶不重复收同一条）。
5. **基线读坏了必须阻断**（`eco_baseline_unreadable`）。静默退回「没有基线」等于让
   「删掉/改坏基线文件」成为关掉差集判据的手段。
6. **没有基线不新增要求**：门那一侧维持第 27 片的判据，只在 detail 里补一句
   「无基线 ⇒ 本份证据**不**声称『自上次发布以来只改了这些』」。
   刻意**不**把「必须有基线」做成新的硬门——那会把当前锚定状态逼成 §二 C 那种补单凑绿。
7. **红着的证据不许悄悄变成基准**：`--write-baseline` 在有阻断项时被拒（rc=2），
   必须 `--acknowledge-not-ready <理由>` 才落盘，且落下来的文件里写着
   `release_ready: false` 与那句承认。拒绝时**不写文件**（有一条用例专钉这件事：
   嘴上拒绝、手上落盘 = 闸没生效）。

## 四、落点

| 位置 | 动作 |
| --- | --- |
| `src/aipd_os/delivery_baseline.py`（新） | `semantic_digest` / `_strip_volatile` / `artefact_index` / `write_baseline` / `load_baseline_semantics` / `diff_since_baseline` / `VOLATILE_FIELDS` / `BASELINE_KIND` |
| `src/aipd_os/release_manifest.py` | `_collect_eco` 加 `root` 与 `baseline_path`：三条新分支（unchanged 优先、added/modified 无单即阻断、removed 未认领阻断）+ `baseline_coverage` 轴 + `since_baseline` / `removed_unclaimed` / `unchanged_since_baseline` 三个读数；`build_release_manifest` 透传 `baseline_path` |
| `src/aipd_os/cli/commands_release.py` | `--baseline` / `--write-baseline` / `--acknowledge-not-ready`；人读输出多一行 `基线=… 判定=…`；红证据落盘被拒退 2 |
| `src/aipd_os/cli/main.py` | 三个新参数与 help 文案 |
| `scripts/production_release_gate.py` | `change_control_closes_deliverables` 多读 `removed_unclaimed` / `baseline_coverage`：未认领下线 ⇒ 拦；`absent` ⇒ 不新增要求但在 detail 里写明 |
| `tests/test_delivery_baseline.py`（新） | 11 条：语义摘要两向、嵌套与数组位置、未声明名不省、非 JSON 不省、四桶不重不漏、读不到算变、写读回环、kind 拒收 |
| `tests/test_release_manifest_eco_coverage.py` | +15 条（20 → 35）：`TestAgainstPreviousRelease`(9) / `TestTheGateReadsTheBaseline`(3) / `TestCliBaselineSurface`(3) |
| `tests/test_production_release_gate.py` | +2 条（22 → 24）：未认领下线拦、零单 + 全没改过 |

## 五、端到端实测

见 §六（真命令行走完「拒绝落盘 → 承认后才落 → 读回来全没改 → 动一行就拦 → 补一张单放行」）。

## 六、实测读数与命令

夹具：`/tmp/eco28/` —— migration v19 的真 `state.db` + 金样品 `bracket.step` 出的真 DFM 报告
（两条带哈希交付物：`dfm.md` 与 `dfm.md.evidence.json`）。驱动器 `/tmp/eco28_walk.py`。

### 基线差集现算（§二 C 那条否决的依据）

```python
git show <v5.6.0 tag>:SOURCE_MANIFEST.json  vs  今天的 SOURCE_MANIFEST.json
→ 新增 101 / 删除 9 / 内容变 82（作用域：整仓 520 → 612 条）
```

### ① 证据还红着就要求落基线 ⇒ 拒，而且不写文件

```
$ aipd release manifest --db $DB --project $P --dfm-doc $DOC --out $EV --write-baseline $BASE
这份证据还有阻断项（['bom_db_missing', 'no_ctq', 'no_drawings']），不落成基线：下一版会把
「没人放行过一次运行」当成上一版交付来比对。确实要先落盘就加 --acknowledge-not-ready 写明理由
  ↳ rc=2   基线文件存在？False
```

### ② 显式承认未就绪之后才落盘（文件里留着这句承认）

```
$ aipd release manifest … --write-baseline $BASE \
    --acknowledge-not-ready "先立比对基准，缺的 CTQ 与图纸下一版补"
  基线已落盘：/tmp/eco28/baseline.json（2 条，就绪=False，已承认未就绪：先立比对基准，…）
  ↳ rc=4        # 承认 ≠ 放行：这份证据照旧不 ok
  基线 ⟶ {"kind": "aipd.delivery_baseline.v1", "release_ready": false,
          "acknowledgement": "先立比对基准，缺的 CTQ 与图纸下一版补",
          "artifacts": ["dfm.md", "dfm.md.evidence.json"]}
```

### ③ 什么都没动，只把基线指回去 ⇒ 零张单也算数

```
$ aipd release manifest … --baseline $BASE
  eco 覆盖=complete 单=0 条 / 交付物=2 条：已闭合 0、无有效单 0、待复验 0、无单可判 0
  基线=/tmp/eco28/baseline.json 判定=complete：新增 0、变了 0、下线未认领 0、证明没改 2
  ↳ rc=4        # 红的还是那三条老阻断项，与变更控制无关
  门（③）⟶ passed=True  coverage=complete; 0/2 条带哈希交付物由 VERIFIED 单逐条对上
             after_sha256；另有 2 条由上一版基线证明语义未变（不需要单）      [rc=2]
```

`单=0 条` 与 `覆盖=complete` 同时成立，正是这一片新增的那句话：**这两条一个字节都没变，
所以没有需要背书的变更**。门的总体 `rc=2` 与这一条判据的 `passed=true` 并存——
这份临时文档本来就缺图纸/CTQ/BOM，第 27 片同一条纪律适用：**只主张这一条判据的读数**。

### ④ 只重新生成一次报告 ⇒ 原始哈希变了，仍判「没改」

```
  重新出报告 rc=0；侧车当前原始哈希 6fa5b89145bad4c7…（与基线里那条不同）
$ aipd release manifest … --baseline $BASE
  基线=/tmp/eco28/baseline.json 判定=complete：新增 0、变了 0、下线未认领 0、证明没改 2
```

这一条是 §三 第 1 点的全部理由：**真生产者、真侧车、真时间戳**，
不是合成 JSON。若无易变字段那一层，这里会凭空长出一次「变更」并要求一张单。

### ⑤ 真改一行结论 ⇒ 拦，两侧一致

```
  $DOC 改了 ⇒ 新哈希 11e3769ea3ea8368…
$ aipd release manifest … --baseline $BASE
  eco 覆盖=incomplete 单=0 条 / 交付物=2 条：已闭合 0、无有效单 1、待复验 0、无单可判 0
  基线=… 判定=incomplete：新增 0、变了 1、下线未认领 0、证明没改 1
  [阻断] eco_change_uncovered: dfm.md 相对上一版基线是**相对基线变了**，却没有任何变更单提到它：
         基线能证明它改了，改了就得有闭合的单
  ↳ rc=4
  门（⑤）⟶ passed=False  coverage=incomplete; 缺闭合单或未复验: ['dfm.md']      [rc=2]
```

同一次改动里，没动过的侧车从 `undetermined`（第 27 片的读法）变成了
`unchanged_since_baseline`（这一片的读法）——那一栏不再靠「反正我也不知道」撑着。

### ⑥ 补一张覆盖新哈希的单、推到 VERIFIED ⇒ 放行

```
$ aipd eco create …                    ⟶ ECO-001｜ECO｜DRAFT｜ECO-001 覆盖基线差集  rc=0
$ aipd eco affected --id ECO-001 --object-id dfm.md --change UPDATE
      --before-sha256 cccc…(64) --after-sha256 11e3769ea3ea…  ⟶ 影响清单第 1 行  rc=0
$ aipd eco transition --id ECO-001 --to {PENDING_REVIEW,APPROVED,IMPLEMENTED,VERIFIED}
      张三 → 李四 → 李四（带落地凭据与生效时间）→ 王五（带复验凭据）      全部 rc=0

$ aipd release manifest … --baseline $BASE
  eco 覆盖=complete 单=1 条 / 交付物=2 条：已闭合 1、无有效单 0、待复验 0、无单可判 0
  基线=… 判定=complete：新增 0、变了 1、下线未认领 0、证明没改 1
  ↳ rc=4
  门（⑥）⟶ passed=True  coverage=complete; 1/2 条带哈希交付物由 VERIFIED 单逐条对上
             after_sha256；另有 1 条由上一版基线证明语义未变（不需要单）
```

「变了 1 + 已闭合 1」与「没改 2」是两种不同来源的合格：前者靠单，后者靠基线。

## 八、收口读数

| 项 | 读数 |
| --- | --- |
| 全量用例 | 2028 → **2056** 条（新增 28：新模块 11 + 判据 15 + 门 2）；两轮全量各 `2053 passed / 0 failed / 3 skipped`（一轮记本轮，一轮带 `AIPD_SOURCE_COMMIT=tag`） |
| 首跑（重锚之前） | `2 failed, 2051 passed` —— 红的正是 `test_packaging.py` 两条 `*_manifest_hashes_match_disk`，属预期，随重锚闭 |
| ruff（CI 范围 `src tests state_service`） | All checks passed |
| mypy（`src tests`） | Success: no issues found in **415** source files（+1：`delivery_baseline.py`） |
| C6 普查 | `scripts/c6_coverage.py` 仍 15 项 = 14 / 0 / 1（档位不变，note 与本片实测数字更新）；`--self-test` 7/7 条注入被抓 |
| 变异电池 | `/tmp/slice28-mutations.py` **15 条：杀 15 / 活 0 / 注入无效 0**；第 27 片的 17 条在同树复跑：第一轮 **15 杀 / 2 注入无效**（E3、E4 的锚被本片改形，命中 0 次），把两条锚重指到现役代码后 **17/17** |
| 端到端 | 真命令行走完六步（§六），门侧读数由子进程真跑 `aipd validate` 取得 |
| 发布门 `--release-ready --tag` | 见下方补记 |
| 重锚 | 见下方补记 |

### 电池放走过一条（记下来，因为它正是这一片要防的那类假绿）

第一轮 **B8**（把「下线必须由 `VERIFIED` 的 `REMOVE` 行认领」放宽成「单里提过就行」）**全绿**：
原判据用例只测了两端——「有合规 REMOVE 单 ⇒ 放行」与「什么都没提 ⇒ 拦」，
**中间那一格「提过，但不是 REMOVE / 不是 VERIFIED」没人测**。
补 `TestAgainstPreviousRelease::test_only_a_verified_removal_endorses_a_vanished_delivery`
（两档：`UPDATE/VERIFIED` 与 `REMOVE/APPROVED` 都不许算认领），再加同族的 **B15**
（只认 `REMOVE`、不要求 `VERIFIED`）——两条一起开火之后才是 15/15。
这与第 26 片 G5「可选那一格没人查」、第 27 片五条存活读数同族：**判据多出来的那一半，
必须有一发注入专门去撞它**，否则「杀掉 N 条」里的 N 会盖住没测到的那一格。

同一次复跑还暴露了**电池自身的腐化**：第 27 片的 17 条在这棵树上是 15 杀 + 2 条「注入无效」——
E3（盲区折叠成合格）与 E4（零张单也算已覆盖）的锚点被本片改 `_collect_eco` 时改掉了形状
（E3 那两行之间插进了 added/modified 分支；E4 的 `"coverage": "undetermined",` 字面量
从早退 return 变成了收尾的 `section["coverage"] = "undetermined"`）。
**判据还在、用例也还在，是注入打不进去**。电池把这件事报成「锚点命中 0 次」而不是「杀掉」，
正是把 `rc∈{4,5}` 且无失败行判成无效的用处；两条锚重指到现役代码后回到 17/17。
教训写在这里：**每次改形一条判据，都要复跑上一片的电池**，否则登记册里的「17 条全杀」
会变成一个没人再能复现的历史数字。

### 易变白名单的边界（刻意留下的读法）

`VOLATILE_FIELDS` 是**全局按整名**匹配的四个键，不区分产物类型：
`generated_at` 在任何 JSON 里都会被省。这不是没代价的省事——真要收紧，
得改成「哪个侧车类型声明哪些字段易变」，未做（§七 第 3 条）。
两侧的反证都在：非 JSON 的交付物（`dfm.md` 报告体）语义摘要 = 原始哈希，
④/⑤ 两步实测就是这一条：重跑只动侧车 ⇒ `unchanged 2`；改报告一行 ⇒ `modified ["dfm.md"]`。

### 重锚补记

提交序列：`a82fdbf`（代码 + 用例 + 两份审计文档）→ 产物重锚提交。

| 读数 | 值 |
| --- | --- |
| 被哈希面 | 612 → **614**（新增 `src/aipd_os/delivery_baseline.py` 与 `tests/test_delivery_baseline.py`），`SOURCE_MANIFEST` 与磁盘逐条一致（0 条不匹配） |
| `PROVENANCE.test_report` | 2053 passed / 0 failed / 2056 total，`source_commit` = `a66040520139…`（tag） |
| `production_release_gate --release-ready --tag` | **8/8 绿**，`release_ready: true`，rc=0 |
| `audit_repo --strict` | rc=1，唯一 ✗ 仍是既有裁决那条「Provenance source commit mismatch: manifest=a66040520139… vs HEAD=…」——锚点按裁决停在 tag，不是本片回归 |

## 七、这一片没做的事

1. **整仓范围的差集**没做（§二 C 的实测就是它的代价）：`SOURCE_MANIFEST` 级别的
   「自上次发布以来改了哪些源码」需要**每一笔提交都有单**，本仓现在一张都没有；
   要把这一格接进门，得先决定「历史怎么算」——补单（造证据，否掉）、
   还是把「本条判据自某次发布起生效」写成一个明确的起点。这是属主裁决，不是实现选择。
2. **基线的真值来源只有 `--write-baseline` 一条路**：不做「从 tag 上自动生成基线」。
   tag 上的 `SOURCE_MANIFEST` 是**仓库文件**清单，不是**交付物**清单，作用域不同。
3. **易变字段仍是全局白名单**（按键名，不按产物类型）：`generated_at` 在任何 JSON 里都被省。
   更严格的做法是按侧车类型声明，未做。
4. **`added` 与「上一版没交的新交付物」不区分**：基线里没有就是新增，第一次交付与
   漏交后补上都算新增。
5. 第 27 片那四条仍未做（署名无身份源、ECO 不联动失效传播、`gates.approved_by` 默认值、
   门只信生产者写进文档的读数不重算哈希）。
