# F-DEP-LICENSE 第 93 片：许可证**正文**与元数据对账（2026-09-29）

量具：`scripts/dependency_license_gate.py`（第 92 片立的那把尺，本片给它加第二个读入面）
判据面：已装发行包 wheel 里打包的许可证文件正文（`*.dist-info/**` 下的 `LICENSE*` / `COPYING*`）
常驻用例：`tests/test_dependency_license_gate.py`（9 条 → **17** 条）
量具自测：`python scripts/dependency_license_gate.py --self-test`（5 条标记 → **8** 条）
取证探针：`python docs/audit/s93/probe93_license_bodies.py`
变异电池：`docs/audit/s93/battery93.py`（读数见 §五）

## 一、分母与原告（现读，四条命令）

```
$ python docs/audit/s93/probe93_license_bodies.py
闭包 45 个名字，其中本机已装 43 个；dist-info 正文文件共 48 个
没有正文 1：['casadi']
有正文但头部认不出 5：['certifi', 'multimethod', 'nlopt', 'pillow', 'typing-extensions']
...
casadi    包树内 58 个许可证文件（例 casadi/include/licenses/CSparse/Doc/License.txt）
mypy      包树内  1 个（mypy/typeshed/LICENSE）
numpy     包树内  3 个（numpy/ma/LICENSE 等）
reportlab 包树内  3 个（reportlab/fonts/DarkGarden-copying-gpl.txt 等）
```

```
$ python scripts/dependency_license_gate.py            # 退码 4（第 92 片那一条原告仍在）
归属：allowed 42 / forbidden 0 / review-required 0 / unknown-license 0 / adjudicated 1
      / out-of-closure 28 / unresolved 2 / declared-missing 1
      / body-checked 37 / body-missing 1 / body-unrecognized 5
      / body-severe-mention 8 / body-looser-than-metadata 0
      / duplicate-records 1 / duplicate-conflict 0
正文面：闭包内读到 48 个 dist-info 许可证文件（断言可比 37、无正文 1、认不出 5、
        正文另有更严声明 8、正文比元数据宽 0）；同名多份（全量名册）1 个、说法不一致 0 个：无
✗ 依赖许可证未裁定 casadi `needs-review`
```

**这一片没有抓到活的"正文与元数据打架"**（43 个包的正文都与元数据同档或更宽）。
按第 90 片那条纪律如实落笔：**这是防御性加严**，牙齿由 8 条自测标记 + 14 臂电池 +
7 条新常驻用例承担，不许写成"实测抓出的活缺陷"。

三条**反证读数**（它们是判据形状的直接来源——"窗口判据"会误报的三格）：

| 包 | 全文匹配会读到 | 真相 | 现在的判决（探针原样读数） |
|---|---|---|---|
| `typing-extensions` | 断言 `gpl-3.0-or-later` + `isc` + `psf-2.0` + `bsd` | 正文是 PSF/ISC，文中**提到** GPL | 断言=(无)、提及=`[bsd, gpl-3.0-or-later, isc, psf-2.0]` ⇒ 落"认不出"，只报 |
| `numpy` | 断言 `gpl-3.0-or-later`（GPL 标题在第 140 / 210 行） | 它自己的 BSD 条款在第 3 行，GPL 标题是它 **quoted 进来的全文** | 断言=`[bsd]`、提及=`[agpl, gpl, lgpl]` ⇒ 不红，落 `body-severe-mention` |
| `cadquery-ocp` | 断言 `agpl`（`license: GNU AFFERO…` 是键值行） | 那是它 bundled 的**别人家**组件（`LICENSES_bundled` 698KB） | 断言=`[apache-2.0]`、提及 8 个家族 ⇒ 不红，只报 |
| `reportlab` | 包树里的 `fonts/DarkGarden-copying-gpl.txt` | 那是它附带的**字体**许可证 | 正文面根本不读包树 ⇒ 断言=`[bsd]` |

