# ANCHOR-REQUIRED 第 86 片：`--source-commit` 从"记得给"变成"不给就拒"

日期：2026-09-28 ｜ 上一片：第 85 片 `docs/audit/SCRIPT_ROW_CENSUS_F-DOC-CMD-SCRIPTS_2026-09-28.md`
｜ 实现：`scripts/release_evidence.py`（`main()` 的锚点前置校验）
｜ 常驻：`tests/test_release_evidence_preflight.py`（+3 条，10 → 13）
｜ 电池：`docs/audit/s86/battery86.py`（三臂，`KILLED 3/3`）

## 一、为什么这一片值一次全量：它复现并关掉了两次实测代价

项目记忆里这条被记过两次，都是**真实烧掉的整轮全量**：

- 第 52 片：绑定那一次只给 `--test-report` 没给 `--source-commit` ⇒
  `generate_provenance` 里 `source_commit or _default_source_commit(repo)` 把锚点**默认成当时的 HEAD**，
  于是 `production_release_gate` 的 `commit_matches_head` 判红、`release_ready: false`；
  修法当时是"再跑一次带两个旗子的调用 + 另开一个提交，**不 amend**（该提交本身就是这条错法的证据）"。
- 第 62 片：收尾时 `AIPD_SOURCE_COMMIT` 误传本轮 HEAD（应为 tag SHA）⇒ 又红一次，又整跑一轮。

两次的共同形状是：**少给一个旗子不当场报错，只在下一环读成"别的东西坏了"**。
本轮开工前先把这条形状跑出来，确认它还活着：

```
$ python scripts/release_evidence.py --repo . --out /tmp/nosc2 --version 5.6.0
写出锚点 = 277c60b4a65a   ← 当时 HEAD
tag 锚点 = a66040520139
是否已经把锚点漂到 HEAD: True        # RC=0，一句警告都没有
```

同一条命令**带上** `--test-report` 时今天已经是 `RC=2`——不是因为有锚点校验，
而是因为第 84 片的清单同源闸**顺带**拦住了它：锚点是清单内容的一部分，
漂到 HEAD 之后即将写出的清单与报告自记的指纹就不同源了。
这是那次改动的意外红利，也说明**剩下的静默通道正是"不带报告的配方第一步"**：

```
拒绝：`--source-commit` 必须显式给出。…（带报告 / 不带报告两条入口都 RC=2，且目录未建）
拒绝：`--source-commit` 不是 40 位十六进制 SHA：'a660405'。…
```

## 二、判据形状与一处"我没做"的决定

`main()` 里两道前置，都排在任何写盘之前（沿用第 84/85 片那条"连目录都不建"的形状）：

1. `--source-commit` 为空 ⇒ 退 2，消息写明"由 `git rev-parse <tag>^{commit}` 现读"；
2. 不是 40 位十六进制 ⇒ 退 2，消息写明**为什么**要全形：
   `production_release_gate` 与 `closeout_verifier` 都按逐字相等比较，
   截断值不会报错、只会永远判红——把读者的排查方向从"我旗子写错了"支到"判据坏了"。

**没做的一半（有意）**：不加"锚点必须等于报告里的 `source_commit`"这一道。
带报告时那件事**已经被两样东西覆盖**——第 84 片的指纹闸（锚点是清单内容之一）与
gate 自己的 `commit_matches_head`；再加一道就是把同一个事实写第三遍，
而"同一个事实写两处"本身是第 46 片记过的那类债（注入一支臂杀不掉，因为另一支还兜着）。

## 三、电池：三臂，其中一臂专打"校验被写松"

`docs/audit/s86/battery86.py`，基线 `rc=0 13 passed`：

```
[KILLED] X1-anchor-may-default-again      增量开火: test_refuses_without_source_commit_on_both_paths
[KILLED] X2-shape-check-dropped           增量开火: test_refuses_a_malformed_source_commit
[KILLED] X3-shape-check-loosened-to-prefix 增量开火: test_refuses_a_malformed_source_commit
合计 KILLED+CRASH-KILL 3 / 3；其余按判决分类：无
```

X3 不是 X2 的重复：X2 撤掉整条校验，X3 把「恰好 40 位」退化成「至少 7 位」——
**git 短 SHA 正好 7 位**，于是 `a660405` 重新通过。
只有第二条能抓住"以后有人嫌它严、顺手改成 `match` + `{7}`"这种最可能的腐化路径。

## 四、镜像与遗留

改了：`scripts/release_evidence.py` 模块 docstring 的用法块与退码段、
`docs/audit/release_evidence_notes.md` 的生成入口叙述、项目记忆里的
**每轮收口重锚配方**（`--source-commit` 由"可带"改成"必填，不给就退 2"）。
遗留两条：

1. **`write_evidence()` 这条 API 仍可传 `None`**（默认 HEAD），
   因为 `tests/test_release_evidence.py` 的 `_make_repo` 直接用它、且那里"锚点 = 临时仓库 HEAD"是**正确语义**。
   本轮只关操作员入口（`main`），没有把 API 一并收紧——收紧要先把那套夹具改成显式传锚点，
   那是另一次改契约，不该混在这一片里顺手做。
   **→ 第 88 片已闭合**：夹具改成显式传 `head`（`tests/test_release_evidence.py:95,102`），
   `write_evidence()` 的默认值删掉、缺锚点在任何落盘之前抛 `BindPreflightError`
   `scripts/release_evidence.py:367`（校验体在 `:382`），牙在 `tests/test_release_evidence_preflight.py`
   末尾三条（`:321`/`:332`/`:346`，含把"恰好 40 位"退化成"至少 7 位"那一臂）。
   `generate_source_manifest()` / `generate_provenance()` 的 `or _default_source_commit(repo)`
   **有意保留**：`production_release_gate` 的 `source_manifest_zero_diff` 要按当前树现算一份
   清单再只比 `(path, sha256)`，那条通道既不写盘也不消费锚点。
