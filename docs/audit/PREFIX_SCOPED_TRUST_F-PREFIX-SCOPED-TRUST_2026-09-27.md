# 信任降到主机 + 路径前缀级（F-PREFIX-SCOPED-TRUST，第 79 片，2026-09-27）

产物：`src/aipd_os/research/fulltext.py`（`OPEN_ACCESS_PREFIXES` + 重写 `is_open_access_url`，
两个 Europe PMC 主机移出主机级表）、`src/aipd_os/research/__init__.py` 导出、
`tests/test_research_fulltext_step.py`（前缀级双向 + 门规则单点）、`tests/test_closeout_verifier.py`
所在的结构守卫保持、README、登记表该行限制句、两篇旧文档的队列更正、`docs/audit/s79/battery79.py`（4 臂杀 4 活 0：W1 前缀换成不存在的、W2 退回主机级、W3 不查前缀表、W4 把门的规则抄第二份）。

## 一、为什么"注释 + 自律"不算边界

第 78 片的信任扩张是这么写的：加两个主机进 `OPEN_ACCESS_DOMAINS`，注释说明"我们只构造
`/webservices/rest/PMC…/fullTextXML`"，另配一条用例钉"只构造这一种 URL"。
问题是那条用例钉的是**我们**的行为，不是**判定**的边界：任何人后来传一个
`https://www.ebi.ac.uk/anything` 进来都会被判开放。EBI 上还有 UniProt、ENA 等服务，
它们的路径不是全文端点。机制版本是把边界写进判定函数。

## 二、双向证据

| URL | 第 78 片 | 第 79 片 |
| --- | --- | --- |
| `www.ebi.ac.uk/europepmc/webservices/rest/PMC12900525/fullTextXML` | open | open |
| `europepmc.org/articles/PMC8783953` | open | open |
| `www.ebi.ac.uk/` | open | **不开放** |
| `www.ebi.ac.uk/some/other/service` | open | **不开放** |
| `europepmc.org/reader/PMC1` | open | **不开放** |
| `evil.test/ebi.ac.uk/...` | 不开放 | 不开放 |

## 三、两条队列的处置（一条更正、一条判定不做）

- "合并 `rerun_for_rework` 与 `run_supervisor` 的口子"：查证后第 72 片已完成，
  s77/s78 两篇记录写错了 ⇒ 原地更正，并新增门规则的单点用例（真正可能分叉的是规则，不是调用）。
- "narrow 具名样本与处置账的直接联动"：与 `UNACCOUNTED` 等价，做了就是永不开火的死闸 ⇒ 不做，理由写在这里。

## 四、终局读数（占位）

## 五、下一片入口

1. 多域可抽性：出版商自有 OA 站点仍以 PDF 为主；要做"从引用元数据推真文本源"的第二个域
   （Europe PMC 之外，如 CORE / DOAB 的主机也按前缀接进来）。
2. `rerun_for_rework` 目前只重跑一次；连续失败的重试上限由引擎管，未验多轮形状。
