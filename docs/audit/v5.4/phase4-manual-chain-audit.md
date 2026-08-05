# 阶段4「连续附件产品手册链」实现真实性审计

- 审计对象：`/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS`
- 审计性质：只读深审，未改动任何生产代码
- 审计日期：2026-08-06
- 结论先行：**该链是「诚实降级」的骨架/模板，而非真实的端到端图像生成管线。**
  - 图像生成适配器 **从不调用任何真实图像模型**（可用的空适配器，显式拒绝伪造图片）。
  - 前批页面仅登记路径，**未真正作为附件喂给任何模型**。
  - 视觉语义审计器与黄金评测器**本体诚实**（无视觉后端时人物/CMF 不假通过），
    **但未被接入任何执行门**,且顶层 `passed` 标志存在乐观偏差。
  - WBX-1 被当作黄金样本，但仓库内仅有元数据清单，黄金图与黄金库字段缺失。

---

## 验证点 1：图像生成是否真的被调用？

**状态：未真实实现（空适配器，诚实拒绝）。**

- 文件：`src/aipd_os/imggen/adapter.py`
- `ImageGenAdapter.generate()`（第 41–54 行）：即使 `available()` 为 True，
  也必然抛 `ImageGenUnavailable("no real backend client is wired up; refusing to fabricate an image")`。
  **代码中不存在任何真实图像模型客户端、HTTP 调用或 SDK 调用。**
- 唯一真实产出是 `write_external_task_package()`（第 56–77 行）：只写一个 JSON
  `*.task.json` 外部任务包，明确标注 `status: external_pending`，**不写任何图片**。
- 执行链 `scripts/manual_chain.py::cmd_run_batch`（第 211–240 行）：
  `adapter = ImageGenAdapter()`（无后端），`adapter.available()` 默认 False；
  即便用环境变量强行置可用，`generate()` 也必然抛异常被 `except` 捕获 →
  `status` 恒为 `external_pending`，`render_page()` 的调用分支**永不可达**。
  即 **run-batch 实际从不渲染任何带图页面，只落盘外部队列任务包**。
- 测试证据：`tests/test_imggen.py` 两条用例均只断言「不可用时抛异常」与
  「写外部任务包且不生成假图」，**没有任何用例证明真实图像模型被调用**。
- 限制：`available()` 的语义（配了 key 就算可用）与 `generate()` 恒抛异常自相矛盾；
  若未来真接入后端，`generate()` 需重写，当前为空壳。

---

## 验证点 2：前批页面是否作为图像附件真正传入下一批？

**状态：仅登记路径，未真正传给任何模型。**

- 文件：`scripts/manual_chain.py`
- `_collect_prior()`（第 120–127 行）：仅收集前批 PNG/JPG 的 `{path, sha256}` 列表，
  存入 `batch_run["prior_batch"]`（第 251 行）。
- `validate()` 只做**结构校验**：非首批必须带 `prior_batch`（第 272–275、300–306 行），
  扩展 prompt 的 `inputs` 必须含前批路径。**没有任何代码把图片字节/路径喂给模型。**
  `visual_bible`、`prior_batch`、`prohibited` 均只是 JSON 状态字段（第 250–254 行）。
- 测试证据：`tests/test_manual_chain_e2e.py` 第 104–110 行仅断言
  `prior_batch` 字段存在且非首批非空，**未断言图片被送入模型**。
- 结论：这是「附件登记 + 状态连续性」，不是「真实作为图像附件传给下一批生成」。

---

## 验证点 3：人物/结构/模块/CMF/相机与光线一致性——真机制还是字段？

**状态：多为字段/元数据，非真实视觉机制。**

| 维度 | 实现情况 | 证据 |
|---|---|---|
| 人物一致性 | 仅字段 `expected_character`（硬编码字符串），审计时标 `requiring_vision`，无视觉后端不真查 | `manual_chain.py:146`；`auditor.py:102-107` |
| 产品结构一致性 | **未实现**。护栏测试注释明确「无 product_structure_consistency」 | `tests/test_visual_honesty_guardrail.py:6-8` |
| 模块一致性 | golden 中按 `modules` 集合判 `role=module` 页；但黄金清单缺 `modules`→`golden_missing` | `golden.py:200-210` |
| CMF 一致性 | 仅字段 `expected_cmf`（硬编码字典），审计标 `requiring_vision` | `manual_chain.py:147`；`auditor.py:110-115` |
| 相机/光线一致性 | **代码中不存在**任何字段或维度；`_collect_visual_bible` 仅登记目录文件列表 | `manual_chain.py:130-137` |
| 曲线/图注/页码/页脚 | **真实实现**（排版器绘制） | `renderer.py:60-99,208-215` |

---

## 验证点 4：中文是否为真实文字？参数是否来自 Product Truth？

**状态：中文为真实光栅化文字，但正文是硬编码模板，仅参数值来自事实。**

- 真实中文排版：`src/aipd_os/layout/renderer.py` 用 STHeiti 字体在 2480×3508 A4 画布
  按字符真实光栅化标题/正文/参数表/曲线/页码（第 127–220 行），非 watermark/占位图。
  `tests/test_layout.py` 验证 A4 尺寸。
