# F-C6 第 33 片：把「门没人跑」这一族闭掉

日期：2026-09-25 ｜ 轮次：本轮（承第 32 片 `gates.approved_by` 去默认值之后）
登记的缺陷类别：**判据写得对，但没人跑它**；以及**自检只断言负向**，
于是「门在拦」与「门永远红」在读数上同形。

## 一、这一格以前为什么是假的

三条都是今天（2026-09-25，改之前）真读到的，不是引用旧登记：

1. **契约点名的闭环判据没人跑。** `references/end-to-end-closure-model.md:10`：
   「只有 `scripts/e2e_acceptance.py` 对项目工件返回 `full_digital_chain_ready=true`，
   才能使用『数字全链路已打通』」；`references/local-cad-fallback.md:25` 第 8 步要求跑它；
   `scripts/runtime_preflight.py:46` 还明写「preflight 不宣布闭环，闭环要 e2e_acceptance」——
   两个脚本把权威互相推，结果**谁都没跑过它**。同一族里
   `scripts/selftest_quality.py`、`scripts/selftest_v4.py` 也一样没有调用者。
   （第一次普查带 `| head -30`，把 `migrations/*` 与登记文本混在一起差点读成「有读者」；
   去掉截断、按「是否 spawn 形态」重判才算数。）
2. **旧 `selftest_quality.py` 的两条判据都只看 `rc != 0`。**
   合规侧对照一支都没有 ⇒ 把 `outcome_acceptance.py` 或 `cad_maturity_gate.py`
   改成「任何输入都退 1」，这份自检照样打印 `{"passed": true}`。
   它还用 `runpy.run_path(cad_maturity_gate.py)`（不带参数）去执行脚本顶页，
   只为拿一个常量字典。
3. **`missing` 的文案替别人下了结论。** `schema_binding.validate_artifact_file`
   报 `errors=["标了交付，但文件不在"]`，可它对交付清单**一无所知**：
   实测对空目录（`/tmp/s33-empty`）与对 `releases/golden-projects/*` 都回同一句。

## 二、修法与三个决定

1. **普查判据取「spawn 形态」**：一个读者要同时出现脚本名与
   `subprocess.run(` / `call(` / `check_call(` / `Popen(`（CI workflow 里出现脚本名即可算），
   只被文本提到不算跑过。决定：**普查面不排除本用例自身**——
   这与第 30 片那条「字面量反查要排除量具自身」不矛盾：那条问的是「谁引用了这个名字」，
   把断言写进去就会虚增分母；这条问的是「谁真的调用了它」，而本用例确实是调用者。
   写第一版时我按惯性排除了自己，那条断言会当场变成「没人跑」的假红，先改掉才跑。
2. **自检补成四支两两对照**（A1 只有产物⇒communication 不放行；A2 全链路+验收达标⇒放行；
   B1 `faceted_brep` 达不到 C7；B2 `native_brep` 填满要求项⇒C7 放行），
   且**断言落在判决字段上而不是只落在退出码**：A1 要看
   `artifact_complete is True and communication_accepted is False`，
   A2 要看 `checkpoint_shape.status == "valid"`。
   少跑到任何一支 ⇒ `rc=7`（与「判据开火」的 `rc=6` 分开），
   免得「一支都没跑」被读成「全通过」。
3. **文案归位**：校验器只说「文件不在盘上」；
   「该交付物已标 complete」由拿着交付清单的 `scripts/quality_gate.py` 在 detail 后补上。
   两侧各有一条常驻用例钉住，且互不相同——这条分工本身就是被断言的对象。

CI 没改：这三台门现在是通过**常驻用例**在 CI 里跑的（`tests/` 在 CI 的 pytest 范围内），
比再往 workflow 里塞一条裸命令更可归因。

## 三、动手前被实测推翻的一条

我一度把「`e2e_acceptance.py` 对 `releases/golden-projects/*` 全部返回 rc=5、
且报『标了交付，但文件不在』」读成一处大缺陷（**契约点名的判据对本仓的样板工程全部不放行**）。
那是**探针瞄错了对象**：`releases/golden-projects/C-supply-chain` 里只有
`report.json` / `quote.csv` / `lab.csv` 三个文件，从来不是这个脚本的输入
（它要的是 `requirements/`、`manual/`、`cad/model.step`、`state/project_checkpoint.json` 那一套）。
按今天真建的夹具（`_full_thread`）跑，包装器 **rc=0、`classification=communication_accepted`**。
所以这一片登记的只有「文案对空目录越界」这一条，样板工程那条**划掉**，
划掉的理由就是上面这句。

