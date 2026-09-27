# 真文本源优先，策略判定挪到下载之前（F-TEXT-FIRST-SOURCES，第 78 片，2026-09-27）

产物：`scripts/research/fetch_fulltexts.py`（`_pmcid_of`、PMC 优先的 `pick_target`、
`sniff_bytes` 认 XML、`xml_to_text`、下载前的 `classify_access`、`not_open_*` 结论词、
`force_fetch`）、`scripts/research/search_papers_by_open_alex.py`（带出 `ids.pmc`）、
`src/aipd_os/research/fulltext.py`（白名单加 Europe PMC 两个主机 + 边界注释）、
`tests/test_research_fulltext_step.py`（+5）、`tests/test_research_fulltext_live.py`（+1）、
登记表与 README、矩阵重生成。

## 一、先探再动手

Europe PMC REST `/{PMCID}/fullTextXML`：OA 条目 200 + `application/xml`（JATS 正文），
非 OA 的 PMC8581587 → 500，带版本号写法 → 404。结论：这条路径**不需要 PDF 抽取器**就能拿到文本，
所以它应当排在 PDF 直链之前，而不是当备选。

## 二、"没正文"的一半原因是连接器丢了字段

OpenAlex 的 `ids.pmc` 一直在返回，第 76/77 片的映射没取。没有 PMC id 就只能看见 PDF 副本，
于是撞上第 77 片那个死路（能下载、被许可、没有抽取器 ⇒ 零正文）。

## 三、策略判定前移

旧顺序：下载 → 交给库分类 → 库判 restricted 时**根本不调 getter**，于是我们已经白下一次，
而 `outcome` 还留着 `extracted_xml`。新顺序：先 `classify_access()`，不开放就不发起请求；
真去取（`force_fetch`）而结果仍不开放时，结论词写成 `not_open_restricted`。

## 四、白名单的边界

加进 `OPEN_ACCESS_DOMAINS` 的是 `ebi.ac.uk` 与 `europepmc.org`，注释写明这份信任的依据
（Europe PMC 只对 OA 收藏返回全文）以及"我们只构造 `/webservices/rest/{PMCID}/fullTextXML`
这一种 URL"；两条常驻用例分别钉住"只构造这一种路径"和"没有顺手放进别的站"。

## 五、在线读数（`AIPD_RESEARCH_INTEGRATION=1`）

| 目标 | kind | outcome | chars | access |
| --- | --- | --- | --- | --- |
| PMC12900525 JATS | xml | extracted_xml | 37970 | open |
| arXiv 2401.04398 PDF | pdf | extracted_pdf | 80991 | open |
| 由 europepmc 链接反推 PMC8783953 | xml | extracted_xml | 16136 | open |

## 六、终局读数（占位）

## 七、下一片入口

1. 白名单是主机级的，构造边界靠我们的代码自律；更硬的做法是让 `classify_access`
   接受"路径前缀"级信任（需要改库的签名与既有用例）。
2. §第 77 片两件仍未做：narrow 具名样本与处置账的直接联动、`rerun_for_rework` 与
   `run_supervisor` 共用口子合并。
