# F-DOC-CMD-SCRIPTS 第 85 片：文档里 `python scripts/X.py …` 那一面第一次有人判

日期：2026-09-28 ｜ 上一片：第 84 片 `docs/audit/BIND_PREFLIGHT_F-BIND-PREFLIGHT_2026-09-28.md`
｜ 尺：`scripts/doc_command_census.py`（新增判红面 ④）｜ 常驻：`tests/test_doc_command_census.py`（+3 条）
与 `tests/test_release_evidence_preflight.py`（+2 条）

## 一、入口：一句入口项把自己问成了真缺口

第 84 片 §八.3 我写下"README 量具目录里没有 `release_evidence.py` 这一行，所以没人守它"。
本轮去核实那句话时先量了分母，结果**我那句话的前提是错的**：

| 现读（`.venv/bin/python` 一次遍历 `README.md` + `QUICKREF_DIRS`） | 数 |
| --- | --- |
| `scripts/*.py` 总数 | **43** |
| 在 README 里有**行首可执行写法**（`python scripts/X.py …`）的 | **3** |
| 在 README 里任意位置被提到的 | 7 |
| README 完全没提到的 | **36** |

也就是说"量具目录"从来不是脚本登记表，而是 3 条手写高亮。
于是"每个脚本都该有一行"这条判据今天会**一次红 40 处**——按第 60 片立尺时的同一条纪律
（"存在性判据上线前先量假阳性面；宽 56／窄 9、真违规 0 ⇒ 不做门"），**不做**。

但量的过程暴露了另一件事：那 3 行（含 `references/` 里的 1 行）**一条都没有任何尺子看过**。
第 60 片立 `doc_command_census` 时判的是 `aipd …` 那一面，理由是"那才是产品命令面"；
可 README/`references/` 里写给工程师和 agent 照抄的另一种形状是
`python scripts/closeout_verifier.py --tag v5.6.0 --expect-test …`——
**它同样是"照着敲"，却不在任何一档里**。这才是 §八.3 那句入口项底下真正的洞。

## 二、判据：三条判决 + 一个刻意不判的第三态

新档 `script_rows()` 走 `quickref_corpus` 的**同一份遍历**（判红面 ② 与续行那格也从这里取，
不另起 `rglob`——第 60 片记过"两档各走一遍迟早漂出两种看得见"），
并把行尾 `\` 折回同一行（README:274→275 的合规续行形状，不折就会把合法旗子读成缺失）。

| 行内写的 | 判决 | 为什么 |
| --- | --- | --- |
| 脚本文件不在 `scripts/` 下 | **脚本缺失**，判红 | 照抄直接 `No such file or directory` |
| `--flag` 不在该脚本 argparse 的长旗子集合里 | **脚本旗子**，判红 | 照抄得 `rc=2` 用法错误；判决文本带出**声明了哪些**与 `difflib` 近形候选 |
| `--flag` 在集合里 | 不判 | 合规侧，自测里同批存在 |
| 该脚本有 `add_argument(*NAMES)` 这类非字面量声明 | **不判**，只进 `script_rows_unbounded` | 读不到全集就把"我没见到"当"它不存在"＝造假红；"看不见"是第三态，不折成违规也不折成通过 |

旗子集合由 AST 读（`script_arg_flags`），不是 ±N 行窗口，也不跑 `--help`：
跑 `--help` 要执行代码，而这一档的用途恰恰是"文档说的和代码声明的对不对得上"，
拿执行结果当权威就把待证的东西当用了。

## 三、立条前先量真语料：这一格不是橡皮章

```
$ python scripts/doc_command_census.py --repo .      # 加档之后、修文档之前
  ✗ 脚本旗子 references/cad-runtime-acceptance.md:6 写了 `runtime_preflight.py --require-cad`
    ⇒ 这个脚本不接受该旗子，照抄会 rc=2 用法错误
    （`runtime_preflight.py` 声明的长旗子共 4 个：--cad-skill-dir --json-out
      --require-any-cad --skill-root；近形候选 --require-any-cad）
