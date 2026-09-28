# F-BIND-PREFLIGHT 第 84 片：绑定那道闸搬进写入侧本体

日期：2026-09-28 ｜ 上一片：第 83 片
`docs/audit/REPORT_MANIFEST_FINGERPRINT_F-REPORT-MANIFEST-FINGERPRINT_2026-09-28.md`
｜ 实现：`scripts/release_evidence.py`、`scripts/closeout_verifier.py`
｜ 常驻：`tests/test_release_evidence_preflight.py`（8 条）+
`tests/test_closeout_verifier.py::test_bind_provenance_fixture_shape_mirrors_production`

## 一、入口与理由

第 83 片把 `report_fingerprint_recorded`（C10）从**判红**改成**前提塌（退 2）**，理由到今天仍然成立：
报告是不可变的历史产物，把缺席判成违规会自锁——attestation 必须 0 failed，而任何在旧报告还绑着时
跑出来的全量都带着这条红，于是永远换不到一份带字段的报告。那次改判在文档里留了一句前提：

> 强制力放在**写入侧**（绑定前逐位比对）与**生产侧常驻用例**

而"写入侧"当时指的是**收尾配方里另写的一个 shell 步骤**（`tmp/s83/s83b.sh` 第 2 步，不等就退 8）。
那不是写入侧，那是一条"记得跑这一步"的约定：`release_evidence.py --test-report` 自己当时
对指纹这件事**一个字都不检查**，跳过那一步照样能把一份与清单不同源的报告绑成 attestation。
本片把那句话变成实现。

## 一之二、选型（本轮真正要拍的只有一个形状问题：比对放在哪、拿什么比）

跳过检索要写理由，但这一条不跳过：它决定"下一轮谁来改才不会改坏"。三个候选都是真实在用的做法。

**候选 A｜沿用本仓既有的 `release_fingerprint.fingerprint_of_document`，只新增"写之前调它"这一步。**
- 功能匹配度：正中。要判的就是"仓库内两份 JSON 是否同源"，不需要签名链。
- License：无新增依赖（stdlib `hashlib`/`json`）。
- 维护活跃度：不适用（自研 58 行，`scripts/release_fingerprint.py`）。
- 安全：不引入供应链面；指纹不抗伪造，但本仓的威胁模型是"自己把旧报告绑成新证据"，不是攻击者改 JSON。
- 代码质量：三方共用一把尺（生产 `tests/conftest.py`、验签 `closeout_verifier.py`、本轮的绑定侧），
  分歧只能来自"某一侧自己另算"，而那件事由一条盲尺用例判着。
- 适配成本：`scripts/release_evidence.py` `git diff --numstat` 现读 **+66 / −6（净 60 行）**，
  含 docstring；再加 8 条常驻用例，本轮实测一轮做完。

**候选 B｜引 in-toto / SLSA 那一类 attestation 工具（`cosign verify-attestation`、slsa-verifier）来做"subject digest 匹配"。**
- 功能匹配度：**思路正中、载体不对**。SLSA 的 Distributing Provenance 一节我亲自打开核对过原话
  （https://slsa.dev/spec/v1.2/distributing-provenance）：
  "Attestations SHOULD be bound to artifacts, not releases. Once published, an attestation is
  immutable and cannot be overwritten; instead, a new release SHOULD be created."
  这句话恰好就是我们的形状：报告是不可变历史产物 ⇒ 不能改它，只能换绑一份新的（第 83 片那次
  自锁的根因就是忘了这条的后半）。
- License：cosign 系 Apache-2.0，兼容；但要拖一整套签名/证书/透明度日志的依赖面。
- 维护活跃度：活跃（不适用"没人管"的风险）。
- 安全：多一层真签名，**但我们没有密钥生命周期**——本仓发布锚点停在 tag、从未重建 bundle
  （属主决定，见项目记忆），引它只会得到一个自签自验的仪式。
