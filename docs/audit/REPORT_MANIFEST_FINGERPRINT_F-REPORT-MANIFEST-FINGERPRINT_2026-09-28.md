# 报告自证「测的是哪一份清单」（F-REPORT-MANIFEST-FINGERPRINT，第 83 片）

日期：2026-09-28。产物：`scripts/release_fingerprint.py`（58 行，本片新落）＋
`scripts/closeout_verifier.py` 的 C10/C11 两格 ＋ `tests/conftest.py` 的注入 ＋
常驻牙 `tests/test_report_manifest_fingerprint.py` 6 条、`tests/test_closeout_verifier.py` 20 条。
入口项来自第 81 片 §七.5（`docs/audit/ASSEMBLY_PDF_IMAGE_F-ASSEMBLY-PDF-IMAGE_2026-09-27.md`），
那一节在本片开头被按事实重写了一次（见 §一）。

## 一、起因：C6 那句"测的就是这棵树"其实说的是旧哈希

`closeout_verifier` 的 C6 `content_parity_measured` 判的是"两条清单哈希用例在名单里且 passed"。
这两条用例（`tests/test_packaging.py::test_release_manifest_hashes_match_disk` /
`::test_source_manifest_hashes_match_disk`）比的是**清单里记的每文件 sha256** 与**磁盘当前内容**。
于是它有一个结构性盲区：清单在跑完全量之后被重写时（每轮收尾"刷清单"那一步必然发生），
用例照样绿——因为它只看"清单 ↔ 磁盘"这一对，而这一对是**一起**被重写的。
报告自己并不携带"我是在哪一份清单之下跑出来的"这一事实。

一手取证（本片当场跑的，不是抄旧摘要）：

```
$ .venv/bin/python -c "import json;d=json.load(open('docs/audit/pytest-report-v5.6.0.json'));print(sorted(d))"
['created', 'duration', 'environment', 'exitcode', 'generated_at', 'package_version',
 'root', 'source_commit', 'summary', 'warnings']        # ← 没有清单指纹
$ grep -n "source_manifest" tests/conftest.py           # 改之前：0 命中
```

代价是可数的，不是修辞。第 81 片为"先绑报告、之后又改了参与哈希的文档"把全量跑了三次，
三份被绑报告自己的 `summary`/`duration` 读出来是：

| 绑定提交 | summary | duration |
|---|---|---|
| `6ca9c41` | 2636 passed / 1 failed | 701.4 s |
| `745e2a9` | 2652 passed / 0 failed | 318.7 s |
| `223db51` | 2652 passed / 0 failed | 329.8 s |

那一轮还顺手推翻了一条我自己写下的收口规矩（"只有换绑新内容报告能解"），
锚点因此改成取**最早**一次绑定（`tests/test_closeout_verifier.py:_pick_anchor()`，
落地提交 `7761c7c`）。这条推翻直接影响了 §七.5 那条入口项的存亡，见下一节。

## 二、入口项被拆掉一半：为什么"事前警告"不再是必做项

§七.5 原文设计的是"事前提示"：发现"同一份报告 sha 已绑过、且此后 `tests/` 动过"就打一行警告，
危害说明写的是"这次重绑会前推报告锚点、`test_roster_gap…` 会因此红"。
锚点既然改成取最早一次绑定，那句危害就不成立了 ⇒ 警告降级为可选提示。
**支撑形状要说清**：主仓历史里"修正之后再绑同一份报告"的实例是 **0 条**——修正之后一共只有
3 次绑定（`745e2a9`→`da57cfe12145`、`223db51`→`8ed70856ff69`、`3c2b5a6`→本报告），内容 sha 各不相同。
所以依据不是历史，而是合成历史控制 `test_rebinding_the_same_report_does_not_move_the_anchor`
（本轮读数 `1 passed`；它同时断"新取法选最早"与"旧取法会把等式判坏"）。
本片同一格里被拆出来的是**真缺口**，即 §一那一句。

