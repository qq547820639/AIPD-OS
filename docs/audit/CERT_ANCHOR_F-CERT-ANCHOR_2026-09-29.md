# F-CERT-ANCHOR 第 95 片：报告的锚点从"操作员自述"改成"跑内实测 + 跑内祖先关系"

量具：`scripts/closeout_verifier.py`（C5 `pinned_source_binding`）
生产侧：`tests/conftest.py:54-70`（报告字段的唯一写入点）
常驻用例：`tests/test_closeout_verifier.py` +3 条（两极 + 老报告回退，合成 git 历史里跑）、
`tests/test_report_manifest_fingerprint.py` 7 条 → **8** 条（真跑一跑盖字段那极）
量具自测：`python scripts/closeout_verifier.py --self-test`

## 一、现读：这一格原先是**替身**，而且方向与我以为的相反

```
$ python -c "…读 tests/conftest.py 的挂钩…"
head = os.environ.get("AIPD_SOURCE_COMMIT", "")      # ← 声明值优先
if not head:
    head = git rev-parse HEAD                        # ← 只有没给环境变量才实测
```

收口配方每一跑都传 `AIPD_SOURCE_COMMIT=<tag SHA>` ⇒ **fallback 分支永远不执行**，
于是"报告锚点 == 被测那棵树的 HEAD"这件事从没在跑内核过：`source_commit` 是
我在命令行上给的那个字符串，跑本身没有对它说任何一个字。

另一半是 C5 的祖先检查用的是**验签时刻**的工作树 HEAD：

```
anc = git merge-base --is-ancestor pinned head      # head = 验签当时 worktree 的 HEAD
```

而收口链在绑定之后还要再提两个提交（门读数、验签读数），所以那个 `head` 已经是
比被测树更靠后的提交——"锚点是它的祖先"因此**恒真**（合法的锚点当然在历史里）。
第 93 片 §五 曾把"指纹是跑内实测"当成链条已闭合的依据，那半边确实成立；
**缺的就是锚点这一半**，本片刻的是这一半。

## 二、改了什么（三处，都有撤销臂级别的读者）

1. `tests/conftest.py`：无条件 `git rev-parse HEAD`（`cwd=_ROOT`，即那一跑真正加载的树），
   另落 `source_commit_measured`；`source_commit` 仍是操作员给的声明值
   ——**工具不许偷偷把声明改成实测**，那是替操作员改证件。
2. `scripts/closeout_verifier.py` C5：有 `source_commit_measured` 时，祖先关系改按
   **那一跑实测的 HEAD** 判（`锚点必须是"被测树"的祖先`）；没有该字段时退回旧行为，
   但在读数里**点名**"报告未带 source_commit_measured ⇒ 这一格弱一档"。
3. `_pristine_report(..., measured_commit=…)`：合成报告默认让实测值 == 锚点自身
   （`merge-base --is-ancestor X X` 退 0 ⇒ 既有夹具语义不变），要判这一格就显式传。

缺席为什么不判红：报告是不可变的历史产物，第 83/92 片两次实测到
"把缺席判成违规会自锁"——0-failed 的 attestation 永远产不出来。
所以缺席＝弱一档 + 点名，判红只给"声明了但实测值不是它的后代"这种** actively 不一致**。

## 三、两极用例（新增 6 条，全部在合成 git 历史里跑）

* `test_pinned_must_be_ancestor_of_the_measured_head`：
  报告实测 HEAD = tag 的**父提交**（锚点不是它的祖先）而验签时刻的工作树 HEAD 是锚点的
  **后代** ⇒ 旧判据全绿、新判据必须判红。这一条就是"验签时刻 HEAD 顶替被测树"的反证。
* `test_stamps_measured_head_and_passes_when_it_descends_from_the_anchor`：
  实测 = 锚点的后代 ⇒ C5 绿，且读数里点名"按那一跑实测的 HEAD 判"。
* `test_absent_measured_commit_falls_back_to_the_verification_time_head`：
  老报告（无该字段）⇒ 不判红，但**不许静默**：读数必须写"这一格弱一档"。
* `test_conftest_stamps_the_measured_head_alongside_the_declared_anchor`（真跑一跑）：
  复制真 `tests/conftest.py` 到一个临时 git 仓库、传一个非祖先锚点 `f*40`，
  断 `source_commit_measured == 那棵树的 HEAD` 且 `source_commit == 声明值`。
  夹具布局本身交过一次学费：conftest 的 `_ROOT = parents[1]`，放成 `repo/conftest.py`
  会让它上一层 ⇒ git 探针空返回 ⇒ **整个键不写**。这恰好演示了"静默留空"为什么比判红难查。

