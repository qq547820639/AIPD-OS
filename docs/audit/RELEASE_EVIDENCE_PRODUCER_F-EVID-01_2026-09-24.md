# F-EVID-01：发布就绪门禁的 CTQ/GD&T 证据没有生产者（已补 `aipd release manifest`）

日期：2026-09-24　范围：新增 `src/aipd_os/release_manifest.py`、`aipd release manifest` 命令、
`src/aipd_os/cad/drawings2d.py`（公差声明可选 `ctq_ref`）、能力行 `industrialize.release_evidence`、
新增常驻用例 `tests/test_release_manifest.py`（10 条）。

一句话结论：门禁的 `gdt_covers_ctq` / `ctq_has_inspection` 从「只能靠人手写 JSON 满足」变成
「由产品侧现取装配」；且 **gdt 只从图纸侧长出来**，所以「登记了 CTQ 但没画上匹配公差」必然判未覆盖。

## 一、取证（实测，非推断）

1. **门禁判据早已 fail-closed**：`scripts/production_release_gate.py:256-286` —— `ctq`/`gdt`
   不是两个都存在的列表就直接 `passed=False`（注释原话「不允许空真通过」）。
2. **但产品侧零生产者**：全仓 `ctq` / `gdt` 数组只出现在两处测试夹具
   （`tests/test_production_release_gate.py:44`、`tests/test_cli.py:336-337`）；`src/` 内零命中。
   旧审计 `docs/audit/v5.4/phase5-cad-audit.md:30` 也记着「仅校验，无 BOM/图纸生成」。
   ⇒ C5/C6 的这两条证据此前只能由人手抄写，抄什么过什么。
3. **权威其实已经在场**：Product Truth 有 `record_type="ctq"`（`product_truth/models.py:17`，
   带 `metadata`）；`ValidationTest` 有 `lower_limit/upper_limit/tolerance`
   （`validation/models.py:223-227`）但**没有任何几何引用**；BOM 有 `BomStore.list_lines`
   与 `BomHeader.revision`；图纸证据（F-DRAW-01 第 1 片）每条尺寸带 `feature` 与 `tolerance`。
4. **不能按名字映射**：CTQ 侧只有自由文本 `name/content`，图纸侧是 `TOP.hole_2` 这类实测视图特征。
   二者靠字符串相似去撮合就是装饰性接线（F-REG-01 的失败模式），所以本轮要求**显式 `ctq_ref`**。
5. **门禁按 tag 锚点严格相等核报告新鲜度**（`production_release_gate.py:454-472`，无祖先豁免）
   ——上一轮收尾时我把证据绑到本轮树的报告上，就是被这条判红抓出来的（见
   `CAD_DRAWING_CHAIN_TOLERANCE_F-DRAW-01_2026-09-24.md` §7）。
6. **`cq.importers.importStep(...).val()` 返回的是 cadquery 的 `Solid` 包装，不是 `TopoDS_Shape`**：
   实测把 `TopExp_Explorer(shape, TopAbs_SOLID)` 喂进去直接 `TypeError`，第一版 `--model` 分支因此
   在真机跑时判 `model_unreadable`。改用 `importStep(...).solids().size()` 后两个不相连实体数出 2。
7. **真机端到端读数**（临时库 + 真实出图 + 真实 CTQ + 3 行 BOM，再把产物喂给真门禁）：
   - 不给 `--model`：`rc=0`、`bom_line_count=3`、`drawing_count=1`、`ctq=1 gdt=1`、
     门禁 `gdt_covers_ctq=True`、`ctq_has_inspection=True`、`file_openable=True`，
     而 `drawing_cad_same_revision=False`（`drawings_version/model_version missing`）
     ——缺输入就判红，不猜；
   - 给 `--model two.step`：`model_version=899106…`（内容哈希），门禁如实报
     `version mismatch: {'model_version': '89910667210a', 'drawings_version': 'A'}`。
     版本不同轨**不是**被生产者抹平的，是被测量出来的。

## 二、候选方案与选型（六维）

| 维度 | A 新增产品侧生产者 `release_manifest` + `aipd release manifest`（选定） | B 让 `cad preflight`/`validate` 顺手产出 | C 只补 JSON schema 模板，继续手写 |
|---|---|---|---|
| 功能匹配度 | 高：门禁要的正是这一份文档，字段全部有权威来源 | 中：那两个命令各自消费**不同** schema 的 manifest | 低：缺口（无生产者）原样留下 |
| License 兼容 | 纯本仓，零新增依赖 | 同左 | 同左 |
| 维护活跃度 | 与产品同生命周期；能力行进 registry 受门禁复查 | 会把两个不同语义文档耦合到一处 | 文档漂移无人复查 |
| 安全风险 | 只读三个本地库/文件，不触网、不执行外部程序 | 复用同一入口易误写他人产物 | 证据可任意伪造，等于无门禁 |
| 代码质量 | 数字来源单一可核；`gdt` 由图纸侧派生，判据不被自证 | 一个函数两种语义，schema 校验会互相掩盖 | —— |
| 适配成本 | 中：新增模块 + 四处命令面登记（吸取 F-CLI-01） | 低但语义错位 | 最低但问题不解决 |

**选定 A。** 关键取舍是**防空真通过**：如果 `gdt` 由 CTQ 派生，`gdt_covers_ctq` 就永远成立
（判据退化为自证）；因此 `gdt` 只能来自图纸证据，且要求「标了公差 + 显式 `ctq_ref` +
偏差数值与 CTQ 上下限一致」三条同时成立，CTQ 缺限值时降级为「按引用成立 + 记 `ctq_limits_missing`」
而不是静默当作已验证。