- 代码质量：不适用（不引）。
- 适配成本：最高。要先把"制品"这个概念引进来（我们现在的"制品"是 git 树 + 一份 JSON 清单）。
- **择一：借语义，不引依赖**——"binder 必须自己重算 subject 摘要，而不是信报告里那个数"
  与"证据不可改写，只能换绑新的"这两条，正是本片 `preflight_report_vs_source` 的形状。

**候选 C｜把规范化换成 RFC 8785（JCS）而不是一套自研 sort_keys。**
- 功能匹配度：JCS 解决的就是"生产端与消费端各算各的哈希"。我亲自打开 RFC 正文核对到原话
  （https://www.rfc-editor.org/rfc/rfc8785.txt）："Cryptographic operations like hashing and signing
  need the data to be expressed in an invariant format so that the operations are reliably repeatable"，
  它约束属性排序、数字按 IEEE 754 序列化，输出称 "Canonical JSON Data"（UTF-8）。
- 但**本仓对象用不上那部分**：由 `SOURCE_MANIFEST.json` 现算值类型分布 =
  `{'str': 1371, 'int': 683}`，float 出现 **0** 处。Python `json.dumps(sort_keys=True,
  separators=(",",":"))` 对 str/int 与 JCS 同读数；分歧只在 float、`-0`、非 ASCII 转义这些
  本清单现在没有的形状上。
- License/维护/安全：引第三方 JCS 包才有这几格；本轮**未逐一检索 PyPI 上的现成实现**，
  所以不假装比过版本。
- 适配成本：为一个不存在的形状引依赖，是本仓反复犯的那类过度工程。
- **结论：不选，但把分歧条件写清并挂成入口项**（见 §八 新增第 4 条）：清单里一旦允许出现 float
  或需要跨语言复算指纹，`fingerprint_of_document` 就要换成 RFC 8785 兼容实现。

**落地处**：A 的实现是 `scripts/release_evidence.py` 的 `preflight_report_vs_source` +
`BindPreflightError` + `write_evidence` 改两阶段；B 借来的那条"只能换绑"写进 §一 与 README 的退码说明；
C 的拒绝理由与翻案条件写进 §八 第 4 条。

> 检索纪律：另有若干处（in-toto Statement v1 的 subject 必须带 digest、sigstore 文档的 fail-closed
> 建议、OPA 的 undefined≠false、deb-buildinfo 的 `Checksums-Sha256` 段、PEP 610 的 `commit_id`）
> 由只读检索件带回，**本轮未逐条亲验，故只作线索、不作为上面任何一格结论的出处**。

## 二、判据形状：三条是实测，不是推的

### ① 比的是规范摘要，不是清单文件的原始 sha256

`generate_source_manifest` 每轮都把 `generated_at` 写成当前时间（`scripts/release_fingerprint.py:5`
记的就是这件事），所以原始字节每轮必变。若 preflight 比原始字节，"刷清单 → 跑全量 → 绑定"这条
**正常**链会被自己拒掉——假红方向的失效比假绿更难查，因为它每次都在收尾的最后一步出现。

- 钉住它的常驻用例：`test_only_generated_at_moving_still_binds`（把清单深拷贝一份、只把
  `generated_at` 改成 2001 年，仍必须 rc=0 且真的落盘）。
- 电池臂 `W3-compares-raw-bytes` 把实现换成
  `hashlib.sha256(json.dumps(source_doc).encode())`，**三条**用例同时翻红
  （`test_binds_and_records_the_fingerprint_when_it_matches`、
  `test_only_generated_at_moving_still_binds`、`test_refusal_does_not_touch_evidence_already_on_disk`）。
  第三条红是结构性的：那份用例先合法绑一次，比原始字节的实现连第一次绑都绑不上。

### ② 三种坏形状各有一根桩，且都不许折成"通过"

| 坏形状 | 判 | 常驻用例 |
| --- | --- | --- |
| 报告读不出（present 但 `parsed=false`） | 拒 | `test_refuses_an_unparsable_report` |
| 报告没带 `source_manifest_fingerprint` | 拒 | `test_refuses_a_report_without_the_fingerprint_and_writes_nothing` |
| 报告记的指纹 ≠ 即将写出的那份清单 | 拒 | `test_refuses_when_the_manifest_content_moved_after_the_run` |
| 不带 `--test-report`（配方第一步刷清单） | 不判 | `test_path_without_test_report_is_not_gated` |