## 四、端到端实测

| 场景 | 读数 |
| --- | --- |
| 完整数字链夹具（6 个产物 + 契约有效的 checkpoint + `quality/outcome_contract.json` + 验收字段 9.2≥8.0） | `e2e_acceptance.py` **rc=0**，`communication_accepted=true`，`classification=communication_accepted`，`checkpoint_shape=valid` |
| 只撤一样：验收分数 7.9 < 8.0 | **rc=5**，`digital_thread_complete` 仍为 true、`communication_accepted=false`（红只来自那一格） |
| 同一绿夹具加 `--require-full` | `requested_gate=production`、**rc=5** ⇒ 通信级绿不被读成量产发布绿 |
| `--json-out` | 文件真落盘（559 字节，内容与 stdout 同源） |
| 空目录 / 只放三个 csv 的目录 | `checkpoint_shape.status=missing`，改后 errors 只剩 `["文件不在盘上"]`（改前是 `["标了交付，但文件不在"]`） |
| 声明侧（G3 里 `cad_contract` 标 complete、path 指向不在盘上的文件） | `quality_gate` 的 finding 为 `missing`，detail 同时含「文件不在盘上」与「该交付物已标 complete」 |
| `selftest_quality.py` 四支 | A1 rc=5 且字段如判据；A2 rc=0/shape=valid/comm=true；B1 **rc=4**；B2 rc=0 ⇒ `{"passed": true}`、进程 rc=0 |
| `selftest_v4.py` | rc=0，`v4 supervisor selftest passed`（旧登记那句话今天仍成立，但过去没人跑它） |

## 五、这一片没做的事

1. **两条判据没有撤回案例**（写进电池的 `KNOWN_SURVIVORS`，不当作杀掉了）：
   - J8「自检里字段照读、但不参与判定」：payload 断言挡得住「顺手删字段」，
     挡不住「留着字段不消费」。要让它可观测，就得让自检把判定式本身端出来——
     那是给判据加仪式，不是加牙。这条性质的真牙齿在包装器那两档绿/撤对照里。
   - J11「把普查放宽成提到过名字就算」：只有在**真读者消失**时才观测得到差别，
     而这里唯一真读者就是本用例；删掉它来「证明有牙」是造假。
2. `outcome_acceptance.py` 与 `e2e_acceptance.py` 仍是 1 空格压缩风格的老脚本，
   本轮只动它们消费的那句话/那条透传，没顺手重排（重排会把 diff 摊到不属于本片的行上）。
3. **契约那句话按字面永远无法满足**（实测，不是推断）：
   `references/end-to-end-closure-model.md:10` 要求「`e2e_acceptance.py` 返回
   `full_digital_chain_ready=true`」，而全仓 `full_digital_chain_ready` 只出现在两处——
   那句契约本身，和 `scripts/runtime_preflight.py:46`（那里它被**硬置 False**，
   并写明 preflight 不宣布闭环）。`e2e_acceptance.py` 与 `outcome_acceptance.py`
   **都没有这个键**（它们交出的是 `requested_gate_passed` / `classification` /
   `digital_thread_complete`）。要么把契约改成实际键名，要么在包装器里补一个别名字段——
   这是**契约语义**的改动，属主没拍之前不动，登记在此。
4. `selftest_quality.py` 的「少跑即 rc=7」只护「少跑」，不护「少判」（见 1）。

## 六、收口读数

（数字一律抄命令输出；取数脚本 `/tmp/slice33-closeout.sh`，日志 `/tmp/slice33-closeout.log`。）

