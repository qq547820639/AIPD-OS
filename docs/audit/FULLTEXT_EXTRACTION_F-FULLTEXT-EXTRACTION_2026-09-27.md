# 取到字节 ≠ 抽出正文（F-FULLTEXT-EXTRACTION，第 77 片，2026-09-27）

产物：`scripts/research/fetch_fulltexts.py`（`sniff_bytes` / `pdf_to_text` /
`MIN_FULL_TEXT_CHARS` / 新计数词）、`pyproject.toml` 的 `full` extra 与
`scripts/research/requirements.txt`（pypdf>=4）、`tests/test_research_fulltext_step.py`（+3）、
`tests/test_research_fulltext_live.py`（在线，默认跳过）、登记表 `research.fulltext_fetch` 改口、
README、`docs/audit/s77/battery77.py`。

## 一、上一片的一句假话

我在第 76 片的"未证实"里写"沙箱无出网，联网端到端未跑"。**没查就写了**。
这一轮先查：`arxiv.org` 返回 200。真跑之后暴露的不是"少一次验证"，而是能力名不副实。

## 二、在线实测把误标逼出来

| 目标 | 下载 | 第 76 片报的 | 应为 |
| --- | --- | --- | --- |
| arXiv 官方 PDF（1638905 B） | 成功 | `access=restricted` | 开放、可抽 ⇒ 抽出 **80991 字**，`open` |
| arXiv `/abs` 落地页 | 成功（服务器实际回了 PDF，sha 与上一行同为 `b852a161da…`） | `restricted` | 同上 |
| OpenAlex 给的出版商 OA PDF（3651992 B） | 成功 | `restricted` | 开放但只抽出空白 ⇒ `pdf_without_text`，**不记 open** |

`restricted` 的含义是"来源不让我拿"，这里是"我拿到了但没抽取器/抽不出文本"。
两者混成一个词，读数就会把**我们缺组件**说成**文章不开放**——方向相反的错误。

## 三、形状

- 三档结论词彼此不相容：`restricted`/`blocked`（不该拿）、
  `pdf_extractor_unavailable`/`pdf_without_text`/`pdf_extract_failed:*`（能拿、抽不出）、
  `short_or_landing_page`（抽出来的短于 `MIN_FULL_TEXT_CHARS=2000`，多半是摘要页）。
- 抽不到文本时**绝不**记 `open`，也不进全文缓存。
- pypdf 是**可选**依赖：缺它只是能力降级，不是失败。

## 四、选型（六维，结论：pypdf）

| 候选 | 功能匹配 | License | 维护 | 安全 | 质量 | 适配成本 |
| --- | --- | --- | --- | --- | --- | --- |
| pypdf 6.19 | 页级 `extract_text()`，够本用途 | BSD-3-Clause（读 wheel METADATA 的 `License-Expression` 现证） | 活跃 | 纯 Python，异常可控 | 单一入口 | 一个 import，最低 |
| PyMuPDF | 抽取质量更高 | **AGPL-3.0** ⇒ 与 Apache-2.0 项目不兼容 | 活跃 | 原生库 | 高 | 直接排除 |
| pdfminer.six | 偏底层（需自己管布局/编码） | MIT | 活跃 | 纯 Python | 高 | 成本高于所需 |
| 外部 `pdftotext` | 够 | 工具本身 GPL（进程调用可用） | — | 依赖系统 | — | 跨平台安装不可控 |

## 五、电池第一版也有活臂

U1（把 strip 判空改成永不空）第一版**存活**：我的空白 PDF 用例喂的是坏文件，
走 `pdf_extract_failed` 分支，压根没经过那道闸。改法：monkeypatch `pypdf.PdfReader`
让页返回 `"   
	  "`，控制打在它声称要防的那一行上。之后 4 臂全杀。

## 六、终局读数（占位）

## 七、下一片入口

1. 在线用例今天只打 arXiv 一个域（出版商 OA 那份抽不出文本是事实，不是缺陷）；
   要扩到多域需先加"从引用元数据推可抽源"的映射（PMC/EURSCIENC 这类真文本源）。
2. 第 76 片 §六 两件仍挂着：narrow 具名样本与处置账的直接联动、`rerun_for_rework` 与
   `run_supervisor` 共用口子的进一步合并。