## 三、选型：两个真实候选，结论改变了实现形状

按最高指令的触发条件（新量具＋跨生产/验签两侧的契约）做了检索。候选都要能回答同一个问题：
**有没有现成机制把"构建期指纹"写进 pytest 的 JSON 报告**。

| 维度 | 候选 A：`pytest-metadata`（用 `--metadata`/`metadata` 存进报告的 `environment`） | 候选 B：`pytest-json-report` 的 `pytest_json_modifyreport`（本仓已在用的顶层字段面） |
|---|---|---|
| 功能匹配度 | **接不上**。`pytest-metadata 3.1.1` 把值写进 `config.stash[metadata_key]`（`pytest_metadata/plugin.py:87,95,96`），而 `pytest-json-report` 读的是 `getattr(self._config, '_metadata', {})`（`pytest_jsonreport/plugin.py:231`）⇒ 报告的 `environment` 恒为 `{}`。本机三份真报告实测 `environment: {}`（含绑进证据那份）。上游已登记：issue #89「pytest-metadata 3.0.0 breaking "Environment"」**state=open**（2023-06-05 开，5 条留言，无关闭它的 PR），修复 PR #90 **state=open, merged=false**（2023-06-12 开，+3/−2） | **匹配**。同一个 hook 已在写 `source_commit`/`package_version`/`generated_at`，新字段与它们同一张面、同一批读者；README 就示范 `json_report['foo']='bar'` 这种顶层加键 |
| License 兼容性 | MPL-2.0（`pytest_metadata-3.1.1.dist-info/METADATA:License-Expression`）——可共存 | MIT（PyPI `info.license="MIT"`） |
| 维护活跃度 | 3.1.1，上传 2024-02-12（PyPI） | 1.5.0，上传 2022-03-15（PyPI）；仓库 `numirias/pytest-json-report`，PR 排队两年未合 ⇒ 不活跃 |
| 安全风险 | 无新增面（已装） | 无新增面（已装） |
| 代码质量 | 插件本身成熟，但与 json-report 的契约断在私有属性上 | 结构简单，`serialize.make_report` 就是 `dict(kwargs)`，不校验 schema ⇒ 加字段安全 |
| 适配成本 | 要装/启用并改读者两侧，且**今天读数恒空**（等于把证据写进一个没人收的箱子） | 一只函数 4 行＋一把独立小模块 |

第三个候选（"生态里有没有现成的『把工件哈希记进测试报告』的惯例"）：
**in-toto `test-result` predicate** 用 `subject[].digest` 与 `configuration[]` 的
ResourceDescriptor（`name` + `digest`）表达"在哪份配置下跑的"，是最接近的既有形状；
未检索到任何 pytest 侧的发射器。SLSA provenance 讲的是构建产物而不是测试结果，不对题。

**择一决定：自研一小块 + 沿用官方 hook**（三选一里选"自研"，理由是候选 A 在本仓 pin 的版本上
**证明不可用**，而候选 B 就是本仓已经在用的那个官方 hookspec，不构成重复造轮子）。
借的是 in-toto 的思路（配置类资源也用内容摘要描述，而不是"我记得顺序"），
没借它的 JSON 形状——本仓报告的两个读者（`closeout_verifier`、收尾脚本）都按顶层键读，
扁平字符串少一层解引用。落地处：`scripts/release_fingerprint.py:31`（摘要规则）、
`tests/conftest.py:69`（生产侧写字段）、`scripts/closeout_verifier.py:354,368`（验签侧两格）。

## 四、判据形状：三条实测出来的取舍，不是推的