2. 第 85 片 §八.1 那条（脚本目录豁免清单）与 §八.2、§八.3 都还开着，本轮没动。

## 五、终局读数（绑定那一跑，全部现读）

| 步骤 | 命令 | 实际读数 |
| --- | --- | --- |
| 干净签出 | `git worktree add --detach .wt-s86 HEAD`（HEAD=`052f60b`） | 建树后 `release_fingerprint.py .wt-s86/SOURCE_MANIFEST.json` = `f39fdbb2cffc`，与主树同一值 |
| 全量 | `PYTHONPATH=$PWD/src AIPD_SOURCE_COMMIT=<tag SHA> python -m pytest -q --json-report` | `PYTEST_RC=0`，`2680 passed, 5 skipped in 395.35s`，报告 `summary.collected=2685`、`len(tests)=2685`、`exitcode=0`、`source_commit=a660405201394050…`（= `v5.6.0^{commit}`，不是 HEAD）、`source_manifest_fingerprint=f39fdbb2cffc…` |
| 绑定 | `release_evidence.py --repo . --out . --version 5.6.0 --source-commit <tag SHA> --test-report …` | `BIND_RC=0`（锚点必填与 40 位校验都放行）、回读 `PROVENANCE.test_report = present/parsed 均 True，2680p/0f/2685t`，指纹格 `f39fdbb2cffc…`；提交 `9555a84` |
| 发布门 | `production_release_gate.py --release-ready --tag v5.6.0 --test-report …` | `GATE_RC=0`，`release_ready: True`，8/8 项全过（`workspace_clean=clean`、`source_manifest_zero_diff=zero diff`、`test_numbers_from_report passed=2680 failed=0 total=2685`、`signature_verifiable=Ed25519 signature verified`、`no_unacknowledged_cve=pip-audit: no unacknowledged CVE`） |
| 收尾验签（第一次，随收口脚本） | `closeout_verifier.py --tag v5.6.0 --expect-test tests/test_release_evidence_preflight.py --min-tests 2685` | **`CV_RC=4`**，11 档里只红 `worktree_clean：工作树有 1 处未提交改动：['?? docs/audit/s86/gate.json']`，其余 10 档绿 |
| 收尾验签（提交取证件后重跑同一个验签器） | 同上，HEAD=`77ac3f5` | **`CV_RC=0`，全部判据绿**：`worktree_clean：工作树干净`、`roster_covers_tree 树 218 文件 / 2595 个 def，报告 218 文件 / 2685 条，双向差集为空`、`size_ratchet 名单 2685 条 ≥ 下界 2685`、`report_bound_to_provenance sha256=3d3e3800cff1` |

## 六、两处本轮实测到的链条性质（值得留在配方里）

1. **`worktree_clean` 这一档管的是"取证件的落盘顺序"，不是产品质量**。第一次 `CV_RC=4`
   不是发布门坏了：脚本把 `gate.json` 的 `git add` 排在了收尾验签**之后**，于是验签器
   正好看见自己上一步留下的未跟踪件。判红内容与 s85 配方（先提交门读数、再验签）唯一的差别
   就是那一次 `git add` 的位置——同一把尺、同一棵树，把 `gate.json`/`gate.log` 先入库再跑就 11/11。
   已按此顺序改正 `docs/audit/s86/closeout86.sh`。两份执行读数**并存不覆盖**：判红那一跑的日志
   是已入库的 `docs/audit/s86/closeout.log`（里面那条 `✗ worktree_clean` 原样留着），
   全绿那一跑的 JSON 落在 `docs/audit/s86/closeout.json`、日志落在
   `docs/audit/s86/closeout-recheck.log`，不把 4 判红改写成"看起来一直绿"。
2. **提交 `docs/audit/**` 不会作废在飞的报告**：`SOURCE_EXCLUDE_PREFIXES` 含 `docs/audit/`
   （`scripts/release_evidence.py` 第 74 行），实测在提交 `0186665`（新增 `closeout86.sh`）之后
   `release_fingerprint.py SOURCE_MANIFEST.json` 仍是 `f39fdbb2cffc` = 报告所记，
   所以绑定照样放行。反过来说：**改 `README.md`/`CHANGELOG.md`/`scripts/`/`tests/` 才会**——
   那是第 84 片 §四之二 烧掉一整轮的原因，这条性质是它的安全侧对照。
3. **`--min-tests` 从 2680 提到 2685**：`size_ratchet` 比的是报告 `tests` 名单条数
   （`closeout_verifier.py` 第 419 行 `len(nodes) >= min_tests`）。上一轮（第 85 片）的名单是 2682，
   本轮新增 3 条用例后实测 2685。写 2680 时它比上一轮还低，等于"本片新增用例没跑到"也不会红——
   棘轮下界必须按本轮实测数现取，不能沿用一个更松的旧数。

## 七、复算入口

```bash
cd AIPD-OS
.venv/bin/python scripts/release_fingerprint.py SOURCE_MANIFEST.json | cut -c1-12   # 应为 f39fdbb2cffc
.venv/bin/python -c "import json;d=json.load(open('docs/audit/s86/closeout.json'));print(d['readings'])"
bash docs/audit/s86/closeout86.sh     # 整条链的配方；重跑会再绑一次（同内容 ⇒ 同指纹 ⇒ 仍放行）
```
电池：`docs/audit/s86/battery86.py`（三臂 X1/X2/X3，`合计 KILLED+CRASH-KILL 3 / 3`）。
