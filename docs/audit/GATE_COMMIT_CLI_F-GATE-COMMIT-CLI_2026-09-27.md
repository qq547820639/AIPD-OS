# 把产品定义门禁的 commit 接上 CLI（F-GATE-COMMIT-CLI，第 69 片，2026-09-27）

产物：`src/aipd_os/cli/main.py`（旗子）、`src/aipd_os/cli/product_commands.py`（支路）、
`scripts/absence_claim_census.py`（`expect: "present"`）、`tests/test_product_gate_commit_cli.py`（4 条）、
`docs/audit/s69/battery69.py`（5 臂）、登记表/README/账本的同批改口。命令数与三张分母不变；
被哈希文件数 669 → 670（新增一个常驻测试文件，差集见 §五）。

## 一、这一步为什么值得单独一片

第 68 片把"没有生产入口"变成了一条可判红的登记；本片把它闭合，
顺带把判据的形状补全：账本从"只有缺席式"变成"缺席式 + 存在式"。
存在式是必要的——**只有缺席式的账本，会在被修好的那一刻自动变瞎**：
`GATE-COMMIT-NO-PRODUCER-*` 一旦撤掉，那句话就没有任何机器再盯着了。

## 二、改口清单（一轮里必须同批动的位置）

| 面 | 改了什么 |
| --- | --- |
| `cli/main.py` | `--commit` 旗子 + parser help |
| `cli/product_commands.py` | 支路：`commit_approved(actor="owner-cli")`，不吞错 |
| `scripts/product_capabilities_extra.py` | `product.definition_gate` 的限制句改口（权威在此） |
| `src/aipd_os/registry_data.py` | 由 `migrate_capability_registry.py` 生成（不手改） |
| `docs/audit/capability_matrix.{md,json}` | 按 tag 重生成 |
| 量具账本 | 撤 2 条缺席式、加 1 条存在式（`expect: present`） |
| 常驻控制用例 | 第 68 片盯 0 调用点的两条改方向（否则绿着守旧说法） |
| `README.md` | 速查加 `--commit`；第 68 片那段"外部调用点为 0"就地更正 |

## 三、两条被实测纠正的预期

1. 我以为第二次 `--commit` 会走 `idempotent_replay` 幂等成功；实测被"非 frozen"拒
   （`commit_approved` 取最新 snapshot，它已 committed）。**代码赢，读数改判**，
   而且这个结果比静默重放更符合"旗子不许把拒绝洗成成功"。
2. 我第一版常驻用例用 `capsys.readouterr().stdout`（该对象只有 `.out/.err`），
   以及把私有方法 `_lineage_edges_for_test` 当断言路径——两处都在跑的第一秒暴露，
   都改成 SQL 直读 `truth_lineage`：判据要盯权威事实，不盯实现里恰好存在的方法名。

## 四、电池（5 臂，杀 5 / 活 0）

E1 摘掉 `expect=present` 那一支；E2 让缺席式永不判红（"永不判红"而不是"取反"——
第一版我写的是取反，被电池自己的 `new 已在树上` 守卫挡下，因为取反后的文本恰是存在式那一支）；
E3 摘掉 CLI 支路；E4 把前置校验的抛错洗成 ok；E5 旗子不进 argparse。
每臂先断言 `old` 恰好 1 处、`new` 不在树上、`compile()` 过，落地后校验 sha 已变，
`finally` 还原并再校验 sha 与基线同值。

## 五、终局读数（占位）

## 六、下一片入口

1. `supervisor.fact_writeback → truth_lineage` 的前提**已解除**：现在生产面能写出
   `requirement`/`feature` 记录（本片 CLI）；仍缺的是"把工作项与那条记录对应起来"的键——
   入口在第 69 片之后可以走 `--commit` 之后的 receipt（`committed_truth_refs_json` 已落表）。
2. 第 64 片留的 `doc_command_census` 只报面收窄仍未做；窄档两个手写词表仍无自证。
