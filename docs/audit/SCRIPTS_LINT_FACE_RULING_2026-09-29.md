# scripts/ 的 lint 面：一页带代价的裁决请求单（2026-09-29）

要拍的是一件已经挂了三轮的事：`scripts/` 下 59 个 .py 量具脚本（顶层 45 + `research/` 14），
CI 的 lint 面一个都不读。
本文不重复论证"该不该管"，只把**每条路的代价量成数**，让属主一次拍完。
文中每一个数字都是本轮（2026-09-29，同一会话）自己跑出来的，命令见 §0 与附录；
与旧文档或会话笔记不一致处，一律以本轮现读为准，并在 §6 指名差异在哪。

## 0. 面在哪：三条现读

| 面 | 定义处 | 今天读数 |
| --- | --- | --- |
| CI ruff | `.github/workflows/ci.yml:144` = `ruff check src tests state_service` | rc=0，`All checks passed!` |
| CI mypy | `.github/workflows/ci.yml:146` = `mypy`（靶单在 `pyproject.toml:93` `files = ["src", "tests"]`） | rc=0，`Success: no issues found in 483 source files` |
| 收口链 | 全量 pytest + `scripts/production_release_gate.py` + `scripts/closeout_verifier.py` | 仓内既有量具的读数：`docs/audit/CI_SURFACE_REGISTER.json`（由 `scripts/ci_surface_census.py` 现读现写）里 `ruff check src tests state_service` 这条的 `kind="consumed"`、`consumers` **只有** `tests/test_ci_face_gates.py` 一项（`:250-256`），`mypy` 同（`:18-21`）⇒ 发布门与收尾验签都不在那两条的读者名单上 |

（补一句形态核对，免得名字级读数冒充结论：`grep -c "ruff\|mypy"` 在那两个脚本里各命中 0 次；
而 `scripts/release_evidence.py` 命中 4 次却**不算读者**——那 4 处是 `.ruff_cache/`、`.mypy_cache/`
两个排除目录的字符串（`:71-72`、`:82-83`），不是跑判据。所以"收口链不读 lint"以册子那条为准，
上面那两次按名 grep 只作**落点图**，不入代价。）

**顺带量到的一格相邻不对称（与本题不同问，别指望 A 顺手修掉）**：`state_service` 在 ruff 面上
（`ci.yml:144` 第三个参数），却**不在 mypy 面上**（`pyproject.toml:93` `files = ["src", "tests"]`）
⇒ 那张面是"半个文件"的 lint-only，不是本单要拍的 `scripts/` 缺口，拍 A/B/C 任何一条都不改变它。

`ci.yml:253` 把 `lint` 挂在 `release-ready.needs` 上 ⇒ lint 确实是发布门，
但它**只覆盖 src/tests/state_service**；`scripts/` 在 ruff 与 mypy 两张面上都不存在。
`pyproject.toml:85` 的 `src = ["src", "tests"]`、`:88` 的
`select = ["E","F","I","W","UP","B","SIM"]`（`:89` 只 ignore `B008`）对 `scripts/` 同样生效，
差别只在"没人拿它去跑 `scripts/`"。

**常驻那族确实只守着上面两条**：`tests/test_ci_face_gates.py:28-34` 的 `COVERED` 写死了
`ruff check src tests state_service` / `mypy` / `schema_check` 三条，`:41` 那条用例
（`test_ruff_face_is_clean`）的判据是 `:46` 的 `assert proc.returncode == 0`。
所以"另有别的管线会判 scripts/"在本仓读不成立：CI 不判，本地常驻也不判。

**本轮复算入口（一条命令，全部读数可重放）**

```bash
cd /Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
.venv/bin/python -B -m ruff check --no-cache scripts --statistics        # 总数与分档
.venv/bin/python -B -m ruff check --no-cache scripts 2>/tmp/e.txt >/dev/null; wc -l < /tmp/e.txt   # 无效 noqa 必须 6
.venv/bin/python -B -m ruff check --no-cache src tests state_service; echo rc=$?                   # 现面 rc=0
.venv/bin/python -B -m mypy scripts --cache-dir /tmp/m1; echo rc=$?                                 # rc=2，面立不起来
.venv/bin/python -B -m mypy scripts --explicit-package-bases --cache-dir /tmp/m2; echo rc=$?         # rc=1，78 条
```

## 0.1 落点文件的四桶（本轮逐文件现算：`test -e` + `git status --short -- <p>` + `git diff --numstat -- <p>`）

**这是一张快照，读法是"什么时候拍的"**：出单这一轮里，并行会话的第 99 片正在这棵树上写——
`git status --short` 的未提交项在我眼皮底下从 **4 项 → 7 项 → 10 项 M（+2 项 ??，含 `docs/audit/s99/`）**，
HEAD 全程停在 `0c840be` 没动过。表里 `README.md(+20/−3)`、`scripts/ci_surface_census.py(+31/−0)`、
`tests/test_ci_surface_census.py(+8/−0)` 三格在收单前又各重算过一次，数值未变；
**其余脏项（CHANGELOG.md 等）与本文落点不相交，故不入表**。
桶一定会漂：动手前重跑上面那三条命令，别抄本表。

