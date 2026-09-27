# 装配步骤 PDF 的图片层（F-ASSEMBLY-PDF-IMAGE，第 81 片，2026-09-27）

产物：`src/aipd_os/cad/assembly_steps_pdf.py`（图片层 + 图框边界句单点化 + `image` 读数）、
`assembly_steps.generate_assembly_steps(draw_image=…)`（拒绝时机挪到落盘之前、`NOT_COVERED` 撤掉过期那一项）、
`--draw-image` 旗子（`cli/main.py` + `commands_drawing.py` 三条前置检查）、
`tests/test_assembly_steps_pdf.py` 6 → 23 个 def / 27 条收集实例、`tests/test_changelog_integrity.py`（新常驻门禁 7 条）、
`tests/test_cad_assembly_steps.py` 一条断言翻转、`scripts/doc_reference_census.py` 的全序修复
配 `tests/test_doc_reference_census.py` 7 → 8 条、README、登记表、
`docs/audit/s81/battery81.py`（17 臂）。

## 一、为什么不自动出图（选型面）

**先说结论**：这一片只做"作者供图就排版、没图就声明没有"，不引入 STEP → 栅格那条路。
下表每个候选的每个维度都指到本轮**真打开过**的出处；每条读数都是主理人自己 `curl` + 读原文取回，
不是转述（派去检索的子代理有一处结论是错的，见本节末）。

| 候选 | 功能匹配度 | License 兼容性 | 维护活跃度 | 安全风险 | 代码质量 | 适配成本 |
| --- | --- | --- | --- | --- | --- | --- |
| **CadQuery 自带的 `show(screenshot=…)`**（`cadquery/vis.py`）——本仓 `cad` extra 已写 `cadquery>=2.4`（`pyproject.toml:51`），而 `pyproject.toml:12` 另有一句更狠的现状：
   "CAD 真实内核（cadquery）**仅在 3.9 验证**（cad-golden-loop 单环境）" | 能出 PNG，走 `vtkWindowToImageFilter` + `vtkPNGWriter`（`vis.py:568-575`）；但**只在非交互分支**设离屏：`if not interact: win.SetOffScreenRendering(1)`（`vis.py:448-450`），同一函数仍然无条件构造 `vtkRenderWindowInteractor`（`vis.py:474`） | `cadquery@2.8.0` PyPI `license = "Apache Public License 2.0"`，与 MIT 兼容（https://pypi.org/pypi/cadquery/json） | `cadquery@2.8.0` 上传 2026-06-21；内核轮 `cadquery-ocp@8.0.1.0.0` 上传 2026-09-05（两个 json 同上） | 未实测：它不在本仓锁定依赖集里，`production_release_gate` 的 `no_unacked_cve` 只扫已锁的闭包 | 官方可视化页对截图功能挂着原话警告：**"Intermittent issues were observed with this functionality, please submit detailed bug reports in case of problems."**（https://cadquery.readthedocs.io/en/latest/vis.html）；它用的 `SetOffScreenRendering` 在 VTK 文档里是 `GetOffScreenRendering () Deprecated, directly use GetShowWindow and GetOffScreenBuffers instead.` 那一对的便捷入口（https://vtk.org/doc/nightly/html/classvtkRenderWindow.html） | **装不上当前解释器**：`cadquery@2.8.0` 的 `requires_python = ">=3.11"`，而本仓 `pyproject.toml:11` 声明 `>=3.9,<3.13`、本机 venv 是 `Python 3.9.6`；它的内核轮还硬钉 `vtk==9.6.2`（`cadquery-ocp` 的 `requires_dist`） |
| **自己搭 VTK / PyVista 离屏渲染** | 能做，`vtkRenderWindow.SetUseOffScreenBuffers(bool)` 的文档语义就是 "Render to an offscreen destination such as a framebuffer"（同上了 vtk 文档页） | `vtk@9.7.0` `license = "BSD"`、`pyvista@0.49.0` `license_expression = "MIT"`（各自 PyPI json） | `vtk@9.7.0` 上传 2026-08-15；`pyvista@0.49.0` 上传 2026-09-08 | 同上：未进本仓依赖闭包，没跑过 pip-audit，不假称"已核过无 CVE" | PyVista 自己给的离屏配方是**系统级**的：其 offscreen devcontainer 要 `apt packages: libosmesa6` + 环境变量 `PYVISTA_OFF_SCREEN=true`（https://raw.githubusercontent.com/pyvista/pyvista/main/.devcontainer/offscreen/devcontainer.json）⇒ 交付面从"pip 装一个包"变成"宿主要有 Mesa/OSMesa 与 GL 上下文" | `pyvista@0.49.0` 与 `vtk` 都要 `requires_python >=3.10`（`pyvista` 依赖 `vtk>=9.3.1,<9.8.0` + `pillow`），本机 3.9.6 同样装不上 |
| **`trimesh` 读 STEP** | 能读，但**不是 B-Rep**：官方格式表对 STEP/STP 那一行写 "cascadio … uses OpenCASCADE to convert to GLB before loading"（https://trimesh.org/formats.html）⇒ 先化成网格，装配关系与约束在这一步就没了 | `trimesh@5.1.0` `license` 是 MIT 全文（PyPI json），`cascadio` 挂在 `extra == "recommend"` | `trimesh@5.1.0` 上传 2026-08-31 | 未实测（同上） | 它解决的是"把一个几何体画出来"，不解决"这张图有没有证过装配顺序" | `requires_python >=3.10`，本机装不上；且它替代不了"图是不是真"的那一半 |
| **`pythonocc-core`** | OCCT 内核直连，功能上能做 | `license = "LGPL"`（PyPI json）——与 MIT 仓库要额外处置静态/动态链接口径 | **PyPI 上 `0.16` 这个版本的文件列表是空的、`urls` 为 null**（`https://pypi.org/pypi/pythonocc-core/json` 现读）⇒ 只能走 conda-forge，本仓 CI 没有 conda 通路 | 未实测 | 未评估：安装通道这一条已经先否掉 | 换的是分发体系，不只是换一个包 |
| **`manifold3d`** | 不做 STEP 输入：其 long description 里 `STEP` 出现 **0 次**，列的是 3MF/GLB/OBJ/OFF/STL（PyPI json 现读） | `License :: OSI Approved :: Apache Software License` | `manifold3d@3.5.4` 上传 2026-09-25 | 未实测 | 与本片问题无关 | 不入围 |
| **接受作者提供的图（本片所选）** | 有图就排、没图就声明没有；不需要几何 | 只用已在 `full` extra 里的 `pillow` + `reportlab`：`reportlab@5.0.1` `requires_python = "<4,>=3.9"`（3.9 可用）、`pillow@12.3.0` `license_expression = "MIT-CMU"`；本机实际装的是 `reportlab 5.0.0 / PIL 11.3.0 / pypdf 6.19.0`（`.venv/bin/python -c "import reportlab,PIL,pypdf"` 现读） | 两个都在活跃发版（reportlab 5.0.1 上传 2026-08-20、pillow 12.3.0 上传 2026-07-01） | 已在 `scripts/production_release_gate.py` 的 `no_unacked_cve` 扫描闭包内，不是新面 | 尺寸与 sha256 都从文件本身读（`PIL.Image.size` 与 `read_bytes()`），不猜 | 零新依赖；`--draw-image` 一条旗子 + 一段排版 |