`nlopt` 值得单独记一笔：它自己的正文头部认不出（MIT 短声明），提及里有 `lgpl-3.0-or-later`
——那是它 bundled 的 NLopt C 库的许可证。**这一格是"提及档"里真实存在的弱 copyleft**，
本片只把它记档不判红（理由见 §四边界 2），列为待裁。

## 二、选型（AGENTS.md 第三节：要拍的是"正文检测用什么实现"）

| 候选 | 一手出处（本轮真开） | 六维结论 |
|---|---|---|
| `scancode-toolkit` 32.5.0 | PyPI JSON：`requires_python >=3.10`、release 上传 2026-05-19、license `Apache-2.0 AND CC-BY-4.0 AND …` | 功能匹配度最高（真做正文检测，规则库带标题/正文分档）；维护活跃；**适配成本＝结构性不可用**：本仓 `.venv/bin/python` 实测 `3.9.6`，`>=3.10` 装不进来；且它自带 ~50 个依赖，会把我们**正在审查的那张闭包**撑大 |
| `license-expression` 30.4.4 | 本机已装（`cyclonedx-python-lib` 的 `license-expression (>=30,<31)`）；`license_expression/__init__.py` 实开 | 只解析/归一 SPDX **表达式**；实测 `get_spdx_licensing().parse('LGPL-3.0-or-later')` 返回的 `LicenseSymbol` 上 `is_copy_left` / `is_perlic` / `text` **全部 ABSENT**（`dir()` 逐字看过）⇒ 既不能替代家族表，也读不了正文 |
| `pip-licenses` 5.5.5 | PyPI JSON：MIT、`>=3.9` | 元数据表格 + `--with-license-file` 只**打印**正文不分类；第 91 片已实测它在 CI 里**没有可失败断言** |
| `spdx-tools` 0.8.5 | PyPI JSON：Apache-2.0、`requires_python >=3.10` | 管 SPDX 文档不管正文；同样被 3.9 挡死 |
| `aboutcode-toolkit` 11.1.1 | PyPI JSON：Apache-2.0、`>=3.9`、末次上传 2023-07-14 | 管 `.about` 文件；活跃度弱 |
| `license-detect` | PyPI 查询返回体无 `info` 字段（即 404） | **未检索到该包**，不补位 |

**择一 = 自研两级指纹 + 借 scancode 的分层思路**（不是引依赖，也不是把它的算法搬过来）：
借的是那一条判据形状——**"文件标题/头部"是断言、"正文中间出现"是提及**，两级不能合成一级；
本仓实测三格（§一 表）就是这一级混用会误报的形状。
决定性理由与前一片同一条：`ci.yml:56` 那个 job 只 `pip install -e .`，
门若依赖未声明的第三方检测器，在 CI 那一侧就永远 SKIP，而"永远 SKIP 的门"正是这一族片子在治的病；
两个真检测器又都要求 Python ≥3.10，连"引依赖"这条路在本环境都不通。

## 三、本片实际改的四处口径（每一处都由读数逼出来）

1. **正文只认 `*.dist-info/**`**，包树里的 LICENSE/COPYING 一律不算它自己的许可证。
   不这么做，`reportlab`（BSD，包树里有 `fonts/DarkGarden-copying-gpl.txt`）会被读成 GPL。
2. **判红只在"正文比元数据更严"**（`SEVERITY[body] > SEVERITY[metadata]`）。
   反向（正文更宽）落 `body-looser-than-metadata` 只报——它不改变"能不能用"的答案。
   提及档（`body-severe-mention`）也只报，不折算成合规、也不擅自判红。
