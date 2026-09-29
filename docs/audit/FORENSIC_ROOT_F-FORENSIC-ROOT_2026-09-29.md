# F-FORENSIC-ROOT 第 96 片：取证脚本的根路径，以及一处被 `[:8]` 截半的读数

日期：2026-09-29。分支 HEAD 起点：`7b1f25c`（本片第 1 项）。

## 一、这一片问的两个问题

1. **读数串被自己截半**（`scripts/closeout_verifier.py` C5）。上一片把锚点改成"跑内实测"
   （`source_commit_measured`）之后，C5 的说明文案里那个标签是
   `f"…是 {anc_src} {anc_ref[:8]} 的祖先"`——`[:8]` 本意只截 commit，但 `anc_src`
   与 `anc_ref` 在同一 f-string 里，读的人分不清哪一段被截。更要紧的是**没有任何常驻用例
   直读这个字符串**：它是给人在门红时看的唯一线索，截错/丢标签在退码上一个字节都不动。
2. **取证脚本把仓库绝对路径写死**。`docs/audit/**.py` 是复算入口，收口之后没人再跑它们；
   一旦换机或换目录，那些 `Path("/Volumes/…/AIPD-OS")` 就指错树——而这件事**没有任何尺子看得见**。

## 二、技术选型（四段，按最高指令第三节）

### 候选清单

| 方案 | 出处（本轮真实打开） |
| --- | --- |
| A `mypy-baseline` 0.7.4 | PyPI JSON `https://pypi.org/pypi/mypy-baseline/json`：`Development Status :: 5 - Production/Stable`、`License :: OSI Approved :: MIT License`、`requires_dist` 里 mypy/pytest 全部挂在 extra 上、最近一次上传 `2026-04-13T08:01:52`；`Source` 指向 `https://github.com/orsinium-labs/mypy-baseline` |
| B `eslint-baseline` 0.4.0 | npm registry `https://registry.npmjs.org/eslint-baseline`：`license: MIT`、`dist-tags.latest = 0.4.0`、`time.modified = 2022-11-25` |
| C 本仓既有形状 `scripts/ci_surface_census.py` | `--emit` 生成名册 + 常驻用例双向对账（第 91 片立起，已在真仓库跑过 5 道判决） |

A 的 README 我按 `raw.githubusercontent.com/kdmurray-labs/...` 猜过一次 URL 得到 404，
按 PyPI JSON 里的 `Source` 字段纠正后只取到元数据；**未亲验其逐行判据实现**，
上表结论仅来自 PyPI/npm 一手元数据与 PyPI 页面摘要（"syncs errors to `mypy-baseline.txt`,
filtering new issues while tracking resolved ones via diffs"）。

### 六维对比

- **功能匹配度**：A/B 记录的是"每条错误一行"的文本基线，判据是**新错误数与已解决数**；
  本面要的是**逐文件布尔事实**（是否写死仓库内路径）+ **豁免类别** + **理由非空** +
  **名册与规则表同源**。A/B 都没有"类别/理由"这一维，也没有"文件消失 ⇒ 该撤"这一极。
- **License 兼容性**：A、B 都是 MIT（已证实，来自 registry 元数据），与本项目 v5.6.0
  自研发布链无冲突。
- **维护活跃度**：A 最近上传 2026-04-13（活跃）；B 最后一次改动 2022-11-25（三年多未动）。
- **安全风险**：A 要引入 mypy 输出解析链与一个外部基线文件；B 要引入 Node 工具链，
  本仓 CI 面没有 Node job。两者都是"为一条判据多带一个运行时"。
- **代码质量**：未亲验（只读了元数据，不据此打分）。
- **适配成本**：A/B 都需要把"取证脚本根路径"这条判据先做成某种 linter 的输出，
  而这条判据的输入是**整仓 `.py` 的字面量扫描 + resolve 比较**，没有现成 linter 产出它。
  自研侧本仓已有同形状件（C），照抄其 emit/对账/自测三段即可。

### 择一决定

**自研，借语义**：借 A/B 共同的核心思路——"基线只列已知项，判据只在新项与漂移项上开火"，
以及 C 的生成/对账双向形状；不引依赖（两条 MIT 工具都解决不了"豁免类别 + 理由 +
文件消失"这三格，引它们等于多带一个运行时换一条用不上的 diff）。
借了什么的落地处：`audit()` 里"未登记 ⇒ 判红 / 已登记但事实不再成立 ⇒ 该撤"这对判决，
就是 A/B 的 new-issue / resolved-issue 两格换了判据单位。

### 落地处

- 量具：`docs/audit/s96/build_forensic_root_register.py`（`facts/audit/emit/render/--self-test`）
- 名册：`docs/audit/FORENSIC_ROOT_REGISTER.json`（`--emit` 生成）
- 常驻牙：`tests/test_forensic_scripts_root.py`（8 条）
- 变异电池：`docs/audit/s96/battery96.py`（Z0 对照 + 14 支撤销臂）
- 第 1 项修复：`scripts/closeout_verifier.py` C5 分支 + `tests/test_closeout_verifier.py::test_c5_detail_names_the_label_and_a_short_head`