**择一决定：不引新依赖，借的是"边界声明"这一层，不是实现。** 上面五个候选里没有一个能在
本机解释器（3.9.6）装上，这是本轮实测到的硬事实——`cadquery>=2.8`、`pyvista`、`trimesh>=5`、
`pillow>=12` 四家的 `requires_python` 都在 3.10/3.11 以上，而本仓的契约是 `>=3.9,<3.13`。
即便升到 3.11，CadQuery 那条路的官方页面自己挂着"功能有问题请报 bug"的警告，
PyVista 的离屏配方要装 `libosmesa6`——那都是把"能不能出图"变成一个宿主问题。
比"能不能出图"更前置的是**"这张图算不算证据"**：本仓对装配视图的既有裁决是
"有一个零件没声明 explode 就 rc=2 拒画"（`cad/assembly.py`，README 速查同段），
理由是摆开一半的爆炸图会让读者把"没动"当成"就该在那儿"。渲染器解决不了这个——
它没有装配约束也没有碰撞检查，画出来的只会是一张**看起来完整**的示意图。
所以本片借的是那条"缺前提就不画"的纪律，实现自研（PIL 量尺寸 + reportlab 排版），
并把"改这条裁决"作为下一片的显式入口（§七.1）。

**子代理读数更正**：派去检索的子代理交回的结论里有一句是 **"vis.py 里没有
`SetOffScreenRendering` 调用"**。我自己重开 `https://raw.githubusercontent.com/CadQuery/cadquery/master/cadquery/vis.py`
后读到 `vis.py:450` 就是 `win.SetOffScreenRendering(1)`（在 `if not interact:` 分支里）——该句作废。
更正后结论不变（交互器无条件构造、官方警告、3.11 门槛三条都还在），但**依据换了**：
从"它不支持离屏"改成"它支持离屏但功能自带 bug 警告、且装不进本仓的 Python 下限"。

## 一之二、本轮哪些改动**没有**做选型检索，理由逐条写清

规则允许"影响范围明确的局部修复"跳过检索，但要求主动说明跳过了什么、为什么。
本轮 8 处改动分三档：

- **跳过，理由是候选集只有一个**（不是"我懒得查"）：六道拒绝时机的改动（①-⑥）与
  `doc_reference_census` 的全序修复。这两处要定的不是"用哪个方案"，而是"判据放在落盘前还是落盘后"，
  没有第二个技术形状可比；引入任何库都不解决这个问题。
- **跳过，理由是沿用上一片已检索过的通路**：图片层的 reportlab `drawImage` +
  `STSong-Light` 与 78 mm 缩放上限。依赖与字体方案第 80 片已定案，本轮只多一个 API 调用；
  版本与 License 本轮仍自己重开 PyPI 对过（`reportlab@5.0.1` `requires_python "<4,>=3.9"`、
  `pillow@12.3.0` `MIT-CMU` + `>=3.10`）。**没有**重读 reportlab 的图形手册页 ——
  那一页只有子代理读过，所以本文档任何地方都不引它的原话（grep 得到 0 处，是刻意的）。
- **该查而当时没查，本轮补**：`tests/test_changelog_integrity.py` 这面新判据。
  它是"新量具"形状的改动，按规则必须先检索成熟实现再决定自研；我第一轮直接自研了。
  补做的检索（keep-a-changelog 的机检器、corgibytes 的 changelog linter、markdownlint/remark 的
  重复行与重复标题规则、pylint `R0801` 等）由第二个只读子代理在跑，
  **结论未回来之前本节记为"检索进行中"**，回来后按四段式补进 §一 的表里；
  如果答案是"有现成工具能判这两形状"，那把门禁就该换成它或借它的判据命名，
  而不是因为我已经写了 370 行就保留。

## 一之三、补做的选型：CHANGELOG 门禁该不该用现成工具（结论：主判据留自研，借语义）

§一之二 把这一格记成"检索进行中"。检索回来后按四段式补在这里——
**动手前我没查，这是流程违规，不因为结论支持自研就改写成一个没犯过的错**。
标注规则：`[亲验]` = 我本轮自己打开过那个源；`[子代理]` = 只读子代理打开并跑过，我没重开。

**候选清单（都是真实存在、可打开的）**

| 候选 | 功能匹配度（形状 1＝连续重复块 / 形状 2＝条目记号重复） | License | 维护活跃度 | 安全 | 代码质量 | 适配成本 |
| --- | --- | --- | --- | --- | --- | --- |
| `jscpd@5.3.2`（copy/paste 检测，Rust 引擎） | 形状 1 **能**（按 token 游程 + `--min-lines`）；形状 2 **不能** | MIT `[亲验]`（`registry.npmjs.org/jscpd/latest` 的 `license` 字段） | npm latest 5.3.2 `[亲验]`；发布日期 `[子代理]` 2026-09-23 | 扫描时不联网（`--semantic` 才要下载模型）`[子代理]` | 8 个平台 optionalDependencies `[子代理]` | 要 Node；**退出码有陷阱**：子代理实测有 clone 时仍 `rc=0`，必须加 `--threshold 0`/`--exit-code` 才会红 ⇒ 直接接进 CI 就是一条假绿 |
| `chavacava/changelog-lint`（Go，`*-repetition` 一族规则） | 两条形状都**不能**：规则键在 `## <semver>` 标题上，而本仓 106 条记账是 9 个标题下的 `- **v…` 项目符号 | MIT `[子代理]` | 仓库已 archived、迁 Codeberg，最后 push 2025-04-04 `[子代理]` | 本地二进制 | — | 结构上看不见本仓的条目形状 |
| `markdownlint@0.41.1` 的 MD024 | 只判"相同**标题**文本"（`no-duplicate-heading`，还有 `siblings_only` 这个专为 changelog 允许重复的开关）⇒ 与形状 2 的"条目记号唯一"不是一回事 | MIT `[子代理]` | 2026-07-13 `[子代理]` | 本地 | — | `MD024` 文档页 `[亲验]`（`raw.githubusercontent.com/.../doc/md024.md`，读到 `siblings_only` 参数与其用途） |
| `@metamask/auto-changelog@6.2.1` 的 `validate` | 判的是 unreleased/未归类/缺当前版本/缺 PR 链接/缺依赖 bump——**没有**任何重复检测；且要求 Node `package.json` + git tag 才能跑 | `(MIT OR Apache-2.0)` `[子代理]`（我这次取 `bin` 字段时 JSON 形状看错，license 未亲验） | 2026-08-18 `[子代理]` | 本地 | — | 本仓不是 Node 项目，装不上这个前提 |
| `pylint` R0801 `duplicate-code` | 判的是**多文件之间**的相似 token 流，不是单文件内的重复块 | GPL-2.0-or-later `[子代理]` | 活跃 `[子代理]` | 本地 | — | 用错工具：它连"同一份文件里贴了两遍"都不报 |
| `keep-a-changelog` 规范本身 | 只是格式约定；仓库不提供机检器 | MIT `[子代理]`（我打 GitHub API 那次返回空，**未亲验**） | — | — | — | 不能判红 |