| 落点文件 | 桶（本轮现算） | 对成单的意义 |
| --- | --- | --- |
| `.github/workflows/ci.yml` | 只差授权（tracked+干净） | A/B 的第①位点今天就能动 |
| `pyproject.toml` | 只差授权 | B1 的 `per-file-ignores`、A 的 mypy `files` 都落这儿 |
| `tests/test_ci_face_gates.py` | 只差授权 | 镜像三连的第②位点 |
| `docs/audit/CI_SURFACE_REGISTER.json` | 只差授权 | 第③位点，且只能由脚本重铸 |
| `scripts/manual_chain.py` `aipd_state.py` `aipd_store.py` `decision_policy.py` `release_evidence.py` | 只差授权 | 债最重的三个文件 + 反证靶 + 那 2 处未报警记号，全部干净可改 |
| `tests/test_exception_hygiene.py` | 只差授权 | §3.2 记号对撞若要改名，改这里 |
| `docs/audit/SCRIPTS_LINT_FACE_RULING_2026-09-29.md` | 自有未跟踪 | 本文；改动天然不进别人 diff |
| **`README.md`** | **带他人未提交**（+20/−3） | **C 的落点今天不干净**：现在往 README 写那一节，会把本单的行走进第 99 片的未提交 diff 里。C 的代价因此不是"0 行代码"，而是"等一次别人的提交，或改落 docs/audit"（见 §2.3 修正行） |
| **`scripts/ci_surface_census.py`** | **带他人未提交**（+31/−0） | 重铸器自己在飞：A/B 若要重跑 `docs/audit/s91/build_ci_surface_register.py`，产物会带上别人未提交的判据变化 |
| **`tests/test_ci_surface_census.py`** | **带他人未提交**（+8/−0） | 见下行 |

**A/B 不需要编辑后两个脏文件**（它们只需要通过），所以不构成撞车；但本文凡引用
`tests/test_ci_surface_census.py` 的行号（`:36`、`:41-43`、`:44`、`:51`、`:65`、`:68`）都是**脏树读数**，
那一版自 `:35` 起比 HEAD 版整体下移 8 行（插入的是"报的条数==逐条注入数"那条断言）——
按行号回读时先 `git diff -- tests/test_ci_surface_census.py` 对一次。

## 1. 要拍什么：三个选项，互不蕴含

### R1 F-SCRIPT-LINT —— 44 个量具文件的 642 条 lint 债在 CI 的 ruff+mypy 两面之外（P2，与第 93 片 §四.7、第 97 片 §三"同问"）

> 编号 `F-SCRIPT-LINT` 是**本轮拟名**：按 `SCRIPT-LINT`/`SCRIPT_LINT`/`SCRIPT LINT`/
> `LINT-FACE`/`F-LINT` 四种分隔与大小写形态全仓检索，唯一命中是本文自身 ⇒ 无既有同号。
> 本文不代登记、**不另开缺陷行**，开放项数与桶计数一律不动
> （口径/严度类待裁只成单，"定性成缺陷"是拍板之后的事）。


- **(A) 全量接入**：`scripts/` 整体进 CI 的 ruff+mypy 面，先清零再挂。
  蕴含"642 条 lint 债 + 78 条类型错一次偿清"，**不**蕴含改动节奏可控。
- **(B) 按文件棘轮接入**：先把**已经为 0 的 15 个文件**挂上（今天就能挂，见 §2.2），
  其余 44 个文件登记在豁免清单里，每片只能变少不能变多。
  蕴含"面从今天起只增不减"，**不**蕴含存量被清；也**不**蕴含 A 那种"一次把 scripts/ 全罩住"。
- **(C) 不接入，只写明**：面保持现状，在量具目录里写清"这 44 个文件的 642 条在 lint 面外"。
  蕴含"零代码改动 + 缺口可见"，**不**蕴含任何一条判据变严。
  （注意 C 的前半句是承重的：**README 今天没有"量具目录"这一节**，实测见 §2.3 第三行。）

三者的判据强度互不推出：A 做完 B 就没必要（但 A 要先把 456 行改一遍）；
B 做完 A 只是"清单清空"这一个动作；C 与 A/B 的唯一共同点是"读数不再靠记"。

**A/B 的真正分水岭不是工作量而是咬合面**：A/B 都要动 `ci.yml:144` 那条命令的**字符串**，
而那条字符串正被三处常驻镜像钉着（§2.1），改它=同批改三处；C 一处都不动。

## 2. 每个选项的代价：机器读数

### 2.0 存量底数（A 与 B 共用的分母）

