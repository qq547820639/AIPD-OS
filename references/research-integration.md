# 学术与公开资料检索集成

## ResearchStudio 适配

本 Skill 内置用户附件中的 ResearchStudio paper-search 脚本，支持并发查询：

- Semantic Scholar
- OpenAlex
- arXiv
- OpenReview
- Crossref
- DBLP

脚本位于 `scripts/research/search_papers.py`，默认执行跨源去重、相关性排序、来源合并和综述标记。

## 使用流程

1. 将工程问题拆成 2–5 个互补检索式：核心术语、同义词、机制词、人因/安全词和应用场景词。
2. 默认搜索近 5 年，并加入少量奠基论文；法规或成熟工程原理可扩大年份范围。
3. 运行：

```bash
python scripts/research/search_papers.py \
  --queries "<query1>|<query2>|<query3>" \
  --start-year 2021 --end-year 2026 --max-papers 10
```

4. 对高价值论文核验 DOI/arXiv ID、摘要、研究方法和适用条件。
5. 将论文登记为 Evidence；不要把论文中别的设备表现直接登记为本产品的 V/S 状态。
6. 提炼设计约束、参数范围、测试方法和研究空白，并关联到具体事实或风险。

## 环境变量

- `OPENREVIEW_USER` / `OPENREVIEW_PASS`
- `OPENALEX_MAILTO` / `OPENALEX_API_KEY`
- `SEMANTICSCHOLAR_API_KEY`
- `PAPER_SEARCH_CONNECT_TIMEOUT_SECONDS`
- `PAPER_SEARCH_TIMEOUT_SECONDS`
- `PAPER_SEARCH_MAX_ATTEMPTS`

匿名接口可用时不强制要求密钥；单一来源失败不得阻塞其他来源。

## 宿主搜索回退

若脚本因网络或依赖不可用：

1. 使用 ChatGPT/Codex 可用的网页或学术搜索工具；
2. 优先官方数据库和原始论文页面；
3. 仍执行跨源去重、年份核验和证据状态登记；
4. 明确列出未成功查询的来源；
5. 不用模型记忆补成“检索结果”。

## 产品研究扩展

学术论文之外，按问题调用：

- 标准与法规原文；
- 专利数据库；
- 竞品说明书和认证文件；
- 供应商数据表、工艺指南和材料数据库；
- 事故、召回和人因研究。

所有当前信息应记录访问日期。