**择一决定：自研判据留下，但明确借了什么。**
没有任何候选覆盖形状 2（"同一片段被部分重贴、条目记号重复"），而形状 2 恰恰是部分重贴能活下来的那一半；
覆盖形状 1 的 `jscpd` 又是"有 clone 也退 0"的语义，接进 CI 得先配 `--threshold 0`。
所以主判据继续是 `tests/test_changelog_integrity.py`。从这些工具里借的是四件事，不是一句"参考了"：

1. **`chavacava/changelog-lint` 的"按结构键判 repetition"粒度**——本仓的 `find_duplicate_entry_headings`
   判 `(vN.M, F-号, 第 N 片)` 三元组唯一，正是 `-repetition` 的按键判法，而不是按字节游程判；
2. **它的"语法错 ≠ 规则失败"退码分离**——反映成本守卫的两条分母断言：读不到文件/条目行与记号数
   不等时**拒绝报 0**，而不是安静地判"没有重复"；
3. **markdownlint 的规则单责与 `MDxxx` 命名习惯**——两把判据各管一种形状、各自带必不开火的控制；
4. **`jscpd` 的"最小游程窗口"语义**——本守卫的 `min_run=6` 就是同一族旋钮，只是实现成精确行比较而非
   Rabin-Karp token 哈希（正因为按精确行比，才有 6 行灵敏度与今天 0 误报的余量）。

**子代理实测的关键对照（我没重跑 jscpd，标 `[子代理]`，但它改变了我的结论）**：
真文件 3132 行在 `--min-tokens 20/30/50/80` 下 0 clone；追加 30 行尾巴 ⇒ 报 29 行 484 token；
追加 6 行 ⇒ 在 20/30 档开火、**50 档静默**；重复一条条目行 ⇒ 0；
同一 `v5.10 F-DRAW-01 第 2 片` 换了措辞 ⇒ 连 `min-tokens 1 / min-lines 1` 都**不开火**；
而把窗口压到 1 行时，干净文件本身就报 98 个 clone。
⇒ 结论落地为两条：**(a)** 不把 jscpd 接成主判据（形状 2 结构上看不见，收紧就 98 误报）；
**(b)** 记一条待办：若要"第二把尺"，`jscpd CHANGELOG.md --min-tokens 20 --min-lines 5 --threshold 0`
是可行的补充档，但必须先验 `--threshold 0` 真能把它变红——不加就是假绿。已进 §七.7。

## 二、两层都要有独立验法

- 有图：`page.images` 非空 **且** 文字仍可抽取（图文两层共存，不是把文字画成图）。
- 没图：**每一页**都没有图片对象（防"留一张空白占位图"这种看起来完整的东西）。
  这条负向断言第一版写成查 `/Contents` 字典里有没有 `image` 键——恒真的空话；
  换掉之后用变异证明它有牙：`docs/audit/s81/battery81.py` 的 **Y1** 臂就是
  "没图那条路也 `drawImage` 一张真 PNG"（用仓库自带的 `assets/golden-references/wbx1/manual_montage.png`），
  落地后 `test_absence_of_an_image_is_stated_in_the_document` 翻红，还原后绿。

## 三、拒绝形状（六道都在写任何产物之前）

1. `--draw-image` 指到不存在的文件：CLI 在生成之前 `rc=2`（用例断言 Markdown 也没落盘）。
2. `--draw-image` 给了**空值**：`rc=2`。这条是本轮补的——原先 CLI 用 `if draw_image and …`
   的写法，空串被当成"没给"，于是"作者明确要一张图"被静默降级成"没有图"，
   照样 rc=0 出一份不带图的文档。本仓对这一类的既有态度是"丢掉作者写过的东西 = 交一份
   自称完整其实少了格子的文档"（同一条写在 `torque` 字段的拒绝理由里）。
   注意这与 `_bom_lines_or_none` 的 `bool(db_arg) != bool(bom_arg)` 是**刻意不同**的：
   那里空值就是没给，这里空值是"给了但没给对"。
3. 只给 `--draw-image` 不给 `--pdf`：`rc=2` / 库侧 `ValueError`。这条也是本轮修的时机 bug：
   原先那条检查写在 `path.write_text(...)` **之后**，所以一次被拒的调用仍然留下一个
   没有 PDF 的孤儿 `.md`（侧车还没写，但文档已经落盘）。现在判完参数才动盘，
   用例除了断 raise，还断 `not out.exists()` 与侧车不存在。

4. **文件在，但内容不是可读图片**（第四条，收尾自查按形状补的）：本轮实测三档坏图——
   文本内容冒充 `.png`、零字节文件、被截断的 PNG——三档都抛
   `PIL.UnidentifiedImageError: cannot identify image file …`，而那时 **Markdown 已经落盘**
   （实测残留 764 字节）、PDF 没写、侧车没写，且 CLI 只接 `ValueError`，
   所以用户看到的是一段 traceback 加一个孤儿 `.md`。前三条检查判的都是"文件在不在"，
   这一格正好漏在中间。
   修法是给图片事实一个唯一判据 `read_image_size()`（`Image.open` + `verify()`，
   走格式识别与 chunk 完整性、不解码像素，所以量大也不贵），三处共用：
   库侧在任何写字节之前调它（坏图 ⇒ `ValueError` ⇒ 零产物）、CLI 侧用它给干净的话
   （`rc=2` + "不是可读图片"，**不套**"装配步骤声明不合法"——方向报错读者会去改 manifest）、
   排版侧也读它拿尺寸（原先自己 `Image.open`，两边各写一遍时一边认这张图另一边不认，
   就又是一次孤儿产物）。常驻用例：三档坏图 × 库/CLI 两面 = 6 条，加一条
   "合规 PNG 不许被这道门误拒"；电池 **Y11**（撤库侧校验）与 **Y12**（撤 CLI 校验）各钉一面。
5. `--pdf` 给的位置已经是个目录：`rc=2`。同一类时机 bug 的另一半——reportlab 要到创建
   canvas 才炸，那时 Markdown 已落盘；现在前置判"能不能写"。用例先 `mkdir()` 把目录造出来再
   拒，因为"路径不存在"是合法形状、不是这一格要判的东西。
6. `--pdf` 给了**空值**：`rc=2`。`if pdf_arg:` 把空值读成"没给旗子"，请求于是被静默丢掉。
   改前形状我在 HEAD `6ca9c41` 的工作树上亲手重开过（`PYTHONPATH` 顶到那份 `src/`，读数打了真正
   被加载的文件路径）：Markdown 与侧车**都落了盘**、退码是那份清单自己的 4（球标未收口），
   不是拒绝专用的 2。库侧不动（不给旗子是合法路径，`pdf_path=None`），CLI 侧先拒；常驻用例两面
   都钉，电池 **Y16** 撤掉这条检查必须开火。
   顺序也改了：这条检查挪到第③条**之前**，于是 `--pdf ""` 同时给图时读者拿到的是"给了空值"而不是"要和 --pdf 一起给"（后者支人去补一个已写的旗子）。两条都 `rc=2`、都零残留，退码分不出好坏 ⇒ 常驻用例钉话术（`test_pdf_blank_together_with_an_image_names_the_blank_flag`），电池 **Y17** 把顺序换回去必须开火。

