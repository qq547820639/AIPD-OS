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
2. 第 85 片 §八.1 那条（脚本目录豁免清单）与 §八.2、§八.3 都还开着，本轮没动。