| 项 | 读数 |
| --- | --- |
| 全量用例 | 2170 → **2182**（+12，全在新增的 `tests/test_gate_runners.py`）。取数顺序照第 32 片配方，但**先修正一处顺序**：两份清单的生产者不同（`regenerate_release_manifest.py` 只刷 `RELEASE_MANIFEST`，`SOURCE_MANIFEST` 只有 `release_evidence.py` 会写），所以「刷清单 → 跑 attestation 那一遍 → 再刷证据」。tag 锚定那一跑：**`2179 passed / 0 failed / 3 skipped`，240.25s，rc=0**；工件提交（`8ce7664`）之后在 `git worktree add /tmp/s33head HEAD` 的干净签出里再跑一遍：**同样 `2179 passed / 3 skipped`，214.52s，rc=0**（先断 `aipd_os.state.db.__file__` 落在签出树上） |
| 被哈希面 | 624 → **625**；逐路径差集：新增 `['tests/test_gate_runners.py']`、删除 `[]` ⇒ 没有意外文件进面 |
| `PROVENANCE.test_report` | `2179 passed / 0 failed / 总 2182`，报告 `docs/audit/pytest-report-v5.6.0.json`（`sha256=2bebb4cda9ae…`），`source_commit = a66040520139…`（tag，按既有裁决不重锚到 HEAD） |
| 发布门（工件提交后、本轮记录 cp 进 `docs/audit/` 之时） | **rc=2，8 项里 7 ✓、唯一 ✗ 是 `workspace_clean`**（` M docs/audit/pytest-report.json`，就是脚本自己在那一刻之前写进去的签出报告）。其余全绿：`test_numbers_from_report passed=2179 failed=0`、`source/bundle_manifest_zero_diff` 都是 zero diff、Ed25519 可验、无密钥、`no_unacknowledged_cve = pip-audit: no unacknowledged CVE`。**干净树上的复跑读数记在下一行** |
| 发布门（干净树复跑，HEAD=`d144134`） | **rc=0，8/8 全绿，`release_ready: true`**（`workspace_clean=clean` 起）；同一棵树上 `audit_repo --strict` 仍只有 tag 锚点那一条红 |
| `audit_repo --strict` | rc=1，唯一 ✗ 仍是既有裁决那条 tag 锚点红（`manifest=a66040520139… vs HEAD=…`） |
| 变异电池 | 本片 `/tmp/slice33-mutations.py` **11 条：杀 9 / 存活 0 / 注入无效 0 / 已知无撤回案例 2**（J8、J11，见 §五.1）；同一棵树上复跑上一片第 32 片 **14/14**、第 31 片 **8/8**、第 30 片 **21/21**（四条都 rc=0） |
| ruff / mypy | ruff（CI 范围 `src tests state_service`）`All checks passed!`；mypy `Success: no issues found in 425 source files`（+1：`test_gate_runners.py`） |
| 其他门 | C6 普查 `--self-test` 7/7；档位仍 **15 / 0 / 0**（本片不动 C6 交付物面） |

## 七、五处自己抓自己的读数

1. **又是管道后的 `$?`**：电池第一次跑成 `... | tail -15; echo rc=$?` 读出 rc=0，
   而它其实返回 1（J11 活着）。改成先重定向到文件、再取 `$?`、再 tail——
   这条已经在记忆里写过一次，本轮是**同一个会话里第二次**踩，说明「跑完顺手 tail 一眼」
   这个动作本身要改成默认写文件。
2. **锚点不能靠猜**：`e2e_acceptance.py` 是 1 空格缩进的老风格，我按 4 空格写的两条锚点
   命中 0 次；CAD 门那条 `    return 0` 也是 0 次（真正的收尾是
   `    return 0 if target_passed else 4`）。把文件逐行 `repr` 打出来再定锚点，
   才有 11/11 全部命中。
3. **一次假归因**（§三）：把「我对错了输入」读成「判据对本仓样板全不放行」。
   规矩：负向读数出来先复核**探针的输入是不是它的合法输入**，再谈缺陷。
4. **两个清单不是同一个工具写的，我因此白烧了一跑。** `regenerate_release_manifest.py`
   只刷 `RELEASE_MANIFEST.json`；`SOURCE_MANIFEST.json` 只有 `release_evidence.py` 会写。
   收口第一版按「先刷清单再跑全量」的顺序跑，attestation 那一跑里
   `test_source_manifest_hashes_match_disk` 照样红（清单只刷了一半），
   于是 `failed=2` 被绑进 `PROVENANCE.test_report` 并被提交（`325185b`），
   后面得再刷一轮证据 + 再跑一次全量才干净。
   规矩：重锚之前先确认**两份清单各自的生产者**都被跑过，再取那一份要当证据的全量读数。
5. **全文扫的门会把登记文本里的「否认」读成「声称」。**
   `tests/maturity_consistency_test.py::test_no_faceted_overclaim` 扫的是整个仓库的文本，
   我在 CHANGELOG 里给 B1 那一支写的否定短语（「到不了」）**不在**它的
   `NEGATION_HINTS` 里（表里收的是「达不到 / 无法 / 不能 / 仅」这些），
   于是登记文本被读成一次过度声称。**本节不复读那句原话**——复读会被同一个
   正则再抓一次（这件事本身就发生了：本文件第一版因引用原话而判红）。
   改的是**登记措辞**（换成表里已有的否定词），没有去放宽那条共享门禁的提示表。