`image_caption` 这个"可改图注"的参数本轮删了：没有任何调用方传它，也没有用例走它——
留着一个没人转的旋钮就是给下一位读者的假承诺。图注改成模块常量 `IMAGE_CAPTION`，
正向用例直接 import 它来断，字面量不在测试里抄第二遍。

## 三之二、独立复核第二轮：reviewer 又抓出五处，一处是它自己的电池替我说话

派第二个只读子代理审 `2075eac..HEAD` 的全量 diff（六类问题：崩溃路径、拒绝一致性、
证据真实性、`NOT_COVERED` 波及面、CHANGELOG 判据能漏什么、本轮新造的假陈述）。
它是在途树与我已提交树混着看的，所以有一句"修复未提交"——那是事实，不是误判。
逐条我自己重开/重跑后的账：

| 编号 | 它的发现（[READ]＝它给了探针输出） | 我这边的复算 | 处置 |
| --- | --- | --- | --- |
| A | 坏内容图片：`.md` 先落盘，`Image.open` 才抛 `UnidentifiedImageError`；CLI `except ValueError` 接不住 → `rc=1` + 孤儿 `.md` | 我同一形状的三档探针（文本冒充/零字节/截断）都是这个结果 | 就是 §三 的第④条，本轮已修；补 3 档 × 2 面 + 合规侧 1 条 |
| B | `--pdf adir`（目录）同样先写 `.md` 再炸 | 复算：`Path.is_dir()` 为真时才炸，不存在的路径是合法新建——我第一版用例把这条写错（没建目录），改后 `DID NOT RAISE` 消失 | 新增第⑤条拒绝 + 用例（建目录做夹具，注释写明为什么） |
| C | `DecompressionBombError` 不继承 OSError/UnidentifiedImageError，会逃出 `except ValueError`；PIL 默认上限 89,478,485 px | 用 `monkeypatch` 把 `MAX_IMAGE_PIXELS` 压到 100 px 真触发（不造 9000 万像素图），确认异常类别与逃逸路径 | 并入第④条的 except；用例断消息里同时有「不是可读图片」与 `DecompressionBomb` |
| D | 只缩不放：1×1 的图被排成 1 pt(≈0.35 mm) 的小点，图注却仍写"示意图"；4000×20 排成 2.3 mm 高 | 认同"不放大"是对的（放大=造像素），错在**证据只报源像素** | 证据加 `placed_mm`；断言取精确换算值——我先写成 `< 0.5`，被自己的电池臂 Y15 打回（写 `[0.0, 0.0]` 也能过），改成 `[round(1/mm,1), …]` |
| E | 图片分支里那条"放不下就换页"不可达：进分支 y=682.0 pt，`draw_h` 被 78 mm(221.1 pt) 压住，触发要 `draw_h > 534.6 pt` | 按它的数复算成立 | 删分支 + 改掉 CHANGELOG 那句"放不下就整块换页"；图固定在首页，由用例钉形状 |
| F | 模式面（P/1/L/RGBA/CMYK/I;16）与 0 高：它测到"全部能嵌"和"0×0 根本存不出来" | 我未重跑这一项（它的探针已给出 PIL 的 `SystemError: tile cannot extend outside image`） | **未找到**需要修的；`if iw and ih` 那个保护按不可达留着不动 |
| G | 成本：6000×6000 PNG（文件仅 0.12 MB）→ maxrss 703 MB、2.48 s；句柄观察是 5 次 `'rb'` + 一次整文件 `read_bytes` | 我改成 `verify()` + 取尺寸两次打开，加 reportlab 自己那次仍是三次打开、一次整文件读；**没省掉读次**，也不假称优化过 | 记账，不改 |

证据真实性那一格另有一条：`pdf.chars` 只数正文写入的字符，不含图框标题栏那两行
（实测 sidecar `chars=276` vs pypdf 抽出 372 个非空白字符），原先只被断成 `chars > 0`。
现在补 `test_chars_counts_body_lines_not_everything_pypdf_can_see`，把这个字段的名字与它真正量的东西对齐。

**`NOT_COVERED` 的波及面**它逐条查了：唯一钉死清单的是 `tests/test_cad_assembly_steps.py:277`
（本轮已翻），其余 8 个读点是复制透传或长度无关（`release_manifest.py:407/460/612` 等），
`--json` 形状无人钉 ⇒ `pdf.image` 新键不破坏任何契约。这一格我复核后同意，没有额外改动。

**电池替我说话的一次**：上一轮 12 臂里 **Y4 存活**——我把第④条加进去之后，
`--draw-image ""` 即使撤掉"空值检查"也会被读图那一步兜住，`rc` 照样是 2。
这正是本仓记过的"一条复合改动要逐支配原告"：一条臂的红被另一条守卫吃掉，
不等于那条守卫有牙。改法是让空值那条**判它自己的话**（CLI 必须说"给了空值"，
不许借读图判据说"不是可读图片"），于是 Y4 重新有目标；这也顺手暴露出
`--pdf ""` 的处理与 `--draw-image ""` 相反（一个当场拒、一个静默当没给）。
**这一条本轮改完了**（不是下一片的事）：`commands_drawing.py` 在生成之前判 `if pdf_arg is not None and not str(pdf_arg).strip():` ⇒ 打印"`--pdf` 给了空值…"并 `return 2`；库侧不动（不给旗子仍是合法路径，`pdf_path=None`）。常驻用例三面都钉：空值拒、不给旗子照常只出 Markdown 且 `pdf` 键写 None、以及叠用时的话术（顺序），电池 **Y16**（撤检查）与 **Y17**（换顺序）各钉一面。

**但 reviewer 交来的读数我重开后作废了一半**：它写"只给 `--pdf ""` 时 `rc=0` 且只出 Markdown"。我在 HEAD `6ca9c41` 的工作树上用 `PYTHONPATH` 顶到那份 `src/`、读数打了真正被加载的文件路径，实测是 **Markdown 与侧车都落了盘、退码 4**（那份清单自己的球标未收口读数）——"静默丢掉请求"这件事成立，"`rc=0`"不成立。退码随清单覆盖度变（全覆盖就是 0），所以这条不能用退码当判据，用例钉的是"拒绝必须给 2""产物必须不在盘上"与"话说对了没有"。

**电池的形状（原写在 §六，那一节整节由 `terminal81.py` 重写，所以搬到这里）**：- 终局 `合计 KILLED 17 / 17；其余按判决分类：无`（臂 17、开火用例名 27 条、`BAD-*` 0 条、存活 0 条）。- 一臂多红本轮 6 支：Y11 4 条、Y12 3 条、Y15 2 条、Y16 2 条、Y6 3 条、Y8 2 条；  上一轮 Y3/Y4 各多红一条普查的"落盘读数==内存读数"用例，本轮没复现  （各 1/1 条），所以那件事记成"同树耦合可复现性未定"，  不记成契约。- Y16 只有一个原告（``tests/test_assembly_steps_pdf.py::test_blank_pdf_value_is_refused_not_treated_as_absent`、`tests/test_assembly_steps_pdf.py::test_pdf_blank_together_with_an_image_names_the_blank_flag``），Y17 也只有一个（``tests/test_assembly_steps_pdf.py::test_pdf_blank_together_with_an_image_names_the_blank_flag``）⇒ 新增的两面各自单点承重。- Y10 的读数形状就是 §四之二 那个症状本身：`1 failed, 57 passed, 24 warnings, 6 errors`——撤掉 `key=_defect_sort_key` 后  崩溃回到 setup 阶段，6 条用例连断言都没跑到；这条臂同时是"新用例有牙"与"旧故障可复现"两份证据。