第一行是本轮新增的第三种：那种报告**根本没有可比对象**，把它写成证据就是一条无法归因的记录，
所以它和"缺席"不同类但同样该拒。最后一行是阴性侧——闸只吃带报告的那一步，
否则"先刷一轮清单"这个动作会被自己挡住，配方就断了。

### ③ 拒写必须不半写：这一条是被电池臂逼出来的，不是先想到的

`write_evidence` 的既有形状是一边算一边写（bundle 先落盘，然后 SOURCE、PROVENANCE）。
把闸放在这种形状里的**任何一处 `write_text` 之后**，都会把"拒写"变成"半写"：树里留下一份
`SOURCE_MANIFEST` 已被重写、`PROVENANCE` 还是旧的（或反之）的中间态，而这次运行对外报的是"被拒"。
这不是设想——电池臂 `W4-gate-moved-after-the-write` 就是把闸挪到 `SOURCE_MANIFEST` 落盘之后，
翻红的正是 `test_refusal_does_not_touch_evidence_already_on_disk`：它先合法绑一次、再拿坏报告去绑，
要求 `out/` 下每个文件**逐字节**不变。

因此定形成两阶段：三份内容全部算完 → 过闸 → 才第一次 `write_text`。
AST 面另有一条接线断言（`test_gate_is_wired_into_write_evidence_before_any_write`）：
`write_evidence` 里那个 `if test_report is not None:` 的体内必须调 `preflight_report_vs_source`，
且该 `if` 节点必须排在函数里**第一个** `.write_text(` 之前。两条各管一面：字节面证"确实没半写"，
AST 面证"顺序不是碰巧"。

## 三、落点为什么不在 `_parse_pytest_report`

第 83 片 §八.4 把落点写成"`_parse_pytest_report` 抄字段 + `write_evidence` 写之前比"。前半照做了
（`PROVENANCE.test_report` 现在多一个 `source_manifest_fingerprint`），后半**改了位置**：
比对不进 `_parse_pytest_report`，而是新开 `preflight_report_vs_source(report_info, source_doc)`。

理由：`_parse_pytest_report` 的职责是"读一份报告、抄出几个字段"，它的输入只有一份报告的字节。
把判决塞进去要让它看见"即将写出的那份清单"——一个它本来没有的参数，于是每个只想读报告的调用方
都得造一个假的 `source_doc` 传进去。**能单独被测的函数应当只有一个输入面。**
`BindPreflightError` 单独成类、`main()` 只 catch 它并退 2，也是同一个道理：
退 2 是"这一步被拒"，不能和别处的 2 混。

## 四、电池：七臂，以及电池自身那次误判

`docs/audit/s84/battery84.py`，靶面 `tests/test_release_evidence_preflight.py` +
`tests/test_closeout_verifier.py`。基线**不全绿**
（`test_roster_gap_equals_tests_changed_since_the_report` 在本片新用例文件还没提交、报告还没重跑的
窗口里合法地红，形状与第 83 片同款），因此按**增量开火**记分，不按退码。

终局：`合计 KILLED+CRASH-KILL 7 / 7；其余按判决分类：无`（逐臂见 `battery84.log`）。

**第一次跑出来的是 `6/7 + BAD-ANCHOR 1`，那条 BAD-ANCHOR 是假读数**，值得单独记：
每臂落地前有一道"注入必须是真改写"的前提，写作

```python
if new and new in src:
    bad = "new 已在树上（空改写）"
```

对**删除型** rep 这条必然为真——W4 的第一步是把整段闸摘掉，替换体 `    results = {}`
本来就是被摘那一段的尾巴，当然是 `src` 的子串。于是那条有牙的臂从未落地过就被判成"没牙"。
收窄成 `if old in new and new in src`（只在纯插入形状上成立）后复跑 7/7。
"什么都没改"这件事仍由后面的 `mutated == src` 判，那一条对所有形状都成立。