## 四、已知边界

1. 老报告（本仓 `docs/audit/pytest-report-v5.6.0.json` 在第 95 片之前绑定的那些）没有该字段 ⇒
   判据对它们只能按验签时刻的树判，读数里点名。**不许**为此加一条"在树里的报告必须带该字段"
   的常驻用例——那会自锁下一代认证（本仓的常驻套件会去读那份被绑定的报告）。
   自我约束的写法是把要求放在**生成侧**：下一代认证跑完必然带这个键，
   而它由 §三 的真跑那条用例守，不由"读历史报告"守。
2. `source_commit_measured` 与 `source_commit` 一样是报告里的自述字段。本片把
   "跑内核过一次 HEAD"变成事实，但没有解决"报告整体可被伪造"——那需要外部见证
   （签名或时间戳授权），属主侧决策，不在在线范围内。
3. `release_evidence.py` 的 `_annotate_test_report` 会往报告元信息里抄 `source_commit`，
   而全仓没有任何常驻用例跑过 `release_evidence.py`（现读 `grep -rln release_evidence tests/` 为空）；
   这是"被认证链消费的量具没有机器读者"这一族的一般情形，第 94 片 §四.6 已记，本片刻意不扩面。
4. `scripts/` 整体仍不在 CI 的 ruff / mypy 面内（`pyproject.toml [tool.ruff]`、
   `[tool.mypy] files=["src","tests"]`；`ci.yml` 跑 `ruff check src tests state_service`）
   ⇒ 本片的 verifier/conftest 改动里，`closeout_verifier.py` 不在 mypy 覆盖面内。

5. 读数文案有一处**截断错位**：C5 绿的时候打印 `它是 报告实测 HEA 的祖先`
   （我把 `anc_src[:8]` 用在了标签上，本意是截 commit 的前 8 位）。
   只影响可读性、不影响判决，但它是"字段被截半"的形状，若哪天有人按字串去匹配这条读数就会漏。
   修法一行（标签不截、commit 截 8 位），排进第 96 片与另外两格一起做；
   本片**不**为这一处重跑认证（那要再烧一跑全量，代价与收益不成比例）。

## 五、认证读数（2026-09-29 收口，一次跑通）

```
$ bash docs/audit/s95/closeout95.sh
PRECHECK OK: 2756 passed / 5 skipped / collected 2761 / 341.xs / fp b143a47e71ea
MIN_TESTS=2761 （上一代下界 2760）      SKIP 面逐条相同：5 条
BIND_RC=0   回读 OK: source_commit=a66040520139 test_report=2756p/0f/2761t fp=b143a47e71ea
GATE_RC=0   release_ready: True | 未过: 无 | 项数: 8
CV_RC=0     11 格全绿
$ .venv/bin/python scripts/closeout_verifier.py … --json docs/audit/s95/closeout-s95-b.json   # 回收 worktree 后
CVB_RC=0    11/11 全绿
```

本片要的那一格在**产物里**看得见，不是只在代码里：

```
报告字段  source_commit_measured = d6baae569c3f     ← 那一跑实测的 HEAD（被测树）
          source_commit          = a66040520139     ← 操作员声明的 tag 锚点
C5 读数   "报告与 PROVENANCE 都绑在 a660405…，且它是 报告实测 HEA 的祖先"
```

最后一行的标签截断是 §四.5 那条已知瑕疵；**关键点是 C5 走了"报告实测 HEAD"这一支**，
不再是"验签时刻的工作树"——收口链在绑定之后还提了 `2e46903`（绑定）与门/验签两个读数提交，
若按旧判据，那时 HEAD 已是被测树的后代，恒真。
`plaintiffs_measured` 这一格也从"1 条"变**2 条**（两片以来第一次点两条 `--expect-test`）。

被哈希文件数：691 → 691（本轮无新增被哈希文件；新产物都在 `docs/audit/`）。
提交链（`git log --oneline` 现读）：`935c1fb` 代码+测试+文书 → `d6baae5` 刷清单
→ `2e46903` 绑定 → `b35de12` 门读数 → … 验签读数 → 有效代报告 → 本节。

**未证事项**：
① 报告整体仍可伪造——`source_commit_measured` 也是报告里的自述字段，只是**由那一跑的进程**写的；
   要外证需签名或时间戳授权（属主侧，见 §四.2）。
② `release_evidence.py` 仍无常驻读者（`grep -rln release_evidence tests/` 空，第 94 片 §四.6 同源）。
③ §四.5 的文案截断未修（有意不为它重跑认证）。