**两条我自己犯的**（记下来免得只记别人的）：
① 上一轮我普查过期句用的关键词是 `PDF/图框版式`，匹配不到第 56 片取证件里
   写作「PDF 版式」的那一行，于是同一份文档 `:122` 改口、`:24` 还在说没做——
   已就地第二次更正，并落进记忆："否证一处之后要按事实关键词把全文再扫一遍"。
② 我在文档里写的 `assembly_steps_pdf.py:132/:147` 会因这轮插入的行号漂移而失效，
   安全文档那一格的引用要在收尾前重新一遍（已重取）。

## 四、记账面：CHANGELOG 被静默重贴了 2074 行（新常驻门禁）

本轮把自己那条 v5.42 条目写进 `CHANGELOG.md` 时，那个一次性补丁脚本把文件尾部的
**2074 行逐字节又贴了一遍**，接在 `- **v5.41 F-ASSEMBLY-PDF 第 80 片：…` 这行标题的**中间**续上
（工作树 5121 行 vs HEAD 3027 行）。该脚本本轮没有留副本，只留下了后果与下面这份对账读数。
`CHANGELOG.md` 参与发布哈希，而上一轮终局读数是 2622 passed / 0 failed 的 2622 条常驻用例
**没有一条**为此翻红——损坏的是一份"给人看的账"，此前没有一条断言看过它的形状。

- 取证：`git diff --numstat CHANGELOG.md` 读数是 `2094 0`（正当增量只有 20 行）；
  逐行对账确认 `worktree[3047:] == HEAD` 那句标题的后半段 + `HEAD[955:]` **逐行相同**，
  即纯重贴而非改写。修法是截断到前 3047 行，之后 `git diff --numstat` = `20 0`
  （**这一组是修复当场的读数**；本节下面那条 v5.42 条目正文后来又扩到 62 行，
  所以门禁一节引的是量具自己现算的当前值，不是这两个数）。
- 门禁：`tests/test_changelog_integrity.py`（7 条）两把纯函数判据——
  `find_duplicate_blocks(lines, min_run=6)` 抓"从两个位置起连续 ≥6 行相同"，
  `find_duplicate_entry_headings(lines)` 抓条目记号三元组 `(vN.M, F-号, 第 N 片)` 重复
  （单行级重复差 `min_run-1` 行，块判据结构上看不见，所以第二条必须独立存在）。
  真文件分母由量具自己现算并用 `-s` 打出来（`7 passed in 0.12s`）：
  `行数=3089 非空行=2965 条目行=106 完整记号=79 min_run=6`，同一次读数还打出
  "余量读数：2..6 中开火的取值 = 一个都没有"——即真文件里连一对相同的非空行都找不到，
  所以 `min_run` 取 2 今天也红不了，取 6 是给合法样板留余量而不是怕当前红。
  主理人自己重跑的三档规模（不转述子代理）：重贴最后 30 行 ⇒ 1 个块、长 25；
  重贴 500 行 ⇒ 1 个块、长 470 + 7 条条目记号重复；重贴 2074 行 ⇒ 1 个块、长 1981 + 56 条。
  必不开火侧也钉了（`min_run-1` 行重贴、两个相同 2 行样板、三份"A + 6 空行 + B" 全为空；
  主理人另跑一遍"追加两行 markdown 表格样板"⇒ `[]`）。
- **同一族 shapes 在 README 里也有一份**：本轮普查（`README.md` 全文扫，分母非空——
  第一次扫我把 `rglob` 用在文件而不是目录上，读到 0 命中，那是量具自己的盲区，重扫才拿到 2）
  发现 README 速查里 `aipd drawing assembly-steps` 那段被同类补丁脚本插坏过：
  一条命令以续行反斜杠收尾，下一行却是**另一条完整命令**——这是第 80 片留下的，
  第 81 片又往上叠了一行 `\ --pdf --draw-image`。已拆成三条各自完整的示例，
  并把"照着抄会得到不完整命令"这件事写进该段注释。`SKILL.md` 同判据扫过是 0 处。
  **改完同一条普查再跑一遍**：`README.md` 两种形状（续行接另一条命令 / 注释行尾反斜杠）都是 0 处，
  `SKILL.md` 也是 0 处——这一格的"没有"是量具跑过之后读出来的，不是推测。
  这两条形状目前**没有常驻判据**（只在 §七.3 登记为待办），所以它们是本轮手查的读数，不是被谁守着。

### 四之二、量具自己也会崩，而且崩得比缺陷安静

本节上面那些 `vis.py:568 / :448 / :474 / :450` 加一处裸名 `vis.py` 的写法，
把 `scripts/doc_reference_census.py` **整个砸了**：`Ref.key()` 的第三元素在"没写行号"时是 `""`、
写了行号时是 `int`，而它内部 `sorted({r.key() …})` 会在同一 `(doc, target)` 下拿 `""` 与 `455` 比大小，
抛 `TypeError: '<' not supported between instances of 'int' and 'str'`。
症状是它那 6 条常驻用例集体 **ERROR**（模块级 fixture 就崩，不是断言红）——
比"判据判错"更难看见，因为它连"是哪条引用有问题"都不说。定位读数：
按 `(doc, target)` 分组后数"同一组里 `line` 类型混用"的组数，全仓只有 **1 组**，
就是本篇 §一 那个 `vis.py`（5 条引用，4 条带行号、1 条裸名）。

- 修的是**序**不是噪声：新增 `_defect_sort_key()`（把 `""` 折成 `-1`），两档缺陷列表都按它排；
  输出元素形状一字不改（`""` 与 `int` 照原样进 JSON），所以
  `for doc, target, line in report["live_defects"]` 这类消费方不必跟着改。
  历史面本来就"只报不判"，所以这次崩溃**没有**放过任何一条真缺陷——但它让整把尺子失明。
- 常驻用例 `tests/test_doc_reference_census.py::test_history_face_sorts_when_line_shapes_mix`：
  合成语料里对同一个指不回的目标既裸引又两次带行号引，断 `""`、`9`、`455` 三种读数都在且
  `live_defects` 为空；改前的实现在这条用例上抛 TypeError（电池 **Y10** 撤掉 `key=` 那一句就是让它回来）。
  该文件 7 → 8 条，实测 `8 passed in 16.24s`。
- 顺手一条纪律：仓外文件（`cadquery/vis.py` 这类）在本仓文档里带行号引用，会被普查记成
  "指不回"的历史面读数——它不是假话，也不是本仓解析得到的事实；本轮把它留在历史面（只报不判），
  同时在 §一 的表里给出可打开的 URL，URL 才是外部读者能核的那一档。