**上游检索（如实说明边界）**：WebSearch「open source release evidence manifest generator
CTQ GD&T BOM drawing revision traceability」与 GitHub 检索均未找到面向**制造/产品成熟度**证据文档的
可复用开源实现，命中的是 SaaS 软文与商业工具（Guthrie QA-CAD）、以及软件制品侧的
CycloneDX/cdxgen、JFrog。未读 in-toto / CycloneDX 的规范源码，因此不评价其格式可否套用；
判断依据是其面向软件产物而非产品成熟度（这一句是**推断**，不是取证）。
可复用的结构惯例其实在本仓内：`scripts/release_evidence.py` 的「收集真实产物 → 逐条 sha256 →
输出 JSON」，本轮照此实现（借鉴思路，未重造格式）。

## 三、落点

| 位置 | 作用 |
|---|---|
| `src/aipd_os/release_manifest.py:36` | `_issue`：问题项带 `feature`，下游按字段机读而非解析中文 |
| `:53` | `_collect_ctq`：Product Truth 的 active CTQ；缺 `metadata.feature` 逐条点名 |
| `:84` | `_agrees_with_ctq`：图纸偏差 vs CTQ 绝对上下限；CTQ 无限值时返回 None（不可核 ≠ 通过） |
| `:94` | `_collect_drawings`：读 `.evidence.json`，**gdt 只在这里长出**；sha256 引用真实图纸 |
| `:156` | `_collect_bom`：行数/版本取自 BomStore（bom.db 按产品口径放在 state.db 同目录） |
| `:180` | `_model_fields`：只支持 STEP 数实体；读不到就**不写** `model_part_count` |
| `:205` | `build_release_manifest`：版本三源独立、不代为对齐；`ok` 只由阻断项决定 |
| `src/aipd_os/cad/drawings2d.py:502` | 公差声明支持可选 `ctq_ref`，落到尺寸证据上 |
| `src/aipd_os/cli/commands_release.py:66` | `cmd_release_manifest`：prose 里把「未取到，不编造」显式打出来；阻断 ⇒ exit 4 |
| `src/aipd_os/cli/main.py` / `command_contract.py` / `commands.py` / `SKILL.md` | 四处命令面同步（F-CLI-01 的教训：契约有、parser 没有 = 没交付） |
| `src/aipd_os/registry_data.py` | 能力行 `industrialize.release_evidence`（partially，限制逐项写明） |

## 四、用例与变异对照

`tests/test_release_manifest.py` 10 条：现取数字/版本 3、gdt 只从图纸长 5（含**合规侧**
「画上了+ref对+数值一致 ⇒ 门禁绿且零问题」与必须开火侧「只登记 CTQ ⇒ 门禁判未覆盖」）、
CLI 面 2。两条门禁断言直接 `subprocess` 跑真 `production_release_gate.py` 读
`evidence_checks`，不在测试里复刻判据。

变异（8 条，全部打破；`landed` 均已 grep 确认落盘）：

| 变异 | 打破的用例 |
|---|---|
| M1 `gdt` 改由 CTQ 侧造（自证式设计） | 未覆盖侧 + 悬空 ref + 数值不一致（3 条） |
| M2 不核数值一致性 | `deviation_mismatch…` |
| M3 悬空 `ctq_ref` 静默跳过 | `dangling_ctq_ref…` |
| M4 把 BOM 版本抄成图纸版本（为过门禁对齐） | `counts_and_versions_come_from_the_real_stores` |
| M5 缺省 `approval_status="approved"`（生产者自批） | 同上（审批字段断言） |
| M6 没图纸也不阻断 | `cli_without_any_drawing_is_not_a_ready_release` |
| M7 CTQ 缺 feature 时退回用正文猜 | `ctq_record_without_feature_is_named` |
| M8 实体数写死 1 | `model_solid_count_is_read_from_the_step_not_assumed` |

排障记录：`--model` 分支在**首轮真机运行**时就判 `model_unreadable`（取证 6）。当时用例没覆盖这条
分支——补了「两个实体数出 2」的用例并改用 cq 选择器，才既有实现也有回归。

## 五、边界（没做，也没声称做了）

- **不做 CTQ↔几何 的自动映射**：`ctq_ref` 必须人写；没写就是「这条公差暂无权威出处」，
  记 `tolerance_unlinked`（非阻断）且不计入覆盖。
- **不修 approval_status**：审批属属主，缺省 `unapproved`。
- **不做 GD&T 形位公差框 / 公差叠加分析**（仍是 F-DRAW-01 后续片）；
- **模型侧只认 STEP**，原生源 `.py` 需要执行构建脚本，未做（读不到就如实不写计数）；
- 本轮**未触碰**真实发布：tag 不动、bundle 不重建不重签、不 push；`releases/golden-projects/**` 不动。

## 六、复算

```bash
export PATH="$PWD/.venv/bin:$PATH"
python -m pytest tests/test_release_manifest.py -q
python -m aipd_os.cli.main release manifest --db state.db --project P \
  --drawing out/bracket.dxf --bom BOM-1 --model out/bracket.step --out evidence.json
python scripts/production_release_gate.py --manifest evidence.json --target C6
# 关键读数：gdt_covers_ctq 由文档里的真实派生项决定；未给 --model 时
# drawing_cad_same_revision 必须是 False（缺输入即判红，不猜）。
```