失败方向值得写清：这不是"注入没打中"（那会读成 SURVIVED，往**假绿**方向错），
而是**判据过严把一条有牙的臂读成没牙**——它给出的读数是"这块没有护栏"，
而真相是"这块有护栏，我的尺子把它误杀了"。第 81 片 §终局读数记过记分面的同族纪律
（`docs/audit/ASSEMBLY_PDF_IMAGE_F-ASSEMBLY-PDF-IMAGE_2026-09-27.md:195`"一臂多红 6 支"），
这次是它的对偶。**两版日志都留着**：`battery84.run1.log` 就是那个错读数本身，
删掉它等于把"我们曾经这样误判过"一起删掉。

## 四之二、闸的真实爆炸半径（第一次干净签出全量换来的，记账）

第一次按配方跑干净签出全量（worktree 检出 `d457981`）读到的不是 0 failed，而是
**`3 failed, 2661 passed, 5 skipped, 8 errors`（507.6 s）**。两组红，成因完全不同，
都必须写下来，因为它们才是"这道闸到底改了谁的契约"的答案。

**第一组：`tests/test_release_evidence.py` 8 个 fixture ERROR + 2 个 FAILED，全是我改的契约的下游。**
`BindPreflightError` 在日志里命中 40 次。根因：`_make_repo`（`tests/test_release_evidence.py:47-102`）
自己造一份 `report.json`，形状是"第 83 片之前的世界"——没有 `source_manifest_fingerprint`。
第 83 片只给**真 conftest**加了那个字段，所以这副手写夹具从没被要求带上它；
第 84 片把闸放进 `write_evidence`，它就成了第一批撞墙的用户。
修法是让夹具**照生产形状造报告**（用 `generate_source_manifest` + `version` 现算指纹再写进去），
不是把闸改成"缺字段只警告"。这是本仓反复记过的那条形状的又一例（手写夹具全绿 ≠ 生产侧走得通），也是**我自己的流程错**：启动那一跑之前我只跑了
`test_release_evidence_preflight` / `test_closeout_verifier` / `test_report_manifest_fingerprint` /
`test_changelog_integrity` 四个文件，**没有跑既有消费者的那一套**。
判据（写进习惯）：**动一个函数之前，先 grep 出它的全部调用点并把那些文件列进本轮的必跑集合**——
本轮这一条的实测代价是一整个 507 s 的全量。

**第二组：`test_closeout_verifier.py::test_dropping_a_whole_resident_file_fires_only_the_roster`
——这一条不是本轮写坏的，是它一直藏着的一个跨轮耦合被本轮暴露。**
它拿**仓库里已绑定的那份报告**当夹具底料（fp 是上一片的 `74b031491f1a`），
删掉一个测试文件的条目，然后断言"只有名单那一格开火"。而本轮已经把清单重锚成
`228cc2e36516` ⇒ C11 `report_fingerprint_matches_disk` 作为**无关连带**一起开火。

关键在于：**这个窗口不是异常，而是每一轮收口的必经状态**——"清单已重锚、报告还是上一片那份"
这段区间里，任何读取"已绑定报告 + 当前磁盘清单"这一对的断言都会红。
上一片为同类形状（C10 判红导致自锁）付过三次全量的代价。
修法不是把那一格从名单里豁免掉（那是把判据改窄来迁就历史读数），而是
**让夹具自带它需要的那个前提**：把合成报告的指纹盖成磁盘现算值，
于是这条用例回到"只测它 docstring 所说的那件事"。C11 自己的正反面由
`test_report_manifest_fingerprint.py` 与 `closeout_verifier --self-test` 那两臂守着，
不靠这条用例顺带看它一眼。

两组各自的净教训：**一道新闸上线时，第一次全量是它的到货检验，不是收尾**；
红要么说明下游夹具停在旧世界（要修夹具），要么说明既有断言偷偷依赖了跨轮一致
（要把依赖变成夹具内的显式前提）。两种都不能靠放宽判据解决。