## 五、第 80 片留下的三处不一致（本片一并修，判据跟着翻）

1. **`NOT_COVERED` 里那句"PDF/图框版式"是假话**：第 80 片已经把 PDF 与图框交付了，
   而每一项都会印进 Markdown 的「本文档不承载」、PDF 正文那份清单、CLI 收尾那一行
   和证据侧车的 `not_covered`——于是**每份带 PDF 的产物都在自称没有 PDF**。
   撤掉该项，并把标题栏一直在单独宣称的「检验点与点检项」并进来（登记表本来就有这句：
   不做逐步骤的检验项接线）。`tests/test_cad_assembly_steps.py::TestEvidenceSidecar`
   那条钉四项清单的断言同批翻，并加两条反向对照：`"PDF/图框版式" not in ev["not_covered"]`
   与 not in Markdown 正文。电池 **Y8** 把旧那项放回去 ⇒ 两条用例一起红。
2. **同一个事实有两处各写一遍**：`_frame()` 的标题栏自写 "工时、扭矩值、检验点、维护指引"，
   正文写 `NOT_COVERED`——两份边界声明互不相干，谁改了另一边都不会红。
   现在标题栏读调用方传进来的同一份 `not_covered`，新增
   `test_the_frame_and_the_body_declare_one_boundary` 把"图框那句 = 正文那份"钉成断言；
   电池 **Y9** 把标题栏那句硬编码放回去 ⇒ 该用例红。
   （`_frame` 里那条分隔线也从 `MARGIN + 60*mm` 改成整幅宽——句子变长后 60 mm 压不住。）
3. **同一句假话还住在第 56 片的取证件里**：`docs/audit/CAD_ASSEMBLY_STEPS_F-DRAW-01_2026-09-25.md:122`
   那行 `- PDF/图框版式：reportlab 中文本机可用，缺的是排版与分页判据。` 在第 80 片之后就不成立，
   而第 80 片只改了登记表与 README，**漏了这一行**——本轮按"接上 X 的那一轮必须 grep 到
   '某类没有 X'并原地改"的纪律补上（原文不删，就地接一段更正并写明是谁漏的）。
   这条不是常驻用例能抓到的：`absence_claim_census` 那把尺子读的是 `registry_data.py` 与
   产品代码的叙述面，`docs/audit/` 在它的作用域外（`doc_reference_census` 才读 docs/audit，
   而它判的是"引用指得回盘上吗"，不是"这句话还成立吗"）。
   本轮的普查读数：`grep -rl "PDF/图框版式"`（去掉 `.venv/ .git/ releases/`）**7 个文件**——
   `CHANGELOG.md`（本轮那条记账）、本篇与第 56 片两份取证件、
   `docs/audit/s81/battery81.py`（Y8 的 old/new 字面量）、`src/aipd_os/cad/assembly_steps.py`
   （解释为什么撤掉该项的注释）、`tests/test_cad_assembly_steps.py` 与
   `tests/test_assembly_steps_pdf.py`（**断言它不出现**的反向对照）。
   七处逐条重开后无一为"活叙述"。顺带记自己一个错：第一遍我写的是
   `grep -rl … releases/ tests/ src/ scripts/ docs/`——**没把 CHANGELOG.md 放进路径清单**，
   于是读到 6 个文件并差点把"6"写上来；分母漏了一个面就不是读数，是猜数。

## 五之二、独立复核：派出去的 reviewer 抓出五处过期镜像（本轮全改，判据跟着开火）

派一个只读子代理按"镜像清单"复核提交 `2df712d`，它交回五条 STALE。
**每条我都自己重开了它指的位置并重跑对应机器**，其中第 3 条是**真红**，不是文本问题：

| # | 位置 | 那句过期的话 | 反驳物 | 本轮处置 |
| --- | --- | --- | --- | --- |
| 1 | `src/aipd_os/cad/assembly_steps.py` 模块 docstring | "版式用 Markdown…所以 PDF 不是不能做，是**本轮不做**"、"明确未实现：…PDF 版式" | 同文件 `:60` 的新 `NOT_COVERED` 注释与 `assembly_steps_pdf.py` 本身 | 两段重写：版式两条都在 + 图片层 + "没有栅格那条路"的裁决；过期项划掉 |
| 2 | `README.md:297` | "not_covered 逐条写明不含维护指引/工时/扭矩/**PDF 版式**" | `assembly_steps.py` 里那四项 | 改成实际四项，并写明第 80 片后这项为什么被撤 |
| 3 | `scripts/absence_claim_census.py` 台账 | 我新写进登记表的那句"本仓没有装配 2D/轴测栅格化那条路"**没挂账** | 机器自己判的：`✗ UNACCOUNTED:cad.assembly_instructions` | 新增登记 `CAD-ASSEMBLY-RASTER-ABSENT`，反证锚点 = `src/aipd_os/cad` 里出现 `to_png / export_png / save_png / rasterize / SetOffScreenRendering / vtkPNGWriter` 任一（本轮实测这 6 个标识符在该目录**0 处命中**，逐条 grep 过），命中即说明栅格路真接上了、这句必须就地改 |
| 4 | `docs/security/dependency-cve-review.md:28`（pillow 行） | "不经手不可信第三方图片；输入均来自**受控生成流程**" | `assembly_steps_pdf.py:132` 的 `Image.open(img_path)`，路径由命令行给定 | 按新事实重写那一格：两个解码点性质不同 + 只读尺寸与字节哈希、不显示渲染、不回写、不发网络；**并记升级受阻**——`pillow@12.3.0` 的 `requires_python` 是 `>=3.10`（PyPI 现读）而本机 venv 是 `Python 3.9.6`，升 pillow 得先动 Python 下限，那是属主裁决项，不是本轮能自决的 |
| 5 | `src/aipd_os/cli/commands_drawing.py:751` 函数 docstring | "`aipd drawing assembly-steps` —— 装配步骤文档（Markdown + 证据 sidecar）" | 它自己的函数体现在会出 PDF 与图片层 | 补成"Markdown，可加 `--pdf` 的 A4 图框 PDF，PDF 那面还能排 `--draw-image`" |

第 3 条的真实代价（不是"文档没改"这么轻）：`tests/test_absence_claim_census.py` **4 条常驻用例红**
——`test_exit_code_zero_on_the_real_repo_and_the_faces_are_named`、
`test_real_repo_all_registered_claims_hold`、`test_every_claim_is_located_in_its_declared_field`、
`test_real_corpus_all_capability_absences_have_a_home`。
第一次干净签出全量跑里最早那批 `F`（第 7-9、12 个用例）就是这 4 条，
**不是负载噪声**——我原先准备把早段红归因给 load 42，是这份归因错了才去逐条开用例名看的。
登记之后重跑：`absence_claim_census` `rc=0`、"判红 0 条：登记的 14 句「仍缺着」现在都还缺着"，
`pytest tests/test_absence_claim_census.py` → **31 passed in 145.78s**。

