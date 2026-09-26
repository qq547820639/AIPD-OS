# F-CTQ-STALE 第 44 片：要求被标陈旧，不等于要求消失了

日期：2026-09-26 归属：发布就绪证据 / CTQ 覆盖分母
状态：已闭（缩水可见 + 常驻 6 条 + 电池 4 条）
落点：`src/aipd_os/release_manifest.py::_collect_ctq`
用例：`tests/test_release_evidence_ctq_status.py`

## 一、复现（先测出来再改）

`_collect_ctq` 用 `truth.query(record_type="ctq", status="active")` 取分母。
最简夹具实测（两条 CTQ，第二条 `set_status(..., "stale")`，其余条件不变）：

```
ctq ids in doc: ['T-001']
issues kinds:   ['no_drawings', 'bom_db_missing']
```

**T-002 从证据里彻底消失，issues 一个字都没提它。** 而门禁的
`gdt_covers_ctq` / `ctq_has_inspection` 是拿 `doc["ctq"]` 当要求面的：
两条变一条，覆盖义务就少一条。只有全部掉光时才由 `no_ctq` 兜住——
所以这是一条**部分缩水即放行**的 fail-open 通路，不是"少报一条"的表述问题。

反讽之处要说清：这个函数自己的 docstring 就写着"缺 feature 的逐条点名（不静默少一条）"。
它对"字段缺"守了纪律，对"状态不在 active"没守——**同一函数内的两种"少一条"，
只有一种被认为需要交代**。这类"纪律只覆盖想到的那一半"是本仓反复出现的形状。

## 二、改判与边界

| 状态 | 进覆盖分母？ | 出点名？ | 阻断？ | 理由 |
| --- | --- | --- | --- | --- |
| `active` | 是 | 缺 feature / 缺检验方法才点 | 是（原有判据不变） | — |
| `stale` / `expired` / `blocked` | **否** | 逐条，带 record_id 与状态名 | **是** | 这是"还没收口的要求"，不是"少一条要求" |
| `superseded` | 否 | 逐条 | 否 | 被新版本取代是合法处置；但分母为什么小了必须让读者看见 |
| 枚举外的状态 | 否 | 逐条 | 是 | **兜底 hardening**：`store.update` 把状态核在 `TRUTH_STATUS` 内，今天没有生产者能写进去（按本仓纪律，没有生产者的守卫要标成加固而不是当成现状） |

分母语义**没有**放宽：陈旧要求不会被拿去和图纸硬核对（那是另一种错——
把没收口的东西当已核对）。变的只有一条：**缩水必须可见**。

## 三、常驻用例（6 条）与两条方向对照

除金路径与序列化外，特意配了两条"另一头"的对照：

- `test_clean_database_does_not_fire_the_new_criterion`：全 active 时新判据必须闭嘴
  （否则它只是一个永远抱怨的判据，下一轮就会被当成噪声关掉）；
- `test_denominator_shrink_is_now_visible`：同一条 CTQ 标 stale 前后，
  分母从 2 变 1（语义不变）**且**点名必须出现——两头各钉一格。
  电池里的 D4（非 active 也收进分母）就是这条对照的注入形态，半径 5 条。

## 四、撤改电池（`/tmp/s44/battery.py`，4 条：杀 4 / 存活 0 / 注入无效 0）

| 注入 | 半径 |
| --- | --- |
| D1 未收口的 CTQ 降级成非阻断 | 2 |
| D2 把 `superseded` 也当成未收口 | 1 |
| D3 点名只写条数不写 record_id | 3 |
| D4 非 active 也收进覆盖分母（反向） | 5 |

对照臂先立（未注入 rc=0）；每条只动它自己那一处，还原按被改文件 sha 比。

## 五、与第 43 片的关系

上一轮之前，"CTQ 被标 stale"几乎只会发生在测试里；`drawing spec` 写出血缘边之后，
`aipd truth propagate --upstream <CTQ>` 会让**图纸声明**被打 stale，而 `truth propagate`
本身也会把上游 CTQ 之外的下游纳入 stale 集合——也就是说"库里存在非 active 的 CTQ"
从理论状态变成日常状态。**这两片是同一件事的两半**：先有了会动的血缘，
再让"动过的要求"必须被看见。若只做 43 不做 44，传播越准，放行反而越松。

## 六、复算入口

```
.venv/bin/python -m pytest tests/test_release_evidence_ctq_status.py -q      # 6 条
.venv/bin/python /tmp/s44/battery.py                                          # 4 条撤改
.venv/bin/python -m pytest tests -k "release_manifest or production_release_gate or golden"
```

## 七、终读数

收尾链：`d9eae00`（代码 + 清单重锚 637→638）→ 全量 → `d2a2dbf`（绑证据 + 报告入库）→ 门禁。

- **全量**：**2308 passed / 3 skipped / 0 failed**，440.86s，跑在 `d9eae00` 的
  `git worktree` 干净签出里（`PYTHONPATH` 指向该签出的 `src`，`AIPD_SOURCE_COMMIT` = tag SHA）。
  报告 sha256 `e00df22d2b8a2dbb…`，已入库并绑进 `PROVENANCE.test_report`
  （passed 2308 / failed 0 / total 2311）。
- 连带面复算（`-k "release or gate or golden or capabilit or registry or truth or evidence"`）
  一度 **4 failed**：3 条是 `capability_matrix.*` 工件在 registry 语法坏掉那一次没能重生成，
  1 条是 `test_release_manifest_hashes_match_disk` 等本轮重锚。两者都不是行为变更——
  **CTQ 判据收紧的实际波及面为 0**（金项目与全部常驻夹具里的 CTQ 都是 active），
  重生成矩阵后该选面 607 passed / 0 failed。
- **`production_release_gate --release-ready --tag v5.6.0`**：**8/8 PASS，rc=0**。
- **`audit_repo --strict`**：rc=1，唯一一条 ✗ 是按设计保留的 tag 锚点项
  （`manifest=a66040520139… vs HEAD=d2a2dbf2c344…`），两份清单 `hash_mismatch_count` 均为 0。
- **文档引用普查（开发树，写本节时测）**：148 份文档 / 3595 处引用，
  `resolved` 2878 / `missing` 136 / `multi` 429 / `external` 81 / `elided` 61 /
  `line_beyond_eof` 10（Σ == 分母 ✓），**现状面 0 条**、历史面 123 条。
  绝对数是开发树读数，且本节写完还会再漂一次（第 41 片 §二 的漂移规则），
  所以被钉住的只有"现状面 0"这一格。

## 八、过程事实（不进 CHANGELOG 的那类）

1. 往 `registry_data.py` 那行超长 dict 字面量里追加中文散文时带了半角双引号
   （`status="active"`、`doc["ctq"]`、`"缩水必须可见"`），字符串被就地截断成**语法错**。
   第一信号不是"引号错了"，而是 `-k` 选面里 **9 条无关用例红**——我差点把它读成
   "CTQ 判据收紧的波及面"。第二次修（只改前两处）仍漏了第三处，而且我第一次的
   就地替换把句子咬成了重复括号。教训落成两条：
   ① 改完被大量用例 import 的数据文件，**先 `python -c "import …"` 或 ruff，再跑测试**；
   ② 追加进代码字面量的中文文案一律用「」，且修文案要用"定位 marker + 断言命中 1 次 +
   整段重写"的脚本，不要在残缺片段上做多次局部补丁式 Edit。
2. `tests/test_release_evidence_ctq_status.py` 初稿也在断言消息里写了半角引号，
   被同一条纪律挡住（改成「」）——写测试时先想"这段文本会不会经过解析器"。