**① 摘要求的是"内容规范摘要"，不是清单文件的 sha256。**
`scripts/release_evidence.py:133` 每次生成都把 `generated_at` 写成当前时间 ⇒ 原始字节摘要
在"刷清单 → 跑全量 → 绑定"这三步之间必然变。拿文件 sha 当判据＝每轮给正常流程判一条假红。
规则写在 `scripts/release_fingerprint.py:24`（`VOLATILE_KEYS = ("generated_at",)`）、
`:28`（只剥顶层）、`:31`（`sort_keys` 后 sha256）。
这一条由两支读数钉住：`--self-test` 的假红控制（两份**字节不同**而摘要相同的清单，判绿）
与电池臂 Y3（把验签侧改成比原始字节 sha ⇒ `--self-test` 当场红）。

**② C10 与 C11 分开：C10 是"有没有可比基准"的前提闸，C11 才是判红面。**
`closeout_verifier` 里缺字段走 `problem("report_fingerprint_recorded", …)`（退 2），
C11 那一格读成 `kind="skipped"`；有字段才做磁盘对账。
`--self-test` 的 C10 臂断"退 2、`problems` 恰好这一格、`violations` 为空、C11 沉默"，
电池臂 Y5（让缺字段也去开 C11 那一判）与 Y4（整支沉默）各钉一个方向。

**③ 磁盘清单读不出是前提塌（退 2），不是判红。**
`:361` 那一支；电池臂 Y6 证明把它折成判红会被 `--self-test` 拒。
这沿用本仓三态纪律："看不见"既不折算成违规，也不折算成通过。

**④ 第一版把"缺字段"判成违规——那是一条自锁，被本轮自己的两次实测推翻。**
原判据形状 `judge("report_fingerprint_recorded", bool(rec_fp), …)`，理由"生产者没记不能读成
值恰好为空的绿"——这句话到今天仍然对。漏想的是**报告是不可变的历史产物**：树里那份旧报告
不出自新 conftest ⇒ 任何在它被换掉之前跑出来的全量都带着这条红 ⇒ 拿不到 0-failed 的证据
⇒ 不能绑定 ⇒ 树里那份永远换不掉。两次一手读数把这条路走死：
①常驻基线 `5 failed, 21 passed`（五条同一因，因此本片电池按"增量开火"记分）；
②干净签出全量（worktree 检出 `7acaced`）`2658 passed / 5 failed / 2668 total`、417.9 s、
`exitcode=1` ⇒ 绑定脚本按前提退 8 拒绑。中途还试过把那一跑的报告**不绑定地**放进
`docs/audit/`（`3d5e0f6`）：它自己也带着那 5 条红，`terminal_clean` 照样判红，死锁没解开，
已把那份**撤回**（`git checkout 3d5e0f6^ -- 那个路径`），本片的 attestation 不引用它。
定形是三态各归各位：缺席＝没有可比基准（退 2，配方过不去）；强制力放在**写入侧**
（收尾脚本在绑定前逐位比对，下一片接进 `release_evidence.py` 本体，见 §八.4）
与**生产侧常驻用例**（真 `pytest --json-report` 端到端那条，删掉注入就翻）。
格名集合与 `STAGE_BOUND` 同步改到十一格；`test_eight_checks…` 那条"真语料必须全绿"的用例
现在**限定**地允许 `problems ⊆ {report_fingerprint_recorded}`，并要求这一判能由
"报告里确实没有那个键"解释——换绑之后 `problems` 为空，该格回到必须绿的名单里。

## 五、真生产者路径与独立盲尺

`tests/test_report_manifest_fingerprint.py::test_production_conftest_stamps_a_real_json_report`
用真 `pytest --json-report` 起子进程跑一条真用例，再读那份真报告断指纹。
第一次试跑借的种子是 `tests/test_packaging.py::test_source_manifest_hashes_match_disk`，
结果它自己先红——我正在改 `scripts/` 与 `tests/conftest.py` 而清单还没刷，那条用例判的正是
清单↔磁盘一致（**这条红是有用的**：它就是 C6 那两条替身用例在工作）。
种子换成读本文件那条不依赖清单新鲜度的纯函数用例（`SEED_SPEC`，
`tests/test_report_manifest_fingerprint.py:33`）。