另外两条 reviewer 顺带交回、我复核为**早于本轮**的欠账：
`README.md:241` 那句"爆炸图与装配约束仍未做"被同文件下面几行的 `--explode` 直接反驳
（第 4x 片接上爆炸图时漏改）——本轮就地更正，只留"装配约束/配合没做"这仍然成立的一半；
`scripts/c6_coverage.py:145-147` 给 `cad.assembly_instructions` 列的 producers/tests 欠
`assembly_steps_pdf.py` 与 `test_assembly_steps_pdf.py` 两项（该档只核存在性与档位一致，
不是判据项）——本轮补上，让普查的 producer 名单与登记表 `implementation_file` 同源。

## 六、终局读数（由 `docs/audit/s81/terminal81.py` 从原件现跑生成，不手抄）

占位：等第 ④ 步那份 0 failed 的报告落盘后由脚本写入。复算入口见本节脚本。

**电池读数已经在盘上**（`docs/audit/s81/battery81.log`，10 臂 **KILLED 10 / 存活 0**，
逐臂打出开火的用例全名，不是只打退码）。两条要如实记的形状：

- **Y3 / Y4 各多打红一条** `tests/test_doc_reference_census.py::test_json_artifact_matches_in_process_reading`。
  原因是量具性质而非判据串味：Y3/Y4 的变异把 `assembly_steps.py` 删掉几行，
  文档里那些 `文件:行号` 引用就落到 EOF 之后或指向别的内容，普查的落盘读数与内存读数当场不一致。
  这两臂**各自想验的那条用例都开火了**（`test_image_without_pdf_is_refused_not_ignored` /
  `test_cli_refuses_blank_draw_image`），多出来的这条是同树耦合，记在这里免得下一位读者以为
  "一条臂只该红一条用例"。
- **Y10 的读数形状就是本节 §四之二 描述的那个症状本身**：`1 failed, 43 passed, 6 errors`——
  撤掉 `key=_defect_sort_key` 之后崩溃回到 setup 阶段，6 条用例连断言都没跑到。
  这条臂因此同时是"新用例有牙"与"旧故障可复现"两份证据。

## 六之二、收口顺序上的一次自伤（真实代价：多烧一整个全量）

第一次干净签出全量（701.4s，`2636 passed / 1 failed / 5 skipped`）里那条红不是产品缺陷，
是我把收口顺序做错了，机检把它照出来了：

- 红的用例：`tests/test_closeout_verifier.py::test_roster_gap_equals_tests_changed_since_the_report`，
  它断的是 **名单缺口 == 报告锚点提交以来 `def` 条数动过的测试文件**。
- 读数：左边 3 个（`tests/test_assembly_steps_pdf.py` 6→13、`tests/test_changelog_integrity.py` 新建 7 条、
  `tests/test_doc_reference_census.py` 7→8），右边 **空集**。
- 来处：`_anchor_commit_for_this_report()` 把"这份报告从哪次提交起算权威"定义为
  **最近一次把同一 `test_report.sha256` 绑进 PROVENANCE 的提交**。我在本轮中途为了刷清单
  跑了两次 `release_evidence.py`（提交 41698a0 与 a3d5159），报告内容没变、sha 相同，
  于是这个基准被一路推到我的测试改动**之后**，`git diff 基准..HEAD -- tests` 自然为空。
  该函数的 docstring 第 165-168 行写的正是这一格（"把 touch 点推到代码改动之后 ⇒ 在途红被放大"，
  第 69 片），这次是我自己把 touch 点挪的。
- 处置：**只有换绑一份新内容的报告能解**，所以按配方走完 ③→④→⑤——先换绑本轮报告
  （提交里如实写"这一跑含 1 条在途红，红在这条自伤"），再跑第二次全量拿 0 failed 那份，
  最后再绑一次并交终局证据。代价：多一整个 700 秒量级的全量跑。
- 立下来的规矩（已写进项目记忆的配方那条）：**本轮只允许跑一次 `release_evidence.py`**；
  要刷清单用 `regenerate_release_manifest.py`（它只动 `RELEASE_MANIFEST.json`，不碰 PROVENANCE）。
  真误绑了不要 revert——那个提交本身就是这条错法的证据。
- 当时我没有去"修"那条判据，理由是它判得对、红的是我的顺序——这句**只对了一半**，
  收尾再撞上同一格时把另一半查清了：`_anchor_commit_for_this_report()` 取的是
  PROVENANCE 历史里**最近**一次绑着同一 sha 的提交。重绑（哪怕内容一字没改）会把基准推到
  本轮测试改动之后 ⇒ 右边空、左边有缺口 ⇒ 必红；而这一红又会被写进被绑的报告，
  `terminal_clean` 读的就是那份文件，于是连带四条常驻用例一起红——**换绑解决不了，
  它会自己续期**。
- 修法取"最早一次绑定"（`_pick_anchor()`：`git log` 新→旧，所以取末项）。基准的语义本来就是
  "这份内容第一次成为权威的那一刻"，之后重绑几次都不该动它。等式 `缺口 == 自基准以来 def 动过的文件`
  一个字没放宽，所以这不是把判据调松，是把基准取错的方向改正。
- 这条改动自己配了**双向**控制（`test_rebinding_the_same_report_does_not_move_the_anchor`）：
  合成历史里同一份 sha 真被绑两次、中间加一条用例，先断候选序列确实是 `[latest, first]`
  （夹具不开火就等于没测），再断新取法两边都等于 `{tests/test_a.py}`，最后断**旧取法**
  （`latest`）会把等式判坏（缺口有、改动空）。只断"新取法对"抓不到"旧取法错在哪"。
- 为了能拿到 0 failed 的那一跑，把上一份**干净**报告（`4a2d9cf`，exitcode 0、tag 锚点、
  2622 passed / 5 skipped）放回 `docs/audit/pytest-report-v5.6.0.json` 当过渡语料：
  `terminal_clean` 读的是这个路径上的文件，不把它换回干净的一份，本轮任何一跑都必然带着
  上一份报告里的红。本轮的 attestation 报告在绑定那一步会覆盖它——它不是本轮的读数，
  只是让常驻验签器不要在收口顺序上假红。**这一格必须写在账上**，否则下一位读者会以为
  那份 2622 是本轮的。

## 七、下一片入口

1. 自动出装配图（STEP → 离屏渲染）需要选型：本节 §一 已经把四家的 `requires_python`、
   License 与"官方自带 bug 警告"量成数了。要改这条裁决，先给一个 §一 里没有的前提
   （例如本仓升到 3.11 且愿意带 `libosmesa6` 宿主依赖），并回答"渲染出来的图凭什么算证据"。
2. `tests/test_changelog_integrity.py` 的缺陷号还写着"F-CHANGELOG-INTEGRITY，本轮未登记"。
   下一片先看清"账本"到底是哪一本（本轮复核过：**没有** `OPEN_ITEMS`/`链级行为基线` 这类文件，
   `docs/audit/sNN/` 只住电池与读数脚本）——真正有机读的只有两处：
   `scripts/absence_claim_census.py:84` 的 `CLAIMS`（14 行，消费方
   `tests/test_absence_claim_census.py:84,93,142`，判据退码 4）与 `CHANGELOG.md` 的
   条目标题（被 `tests/test_changelog_integrity.py:47-56` 解析，且 `:274,282` 要求
   任何含"第…片"的 `- **v` 行必须带完整 `F-<ID>` 记号）。所以"登记 F-CHANGELOG-INTEGRITY"
   的正确形状是：**下一片的 CHANGELOG 条目自带这个 id**（新行的分母由那两条镜像断言现算，
   加行安全，界值是 `>=2000/>=1800/>=60/>=60`），而不是去某张不存在的表里加一行。