## 三、判据与口径

三档事实由 `facts()` 现扫（`docs/audit/**.py`，**排除量具自身**）：

| 档 | 判据 | 处置 |
| --- | --- | --- |
| 仓库内绝对字面量 | `ABS_RE` 抓到引号内的整串绝对路径，`Path.resolve()` 后落在仓库根之内 | 必须被**恰好一条**点名规则接住并登记，否则判红 |
| 仓库外绝对字面量 | 同一批字面量里不落在仓库内、且命中 `HOST_RE`（`/Volumes`、`/Users`、`/home`、`/tmp` 等真挂载根） | **只报不红**：那些路径本身就是当轮读数的来处 |
| `tempfile.*` | 自己造临时目录 | 不算缺陷，也不进只报档（它可重放） |

判决（每一支都在 `--self-test` 里有对应注入臂）：`根路径未点名`、`名册该撤`（两极：
文件还在但已不写死 / 文件没了）、`点名规则不唯一`、`名册缺条目`、`名册规则过期`、
`豁免理由空缺`；前提：`register_missing` ⇒ 退 2，`corpus_empty` ⇒ 退 2。
档位求和恒等于分母（`exempt + derived + unwatched == py_files`）由常驻用例断，
不靠人记数字。

点名规则三条一律带 `/` 左边界，`--emit` 与 `audit()` 共用同一把 `facts()` ⇒
名册不可能被"重新生成一次"洗成比规则表更宽。

## 四、本轮真实踩到的四格（都已按它行动，不是推测）

1. **ASCII 白名单字符类把全部原告漏掉**。第一版 `ABS_RE` 是
   `["'](/(?:Volumes|Users)/[^"']*?)/?["']`；改成通用类时我又写成
   `[A-Za-z0-9_.+~/:-]` —— 本仓根含中文（`AI全链路自研`），于是真语料读数
   `.py 66 个（写死仓库内 0、写死仓库外 0）` **且 `ok: true`**。
   这是第 90 片"识别面漏非 ASCII 路径"同一格的**第二次**。
   修法：`["'](/[^\s"'`\\]{3,})["']`，并新增常驻用例
   `test_the_abs_probe_reaches_a_non_ascii_repo_path`——它先断前提
   （`assert not str(ROOT).isascii()`，仓库根哪天变成纯 ASCII 就响亮报错而不是静默失效），
   再把真根当字面量塞进夹具断"必须判成仓库内"，并断真语料 `inside_hardcoded > 0`。
   电池臂 Z10 就是这条回归（退回 ASCII 白名单 ⇒ 应被抓住）。
2. **点名规则不许用词形猜**——`battery\d+\.py$` 没有左边界时，
   `docs/audit/s84/after_battery84.py`（等电池退出、做三道到货检验的**接收脚本**，
   不是电池）被同一形状吞成豁免。加 `/` 左边界之后它落回"未点名"，于是本轮把它和
   另外三个同类脚本（`s81/e2echeck.py`、`s81/probe6.py`、`s90/probe_z10_survival.py`）
   的仓库根字面量改成 `Path(__file__).resolve().parents[3]`。
   常驻用例 `test_a_name_shape_rule_can_mis_bucket_a_file` 钉这一格，电池臂 Z? 无（
   形状由规则表本身承担，靠 `after_battery1.py` 夹具开火）。
3. **f-string 里嵌同族引号在 py3.9 会吃掉尾引号**。`f'R = Path("{hard / "src"}")\n'`
   在本仓 venv（Python 3.9.6，`.venv/bin/python -V` 现读）上生成的字节是
   `R = Path("/var/…/hard/src)` —— 收尾引号没了，于是那支"必须开火"的臂读到 0 条判决，
   与"量具没牙"在终端上完全同形。修法：注入文本一律由 `json.dumps` 生成引号
   （`_lit()`），并且 `_write()` 落盘前先 `ast.parse`——夹具必须是合法 Python。
4. **自测臂之间不许留残留**。第 5、6 支臂注入的 `s2/terminal2.py` 没清掉，
   第 8 支"只报不红"的对照臂当场读到它的原告。`_clean()` 改成整片
   `shutil.rmtree(docs/audit)` 再重建，并把这条写进函数 docstring。

## 五、读数

见 §六（认证那一节由收口脚本回填）。尺子侧现读：

- `--self-test`：14 条臂全部立住，退 0。
- 真仓库（`--repo .`）：`写死仓库内 50 / 写死仓库外 21 / 用 tempfile 2`，
  名册 50 条，`exempt 50 + derived 17 == py_files 67`，`unwatched 0`，退 0。
- 门禁自己抓到的第一笔真原告：新增 `docs/audit/s96/battery96.py` 之后
  `--repo .` 当场退 4、点名 `名册缺条目 docs/audit/s96/battery96.py:40`（现读），
  再 `--emit` 才归零——这条不是合成的，是本片过程中自然发生的。
- `tests/test_forensic_scripts_root.py`：8 passed；`ruff check` 与 `mypy` 各自 0 错。