3. **同名多份元数据记录**：档位取**最严**那份、id 取并集，档位不同才判红。
   实测本环境 `aipd-os` 有两份记录（`.venv/.../aipd_os-5.6.0.dist-info` 11 个文件 +
   遗留 `src/aipd_os.egg-info` 206 个）；`同名多份：['aipd-os']` 原本只在名册上出现、
   **一个桶都不进**（对账只在闭包内跑，而项目自身从声明根走不到）⇒ 补了闭包外那一跑，
   `duplicate-records` 由全量名册现算。这条是"覆盖面自己看不见自己"的形状。
   按 id 面判会让"classifier 写 `BSD License` + 表达式写 `BSD-3-Clause`"这种同族双写全部误红
   （第一版就是这么写的，被常驻用例的反极抓住）。
4. **元数据 id 清洗成标识符 + 台账允许粗名覆盖细串**。
   实测 `numpy` / `multimethod` / `reportlab` / `cadquery` 四家把**整段许可证全文**写进
   `License` 字段；那种串进 id 面之后，台账那侧"逐字对上许可证串"在数学上不可能满足 ⇒
   这类包挂上裁定条目也永远红（出口被闸门自己拦死）。清洗后 `numpy` 的 ids == `['bsd']`，
   classifier 的粗名 `bsd` 能覆盖人写的 `BSD-3-Clause`，而真换族（裁成 MIT）仍判「该撤」。

## 四、已知边界（未做与做不到的，逐条写清哪一面）

1. **头部窗口＝前 8 个非空行**。没有标题行、标题在 8 行之后的正文会落"认不出"（实测 5 个：
   certifi / multimethod / nlopt / pillow / typing-extensions）。这是**有意的保守**：
   窗口放宽到全文就会读到 §一 那三格误报。认不出只报不红 ⇒ 不会假绿，也不会假红。
2. **提及档不判红**。所以"某个包把 GPL 组件静态编译进主模块"这一类，本面**看不见**——
   要拦它得解析 `LICENSES_bundled` 的 `name:` / `files:` 字段并对照实际导入路径，
   属另一把尺（未做，列为待裁；`nlopt` 的 LGPL 提及是这条边界上今天最该看一眼的格）。
3. **SPDX 带括号的表达式仍未解析**（`parse_expression` 见 `(` 返回空），沿用第 92 片那条边界。
4. **正文读的是本机 site-packages，不是 `SOURCE_MANIFEST.json` 描述的那套环境**。
   换机器/换 Python 分母就会漂 ⇒ 常驻用例只钉关系（`body-checked >= 30`、casadi 必落
   `missing`、已知误报名单不许开火），绝对数一律留在本文并注明时点。
5. **`aipd-os` 的两份重复安装记录没有被清掉**，本片只让它可见。
   删除遗留 `src/aipd_os.egg-info` 是属主侧动作（不可逆且影响共享状态），不在本轮自主范围。