3. README 那处"续行接另一条命令"的形状**没有常驻判据**，本轮已把它量成数（不再是要不要做的猜）：
   主理人自己重跑的普查分母 **183 个 `.md` 文件 / 22,119 行**，其中
   以 `\` 收尾的行 **58** 处；形状 a（`\` 后紧跟另一条 `aipd` 命令）今天 **0** 处，
   形状 b（注释行以 `\` 收尾）今天 **0** 处；
   **正向对照成立**：`git show 3784a0a:README.md` 上两处各命中 1 次
   （`:271` 是形状 a、`:272` 是形状 b），即这条判据能咬本轮真实损坏、今天不误伤。
   ⇒ 结论：形状 a 可以做成常驻判据（挂进 `doc_command_census` 的一档或新常驻用例，
   必开火夹具用 `git show 3784a0a:README.md` 那一段的真实形状，不许手写相似片段）；
   形状 b 只报不判——它是词法巧合，没有结构第二半，任何合法的 `--flag  # 注 \` 都会红，
   今天 n=0 不足以证明它长期安静。
4. 第 79 片两件仍挂着：其余开放来源主机的路径级收紧、`rerun_for_rework` 多轮失败/退避形状。
5. §六之二 那类自伤目前靠 roster 用例事后照出来（代价一整个全量）。**候选的"事前拦"已量过，
   且量出来是"不能这样做"**：全仓 `PROVENANCE.json` 被改写过 217 次，其中
   "相邻两次绑定同一份报告 sha256"**42 次**，再加一条"两次之间 `tests/*.py` 动过"仍剩
   **24 次**——把这个当判据红就是 24 条历史欠账当场炸响，而它们绝大多数是配方内正常的重跑。
   ⇒ 改法不是门禁而是**提示**：`release_evidence.py` 在准备写入时发现
   "同一份报告 sha 已在更早的 PROVENANCE 提交里绑过、且此后 `tests/` 动过"，就在 stdout
   打一行警告（说明这次重绑会前推报告锚点、`test_roster_gap…` 会因此红），
   不改退码、不阻断。下一片按这个形状做，并给它一条"警告必须打出来"的常驻用例
   （用合成 git 历史或临时仓库，别拿主仓历史当夹具）。
6. §一之三 落的一条备选第二尺（**不是必做**）：
   `jscpd CHANGELOG.md --min-tokens 20 --min-lines 5 --threshold 0` 作为形状 1 的补充档。
   接之前必须先证 `--threshold 0` 真能让"有 clone"变非零退码——子代理实测不加它时
   有 clone 也 `rc=0`，那是一条假绿；本仓要的是判据会红，不是会打印。
   并且它只能当**副尺**：形状 2（部分重贴后条目记号重复）它结构上看不见。

## 八、真产物一侧的独立读数（走真 CLI，不是常驻用例）

常驻用例造的是 `220×140` 的合成图；这里补一份**真图真命令**的读数，
免得"夹具全绿而生产侧从没走过"那一格再次发生（工作件在
`/Volumes/Extra/CodeProj/AI全链路自研/tmp/s81/e2e/`，产物 `steps.pdf` 2 页）：

- `aipd drawing assembly-steps --manifest … --pdf … --draw-image assy.png` → `rc=0`，
  CLI 自报"PDF：…（2 页，图框 + 标题栏，文字可抽取）"，证据侧车 sha256 打在收尾行上。
- 独立解码（pypdf 重开 PDF，不信 CLI 自报）：每页图片对象 `[1, 0]`（首页有、次页无），
  抽取文本里 `装配示意图（由作者提供）`、`示意图文件：assy.png`、步骤原文 `支架贴合基面` 都在。
- 证据读数与文件本体对账：`pdf.image = {pixels:[1140,1728], bytes:2300614,
  sha256:f3f31f50…c812}`，与 `sha256(assy.png 字节)` 与 `len(字节)` **逐项相等**（不是抄 CLI 的话）。
- 六道拒绝走真 CLI（`tmp/s81/probe6.py`：每条一个进程、跑前删干净同名产物、跑后按 glob 数残留），
  **9 次拒绝调用全部 `rc=2` 且盘上零残留**，逐条首行原样抄：
  ① `--draw-image 指向的文件不存在：…/nope.png`；② `--draw-image 给了空值：要么给图片路径，要么别给这个旗子`；
  ③ `--draw-image 要和 --pdf 一起给：Markdown 版式不嵌图，只给图就等于把这张图丢掉`；
  ④ 三档坏图（文本冒充 PNG / 零字节 / 截断）都是 `--draw-image 的文件不是可读图片：…
  （UnidentifiedImageError: cannot identify image file …）`；
  ⑤ `装配步骤声明不合法：--pdf 要的是一个文件路径，它现在是个目录：…/adir`——
  只有这一条套在通用前缀下（句子来自库侧 `ValueError`，不是 CLI 自己写的）；
  ⑥ `--pdf 给了空值：不给这个旗子就是不出 PDF；要出就给路径（裸 --pdf 走同名 .pdf）`。
- **检查顺序的读数**：`--pdf ""` **同时**给 `--draw-image` 那一格（probe 里的 `r6b`）今天拿到的是⑥的话，
  改顺序之前拿到的是③的话。两条都 `rc=2`、都零残留，所以这件事在退码面上是看不见的，
  只有话术用例 `test_pdf_blank_together_with_an_image_names_the_blank_flag` 抓得到（电池 Y17 反向钉）。
- 正例在改完顺序后**又重开了一次**（`tmp/s81/e2echeck.py`，1140×1728 的真 PNG）：`rc=0`、
  `fin.md` / `fin.md.evidence.json` / `fin.pdf` 三份齐、pypdf 独立解码每页图片对象 `[1, 0]`、
  图注/图文件名/步骤原文/"本文档不承载"四段文字都抽得到，`pdf.image` 的
  `pixels=[1140,1728]`、`bytes=2300614`、`sha256=f3f31f50…c812` 与文件本体逐项相等，
  `placed_mm=[51.5, 78.0]`（纸面毫米，与源像素两根轴）。
- 无图正例：`--pdf` 不给图 ⇒ `rc=0`、每页图片对象 `[0]`、文本写明"本档没有装配示意图"、
  证据里 `pdf.image` 这个键**在**且值为 `None`。
- 一条顺带读数：`本文档不承载：` 在 2 页 PDF 里出现 **3 次**（每页图框标题栏各 1 次 + 正文清单 1 次）。
  这是标题栏改成读同一份 `NOT_COVERED` 之后的预期形状，不是重复记账；
  如果将来把它做成"只在一处"，需要同时决定标题栏那一格留白还是留短标签，别默认现在这形状是对的。