```
ruff check --no-cache scripts  ⇒  Found 642 errors.   （64 fixable，另有 10 需 --unsafe-fixes）
按规则码：265 E702 / 191 E501 / 98 E701 / 28 I001 / 16 E401 / 13 F401 / 5 SIM105 / 5 UP045
          / 4 W292 / 3 SIM102 / 3 SIM115 / 2 B007 / 2 SIM117 / 2 UP035
          / 1 各：B904, E402, F541, F821, SIM108            （Σ=642）
文件数：scripts/ 下 .py 共 59 个（顶层 45 + research/ 14，`ls scripts/*.py scripts/research/*.py`）
        有命中的 44 个；为 0 的 15 个
落点行：642 条只落在 **456 个不同物理行**上
        E702 265 命中 → 155 行；E701 98 命中 → 98 行；E501 191 命中 → 191 行
        三类合计 380 行；与 E702/E701 完全不重叠的"纯超长行" 133 行
        同一行既是 E702 又是 E501 的 44 行；既 E702 又 E701 的 6 行
scripts/research/ 单独量：40 条（即顶层 scripts/ 602 条）
```

**"642 条"不等于"改 642 处"**：分号类一行常带 2–3 个命中（`aipd_state.py:27` 一行三个 E702），
且那 44 行"分号+超长"重合处，拆一次分号两类的债一起掉。A 的改动落点下限按**行数**算＝456 行。

**存量里混着两种债，别一锅端**：**可能藏真 bug 的 19 条**＝
F401 未用导入 13 + SIM115 文件没用 `with` 3 + **F821 未定义名 1** + B904 1 + F541 1；
**其余 623 条是排版/风格/现代化**（E702 265 / E501 191 / E701 98 / I001 28 / E401 16 / W292 4 /
UP045 5 / SIM105 5 / SIM102 3 / SIM117 2 / UP035 2 / B007 2 / E402 1 / SIM108 1）；19 + 623 = 642 ✓。
那条 F821 在 `scripts/decision_policy.py:20:137`：
该行的 `Path(a.event)` 落在 `... if False else ...` 的死支里，所以今天**炸不出来**——
它是"面外看不见的那一类"的最好样本，不是急症。

### 2.1 (A) 全量接入

| 代价项 | 读数 |
| --- | --- |
| 今天会红的 CI 判据 | `ci.yml:144` 一条 job 立刻红：642 errors（rc=1）。它是 `ci.yml:253` `release-ready.needs` 的成员 ⇒ **发布链当场断** |
| 今天会红的常驻判据 | 改了 `tests/test_ci_face_gates.py:29-30` 的 argv 之后，`test_ruff_face_is_clean`（`:41`）当场红，红字里带的就是那 642 条 |
| mypy 半边**不是"多少条错"，是面立不起来** | `mypy scripts` rc=**2**，`Found 4 errors in 3 files (errors prevented further checking)`，其中 `scripts/audit_repo.py: error: Source file found twice under different module names`。要先把模块名解析配好（`pyproject.toml:91-96` 加 `--explicit-package-bases` 等价配置），配好之后实测 rc=1、**78 errors in 23 files**（分档：assignment 13 / arg-type 13 / no-any-return 11 / union-attr 8 / operator 7 / has-type 7 / misc 6 / index 4 / import-untyped 4 / 其余 5）。这 78 条是在 `warn_return_any = true`（`pyproject.toml:94`）下量的 |
| 改动量 | 排版/风格类 623 条，与那 19 条真 bug 候选合起来落在 **456 个不同物理行**上；每次拆行净增 1 行 ⇒ 净增 ≥456 行。其中 64 条可 `ruff check --fix` 自动（I001 28 / E401 16 / F401 13 / W292 4 / UP035 2 / F541 1），10 条要 `--unsafe-fixes`；剩 **578 条手工** |
| 必须同批改的接线位点 | ① `.github/workflows/ci.yml:144`（命令字符串）② `tests/test_ci_face_gates.py:29-30`（`COVERED` 的**键**就是那条命令的逐字）③ `docs/audit/CI_SURFACE_REGISTER.json:250`（同一字符串的登记项，由 `docs/audit/s91/build_ci_surface_register.py` 现读现写，不能手改）④ 若接 mypy 再加 `pyproject.toml:93` |
| 不改 ②③ 会翻红的常驻用例 | `tests/test_ci_face_gates.py:67` `test_register_points_here_and_only_here`（`:79` 断两个集合**逐字相等**）、`tests/test_ci_surface_census.py:51`（`:65` 要求册子里每条命令在 ci.yml 里逐字命中）、`tests/test_ci_surface_census.py:36`（`:44` 要求 `unwatched == 0`，新命令没消费者即红）。**这三条是 A 的隐性入场券，不是可选加固** |
| 会不会误伤既有引用面 | 实测不会判红：现状面（README/SKILL/QUICKSTART/docs 架构与 security）里 `scripts/*.py:NNN` 这种带行号的引用**命中 0 处**，且 `scripts/doc_reference_census.py:192` 的行号判据只判"超出文件行数"；带行号的引用全在 `docs/audit/` 历史面（`scripts/release_evidence.py:235` 被引 14 次），那是只报不判的档 ⇒ 重排会让历史面那些 `:NNN` 指向别处而**不会**报警 |

**"改一处长什么样"**（两行文本都从盘上读，未改）：

E702 一例，`scripts/manual_chain.py:43`
```diff
-    save(a.state, d); print(json.dumps(d, ensure_ascii=False, indent=2))
+    save(a.state, d)
+    print(json.dumps(d, ensure_ascii=False, indent=2))
```
E701 一例，`scripts/aipd_state.py:18`
```diff
-    try: return json.loads(value)
+    try:
+        return json.loads(value)
```
E701 这例顺带说明 A 的**连锁成本不是零**：紧挨的 `:19` 是同一类的 `except ... : raise ...`
（还额外吃一条 B904，报在 `:19:41`），把 `:18` 拆成两行之后**该文件后续行号整体 +1**，
`:18/:19` 上原有 3 条命中的位置全变——这正是历史面引用没人报警的那一格。

### 2.2 (B) 按文件棘轮接入

**首片代价实测为 0 行清零**：把 §2.0 那 15 个已为 0 的文件直接并进现有命令，
面仍是 `rc=0`、`All checks passed!`：

```bash
ruff check --no-cache src tests state_service \
  scripts/ci_surface_census.py scripts/command_surface_census.py scripts/dependency_license_gate.py \
  scripts/doc_reference_census.py scripts/migrate_capability_registry.py scripts/product_capabilities_extra.py \
  scripts/quality_gate.py scripts/regenerate_release_manifest.py scripts/release_evidence.py \
  scripts/release_fingerprint.py scripts/research/fetch_fulltexts.py scripts/research/postprocess.py \
  scripts/selftest_quality.py scripts/selftest_state.py scripts/state_perf_gate.py
# ⇒ rc=0，All checks passed!（stderr 警告从 3 条涨到 5 条，见 §3.2，不翻红）
```

**B 有两种落法，差别就在"只能变少"能不能被机器判**（本节按 AGENTS.md §三出四段，出处均可打开）：

1. **候选清单**
   - **B1 借 ruff 原生 `[tool.ruff.lint.per-file-ignores]`**（配置项，出处：ruff 0.16.1，`pyproject.toml` 的 `lint.per-file-ignores`）。本轮实测它在 0.16.1 上真的生效：登记文件 `rc=0`，未登记的同内容兄弟文件 `rc=1` 报 E702（`--config /tmp/pfi_probe/pyproject.toml`，两臂都跑过）。
   - **B2 自建"文件 × 规则码 → 命中数基线"清单**，常驻用例现跑现比。仓内同形状已有三处先例可借：`tests/test_ci_surface_census.py:68`（注入→开火→补登记→转绿→**撤登记→再开火**四步）、`tests/test_service_write_surface_parity.py:157`、`tests/test_command_surface_census.py:17`（双向棘轮）。
   - 未检索到仓外更成熟的第三候选（ruff 侧没有内置 ratchet，`.ruff.toml` 无基线概念）。
2. **六维对比**（只比这俩真实存在的方案）：功能匹配度——B1 只能按"文件×规则码"**全有全无**地豁免，表达不出"这一格只能变少"（新增命中照样被吞），B2 能；License——两者都是 MIT/本仓自有，无冲突；维护活跃度——B1 随 ruff 走（本仓 `requirements` 钉 `ruff>=0.4`，`pyproject.toml:61`），B2 是自家代码；安全——都无外部执行面；代码质量/适配成本——B1 **约 15 行配置**、B2 **一个新清单 + 一条新用例**（≈60–80 行）。
3. **择一决定**：**先 B1 后 B2，且 B1 必须配一条计数上限用例**。B1 借的是 ruff 的接口语义（不自研豁免解析），把 44 个未清文件按"文件×规则码"写进 `pyproject.toml`；"只能变少"这一格 B1 结构上看不见，所以必须借 B2 的思路补一条常驻断言（现跑 `ruff check <file> --statistics` 与登记值比 ≤）。纯 B1 不是棘轮，只是把债永久化并给它起名叫棘轮。
   *（这一择一只定"若拍 B，内部怎么实现"。A/B/C 本身原先被本单写成"待属主拍板"，
   第 99 片撤回那个框架并按 §5.1 **定为 B**——可自决项不外包，且落点全部可回滚。）*
4. **落地处**：`pyproject.toml:87-89` 之后新增 `[tool.ruff.lint.per-file-ignores]` 段；
   `.github/workflows/ci.yml:144` 的命令改成含 `scripts`（同 §2.1 的 ①②③ 三处镜像一起改）；
   新增常驻用例落 `tests/`（本文不猜文件名，命名与登记随实施那一片定）。

**B 今天会红谁**：首片**一条都不红**（15 个文件本来就是 0，实测 rc=0）。
红的是镜像三连（`tests/test_ci_face_gates.py:67`、`tests/test_ci_surface_census.py:36` 与 `:51`）——
只要 ci.yml 的命令字符串变了而册子没重铸，它们就先红，**这是 B 也躲不掉的入场券**。
mypy 半边本单**定为不接**（技术判断，不占裁决位）：`mypy scripts` 今天 rc=2（模块名撞车），
把它做成"按文件棘轮"要先解决命名，那不是豁免清单能表达的形状。

### 2.3 (C) 不接入，只写明

| 代价项 | 读数 |
| --- | --- |
| 会红的判据 | **0 条**（两条面今天实测均 rc=0，C 不动它们） |
| 改动量 | 0 行代码，文档若干行；**但落点 `README.md` 本轮现算是"带他人未提交(+20/−3)"而不是"只差授权"** ⇒ C 的真实代价含一次"等第 99 片提交"或"改落 `docs/audit/`"的取舍，见 §0.1 |
| 但"README 量具目录"这个落点**当前不存在** | `README.md` 的标题序列里（`## 一、AIPD 是什么` → `## 二、…核心功能` → `## 三、三分钟快速上手` → `## 四、常见场景`）**没有量具/门禁目录一节**；全 README 里"量具"字样只出现 1 次，在 `README.md:623` 的一行注释里 ⇒ C 要么新开一节（那是文档结构决定，不是抄一行），要么改落到已有的机械面上：`docs/audit/CI_SURFACE_REGISTER.json`（32 条 `"command"` 项）旁边那份 CI 面现状文档 |
| 写进 README 的隐性成本 | README 是 `scripts/doc_command_census.py:124` 的 `QUICKREF_FILES` 判红成员（`tests/test_doc_command_census.py:1096` 也以它为独立分母）⇒ 那一节里任何看着像命令的行都会被"举例必须点得到名"的判决过一遍；`docs/audit/` 则是 record 档（同文件 `:158` `RECORD_DIR_PREFIXES`），只报不判。**所以这段文字写在 docs/audit 比写在 README 便宜** |
| C 之后仍然存在的缺口 | 全部：642 条 / 456 行 / 44 文件继续两面不可见，且没有任何机械判据盯这个数——本文的数也一样会漂（§6 就是漂过一次的证据） |

## 3. 分布：规则码 × 文件

### 3.1 前 10 名（本轮 `ruff check --no-cache scripts --output-format=concise` 解析，642 行逐条聚合）

| # | 规则码 | 文件 | 命中数 |
| --- | --- | --- | --- |
| 1 | E702 | `scripts/manual_chain.py` | 86 |
| 2 | E702 | `scripts/aipd_state.py` | 78 |
| 3 | E501 | `scripts/aipd_store.py` | 29 |
| 4 | E501 | `scripts/manual_chain.py` | 23 |
| 5 | E501 | `scripts/aipd_state.py` | 20 |
| 6 | E501 | `scripts/cad_convergence.py` | 18 |
| 7 | E701 | `scripts/manual_chain.py` | 16 |
| 8 | E701 | `scripts/aipd_store.py` | 15 |
| 9 | E701 | `scripts/aipd_state.py` | 15 |
| 10 | E702 | `scripts/aipd_store.py` | 12 |

（≥10 条的格一共 13 个，表里截了前 10；剩下三个是第 11 名
E501 `scripts/faceted_step.py` 11 条，与并列的第 12–13 名
E701 `scripts/decision_policy.py`、E701 `scripts/check_skill_package.py` 各 10 条。）

**集中度是这条裁决真正的抓手**：`manual_chain.py`(126) + `aipd_state.py`(114) +
`aipd_store.py`(61) 三个文件占 **295/642＝46%**，15 个文件占 0 条。
按文件总量排序的前 12：126 / 114 / 61 / 26(`runtime_preflight`) / 25(`cad_convergence`) /
24(`decision_policy`) / 23(`check_skill_package`) / 18(`outcome_acceptance`) / 18(`local_cad_adapter`) /
17(`faceted_step`) / 15(`selftest_v3`) / 15(`lifecycle_gate`)。
⇒ "先接已清零的 15 个"覆盖 25% 的文件、0% 的债；债几乎全在那三个文件里。

### 3.2 无效 `# noqa`：**6 处**，不是 4 处

`ruff check --no-cache scripts` 的 stderr 实测 6 行；去掉 `--no-cache` 只剩 4 行
（`release_evidence.py` 那 2 条被缓存的回放吞掉）。旧文里那个"4"就是缓存读数：

| # | `file:line` | 它实际想豁免的门 | 那处真实形状 |
| --- | --- | --- | --- |
| 1 | `scripts/aipd_store.py:195` | `tests/test_exception_hygiene.py:60`（读 `# noqa: EMPTY_EXCEPT`） | `except ValueError:` + 下一行 `pass` ⇒ 卫生门**真需要**它 |
| 2 | `scripts/aipd_store.py:286` | 同上 | `except json.JSONDecodeError:` + `pass` ⇒ 需要 |
| 3 | `scripts/aipd_store.py:290` | 同上 | 同上 ⇒ 需要 |
| 4 | `scripts/audit_repo.py:326` | 同上 | `except OSError:` / 注释行 / `pass` ⇒ 需要 |
| 5 | `scripts/release_evidence.py:259` | 同上 | `except Exception:` + `return "not-installed"` ⇒ **体不是 pass**，`_only_pass`（`:32-39`）根本不命中，这枚记号是**装饰** |
| 6 | `scripts/release_evidence.py:272` | 同上 | `except (OSError, subprocess.SubprocessError):` + `pass` ⇒ 需要 |

`EMPTY_EXCEPT` **确认不是 ruff 的规则码**：`tests/test_exception_hygiene.py` 的 docstring
（`:4`、`:7`）把它写成豁免政策要求的记号，判据在 `:60` `if "# noqa: EMPTY_EXCEPT" in block: continue`。
该门的扫描面是 `SCAN_DIRS = [src/aipd_os, scripts]`（`:16-19`），且 `scripts` 走
`:26` 的 `glob("*.py")`——**不递归**，所以 `scripts/research/` 14 个文件既不在卫生门里、
也不属于"豁免记号"的争地盘。

**面内同病，且今天就在绿面上**：`src/aipd_os/web/server.py:262`、
`src/aipd_os/supply_chain/quotes.py:146`、`quotes.py:160` 同样用 `EMPTY_EXCEPT`，
`ruff check --no-cache src tests state_service` **rc=0 而 stderr 有这 3 条警告**。
⇒ 记号冲突不会把面判红（`tests/test_ci_face_gates.py:46` 只断 returncode），
A/B/C 都不必为它付账；**但**它决定了"面外警告数"从 3 涨到 5 这类漂移没人报警。

**还有一处真正的对撞**（不是措辞病）：`SIM105`（"改用 `contextlib.suppress`"）在
`scripts/aipd_store.py:194:17 / 285:21 / 289:21` 报的正是上面 1–3 号那三个 try 块。
按 ruff 的建议改 = 删掉 `except ...: pass` = 连 `# noqa: EMPTY_EXCEPT` 一起没地方放；
反过来为了消 ruff 警告而删掉记号、保留 `pass`，`tests/test_exception_hygiene.py:66` 立刻红。
两把尺在同一批行上各说各话 ⇒ 接进面之后这三处**只能选一边**。选哪边是实施侧自决（不占属主裁决位）：
本单取的默认解是"记号改名（ruff 不再当它是 noqa）+ 卫生门读新名"，代价＝
`tests/test_exception_hygiene.py:4,7,60` 三处判据文案 + 9 处记号（scripts 6 + src 3），
与 A/B/C 的选择不联动（选 C 时它仍然可以做，也可以不做——它消的是警告不是债）。
（此条为**读判据得出的推断**，未执行——本轮不许跑 pytest；9 处记号也未逐一确认是否真为 `pass` 体，见附录④。）

## 4. 收紧之后怎么知道闸真长出来

**反证 1（对 A，也对 B 已接进来的那 15 个文件）**：往 `scripts/decision_policy.py` 末尾加一行合法但脏的
`x=1;y=2`，要求 **`tests/test_ci_face_gates.py:41` `test_ruff_face_is_clean` 先红**（它跑的就是那条被加宽的命令），
CI 侧 `.github/workflows/ci.yml:144` 同步红。
现状覆盖档：**未覆盖**。今天注入这一行，全仓没有任何一条常驻用例或 CI job 会红——
能碰到 `scripts/` 的常驻扫描都不判排版本：`tests/test_exception_hygiene.py` 只问空 except，
且它对 `SyntaxError` 是 `continue`（`:52-53`）；`tests/test_lab_impact_propagation.py:247-256` 同样 `except (SyntaxError, OSError): continue`；
`tests/test_gate_runners.py:76-98` 只按**脚本名文本**找读者。
唯一常驻的"能不能解析"尺子 `tests/test_forensic_scripts_parse.py` 的语料是
`docs/audit/`（`:20` `FORENSIC_DIR`），**不含 `scripts/`**。

**反证 2（对 B 的棘轮方向）**：把一个已接进来的文件从棘轮清单里摘掉（或给它的登记基线 +1），
必须有一条用例翻红。现状覆盖档：**未覆盖**——仓里今天没有"lint 面豁免清单"这件东西，
所以既没有清单也没有守它的用例。可借的形状现成：`tests/test_ci_surface_census.py:68`
那条"注入→开火→补登记→转绿→**撤登记→再开火**"四步（注释 `:71-73` 写明了为什么第四步不可省：
登记面最常见的退化是**撤不掉**），以及 `tests/test_command_surface_census.py:17` 的双向棘轮。
B 的实施必须把这两步照搬，否则 B 只是把 642 条换个地方放着。

**反证 3（对"记号改名"这件事本身，若 §3.2 的默认取法被采纳）**：删掉
`scripts/audit_repo.py:326` 的豁免记号但保留 `pass`，`tests/test_exception_hygiene.py:66`
`test_no_uncommented_empty_except` 必须红。覆盖档：**已有常驻用例**（判据读于 `:56-62`，本轮未执行）。

## 5. 今天不拍的代价，和唯一需要回答的问题

**不拍的代价（缺口继续存在，且已经漂过一次）**：`scripts/` 的 642 条 lint 债 / 456 个落点行 /
44 个文件在 ruff 与 mypy 两张面上都不可见，而那两条命令在仓内消费表上的读者只有
`tests/test_ci_face_gates.py` 一个（§0 表，`CI_SURFACE_REGISTER.json:250-256`）⇒ 收口链不在名单上；
这个数只能靠文档抄，一抄就漂——第 93 片记的"643 条 / 4 处无效 noqa"今天现读是
"642 条 / 6 处"（§6）。三轮文档（`DEPENDENCY_LICENSE_BODY_F-DEP-LICENSE_2026-09-29.md:106-117`、
`CI_SURFACE_LINES_F-CI-SURFACE_2026-09-29.md:111`、`RELEASE_EVIDENCE_TEETH_F-PROD-READER_2026-09-29.md:200-210`）
都已经把这一格指为"与 lint 面加宽同一个待裁项"，**它缺的不是论据，是一个数**。

**这一格原先被当成"要属主回答的问题"，第 99 片撤回到位**：按《最高指令》第一节，
"选哪个方案、某条规则留不留"属可自决项，把它包装成"请拍板"等于停工；而这一项的落点
（改 `ci.yml` 里一条命令字符串 + 三处镜像 + 一份豁免清单）全部可回滚、不写他人环境、
不发布上线 ⇒ 归可自决那一档。下面直接落决定，不再回来问第二遍。

### 5.1 决定：拍 **B**，且 mypy 半边本单不接（实施=第 100 片）

- **拍 B**：`ruff` 面第一步只把**已经 0 债的 15 个文件**并进现有命令；其余 44 个文件
  进 `[tool.ruff.lint.per-file-ignores]`（B1，借 ruff 接口语义，实测 0.16.1 真生效：
  登记文件 `rc=0`、同内容未登记兄弟文件 `rc=1`），并**必须**配一条"文件 × 规则码命中数
  ≤ 登记值"的常驻用例补上 B1 看不见的那一格——纯 B1 不是棘轮，是把债改名永久化。
- **为什么不拍 A**：A 要先改 456 个物理行（642 条落点）才能把面挂上，中间任何一步红都会
  让 CI 面长时间不可用；而 A 相对 B 的净增量只是"清单最终清空"这一个动作，没有额外的咬合面。
- **为什么不拍 C**：C 只让缺口"可见"，不改判据强度；而 B 的首片代价实测为 **0 行清零 +
  一条都不红**，C 省下的那点改动不足以换掉一面只会变严的闸。
- **mypy 半边不接**（技术判断，不是待裁项）：`mypy scripts` 今天 rc=2（模块名撞车，
  面立不起来），要做成按文件棘轮得先解命名，那不是豁免清单能表达的形状。
- **主理人复核**（入门禁档一律亲手重开）：`ruff check --no-cache scripts` ⇒ **642 条**、
  `--output-format concise` 逐条数同为 642、命中 **44** 个文件、`find scripts -name "*.py"` ⇒ **59**、
  两集合求差 ⇒ **15** 个 0 命中文件、合并跑 `ruff check src tests state_service <那 15 个>` ⇒
  **rc=0 / All checks passed!**、`Invalid # noqa` **6** 处（`aipd_store.py:195,286,290`、
  `audit_repo.py:326`、`release_evidence.py:259,272`）、`mypy scripts` ⇒ **rc=2 / 4 errors in 2 files
  (errors prevented further checking)**、`mypy scripts --explicit-package-bases` ⇒
  **rc=1 / 78 errors in 23 files (checked 59 source files)**、`ruff --version` ⇒ **0.16.1**。
  本单其余未经我重开的读数（§2 的 456 行、§3.1 前 10 名、§3.2 波及 9 处、§4 的反证覆盖档）
  仍按**导航档**使用，实施那一片要逐条重开再动行。
- **一处我自己的读法错误记在这里**：复核时先跑的是 `mypy scripts 2>&1 | tail -3` 再取 `$?`，
  读到的是 `tail` 的退码 0——正是记忆里那条"wrong `$?`"。改为落盘后取 `$?` 才读出 rc=2。
  凡退码进判据或进文档，命令不许挂管道。

其余都不占裁决位：镜像三连的必改位点已定位到行；反证三条的覆盖档（未覆盖 / 未覆盖 / 已覆盖）已定；
落点文件的四桶已逐文件算过两遍（§0.1：**A/B 的全部落点今天都是"只差授权"**；
C 的落点 `README.md` 带他人未提交改动 +20/−3，故 C 多付一次"等提交或换落点"）；
B 内部用 B1 还是 B2、以及 §3.2 那枚记号怎么改名，是实施侧自决，按本单位点直接动手。


## 6. 与旧读数的差异（现读覆盖旧数）

| 项 | 会话笔记 / 旧文档 | 本轮现读 | 定档 |
| --- | --- | --- | --- |
| `ruff check scripts` 总数 | 643（`DEPENDENCY_LICENSE_BODY_F-DEP-LICENSE_2026-09-29.md:109`） | **642** | 现读为准；四个主档 E702 265 / E501 191 / E701 98 / I001 28 **与旧文档逐字相同**，差的那 1 条在长尾（旧文档只列了主档 + "少量其他"，无法指认是哪条），且第 93 片之后 `git log -- scripts` 有 s94–s98 五片改动 |
| 无效 `# noqa` 处数 | 4（同上 `:110-111`；会话笔记亦 4） | **6** | 现读为准。旧数＝带缓存跑法的读数；两条被漏的是 `scripts/release_evidence.py:259/272` —— 会话笔记点名的 `:272` **确实**用了 `EMPTY_EXCEPT`，但它不在 ruff 报的那 4 条里，这个错位本轮由 `--no-cache` 复算澄清 |
| 量具脚本数 | "46 个量具脚本都住在那儿"（同上 `:108`） | `scripts/` 下 **.py 59 个**（顶层 45 + `research/` 14） | 口径不同而非矛盾：旧文那 46 未说明是否含 `research/`，本轮只报自己的分母与切法 |
| mypy 接入代价 | 旧文未量 | `mypy scripts` **rc=2（面立不起来）**；`--explicit-package-bases` 后 **78 errors / 23 files** | 本轮新增读数 |

## 附：本轮真实执行过的取证（读数记录；复算入口只有 §0 那一份）

```
ruff 0.16.1（.venv/bin/python -B -m ruff）；mypy 同 venv
ruff check --no-cache scripts --statistics                    ⇒ Found 642 errors. / 64 fixable / 10 hidden
ruff check --no-cache src tests state_service                 ⇒ rc=0, All checks passed!（stderr 3 条警告）
ruff check --no-cache scripts (stderr 单独计数)                ⇒ 6 行警告；不带 --no-cache ⇒ 4 行
ruff check <上面 §2.2 的 15 文件 + 现面>                        ⇒ rc=0, All checks passed!（stderr 5 行）
mypy（配置面）                                                 ⇒ rc=0, no issues found in 483 source files
mypy scripts                                                  ⇒ rc=2, Found 4 errors in 3 files (prevented further checking)
mypy scripts --explicit-package-bases                          ⇒ rc=1, Found 78 errors in 23 files (checked 59 source files)
ls scripts/*.py scripts/research/*.py                          ⇒ 59 行
grep -c 'ruff\|mypy'  scripts/closeout_verifier.py …production_release_gate.py ⇒ 0 / 0
grep -c '"command":'   docs/audit/CI_SURFACE_REGISTER.json     ⇒ 32
git status --short（出单时第二次读，HEAD 仍是 0c840be）        ⇒ 7 项 M + 2 项 ??
  M README.md(+20/−3)  M docs/audit/FORENSIC_ROOT_REGISTER.json(+119/−0)  M docs/audit/s83/s83b.sh(+3/−3)
  M docs/audit/s96/build_forensic_root_register.py(+64/−13)  M scripts/ci_surface_census.py(+31/−0)
  M tests/test_ci_surface_census.py(+8/−0)  M tests/test_forensic_scripts_root.py(+42/−2)
  ?? docs/audit/SCRIPTS_LINT_FACE_RULING_2026-09-29.md（本文）  ?? docs/audit/s99/
  ⇒ 除本文外全部是并行会话第 99 片的未提交改动；本轮**未编辑其中任何一个**
  ⇒ mypy 配置面那条 rc=0（483 文件）是在**这份脏树**上读到的；ruff/mypy 对 scripts/ 的读数不受影响
    （脏项里没有 scripts/*.py 除 `scripts/ci_surface_census.py`，而它不在 44 个有命中的文件里）
```

**这份复算入口刻意不含"跑全量门禁"**：本单的前提是有一代认证可能在别处在飞、
性能门对负载敏感（任务边界亦禁止跑 pytest），所以按 `costed-ruling-request-sheet`
要求的"跨文件对账 + 全部门禁复算已跑绿"这一格**本单未交付**，写成待办交给实施那一片：
拍完任一选项后必须先跑 `make`/常驻门再谈合入。此处不留"已验证"三个字。

**本轮未亲验（一律不判红）**：
① 所有常驻用例的**实际**红绿（按任务边界未跑 pytest），§2/§4 的"哪条会红"全部是
**读判据 + 复算判据输入**得到的，档位在各处已标；
② `tests/test_ci_surface_census.py:36` 那几条分母（`ci_commands`、`register_size`）的**现值**——
只读了阈值与登记项数（32），没跑 `scripts/ci_surface_census.py`（不属本轮允许的取证命令面）；
③ B1 的 `[tool.ruff.lint.per-file-ignores]` 只在 `/tmp` 合成树上验过两臂，
**没**在本仓 `pyproject.toml` 上验过（那属实施那一片）；
④ §3.2 末"改名的波及面 9 处"由 `EMPTY_EXCEPT` 全仓 grep 得到，未逐一确认每处是否真为 `pass` 体。