6. 台账的 `casadi` 条目仍是 `needs-review` ⇒ 门交付时是红的，这是有意的（见 §三与第 92 片 §三）。
7. **顺带量到的一条覆盖面缺口（本轮不修，写清读数）**：CI 的 lint 门跑的是
   `ruff check src tests state_service`（`.github/workflows/ci.yml:144`），**不含 `scripts/`**，
   而量具脚本都住在那儿（**第 93 片当时**读 46 个）。第 99 片重开这一格的现读：
   `find scripts -name "*.py" | wc -l` ⇒ **59 个**（45 顶层 + 14 `scripts/research/`）；
   `ruff check --no-cache scripts` ⇒ **642 条**（本文件第 93 片记的 643 条是当时的读数，
   长尾差 1 条无法指认是哪条），`--output-format concise` 逐条数同为 642、
   只落在 **44 个**文件上（15 个文件 0 命中）；stderr 的
   `Invalid # noqa directive` 由 4 条涨到 **6** 条（新增两处正是第 97 片按同一惯例加的
   `scripts/release_evidence.py:259,272`；连同 `audit_repo.py:326`、`aipd_store.py:195,286,290`）。
   这 6 处的写法是 `# noqa: EMPTY_EXCEPT - 理由`——`EMPTY_EXCEPT` 不是 ruff 的规则码，
   所以 **ruff 侧等于没豁免**（并且那六个位点的体都不是空体，ruff 本来也无事可豁免）；
   真正消费这个记号的是 `tests/test_exception_hygiene.py`，它按文本读，豁免在那一面是生效的。
   ⇒ 一句话：这是**同一个记号在两张面上的读法不同**，不是豁免失效；代价单见
   `docs/audit/SCRIPTS_LINT_FACE_RULING_2026-09-29.md`（含把 `scripts/` 接进 lint 面的
   A/B/C 三选项、各自改哪几行与今天会红哪几条常驻用例）。`ruff check src tests state_service` 与
   `ruff check docs/audit/s93` 本轮复算仍是 `All checks passed!`；
   `docs/audit/s92/battery92.py` 有 5 条 E501（上一片留下，未并入任何门）。
   为什么不在本轮顺手接进 CI 面：接它要先把那 642 条（第 93 片记 643，第 99 片复算）清掉
   或做逐文件豁免，属于"lint 面加宽"那种独立一片（同第 91 片 F-CI-SURFACE 一族），
   混进许可证这一片会把两件事的证据搅在一起。
   **第 99 片复算时更正这里的一个前提**：不必先清完才谈接入——59 个脚本里有 **15 个**
   今天已经 0 命中，`ruff check src tests state_service` 加上那 15 个文件合并跑现读
   `rc=0 / All checks passed!`（stderr 的 invalid noqa 由 3 行涨到 5 行，都是同一记号族）。
   ⇒ "先清债再接入"这个顺序不成立，正确形状是"先把 0 债的那批接进来当棘轮起点"；
   代价与三选项见 `docs/audit/SCRIPTS_LINT_FACE_RULING_2026-09-29.md`。

## 五、同片第二项：清单指纹遇到 float 就**拒算**（`scripts/release_fingerprint.py`）

入口那条写的是"清单里一旦出现 float 就换 RFC 8785"。动手前先量现读：

```
$ python -c "…扫描 SOURCE_MANIFEST.json / PROVENANCE.json / RELEASE_MANIFEST.json 里的 float…"
SOURCE_MANIFEST.json float 个数: 0 []
PROVENANCE.json float 个数: 1 [('.test_report.generated_at', 1790637169.0965009)]
RELEASE_MANIFEST.json float 个数: 0 []
```

⇒ 被这把指纹摘要的文档（`SOURCE_MANIFEST.json`）**今天一个 float 都没有**，
唯一带浮点的是 `PROVENANCE.json` 里 pytest 报告的 `generated_at`，而它不进摘要。
所以本轮**不实现** RFC 8785 的数字序列化（没有消费者的换算就是死码），
改把"一旦出现"钉成前提门：`find_floats()` 深度遍历 → 有 float 就 `ValueError`，
`fingerprint_from_file()` 把它读成 `(空指纹, 说明)`＝**前提塌**而不是"内容不同"
（同第 92 片那条规矩：不可变证据产物的读不出，只能阻塞收尾，不许折算成违规）。

为什么"拒"是对的方向而不是偷懒：`json.dumps` 落浮点走 Python 的 `repr`，
`1` 与 `1.0` 语义相同却得**不同**摘要，跨解释器/跨生产者就漂；
RFC 8785 §3 自己也写明数值须按 ECMA-262 §7.1.12.1 序列化，且
"occurrences of NaN or Infinity MUST cause a compliant JCS implementation to terminate
with an appropriate error"（本轮亲自开 `datatracker.ietf.org/doc/html/rfc8785` 读到，
不是转述）。真要接上 RFC 8785 的那天，触发条件就是这条判据第一次红。

常驻牙：`tests/test_report_manifest_fingerprint.py` 6 条 → **7** 条，新那条形如
"另写一遍的那份独立算式也必须同拒"（`_flatten` 生成器写法与 `find_floats` 不共用），
并带两条不拒的极：整数照算（动了内容就是不同数）、只换 `generated_at`（即便写成浮点）
仍读成同一份清单。