## 五、镜像清单（本轮实际改到的每一处）

命令面三张分母、census 分母、`command_contract.py`、`cli/main.py`、SKILL 计数**全不动**
（本轮不加命令、不加旗子）。被哈希**文件数 +1**（只有新增的那个测试文件）。

| 面 | 改了什么 | 有没有常驻用例守着 |
| --- | --- | --- |
| `scripts/release_evidence.py` | 闸本体 + 模块 docstring 的退码说明 | 有（8 条） |
| `scripts/closeout_verifier.py` | `_bind_provenance` 替身加键；C10 叙述改成"写入侧已交付" | **没有**——见下 |
| `tests/conftest.py` | docstring 那句"缺席由 `report_fingerprint_recorded` 判红"是第 83 片自己留下的过期话 | 没有 |
| `README.md` 量具目录 | closeout_verifier 那段补"写入侧现在也拒" | 只有"行首可执行写法"那条 |
| `docs/audit/release_evidence_notes.md` | PROVENANCE 字段表、新增"带 `--test-report` 会先过闸"一节、§5 测试名单 | 不参与哈希 |
| 第 83 片取证文档 | §三、§六之二第 1 条、§八 第 2/4 项**原行内**更正 | 不参与哈希 |
| 第 81 片取证文档 | §"强制力因此挪到写入侧"那句原行内更正 | 不参与哈希 |
| `CHANGELOG.md` | v5.45 一条；v5.44 那条"下一片接进本体"按分轮口径**不改**，由新条目翻转 | 有（结构门禁） |

**中间那一行没有牙。** "替身与生产两侧键集各走各的"这件事，靠的是本轮新写的
`test_bind_provenance_fixture_shape_mirrors_production`：它用**生产函数**
`release_evidence._parse_pytest_report` 读同一份报告，再拿验签替身 `_bind_provenance` 的结果逐键比。
这条是跨文件的，因此 W7（只撤替身那半边）与 W6（只撤生产那半边）各打中它一次——
两臂的增量开火名单不同（W7 只 2 条红、W6 带着另外 4 条），这正说明两侧各自在算，
而不是同一个判断被读了两遍。

## 七、复算入口

```bash
cd /Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
.venv/bin/python -m pytest tests/test_release_evidence_preflight.py \
    tests/test_closeout_verifier.py tests/test_report_manifest_fingerprint.py -q
.venv/bin/python docs/audit/s84/battery84.py        # 约 6 分钟，会临时改写两个 scripts/ 文件
.venv/bin/python scripts/closeout_verifier.py --tag v5.6.0 \
    --expect-test tests/test_release_evidence_preflight.py
```

电池会**临时改写** `scripts/release_evidence.py` 与 `scripts/closeout_verifier.py`，
每臂 `finally` 里按原文写回并断言 sha 回到基线；跑它的时候别同时编辑这两个文件。
日志重定向到文件时是块缓冲的，`wc -c` 读到 0 不代表没在跑（本轮实测踩到一次）。

## 八、遗留

1. **`RELEASE_MANIFEST.json` / `BUNDLE_MANIFEST.json` 的同类指纹仍没做**。沿用第 83 片 §八.1 的
   理由（`--test-report` 那步只重写 SOURCE/PROVENANCE，bundle 只在打 tag 时生成），
   本轮没有改变这件事的任何证据。要不要做取决于正式发版那轮是否把 bundle 也绑进证据——属主裁决项。
2. **验签侧 `_bind_provenance` 仍是手写的报告解析替身**。本轮加的那条键集对照只保证"两边键不散"，
   不保证"两边推导同逻辑"（`failed = total - passed - skipped` 这一步两边各写了一遍）。
   真正的修法是让验签侧直接调用生产侧 `_parse_pytest_report`——那要处理 `scripts/` 之间的
   import 方向，且 `closeout_verifier` 的 `--self-test` 全部依赖替身的可控性，不是本片范围。