- 但正文内容：`scripts/manual_chain.py::_build_defn`（第 148–191 行）全部是**硬编码中文字符串**
  （封面/原理/模块/场景/CMF/QA/结语），**不来自 Product Truth 理论**。
- 参数值：来自 `--facts` JSON 的 `params` 字典（第 142、158–159 行），
  即**峰值扭矩/重量/容量等数值确实来自事实文件**；golden 的 `params_from_fact_sheet`
  会校验，但黄金清单缺 `params` 字段→`golden_missing`。

---

## 验证点 5：是否只重建失败的责任页？

**状态：只产出「重建计划」，无真正执行重跑的责任页入口。**

- `src/aipd_os/visual_audit/auditor.py::audit_batch`（第 214–226 行）会定位失败页与失败维度，
  生成 `rebuild_plan: [{page_id, failed_dimensions}]`——**机制存在**。
- 但 `scripts/manual_chain.py` **没有任何命令/路径接收 rebuild_plan 并只重跑单页**；
  `render_page()` 总是整页渲染，无局部重绘。
- 测试证据：`tests/test_manual_chain_e2e.py` 第 134 行仅断言「无失败页时 rebuild_plan 为空」，
  **从不测试真实返工单页的路径**（该路径根本不存在）。

---

## 验证点 6：是否仅靠白占比/熵/边缘/哈希/分辨率判定？语义视觉审查是否被强制？

**状态：审计器本体语义且诚实，但语义审查未接入门，且顶层 `passed` 有乐观偏差。**

- 禁止依赖：`references/manual-quality-system.md:42` 与 `product-manual-pipeline.md` 明确
  「确定性预检通过后仍需独立多模态审计」「不得以页面尺寸正确就判定通过」。
- 审计器本体（`auditor.py`）是语义级（结构/角色/叙事/参数/中文/禁伪），
  `character_consistency`/`cmf_consistency` 无视觉后端时 `passed=False`、
  `requiring_vision=True`，**不伪造通过**——`tests/test_visual_honesty_guardrail.py` 通过。
- **顶层 `passed` 偏差**：`auditor.py:174`
  `passed = (not non_vision_fail) and (not vision_pending or True)`，
  `(not vision_pending or True)` 恒为 True → 仅当视觉维度待审时 `passed` 仍为 True。
  护栏测试**未断言 `result["passed"] is False`**，该偏差未被测试捕获。
- **门未接入语义审查**：`scripts/manual_chain_gate.py`（全文件）只调用
  `manual_chain.py validate`（纯状态结构校验）决定 `manual_complete`，
  **不调用 `VisualAuditor`，也不调用黄金评测器**。
- `scripts/manual_preflight.py` 是纯确定性启发式（white_ratio/entropy/edge_density/aHash/尺寸），
  但它自己正确警告「necessary but not sufficient……independent visual review……mandatory」，
  未把语义审查误当已做。
- 结论：语义审查**有实现但被文案/测试宣称为强制，实际未接入任何自动门**；门只查结构状态。

---

## 验证点 7：WBX-1 是否被当作黄金样本？

**状态：是（元数据层面），但黄金图与黄金库字段缺失，到达不了真实语义对照。**

- `evals/wbx1_golden_reference_manifest.json`：登记 16 条目，仅含 `file/width/height/mode/sha256`，
  `status: golden_reference_registered`。
- `src/aipd_os/visual_audit/golden.py` 以该清单为黄金输入；`GoldenGapEvaluator.evaluate`
  缺 `modules/copy_text/params` 维度时返回 `golden_missing`（0.5、passed=None），绝不假装通过。
- 测试证据：`tests/test_visual_golden.py` 断言清单存在且含 `golden_reference_registered`，
  断言 15 维键齐全、PNG 缺失如实失败。
- 限制：清单引用的实际黄金 PNG（`1.png`…`16.png`，`source_dir=/mnt/data/wbx_manual_ref`）
  **不在本仓库**；`assets/golden_samples` 仅 5 张 jpg，`assets/golden-references/wbx1` 仅 1 张
  `manual_montage.png`。故 WBX-1 仅作「已注册的元数据锚点」，无法进行真实逐页视觉对照。

---

## 测试结果

命令：`.venv/bin/python -m pytest tests/test_imggen.py tests/test_layout.py tests/test_manual_chain_e2e.py tests/test_visual_honesty_guardrail.py tests/test_visual_golden.py -q`

**结果：11 passed in 4.58s**（全部通过，但均未覆盖「真实图像模型被调用」与「单页返工执行」两条真实路径）。

---

## 总体诚实性结论

- 代码对「我没有真实图像后端」**是诚实的**：适配器拒绝伪造，任务包标 external_pending，
  视觉维度不假通过，预检脚本自证不足。
- 但对「我 PIPELINE 已输出成品手册」**是夸大的**：run-batch 实际只产出外部队列任务包，
  无真实成图；门只查状态结构，不强制语义审查；顶层 `passed` 忽略视觉待审维度。
- 因此阶段4的「连续附件图像生成 + 语义视觉审查门 + 黄金对照」是**骨架/模板 + 诚实降级**，
  **不是**已运行的真实图像生成与语义验收管线。