```

并且**亲手跑过那行**证明它确实是假话，不是判据太严：

```
$ python scripts/runtime_preflight.py --require-cad --json-out /tmp/x.json
runtime_preflight.py: error: unrecognized arguments: --require-cad        # 退码 2
$ python scripts/runtime_preflight.py --require-any-cad --json-out /tmp/x.json
{ "architecture_ready": true, ... }                                       # 退码 2 = 该工具自己的判决码
```

最后一行是本轮自己差点读错的地方：两个命令退码**都是 2**，
但一个是 argparse 的用法错误、一个是工具自己"前置条件不满足"的 verdict。
**退码不能单独当判据**（项目记忆里那条老纪律），得看输出形状。

修文档：`references/cad-runtime-acceptance.md:6` 的 `--require-cad` → `--require-any-cad`。
修完真仓库 `CENSUS_RC=0`、`script_rows 4 / judged 4 / unbounded []`。

## 四、自测与常驻的两极

`--self-test` 加了 5 行合成语料与四支判决，`9 条合成读数全部对上`（退 0）。
分母键自报并各自钉死：`script_rows == 5`、`script_rows_judged == 4`、
`script_rows_unbounded == ["zzz_dyn"]` ——**判 4 而不判 5 是设计**，
所以那个 1 的差只由 `unbounded` 这一格解释，不能由"整档没跑"解释。
夹具脚本名一律 `zzz_` 前缀：第 60/61 片两次写死"将来可能被注册的真名"都崩过。

常驻 3 条（`tests/test_doc_command_census.py`）：
必开火两支（假旗子、不存在的脚本）、合规侧不开火（真旗子 + 反斜杠续行）、
不封闭不判（`add_argument(*NAMES)`）；再加一条真仓库分母下界
`test_fourth_judging_face_is_live_in_the_real_repo`——
没有它，前面三条可以只在合成语料里活着，而真语料被静默收窄成 0 行也照样全绿
（第 60 片的 autouse 收窄事故就是这个形状）。

## 五、同批落地的另一件（第 84 片 §八.6）

`preflight_report_vs_source` 原来用 `if not report_info.get("parsed")` 一次盖住两种输入：
文件存在但 JSON 坏（`present:true, parsed:false`）与**路径根本不存在**
（`{"present": false}`，连 `parsed` 键都没有）。后者的判决文本却写着
"present 但 parsed=false"——说反了，而它恰是操作员最容易犯的那种（旗子值打错一个字母）。
本轮按 `present`/`parsed` 拆成两条文案，并补两条常驻用例：
一条钉"路径不可读"这一形状（含"连输出目录都不建"），
一条钉**两条判决文本必须不同**（这才是本轮真正要的东西：同形文案会让"路径打错"
读成"报告坏了"，把人支到错的方向）。

派出去的子代理在写这条时自己发现并绕开了一个宿主陷阱：`main()` 先 `Path(...).resolve()`，
macOS 上 `tmp_path` 的 `/var/…` 会解析成 `/private/var/…`，
所以断言里比的是 `str(missing.resolve())` 而不是原始 `tmp_path`——
写成前者才与工具实际输出的那一串逐字节相同（平台相关的字面量不进断言，同第 57 片那条）。

它同时用三支回退臂证明了这两条用例有牙（撤掉拆分 ⇒ 2 failed；把两条文案互换 ⇒ 2 failed；
去掉路径回显 ⇒ 2 failed），并复算 `docs/audit/s84/battery84.py` 八臂锚点全部仍唯一。

## 六、镜像面（本轮实际改到的每一处）

命令面三张分母、census 分母、`command_contract.py`、`cli/main.py`、SKILL 计数**全不动**
（不加命令、不加旗子）。`scripts/` 与 `tests/` 都参与发布哈希 ⇒ 清单要重锚；
被哈希**文件数不变**（只改内容，没加新脚本、没加新测试文件）——这条可以反查自己有没有误加文件。

| 面 | 改了什么 |
| --- | --- |
| `scripts/doc_command_census.py` | 新增 `script_arg_flags` / `script_rows` / 档 ④ 接线 / corpus 三个键 / 两格自己的 render 话术 / `difflib` 近形候选 / 自测四支臂 |
| `references/cad-runtime-acceptance.md` | 真缺陷：`--require-cad` → `--require-any-cad` |
| `tests/test_doc_command_census.py` | +3 条（必开火、不封闭不判、真仓库分母下界） |
| `scripts/release_evidence.py`、`tests/test_release_evidence_preflight.py` | §五 那条拆分与 2 条用例 |
| `README.md` | 量具目录给 `doc_command_census` 补一段第四档说明；闸的形状从三种改四种；**把"8 条/20 条"这类计数句改成"由判据现读"** |
| `docs/audit/release_evidence_notes.md` | 同上：坏形状四种、条数不再抄 |
| `docs/audit/BIND_PREFLIGHT_F-BIND-PREFLIGHT_2026-09-28.md` | §八.6 与 §八.3 原行内标注被本轮闭合到哪一步 |
| `CHANGELOG.md` | v5.46 一条 |

## 七、复算入口

```bash
cd /Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
.venv/bin/python scripts/doc_command_census.py --self-test     # 9 条合成读数
.venv/bin/python scripts/doc_command_census.py --repo .        # 退 0，四档分母非空
.venv/bin/python -m pytest tests/test_doc_command_census.py \
    tests/test_release_evidence_preflight.py -q
```

## 八、遗留

1. **"每个 `scripts/*.py` 都该在文档里出现"这条判据仍然不存在**，也不该存在（40 处假阳性）。
   如果哪天要做，正确形状是反过来：**登记一份"有意不进目录"的豁免清单**并让"不在目录且不在豁免"
   变红——那才是有分母也有牙的版本，本轮没做。
2. **`python -m` 形式与 `python3` 变体**：正则收了 `python3 scripts/…`，但 `-m aipd_os.…`
   那种模块入口没判（它不在 `scripts/` 下，权威面得换）。今天 0 处，所以只登记不建档。
3. **`docs/audit/` 与 `tests/` 里的 `python scripts/X.py` 只报不判**：它们走的是记录面
   （第 75 片的 live/record 分桶），本轮沿用同一纪律——把记录面里的历史命令判红，
   等于惩罚"把当时怎么跑的写下来"。
4. **本轮没给档 ④ 配变异电池**：它的牙由 `--self-test` 四支臂 + 3 条常驻两极 +
   §五那三支回退臂证明，沿用第 60/61 片这把尺自己的既有惯例（它历史上就没有电池）。
