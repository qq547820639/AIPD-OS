# 装配步骤 PDF 的图片层（F-ASSEMBLY-PDF-IMAGE，第 81 片，2026-09-27）

产物：`src/aipd_os/cad/assembly_steps_pdf.py`（图片层 + 图框边界句单点化 + `image` 读数）、
`assembly_steps.generate_assembly_steps(draw_image=…)`（拒绝时机挪到落盘之前、`NOT_COVERED` 撤掉过期那一项）、
`--draw-image` 旗子（`cli/main.py` + `commands_drawing.py` 三条前置检查）、
`tests/test_assembly_steps_pdf.py` 6 → 13 条、`tests/test_changelog_integrity.py`（新常驻门禁 7 条）、
`tests/test_cad_assembly_steps.py` 一条断言翻转、`scripts/doc_reference_census.py` 的全序修复
配 `tests/test_doc_reference_census.py` 7 → 8 条、README、登记表、
`docs/audit/s81/battery81.py`（10 臂）。

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

## 二、两层都要有独立验法

- 有图：`page.images` 非空 **且** 文字仍可抽取（图文两层共存，不是把文字画成图）。
- 没图：**每一页**都没有图片对象（防"留一张空白占位图"这种看起来完整的东西）。
  这条负向断言第一版写成查 `/Contents` 字典里有没有 `image` 键——恒真的空话；
  换掉之后用变异证明它有牙：`docs/audit/s81/battery81.py` 的 **Y1** 臂就是
  "没图那条路也 `drawImage` 一张真 PNG"（用仓库自带的 `assets/golden-references/wbx1/manual_montage.png`），
  落地后 `test_absence_of_an_image_is_stated_in_the_document` 翻红，还原后绿。

## 三、拒绝形状（三条都在写任何产物之前）

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

`image_caption` 这个"可改图注"的参数本轮删了：没有任何调用方传它，也没有用例走它——
留着一个没人转的旋钮就是给下一位读者的假承诺。图注改成模块常量 `IMAGE_CAPTION`，
正向用例直接 import 它来断，字面量不在测试里抄第二遍。

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
- 我没有顺手去"修"那条判据：它判得对，红的是我的顺序。放宽它等于把"报告与代码同锚"这格
  永久变成假绿（见 [[feedback-gate-criterion-refactor]] 的"判据不许为了绿而松"）。

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
- 三条拒绝各自走真 CLI（`python -m aipd_os.cli.main …`，逐个看 rc 与产物是否存在）：
  缺图文件 / 空值 / 只给图不给 `--pdf` ⇒ 三条都 `rc=2`，且 `.md` **都没落盘**，
  首行分别是"指向的文件不存在""给了空值""要和 --pdf 一起给"。
- 无图正例：`--pdf` 不给图 ⇒ `rc=0`、每页图片对象 `[0]`、文本写明"本档没有装配示意图"、
  证据里 `pdf.image` 这个键**在**且值为 `None`。
- 一条顺带读数：`本文档不承载：` 在 2 页 PDF 里出现 **3 次**（每页图框标题栏各 1 次 + 正文清单 1 次）。
  这是标题栏改成读同一份 `NOT_COVERED` 之后的预期形状，不是重复记账；
  如果将来把它做成"只在一处"，需要同时决定标题栏那一格留白还是留短标签，别默认现在这形状是对的。