3. **README 量具目录里没有 `release_evidence.py` 那一行 `python scripts/release_evidence.py …`**。
   读数分两个时点：`git show HEAD:README.md` 里 `release_evidence` 出现 **0** 次（这是写这句话时
   唯一成立的形式），本轮改完之后工作树里有 2 次，但都是我新增的**叙述**（README.md:501,504），
   不是量具目录那一档的行首可执行写法。也就是说"文档里有没有它的退码说明"这件事
   至今没有任何尺子看着——`test_the_instrument_itself_is_cited_in_the_tool_catalog` 只钉
   `closeout_verifier.py` 自己那一行。列为入口项：要么把它收进量具目录并接受
   `doc_command_census` 对它的作用域，要么明确写一句"发布证据工具不在量具目录内"并挂豁免。
   （旁注：这句"0 次"最初是从一个只读子代理的普查里抄来的，它现在已经被本轮自己改成 2 次——
   是"入门禁档必须亲手重算"的现行版本，记在这里当反例。）
4. **清单里一旦出现 float，`fingerprint_of_document` 与 RFC 8785 就分家**。现在的自研规范化是
   `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))`，对 str/int 与 JCS 同读数
   （本轮实测 `SOURCE_MANIFEST.json` 值类型只有 `str`/`int`，float 0 处）。翻案条件写死在这里：
   谁给清单加了一个浮点字段（比如覆盖率百分比、耗时），或者要跨语言复算这份指纹，
   就必须换成 RFC 8785 兼容实现，并给"两种实现同读数"补一条常驻用例——
   而不是让下一位读者从 `canonical_document` 的黑名单里自己猜这件事。
5. **`release_fingerprint.py` 的 docstring 原本把黑名单写成白名单**（"规范摘要只吃
   `version`/`source_commit`/`coverage`/`files`"），而实现只剥 `VOLATILE_KEYS`，顶层的 `name`
   其实**也在**摘要里。本片顺手就地改正为黑名单叙述（同一个文件第 5-9 行）。
   这件事没有任何常驻用例守着——它是本轮改指针时读码撞见的，属于"叙述与实现各说各话"的又一例。
6. **闸的"读不出"那一判把两种形状合并成了一个消息，其中一种是错的**（本轮自查读码抓的，
   判决方向没错、只有归因文案错，所以**没有推迟收口去改它**——那要多烧一整个全量，见 §六 第 3 条）。
   由 `_parse_pytest_report` 现读，走到 `not report_info.get("parsed")` 这一支的输入其实有两种：

   | 输入形状 | `_parse_pytest_report` 的返回 | 我的消息 |
   | --- | --- | --- |
   | 文件在、JSON 坏 | `{"present": True, "parsed": False, ...}` | ✓ 正确 |
   | `--test-report` 给了不存在的路径 | `{"present": False, "path": ...}`（**根本没有 `parsed` 键**） | ✗ 说成"present 但 parsed=false" |

   第二种恰恰是**操作员最容易犯的那个**（旗子值打错一个字母）。修法很小且必须成对做：
   按 `present` 与 `parsed` 分两条消息，并给"路径不存在"补一条常驻用例——
   现在树上只有 `test_refuses_an_unparsable_report` 覆盖第一种（它断的 `"读不出"` 对那一种是准确的），
   第二种是**一条没有任何用例经过的分支**。这两处请搭下一片的必经重锚一起做，不要为一句文案单独跑一整个全量。
7. **"整批不写"精确到面**：`write_evidence` 第一句是 `out_dir.mkdir(parents=True, exist_ok=True)`，
   它在闸之前 ⇒ 被拒时**输出目录本身会被创建**，只是里面没有任何文件。
   常驻用例与 §六 的现场演示断的都是"目录里文件清单为空"（`left == []`），这个强度是够的；
   但 docstring 与 README 里"一个字节都不落盘"这句要读成"没有任何证据文件落盘"。
   要把措辞也拧成绝对零副作用，就把 `mkdir` 挪到闸之后——那一行改动请搭下一片的必经重锚做，
   别为它单独跑一整个全量。
