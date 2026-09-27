# 全文获取的消费者（F-FULLTEXT-STEP，第 76 片，2026-09-27）

产物：`scripts/research/fetch_fulltexts.py`（新步骤）、
`scripts/research/search_papers_by_open_alex.py`（带出 `is_oa`/`oa_url`/`oa_license`）、
`tests/test_research_fulltext_step.py`（6 条）、`tests/test_research_fulltext_fetcher.py`（4 条）、
`scripts/absence_claim_census.py`（`duplicate_claim_id` 前提 + 账本换条 + 具名样本改指）、
登记表 `research.fulltext_fetch` 该行、README、`docs/audit/s76/battery76.py`。

## 一、这一步只做连接器侧的两件事

1. **这条记录有没有合法的开放副本**：只用来源自己返回的字段（OpenAlex `is_oa`+`oa_url`、
   arXiv 按 id 推官方 PDF 直链、其余来源只认已有的 `oa_url`）。
2. **该用哪个 URL 去取**：取不到就报"没标开放副本"，**不去 scrape 出版商页面**。

下载、编码判定、缓存、SHA-256、access 分类全部复用库里那份
`src/aipd_os/research/fulltext.py`（它本来就写着诚实契约：非法 UTF-8 字节 = 拿不到）。

## 二、为什么之前接不上：连接器把答案丢了

OpenAlex 的响应里有 `open_access` 与 `best_oa_location`，连接器映射时**两个都没取**，
所以记录里只剩 DOI。这不是"少一个字段"，是让下游只剩两种坏选择：猜 URL（可能撞 robots、
可能只拿到付费墙 HTML）或者永远报"没有开放副本"。

## 三、选型（零新依赖优先）

| 候选 | 功能 | 依赖/条款 | 结论 |
| --- | --- | --- | --- |
| OpenAlex `best_oa_location` | 开放副本地址 + license | CC0 数据、无 key、我们已是六源之一 | **选它** |
| Unpaywall | 同上 | 要 email 参数、非商用条款、新外部依赖 | 不选：字段等价 |
| Semantic Scholar `openAccessPdf` | 同上 | 部分字段要 key | 不选：收益不抵依赖 |
| 抓出版商页面 | — | 版权/robots 边界，库里实现本身拒绝 | 不做 |

## 四、两处我自己造的缺陷（都被自己的闸抓回）

1. `s[:i] + 新条目 + s[j:]` 里 `j < i`，四块登记被复制。重复 id 不改判决、`rc` 仍 0
   ⇒ 加 `duplicate_claim_id` 前提 + 守卫用例（账本不许有僵尸条目）。
2. `--offline` 用例第一版钉"没拿到全文"，T4 臂摘掉 offline 判断后仍绿
   （真下载 PDF 也判 restricted ⇒ 两种因果同一读数）。改钉原因：离线**不许构造下载器**。

## 五、终局读数（占位）

## 六、下一片入口

1. 联网端到端仍需在能出网的环境跑一次（本机测试全部注入 getter，离线不下载）；
   这一步的 `e2e_evidence` 已按"联网跑通即拿到正文；离线模式只登记可取性"写清，不假装已在线验过。
2. 第 64 片留的 `doc_command_census` 只报面收窄已完成；剩两件：narrow 具名样本与处置账的**直接**联动、
   `rerun_for_rework` 与 `run_supervisor` 的共用口子进一步合并。