同文件 `:37` 的 `_independent_digest()` 是把摘要规则**另写一遍**的盲尺，
`test_module_digest_matches_an_independently_written_copy` 拿真清单断两边相等。
它挡的是"某一侧被改动而另一侧没跟着改"（电池臂 Y2 就是这条：把 `VOLATILE_KEYS` 清空 ⇒
盲尺照旧、模块变了 ⇒ 4 条用例同时翻）。两侧同时改等于公开改契约，不在它职责内。

## 六、电池（`docs/audit/s83/battery83.py`）

基线不是全绿（§四④），所以**判决按"增量开火"而不是退码**：先跑一次基线记下 FAILED 集合，
每条臂要求 `fired − baseline` 非空才算杀掉。这是本片新记的一条电池纪律。

| 臂 | 撤掉哪根牙 | 增量开火 |
|---|---|---|
| Y1 | `tests/conftest.py:69` 算出来却不写 | 只有 `test_production_conftest_stamps_a_real_json_report` |
| Y2 | `VOLATILE_KEYS` 清空（不剥时间戳） | 盲尺那条＋假红那条＋命令行面那条＋生产侧那条＋`--self-test` spawn |
| Y3 | 验签侧改成比原始字节 sha | 6 条（含 `--self-test` spawn 与四格"只点亮自己那一格"的期望） |
| Y4 | C10 那一支整支沉默（缺字段不再拦） | `--self-test` spawn＋真语料两极那条 |
| Y5 | 报告没带指纹时让 C11 也开火 | `--self-test` spawn＋跨阶段解释那条 |
| Y6 | 清单读不出折成判红 | `--self-test` spawn |

终局读数：`合计 KILLED+CRASH-KILL 6 / 6；其余按判决分类：无`，
落盘日志 `docs/audit/s83/battery83.log`。无 CRASH-KILL（六臂都是判决翻转）。

## 六之二、终局读数（绑定那一跑，全部现读）

| 格 | 读数 |
|---|---|
| 干净签出 | worktree `/Volumes/Extra/CodeProj/AI全链路自研/tmp/s83/final2` 检出 HEAD，`aipd_os` 真被加载自 `/Volumes/Extra/CodeProj/AI全链路自研/tmp/s83/final2/src/aipd_os/__init__.py` |
| summary | `{'passed': 2663, 'skipped': 5, 'total': 2668, 'collected': 2668}`，`exitcode=0`，`duration=480.4 s` |
| 跳过（与上一轮同一批） | 5 条：联网与真实邮件服务的既有用例 |
| 报告指纹 | `source_manifest_fingerprint=74b031491f1a979b…` == 磁盘 `SOURCE_MANIFEST.json` 内容规范摘要 |
| PROVENANCE 绑定 | `test_report.sha256=8a1d6b7db023…`，与磁盘那份逐字节一致；绑定提交 `7e631c9`（HEAD 当时 7e631c9，链后还有收尾提交） |
| 清单分母 | SOURCE 683 个文件 / RELEASE 683 个文件（`docs/audit/` 整体排除 ⇒ 0 条） |
| 发布门 | 链内第一轮 `release_ready=False`（红在 `workspace_clean`，见下面第 3 条）；链内第二轮 `release_ready=True`（8 项全过）；文档定稿后复跑 `release_ready=True`（8 项全过，退码 0） |
| 收尾验签 | `closeout_verifier --tag v5.6.0 --expect-test tests/test_report_manifest_fingerprint.py --min-tests 2660` ⇒ 全部判据绿（十一格） |

三条本片该记住的形状：

1. **"报告与清单同源"这件事现在是两处读的**：绑定脚本在写之前就比（不等退 8，是 C11 的事前档），
   `closeout_verifier` 在绑定之后照 C10/C11 复核。事前档现在只活在收尾脚本里 ⇒ 下一片接进
   `release_evidence.py` 本体（§八.4），否则它守的是"我记得跑这一步"。
