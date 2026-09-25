# AIPD-OS v5.6.0 —— 你的 AI 产品开发主管：把一句话想法，变成有依据、可交付的产品

> 一句话：**AIPD 帮你把「我想做一个……的产品」从一句话，一步步推进到可以交付的成果——研究、设计、验证、生产准备全程由 AI 按专业流程跑腿，每一步都有依据可查，重大决定始终由你把关。**

---

## 目录

1. [AIPD 是什么](#一aipd-是什么)
2. [它帮你做什么](#二它帮你做什么核心功能)
3. [三分钟快速上手](#三三分钟快速上手)
4. [什么时候用得上](#四什么时候用得上常见场景)
5. [你可能想问的](#五你可能想问的faq)
6. [帮助与支持](#六帮助与支持)
7. [附：常用命令速查](#附常用命令速查)

---

## 一、AIPD 是什么

做产品最难的不是动手，而是**全程组织**：这个想法靠不靠谱？用户是谁？技术上做不做得出来？需求有哪些？图纸、物料清单、成本、测试……每一步都要有人盯。一个人或小团队往往顾此失彼，最后不是漏了环节，就是「想当然」地推进。

AIPD（AI Product Development，AI 产品开发）把这件事接了下来。它是一位**24 小时在线的「产品开发主管」**：

- **你负责**：说清楚想要什么、在关键节点做决定；
- **AIPD 负责**：按专业流程推进其余工作，并且**每一步的依据、来源、状态都留痕可查**。

### 一个类比

想象你请了一位经验丰富的产品总监：你把想法告诉他，他列出工作计划、按部就班地干活，每完成一个里程碑就向你汇报；遇到「方向选择、大额投入、安全合规」这类大事，才来敲你的门。AIPD 就是这位总监——只是它 24 小时在线，而且每一步都有记录。

### 它适合谁

| 角色 | 能获得什么 |
|---|---|
| 产品负责人 / 创业者 | 快速验证想法、形成结构化产品定义，不遗漏关键环节 |
| 工程师 | 从需求到设计、验证、制造准备的全程工程推进助手 |
| 管理者 | 随时掌握项目进度、风险、待决策事项，所有结论可追溯 |
| 任何人 | 只需会描述想法、会读进度、会做选择——**不需要会写代码** |

---

## 二、它帮你做什么（核心功能）

### 🧭 1. 把「一句话」整理成清晰的产品定义
告诉 AIPD 一句话想法，它会把它整理成结构化定义：**目标、要解决的问题、目标用户、期望结果、限制条件**。拿不准的地方会被单独列成「待验证的问题」，而不是假装已经知道答案。

> 例：你说「我想做一个帮助独居老人居家康复的产品」，AIPD 会拆出「高龄用户训练难以坚持」「连续选择带来负担」等命题，并标明哪些还需要证据支持。

### 🔍 2. 每个结论都能回答「从哪来的」
- AIPD 会自动检索外部资料（论文、专利、公开信息）作为候选证据，并诚实标注来源与状态；
- 找到的资料需要你确认后，才算「支持某个结论」；没确认的只是「待确认」，不会被当成事实；
- 简单说：**检索到 ≠ 证实**。证据归证据，结论归结论，从不混为一谈。

### 🧠 3. 从证据推导出需求与功能
AIPD 最有价值的能力之一，是「证据 → 产品定义」的完整转译：

```
证据 → 洞察 → 产品机会 → 产品原则 → 需求 → 功能
```

更妙的是**可回溯**：选中任意一个功能，可以一路回查它基于哪条需求、哪条原则、哪个洞察、哪条证据——**不会出现「凭空冒出来的功能」**。

### 🚪 4. 产品定义门禁：由你把关，AI 不自批
需求和功能整理得差不多时，AIPD 会给你一份「门禁报告」：还差什么、哪里冲突、哪些未知项需要豁免。门禁通过后，**由你明确批准**才正式冻结。

- AI 可以解释「为什么建议批准」，但**不能替你做决定**；
- 没有你的批准，任何需求/功能都不会被当成「已定案」。

### ✋ 5. 决策中心：只有大事才来敲门
只有**方向分歧、价值取舍、不可逆投入（如开模、采购）、安全或合规影响**时，AIPD 才停下来问你。每次询问都会给你：问题是什么、AI 的建议、可选方案、每个方案的影响（成本/时间/风险）。日常执行类工作它自己做，不打扰你。

### 📊 6. 随时可见的项目状态
一个命令查看：项目进行到哪个阶段、完成了什么、有哪些风险（红黄绿分级）、有哪些事等你拍板。支持命令行文字版、JSON 格式（便于接入其他工具），也有图形化网页界面。

### 🏭 7. 专业子系统（按需使用）

| 子系统 | 干什么（大白话） |
|---|---|
| 产品手册 | 自动规划并生成图文手册，配视觉质量检查 |
| 工程与图纸 | 从设计意图到生产放行的成熟度推进（C0→C7），带几何校验 |
| 供应链 / 工业化 | 报价、供应商、实验数据登记，试产三阶段（EVT/DVT/PVT）跟踪 |
| 物料清单与成本 | 结构化 BOM（零件、数量、材料、工艺、供应商、单价）+ 一键成本核算（材料 + 模具摊销 + 一次性投入 + 毛利），发布前检查「是否达到开模可用」 |
| 验证与质量 | 验证计划/测试/执行/结果全链路管理，自动标记过时结果，失败自动创建 Issue |
| Issue 与纠正措施 | 问题跟踪、根因分析、纠正措施、重新验证闭环，不能通过简单改状态绕过验证 |
| 制造就绪度 | 确定性计算 8 个维度（产品定义/CAD/BOM/成本/验证/问题/供应链/谱系），缺数据默认「待验证」而非「通过」 |
| 生产发布门禁 | 发布前自动核对：测试是否通过、证据是否齐全、签名是否有效 |

### 🔐 8. 诚实与安全（默认行为）
- **绝不假装成功**：外部能力不可用时，明确告诉你「这项需要外部资源」，而不是返回一个假的结果；
- **未知就是未知**：没评估过的不填默认值，算不准的不显示伪精确数字；
- **数据隔离与加密**：项目之间相互隔离，敏感信息加密存储，所有写操作有审计记录；
- **重要操作需确认**：高风险动作（如正式发布）需要你批准。

---

## 三、三分钟快速上手

> 前提：电脑上已安装 Python 3.9–3.12 并安装好 AIPD（详细安装步骤见 [`QUICKSTART.md`](QUICKSTART.md)）。下面的示例在命令行操作；你也可以运行 `aipd ui` 用浏览器操作。

### 第 1 步：从一个想法开始（约 30 秒）

```bash
aipd onboard --db state.db --idea "我想做一个利用 AI 帮助独居老人居家康复的产品"
```

AIPD 会创建你的第一个项目，把想法整理成初步定义，并立刻产出第一份结果。记下显示的项目 ID。

### 第 2 步：让 AI 推进工作

```bash
aipd run --project p1 --db state.db --until-decision
```

- 一切顺利时，它会一路推进到某个阶段完成；
- 遇到需要你决定的事，它会停下来，并列出待决策事项。

### 第 3 步：查看项目状态

```bash
aipd status --db state.db --project p1
```

你会看到：当前阶段、已完成工作、待决策项、风险等一目了然的概览。

### 第 4 步：做出你的决定

```bash
aipd decide --db state.db --decision-id D-001 --choice "按 AI 推荐路径继续"
```

批准后 AIPD 会继续推进，所有决策都会留档。

### 第 5 步：查看产品定义，必要时批准门禁

```bash
aipd product show --db state.db --project p1      # 产品定义进展
aipd product gate --db state.db --project p1 --propose   # 创建批准事项
```

门禁通过后由你批准，需求与功能才会正式冻结。

### 第 6 步：随时体检（可选）

```bash
aipd doctor
```

一键检查环境是否健康，并告诉你哪些外部能力可用、哪些需要配置。

---

## 四、什么时候用得上（常见场景）

### 场景 1：验证一个新想法值不值得做
```bash
aipd onboard --db state.db --idea "一款给独居老人用的智能服药提醒器"
aipd run --project p1 --db state.db --until-decision
aipd status --db state.db --project p1
```
→ AIPD 会推进研究阶段、检索相关证据、整理关键假设，让你快速判断想法是否站得住。

### 场景 2：已有明确需求，直接开始工程
```bash
aipd init --db state.db --project p1 --name "智能药盒" --goal "开发一款带提醒与联网上报的药盒"
aipd run --project p1 --db state.db
```
→ 跳过想法探索，直接进入工程推进；遇到设计取舍时再请你决策。

### 场景 3：管理一个进行中的项目
```bash
aipd resume --db state.db                        # 上次进行到哪、下一步该做什么
aipd status --db state.db --project p1           # 总览：阶段/风险/待决策
aipd decide --db state.db                        # 处理待决策事项
aipd run --project p1 --db state.db              # 继续推进
```

### 场景 4：生成产品手册 / 推进图纸 / 准备生产
```bash
aipd manual plan --db state.db                        # 规划手册
aipd cad preflight --manifest cad_manifest.json      # 图纸发布前检查
aipd drawing generate --native bracket.py --out out/bracket.dxf --part bracket --views FRONT,TOP  # 3D→二维工程图 DXF
aipd drawing spec --db state.db --project P --out tolerances.json
#   ↑ 声明的生产者：把 Product Truth 里 status=active 的 CTQ 转成上面 --spec 那份 JSON，
#     ctq_ref 由产品写而不是人抄。CTQ 必须显式给 metadata.drawing_feature 与 nominal
#     （不按名字/直径猜映射、缺标称值不拿实测值顶）；有缺口就不落盘并返回 4。
#     记录还可带 "gdt": [{"characteristic": "position", "zone": 0.05,
#     "diametral": true, "datums": ["A"]}] 与 "datum_id": "A" ⇒ 形位框与基准
#     方案同样从需求侧长出；同一特征上「一条尺寸 + 一条形位」合并声明，同类重复则两条都撤回。
#     位置度类声明还可带 "basic": [x, y]（理论精确位置，与挂点同坐标同单位）⇒
#     出图时拿投影实测圆心核偏差（直径带按 2×距离），超带判 position_deviation_exceeded
#     并返回 4；没带 basic 则点名 position_basic_missing，不拿实测当理论位置。
aipd drawing generate --native bracket.py --out out/bracket.dxf --part bracket --spec tolerances.json
#   ↑ 尺寸链按实测孔心自动给出；公差只认 --spec 声明，格式
#     {"features":[{"feature":"TOP.hole_2","tolerance":{"upper":0.05,"lower":-0.05}}],
#      "global_tolerance":{"upper":0.2,"lower":-0.2}}；不传则图上不含任何公差，
#     声明的特征在图上找不到时命令返回 4（未收口）而不是静默少标；
#     同时做一维公差叠加：各段公差带之和超过总宽自己声明的带 ⇒ 判图纸自相矛盾（也返回 4），
#     任何一环没声明公差则判「不可判定」而不是按 0 折算。
#   声明条目可带 "limits":{"min":5.95,"max":6.05}（绝对合格域）：出图时拿投影
#     实测值反查它，落在域外判 ctq_window_violation 并返回 4（图纸与需求不一致）。
#   spec 条目还可带 "gdt": [{"characteristic": "position", "zone": 0.05,
#     "diametral": true, "datums": ["A","B"]}]，配顶层 "datums":
#     [{"id": "A", "feature": "TOP.hole_1"}] ⇒ 画 GD&T 特征控制框，引线挂到实测孔心；
#     基准解析不到、特征不存在或类型不认识即判未收口（4），不画半截框。
aipd drawing generate --out out/bracket.dxf --part bracket --views FRONT,TOP --section Y=0
#   ↑ 剖视是真做的布尔切割：`--section X|Y|Z=偏移` 保留 ≥ 偏移的一侧，切出的材料面
#     用 DXF `HATCH`（ANSI31 图案线）填剖面线，`material_area_mm2` 由内核量得；
#     切不到材料/边界接不成闭合环 ⇒ 明说原因并判未收口（4），不交空白剖视当成果。
#     母视图上会画剖切符号（剖切线 + 指向保留侧的短划 + 两端字母），剖视标 «A-A»、
#     第二刀 «B-B»；切到空气的那一刀不编号也不标符号。
aipd drawing generate --out out/bracket.dxf --part bracket --views TOP --detail "TOP@(-30,0)/12=2"
#   ↑ 局部放大：`--detail 母视图@(u,v)/半径=倍数`，圆心/半径是**母视图局部坐标与模型单位**
#     （可直接抄证据里的孔心），倍数是相对母视图印出比例的放大（须 >1，否则不是放大）。
#     做法是拿放大圆去解析式裁剪母视图**已判定可见/隐藏**的折线：母视图上画裁剪圈 + 编号，
#     放大图按「全局比例 × 倍数」画并标 «DETAIL 1  2:1»；尺寸只从母视图**继承**测点落在圈内
#     的那些且保留原名（`inherited_from`），所以声明好的公差与 ctq_ref 一起带到放大图上，
#     而总尺寸/以零件边缘为锚的链段一律不带（裁剪窗的大小不是零件尺寸）。
#     圆内没有图线 ⇒ 不编号、不画圈，判「放大未收口」并返回 4；母视图名写错直接报错（2）。
aipd drawing assembly --manifest assembly.json --out out/assy.dxf --part ASSY-1 --views TOP,FRONT
#   ↑ 装配图：manifest 形如 {"parts":[{"name":"支架","step":"a.step","balloon":1,
#     "offset":[0,0,0]}]}。**每个零件单独投影再叠加**，所以每条图线天然知道自己属于谁
#     （合并成一次投影会把孔全局重编号、包络并成一个、被压住的边判成不存在）。
#     球标编号**只认你写的 `balloon`**：缺号/重号/写 0/零件重名/STEP 读不到一律返回 2，
#     且不落半成品图纸——按遍历顺序发号等于图纸在声称一个作者从没说过的编号。
#     引线挂在**实测**投影质心上；球标只标在 `--views` 的第一个视图上，证据用 `balloon_view`
#     明写这一点（否则「这里故意不编号」与「发号失败」在证据里同形）。
#     零件沿投影方向叠着 ⇒ 两个球标会指向同一个位置，图能交付但读图分不出归属，
#     这种情况点名告警并建议换一个能分开零件的视图当球标视图。
#     不接 BOM 时明细表只有 ITEM/PART 两列：数量、单位与材料的权威都在 BOM，
#     没接线就一个猜测值都不印。
#     只报「包络投影重叠面积」，**不是干涉判定**（本轮不做实体求交）；
#     装配视图上 `--section/--detail` 直接拒绝（2），爆炸图与装配约束仍未做。
aipd drawing assembly --manifest assembly.json --out out/assy.dxf --part ASSY-1 \
                      --db state.db --bom BOM-001 --project P --explode   # 接上 BOM + 爆炸视图
#   ↑ 给 --db/--bom 就交叉核对球标↔BOM 行，明细表长出 QTY/UNIT/MATERIAL/PROCESS 四列；不给就维持
#     ITEM/PART 两列、一个猜测值都不印。对应关系**只认 manifest 里声明的 bom_item**：
#     {"parts":[{"name":"支架","step":"a.step","balloon":1,"bom_item":"BRACKET-01"}]}。
#     不按零件名字自动映射（名字相似不等于同一个东西）；没声明 bom_item 的零件即使
#     与某行同名也不对上。数量、单位、材料与工艺一律取自 BOM 行，材料/工艺走**同一条**绑定结果
#     （没绑上/歧义/那行本身没填都留空，不写 "-" 这类占位符——占位符会被读成图上有这么个值）；
#     两格各填各的，**不许互相顶**（拿工艺顶材料会把真正缺的那一半盖住）；
#     manifest 写 quantity / material / process 都不读（解析器三个都不认），明细表每格只有一个来源。
#     工艺那一格只装**一道主工艺**：多工序路线（工序顺序/工时/工序成本）本仓不建模——
#     成熟实现把它建成独立对象（Dynamics 365 BC 的 Routing + 行上 Routing Link Code、
#     ERPNext v15 的 BOM Operation 子表），要做就先建 operations 表。
#     供应商**刻意不上图**（裁决，不是漏做）：明细表随图纸版本冻结，供应商是商务事实，
#     本仓契约里它只叫「候选供应商」且归在供应链开发清单。
#     四种情形判未收口（退出码 4）：声明的行找不到 / 同一 item 在 BOM 里有多行（歧义）/
#     零件没声明 bom_item / BOM 有行而图上没有球标指它（这张图漏了零件）。
#     绑不上的数量/材料/工艺都留空，不折算成 0。那四列在不在只看 BOM 接没接上，不看有没有值
#     （「全部行都没材料」恰恰最需要看得见，用「有值才长列」的写法它会整列消失）。
#     出图时命令行直接报哪一半还缺：材料已填 2/2 行、工艺已填 1/2 行，缺的点名到球标。
#     --db 与 --bom 必须一起给，且那张 BOM 得真在：
#     编号写错会当场 rc=2，而不是被当成空 BOM 报成一堆「每行都找不到」。
#     注意 --db 指的是**状态库**：BOM 按产品口径取同目录的 bom.db（不给权威状态库加表，
#     状态库迁移已冻结）。读不到那个文件就报错，不顺手建一个空库。
#     --explode 出爆炸视图：位移**由作者声明**（每件一个 "explode": [x,y,z]），
#     图上一条装配位→爆炸位连线（EXPLODE 层），编号仍只认你写的 balloon。
#     有一个零件没声明就直接 rc=2——摆开一半的爆炸图会让读者把「没动」当成「就该在那儿」。
#     不自动求拆卸方向：文献那套（离散球面搜索 + 无碰撞路径校验）要装配约束与实体求交两样
#     本仓没有的前提，硬算就是画一张没证过的装配顺序。位移与视线平行时告警「看不出分离」。
aipd drawing assembly-steps --manifest assembly.json --out assembly.md --part ASSY-1 \
  --db state.db --bom BOM-1
#   ↑ 装配步骤文档（C6「装配/维护」里**装配**那一半）：同一份清单多一段 "assembly_steps"：
#     [{"no":1,"action":"支架贴基面，两颗 M5 先不拧紧","balloons":[1]}]——
#     序号、动作原文、这一步动哪些球标都由你写。四件事它不做：不补号（没写 no / 重号 /
#     断档 1·2·4 一律 rc=2 并点名缺哪个号）、不按遍历顺序发号、不引用清单里没有的号
#     （balloons 写 7 而图纸没这个号 ⇒ rc=2，文档不能指着不存在的零件）、
#     不接你写的别的字段（"torque": "12 N·m" 是 rc=2 **拒绝**而不是静默丢——丢掉就得到
#     一份少了一格还自称完整的文档；要表达请先写进 action 原文）。
#     反过来，「球标有号而没有任何步骤装配它」不拒：文档照出，但写进未收口、CLI 退 4——
#     图纸编了号、说明书里没人装这一件，是缺陷不是崩。
#     数量/单位/材料/工艺仍只来自绑上的 BOM 行（与装配图同一个 bind_bom、同一条「两格不许互相顶」）；
#     没接 --db/--bom 时零件清单只有 ITEM/PART 两列，一个猜测值都不印。
#     证据侧车 not_covered 逐条写明不含维护指引/工时/扭矩/PDF 版式，读者不会把骨架当全文。
aipd drawing assembly-step --manifest assembly.json --out assy.step --part ASSY-1
#   ↑ 总装 STEP（C6「总装/单件STEP」里的总装那一半；单件一直是零件自己的 .step）：
#     按 manifest 逐件导入再摆放，**摆放只用清单里声明的 offset**——与出图、爆炸视图同一个位置事实。
#     写完立刻**重新导入逐件核对**：每个实体的中心要等于「源 STEP 自己量出的中心 + 偏移」、
#     体积逐件相等（中心管位置、体积管大小，两个都对才算同一件）。对不上就
#     **删掉刚写的文件并报错**——一份声称装了 N 件、实际少一件的 STEP 比不出货危险，
#     下游 CAM/PLM/报价读到什么就是什么。多实体零件按件聚合体积，不按「一个零件=一个实体」猜。
#     两件声明在同一位置是合法的叠料，但会在证据里报 coincident_placements，不静默合并。
#     已知边界（本机实测，不是猜）：OCCT 把非 ASCII 零件名按单字节写进 PRODUCT(...) 变成
#     mojibake，所以「哪个球标对应哪块几何」只由 .evidence.json 承载，不宣称 STEP 里名字可读。
aipd drawing dfm --step bracket.step --out dfm.md --part BR-1 --material 6061-T6 [--spec spec.json]
#   ↑ DFM/DFA 分析：几何事实全部**内核实测**——最小壁厚（**两法各量各的，min 取较薄者**：
#     三轴网格射线进→出配对 + 沿面法向并验材料段。旧话「斜置只测厚不测薄」已被实测推翻：
#     同一块 3mm 斜板三轴法随网格间距给出 1.00/2.02/3.00，法向法恒 3.00；而金样品上三轴
#     抓到 2.00、法向读成 2.24（法向这条还随**每面采样上限**变：12×12 是 2.24，6×6 是 3.73，
#     所以上限与两个数一起交出去）、
#     整孔直径/深度/深径比、**孔周留肉**（孔口圆到最近自由边的精确极值距离，相邻孔口边同算一边；
#     逐口各给读数、行取最薄口、聚合取最薄孔）、最小内圆角半径、同轴孔系、包络与体积。
#     孔与圆角/外圆靠**两根正交的拓扑判据**区分，不读名字也不按半径猜：
#     ① 圆柱面角向张角满一周才算整周（实测 Ø6×10 孔 1.0000、R2 圆角 0.2500、半圆缺口 0.5000）；
#     ② 满一周还分不出孔与外圆，故从面上一点径向外移 1µm 问实体分类器——落进材料里才是孔
#       （Ø20 圆棒侧面也满一周：旧口径把它报成一个 Ø20 的孔，本机复测三件已改正）。
#     阈值每条带来源（URL + 访问日期 + 来处类别 + 一句限定）：金属壁厚 0.8mm 与塑料 1.5mm
#     出自 HLH Rapid 与 Xometry 两页**各自独立**的同量级读数，深径比 4×（保守）/10×（上限）来自 Xometry，
#     公差 0.025mm 是厂商标称可达；本仓**不发明阈值**，也拿不到 ISO 正文（3ERP 那份是转述）。
#     孔边距这一档**厂商页里没有**（本轮检索 HLH Rapid / Xometry / 3ERP 均无），所以走第三类来处
#     `borrowed_out_of_scope`：数借自本表内「最小壁厚」那条，`source.stated_for` 指回去、
#     报告里印出「页内原述是给金属最小壁厚的」，只判 advisory 由制造方核 —— **外推不自证为标准**。
#     内圆角那条厂商给的是「≥ 腔深 1/3」的比值，本仓没有可比的腔深定义 ⇒ 只报实测半径不设阈值。
#     测不出来就记盲区（材料认不出类别、没有整孔、孔口开在曲面上量不到口边圆、没有 --spec、
#     单个平面量不出厚度），**不折算成合格**；误差方向两法各自写明，这条印在报告的 caveat 里。
#     hold 类结论（深孔 >10×、公差严于 0.025）让命令退 4；advisory 与盲区只提示不阻断。
aipd interfaces --repo . --out interface-contract.json
#   ↑ 接口清单与契约证据（**不叫 ICD**：ICD 的「责任与变更授权」「接口职责」两节只能由对侧给，
#     本仓单方产一份叫 ICD 的文件等于伪造签署）。85 条接口逐条带定义件 sha256、取证用例与
#     「证到什么 / 证不到什么」两栏，分母全部**重算**：CLI 56 条取自 command_contract、
#     MCP 6 条取自 mcp_server.py 的 def mcp_*、schema 5 份取自 assets/schemas 实况、
#     出网消费者 11 个按 aipd_os.net.http 的 import 反查——抄计数会在改名那天静默漏项。
#     取证用的是 AST 解析（文件在 + 符号在 + 真收得到 test），另有一条常驻用例把这套解析
#     与 `pytest --collect-only` 的真读数对齐，并配 must-not-fire 一侧。判定七轴：
#     未取证 / 没有实例被按它校验的契约 / 绑定读不到 / 只判存在的落点 / 形状副本与权威不一致 /
#     权威读不到 / 定义件缺失——定义件不在盘上必退 4，其余只让判定 incomplete，
#     默认不拦、--strict 才拦。七轴**逐轴**都有必须开火的用例（整体断 incomplete 会被
#     「别的轴本来就脏」掩盖，第 30 片的电池放过两条这样的注入）。
#     第 30 片更正过这条判据的方向：第 29 片按**文件名字面量**反查消费者，看不见
#     schema_check.py 的**命名约定**绑定（stem + DATA_DIRS），把四份「有人按约定校验」的
#     契约报成孤儿；现在绑定目录用 AST 从真校验器**现抽**，抽不到单列 blind 轴。
#     今天的真读数：五份契约都有实例被按约定校验过（含新补的 assets/templates/fact.json），
#     contracts_without_instance=0、只判存在的落点=0（quality_gate G9 与 outcome_acceptance
#     现在按同名词干的契约核形状，五态 valid/invalid/unreadable/no_schema/missing 都不折成通过）、
#     形状与 FACT_STATUSES 不一致=0（$defs.fact 已单源化到 fact.schema.json）、未取证 2。
#   ↑ 门的要求表（第 31 片）：`scripts/quality_gate.py` 不再自带 G 表，改读
#     `assets/templates/gate_requirements.yaml`（那是唯一权威；读不到就退 3 并拒绝判决，
#     不悄悄拿旧副本继续判）。今天从「声明 50」里强制 41 项——少要求的 9 项（CAD 阶梯的
#     `cad_primary_step` 等）逐项在 `gate_requirements.UNPRODUCED` 里具名并写理由：
#     本仓没有产这些类型的代码，硬接进门只会把 G3-G8 变成永久红灯。
#     `cad_contract` 从今天起是 G3 的硬要求（它有 schema、模板，发布门真在核它），
#     并因此也进了形状门那侧：标了完成却没填 path ⇒ 单独报一条 `path_missing`。
#   ↑ 门禁台账的批准归属（第 32 片）：`gates.approved_by` 原来是
#     `NOT NULL DEFAULT 'AI-internal'`，写入口 `AIPDStateDB.add_gate` 也带同名默认值 ⇒
#     任何不写审批人的调用都把「没人批」记成「AI-internal 批了」。migration v20 把这一列
#     重建为可空、无默认值（V1 冻结文本改不得，所以只能以重建落地），不写就是 NULL；
#     历史行原样保留，由 `src/aipd_os/gate_attribution.py` 在**读侧**按机器身份词表
#     （`src/aipd_os/actors.py`，与 ECO 共用一份）分成 human / non_human / unattributed。
#     今天的真读数：`quality_gate` 输出多一段 `gate_approval_attribution`，只报不判——
#     「这个 actor 真是某个人」没有身份源可证，拿它当放行依据等于把署名当证据。
#   ↑ 门有没有人跑（第 33 片）：契约把 `scripts/e2e_acceptance.py` 写成「数字全链路已打通」的
#     唯一判据，但过去全仓没有一处调用它（`selftest_quality.py`、`selftest_v4.py` 同样没人跑）；
#     今天由 `tests/test_gate_runners.py` 常驻盯着：每台门都要有 spawn 形态的真读者
#     （只被文本提到不算跑过），包装器的退出码透传/`--require-full` 映射/`--json-out` 落盘逐条核。
#     `selftest_quality.py` 也从「两条只看 rc≠0」改成 A1/A2/B1/B2 四支两两对照——
#     **没有合规侧的自检，分不清「门在拦」和「门永远红」**。
#     同一批把 `missing` 的文案归位：校验器只说「文件不在盘上」，
#     「该交付物已标 complete」由拿着交付清单的 `quality_gate` 自己补。
aipd release manifest --db state.db --project P --drawing out/bracket.dxf --bom BOM-1 --out evidence.json
#   ↑ 发布就绪证据现取装配：CTQ 取 Product Truth、gdt 只从图纸证据长出来，版本三源独立不代为对齐
#     图纸按 kind 分成单件图与装配图分别计数（part_drawing_count / assembly_drawing_count）。
#     装配图特有的五条判定：球标↔BOM 未闭合 ⇒ assembly_unresolved（阻断）；
#     已绑上但那一行没填材料 ⇒ material_missing、没填工艺 ⇒ process_missing（各一条、都阻断、
#     逐图点名到球标——C6 要的是「材料与工艺」，合成一条就看不出还差哪一半）；
#     图上数量所属 BOM 与本份证据所核 BOM 不一致 ⇒ assembly_bom_mismatch（阻断）；
#     出图时没接 BOM ⇒ assembly_bom_unverified（提示，不阻断：图仍成立，只是数量没核）。
#     一张漏了零件的装配图不能再读成 ok=true。
#     行级事实覆盖读数随各张图的引用带（bound_rows / with_material / with_process /
#     unbound_rows / missing_material / missing_process / drawings_without_bom），文档级
#     bom_line_coverage 只聚合数得清的那几项——多张装配图的球标都从 1 开始编号，
#     「哪几行缺」一律逐图读、不拍平；没绑上的行不重复算成缺材料/缺工艺，
#     没接 BOM 的图写成盲区而不是 0。
#     --steps-doc assembly.md 才写 C6 的 assembly_instructions 那一格（{path, sha256}）：
#     没交文档就**不写这一格**（而不是写一个空的），侧车不在 ⇒ steps_evidence_missing，
#     球标没人装 ⇒ steps_balloons_uncovered，都阻断；同时带 assembly_steps 汇总
#     （step_count / declared_balloons / unreferenced / not_covered / 侧车哈希）。
#     --dfm-doc dfm.md 才写 dfm_dfa 那一格（{path, sha256} + dfm_summary：
#     hold/advisory/blind/measured、材料分类、not_covered、侧车哈希）；
#     dfm_hold_findings 阻断，dfm_advisory_findings 与 dfm_unmeasured 只提示。
#     --assembly-step assy.step 才写 C6「总装/单件STEP」里总装那一半：文件引用进
#     step_assemblies（门禁当 FILE_KEYS 逐条核存在与哈希），事实进 assembly_model。
#     **不止核「文件在」**（契约明写「STEP 存在不能单独证明生产可用」）：侧车自己声明的
#     每件两个体积要能相减对上、每件源实体数相加要等于它报的 solid_count、侧车写的
#     document_sha256 要等于眼前这份文件——任一条自相矛盾即 assembly_model_disagrees_with_itself
#     / assembly_step_hash_mismatch（阻断，不替它盖章）；核对方法不是「写完回读逐件对上」
#     ⇒ assembly_step_unverified。还跟装配图的球标↔件号对账：只对一张装配图配一份总装 STEP，
#     多张记 ambiguous_pairing（按名字猜配对不判），没图记 no_assembly_drawing（盲区，不判成失败）。
#     非 ASCII 件名在 STEP 里不可读这条边界原样带进 name_readability，不粉饰成「已随模型交付」。
#     侧车名一律 = **产物全名** + `.evidence.json`（`assy.step` ⇒ `assy.step.evidence.json`）：
#     早先各写入点各自「换个后缀」，`assy.step` 与 `assy.dxf` 会拼成同一个 `assy.evidence.json`
#     并互相顶掉——出完图再读模型，读到的是图的凭据（F-EVID-03，已修；拼法收进
#     `cad/evidence.sidecar_path` 一处，写侧读侧都走它，留一处旧写法就有常驻用例判红）。
#     **eco 这一格（第 27 片）**：把文档里所有带 `path`+`sha256` 的条目递归收出来（不硬编码
#     「报告 + 侧车」），逐条问「这份内容是哪张单带来的、那张单复验了没有」。四处置不合成
#     一个百分比：`covered`（`VERIFIED` 单的那行 `after_sha256` 与实际一致）／
#     `eco_change_uncovered`（阻断：有单提到但没有一张**有效**单对得上——被否、被替代、
#     还没批的都不背书）／`eco_change_unverified`（阻断：对得上但单还没走到 `VERIFIED`，
#     **批了不等于复验了**，`open_orders` 点名到单号）／`undetermined`（不阻断只交清单：
#     没有单提到它 ⇒ 本仓没有上一版基线可比，判合格是假绿、判违规是把「没登记」当「改了没提单」）。
#     `coverage` 三档 `complete`/`partial`/`incomplete`：有单却没全覆盖只敢说 partial。
#     门读同一格但口径更严：`production_release_gate` 的 `change_control_closes_deliverables`
#     把「一张单都没有」也读成**不通过**——生产者管「这份证据有没有说错话」，门管「够不够格签字」。
#     **不证明**「自上次发布以来只改了这些」——第 28 片把这一半补上了：
#     --write-baseline 把本次交出去的带哈希交付物落成下一版的基线
#     （aipd.delivery_baseline.v1；**证据还有阻断项时被拒（退 2）且不写文件**，
#     确实要先立基准就加 --acknowledge-not-ready 写明理由，落下来的文件里留着
#     release_ready:false 与那句承认）；下一版 --baseline 指回它，于是「没单提到」一分为三：
#     unchanged_since_baseline（基线证明语义未变 ⇒ **不需要单**，零张单也能 complete）、
#     added / modified（没闭合单即阻断）、removed（基线有而这版没交 ⇒ 必须有一张 VERIFIED 的
#     REMOVE 行认领，否则 eco_deliverable_removed_uncovered 阻断）。比对用**语义摘要**：
#     VOLATILE_FIELDS 按整名声明四个时间类键、递归剔除并把剔掉的位置写进 volatile_dropped
#     （真侧车每次重跑 generated_at 必变，按原始字节比会把「又跑一遍」读成工程变更）；
#     非 JSON 的交付物不省任何东西，语义摘要就是原始哈希。基线文件读坏 ⇒ eco_baseline_unreadable
#     阻断，**不**静默退回「没有基线」（否则删掉基线就是关掉判据的开关）。
#     整仓范围的差集仍未做：tag 清单与今天的实测差 101 增 / 9 删 / 82 改而一张单都没有，
#     接成硬门只能靠补写事后变更单凑绿——那是造证据。
python scripts/c6_coverage.py          # C6 那 15 项交付物各自做到哪一步了（诊断档）
#   ↑ 分母逐字取自 references/production-cad-deliverables.md 那一行：改契约不改映射会当场红。
#     三档读数：有生产者且有常驻用例 / 只有校验方（门会判声明，但产品侧没有落点）/ 零实现。
#     2026-09-25 第 26 片后实测 14 / 0 / 1（第 19 片那次是 13 / 1 / 1）：零实现只剩 ICD 一项，
#     「版本与ECR/ECO」由第 26 片升 producer，第 27 片把它接进发布门（判据读同一格，档位不再变）。「装配/维护」升 producer 指的是**装配那一半**（维护指引仍无
#     生产者），「DFM/DFA」是第 19 片从 checker_only 升上来的；这两句写在映射 note 里、
#     不在档位里，动档位之前先读 note。
#     这张表的作用就是决定下一片做什么，而不是继续在已交付的项上精雕。
#     它刻意**没接进** `production_release_gate`：普查里今天就有零实现项，挂成阻断等于没人看。
aipd truth propagate --db state.db --project P --upstream T-001 --reason "载荷口径改了"
#   ↑ 失效传播：沿血缘把下游 truth 标 stale、生成有界返工任务（rework_tasks，默认上限 3 次），
#     并给出 owner 可读的四段变更说明（改了什么/为何影响/修复计划/需要批准什么）。
#     本次新置 stale 与此前已 stale 分两栏报——空的那一栏不等于「没影响」。
#     有下游待返工即退出码 4。返工的**执行**（run_rework）本仓刻意未接：没有真实执行器时
#     引擎只判 blocked，绝不伪造成功。
aipd truth tasks --db state.db --project P [--status pending]     # 只读列返工待办
aipd industrialize --db state.db                      # 登记报价/供应商/实验数据
aipd validate --manifest manifest.json --target C5    # 验证是否达到目标成熟度
#   ↑ 门里凡是「引用一个文件」的键（drawings / step_assemblies / step_parts / bom /
#     inspection_plan / assembly_instructions / release_manifest / physical_evidence…）
#     **逐条**核存在与哈希：数组形状（模板与 `aipd release manifest` 写出来的就是数组）
#     以前整条跳过 ⇒ 图纸全删、全被改过也读成「所有引用文件可打开」（F-EVID-02 已修）。
#     没写 sha256 的条目只核存在，不现场算一个当期望值（现场算等于永不失配）。
#     哈希核对按级触发：某键只在该目标级被要求时才核哈希，低一级只过 file_openable。
```

### 场景 5：准备开模物料清单与成本
```bash
aipd bom add --db state.db --part 外壳 --material ABS --process "注塑" --quantity 1
aipd quote apply --db state.db --file quotes.csv      # 报价 → quote.* 事实 → 该行单价
aipd bom show --db state.db --tooling 50000 --quantity 1000 --margin 20   # 汇总 + 发布检查
aipd cost calc --db state.db --tooling 50000 --quantity 1000 --margin 20   # 成本核算
aipd bom release --db state.db                        # 清单全过才置 released，否则 exit 4
```

### 场景 6：发布前自查
```bash
aipd release check
```
→ 核对测试数字、证据完整性、签名有效性。全部通过才允许正式发布；任何一项不满足都会明确列出，绝不「放水」。

---

## 五、你可能想问的（FAQ）

**Q1：AIPD 会自己做所有决定吗？**
不会。它只在「方向分歧、价值取舍、不可逆投入、安全合规」时才征求你的意见；日常执行类工作自行完成。所有决策都需要你确认后才执行。

**Q2：「产品定义门禁」是什么？为什么 AI 不能自己批准？**
门禁是产品需求与功能「定稿」前的最后检查。**批准权在你**——AI 可以解释和建议，但不能替你把产品定义「定案」。这是为了确保产品方向由人掌控，而不是由机器默认。

**Q3：「待确认」「待评审」是什么意思？**
AI 找到的资料默认是「待确认」状态。只有经过确认后，它才会被算作支持或反驳某个结论。这样能避免「AI 搜到一篇论文就当结论成立」的想当然。

**Q4：它说「外部能力不可用」是什么意思？**
有些功能（如论文检索、真实图纸内核、视觉检查）需要外部服务或专业软件。未配置时，AIPD 会诚实告诉你「这项暂时做不了」，并指导你配置或人工回填，而不会返回一个假的结果。

**Q5：`aipd run` 跑了一下就停了，正常吗？**
正常。停下来的原因通常有三类：① 需要你决策（用 `aipd status` 查看待决策项）；② 依赖外部能力（需要配置或人工介入）；③ 当前阶段工作已全部完成。用 `aipd status` 一看便知。

**Q6：我的数据安全吗？**
项目数据默认存储在本地数据库；敏感字段加密存储；项目之间相互隔离；所有写操作都有审计记录。生产环境部署时需配置强密钥（详见部署文档）。

**Q7：想重来或恢复怎么办？**
- `aipd resume`：恢复上次会话进度；
- `aipd recover`：回滚最近一次可撤销操作，或从备份恢复数据库；
- `aipd reset`：重置项目（会先备份）。

**Q8：界面显示「blocked_external」是什么？**
意思是：当前步骤需要外部资源（如真实网络检索、真实图纸内核），当前环境不可用。按提示配置相关外部能力，或人工完成后回填结果即可继续。

**Q9：我可以用中文交流吗？**
可以。AIPD 的中文界面与自然语言决策全程支持中文输入。

**Q10：我完全不会写代码，能用吗？**
能。你只需要会描述想法、会读进度、会做选择。上面所有示例命令都可以直接复制粘贴；也可以运行 `aipd ui` 用浏览器全程操作。

---

## 六、帮助与支持

- **上手遇到问题**：先看 [`QUICKSTART.md`](QUICKSTART.md) 与本文 FAQ；
- **环境不对劲**：运行 `aipd doctor` 一键体检，它会告诉你缺什么、怎么补；
- **命令不会用**：运行 `aipd usage` 列出全部命令；每个命令都自带说明与示例（`aipd <命令> --help`）；
- **想了解背后的原理与安全设计**：[`SECURITY.md`](SECURITY.md)（安全模型）、[`THREAT_MODEL.md`](THREAT_MODEL.md)（威胁模型）、`docs/`（架构与版本历史）；
- **参与贡献**：[`CONTRIBUTING.md`](CONTRIBUTING.md) 与 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。

---

## 附：常用命令速查

AIPD 的**一键命令**（`aipd <cmd>`；权威清单是 `src/aipd_os/cli/command_contract.py`
里的 `PUBLIC_COMMANDS`，由 `scripts/skill_quality_audit.py` 与 `SKILL.md` 逐名核对，
旧版别名保留兼容）：

- 核心流程：`init` / `intake` / `resume` / `status` / `run` / `decide`
- 所有者体验：`onboard` / `dashboard` / `operate` / `ui` / `reset` / `recover`
- 手册链：`manual plan` / `manual generate`
- 图纸：`cad preflight` / `cad build` / `drawing generate` / `drawing spec` / `drawing assembly`
- 产品定义：`product show` / `product gate`
- 工业化：`industrialize` / `validate`
- 制造就绪：`bom show` / `bom add` / `bom release` / `quote apply` / `cost calc`
- 工程变更（v5.12）：`eco create` / `eco affected` / `eco transition` / `eco show`（影响清单带改前/改后 sha256；批准人必须与创建人不同，被状态机拒 ⇒ 退 4）
- 审计与发布：`audit` / `interfaces` / `release check` / `test` / `eval` / `package`
- 运维体检：`doctor` / `version --verbose`

---

*AIPD-OS v5.6.0 —— 让你的每个产品想法，都有条不紊地走向现实。*