## 六、认证读数（2026-09-29 收口，一次跑通，无第二代）

链条：`17439a4` 代码+文档 → `60e1484` 刷清单 → `git worktree add .wt-s93 HEAD` 干净全量
→ `docs/audit/s93/closeout93.sh`（绑定 → 门 → 读数入库 → 验签）→ 回收 worktree → `-b` 复算。

```
PRECHECK OK: 2749 passed / 5 skipped / collected 2754 / 493.9s / fp a059971de064
MIN_TESTS=2754 （上一代下界 2745）
SKIP 面逐条相同：5 条                     ← 双向差集为空（不是只看 FAIL=0）
BIND_RC=0    回读 OK: source_commit=a66040520139 test_report=2749p/0f/2754t fp=a059971de064
GATE_RC=0    release_ready: True | 未过: 无 | 项数: 8
CV_RC=0      11 格全绿（report_bound_to_provenance / counts_counted_from_roster /
             terminal_clean / roster_covers_tree / pinned_source_binding /
             content_parity_measured / report_fingerprint_recorded /
             report_fingerprint_matches_disk / worktree_clean / plaintiffs_measured /
             size_ratchet）
CVB_RC=0     回收 worktree 后 -b 复算仍 11/11；主树脏条目 0、worktree 数 1
提交链（`git log --oneline` 现读，不是凭印象）：
`17439a4` 代码+文档 → `60e1484` 刷清单 → `fd41e11` 绑定 → `b20a596` 门读数入库
→ `a169c0a` 验签读数入库 → `217db7d` 有效代报告入库 → 本条补记。
**这一行先前是写错的**：我第一版凭轮次印象写成 `5c9b0ad` / `337b...` 两条不存在的哈希，
是 `git log` 现读之后才改对的。留错不删——"读数从印象里补"正是这一族文档最容易犯的病，
把它留在原地比抹掉更有约束力。
```

被哈希文件数 **691 → 691**，新增/移除差集皆空 ⇒ 本轮所有产物
（取证文档、探针、电池、派生脚本、报告、日志）都住在 `docs/audit/`，不参与清单哈希；
参与哈希的只有 `scripts/` 两处与 `tests/` 两处与 `README/CHANGELOG/docs/security` 的文字。

电池是我**亲手重跑**的（子 agent 那份只当导航档）：

```
$ python docs/audit/s93/battery93.py
原文件 sha=73b896ada9bd
[ANCHORS OK] 14 支臂、15 处编辑各命中 1 次
[CONTROL OK] Y0 原样全绿
合计 KILLED 14 / 14；其余按判决分类：无
收尾复算 sha=73b896ada9bd（等于开局，也等于 HEAD）
```

两条机制读数（不是估算，是基线对照现算）：Y1（窗口退回全文）在真语料上多开
**1 笔**打架（numpy），`body-checked` 37→40、`body-unrecognized` 5→2；
Y2（严重度按提及算）多开 **5 笔**（cadquery-ocp / librt / mypy / numpy / pathspec），
`body-severe-mention` 8→3 ⇒ 两臂都不是等价变异。
Y10（重复对账只在闭包内跑）`--self-test` 抓不到，只有
`test_outside_closure_duplicate_records_still_reconcile` 与真语料那条能看见——
合成语料里那个重复名字 `b-dualrec` 从声明根走得到，正是本仓 `aipd-os` 的反面。

门禁今天仍红一条，且不是收尾失败：

```
✗ 依赖许可证未裁定 casadi `needs-review`      （rc=4，全量里由常驻用例钉住"它还没被拍板"）
```

**未证事项**：正文面在真语料上是 **0 条判红**（防御性加严，见 §一），
未验证的是"上游真的低报许可证"这件事在本仓闭包内是否曾发生过——那需要历史轮子的
正文比对，本面只保证下一次发生时会被拦下。