2. **换绑之前那 5 条红不是判据坏，是判据在要求换绑**。第一版把它写成判红造成自锁，
   改判前提塌之后配方仍然过不去（退 2），只是不再伪造"有 5 条违规"这个读数。
   写这一节时报告已经带着字段，`problems` 为空，十一格全绿——那条限定放行
   （`problems ⊆ {report_fingerprint_recorded}`）就此回到"必须绿"的名单里。

3. **链上有两处非零退码，两条都是我自己的伤，归因写在这**：
   ① 链内第一轮发布门 `release_ready=False`，红在 `workspace_clean`，未跟踪项是
   `?? docs/audit/s83/terminal83.py`——我在链条跑到一半时把取数脚本写进了树里；
   收尾提交把它一起收下之后，第二轮与文档定稿后的复跑都是 8/8。
   ② `resident2_rc=1`：绑定那一步之后、提交之前那一小段窗口里
   `test_fingerprint_verdict_always_has_a_content_level_explanation` 红——它拿
   `git show <锚点>:SOURCE_MANIFEST.json` 当基准，而那一刻报告与清单都还没进提交，
   锚点仍指向上一轮的绑定提交。这正是本文件开头那条老规矩（**常驻用例不许假设仓库处于
   "刚绑定"那一小段窗口**）的第 N 次显形；提交之后该用例复跑为绿，判据没有为此放宽。

## 七、复算入口

```
python scripts/closeout_verifier.py --self-test                      # 22 臂合成读数
python scripts/release_fingerprint.py SOURCE_MANIFEST.json           # 打当前清单的规范摘要
pytest tests/test_report_manifest_fingerprint.py tests/test_closeout_verifier.py -q
python docs/audit/s83/battery83.py                                   # 六臂，逐臂还原并校验 sha
```

## 八、本片没做的事（登记，不是遗漏）

1. **`RELEASE_MANIFEST`/`BUNDLE_MANIFEST` 的同类指纹没做**。理由：C6 那两条替身用例判的正是
   这两份清单↔磁盘一致，而"跑完之后被重写"这件事对二者同样成立；但 `--test-report` 那步只重写
   `SOURCE_MANIFEST`/`PROVENANCE`（实测：绑定那次 `git status` 只列这两个），bundle 只在打 tag 时生成。
   要不要一并做，取决于正式发版那轮是否把 bundle 也绑进证据——那是属主决定，列为线下项。
2. **缺字段读成前提塌（退 2），C11 同时沉默**。这一判的代价是：常驻用例在"旧报告还绑着"的那段
   窗口里对该格不判绿（限定成 `problems ⊆ {report_fingerprint_recorded}` 且必须能由"报告没那个键"
   解释）。所以强制力**必须在写入侧补上**，见第 4 项。
3. **`environment` 恒为 `{}` 这件事本仓没修**。它是上游 issue #89；本仓不受影响（不读那一格），
   但值得知道：任何指望 `environment` 携带元数据的方案在本仓 pin 上都是空转。
4. **下一片该做：把"拒绑没有指纹／指纹不同源的报告"接进 `scripts/release_evidence.py` 本体。**
   现在这道比对只在收尾脚本的前提核对里（`tmp/s83/s83b.sh` 第 2 步：报告指纹与磁盘清单逐位比对，
   不等就退 8），也就是说它守的是"我记得跑这一步"，不是工具自己。落点：`_parse_pytest_report`
   （`release_evidence.py:236-278`）把 `source_manifest_fingerprint` 抄进
   `PROVENANCE.test_report`，`write_evidence` 在写之前比"报告记的那份"与"即将落盘的这份"，
   不等就拒（不写文件、非零退码）。两极都要配：删掉 conftest 注入 ⇒ 必须拒；
   只刷 `generated_at` ⇒ 必须照绑。这一格补上之后，"缺席读成前提塌"才真正不是放水，
   而是"由更靠前的一道闸拦下"。
