# Golden E2E fixture：Idea → Evidence（v5.8 Commit 15）

> **EPISTEMIC_NOTE**: 本目录 fixture 数据仅用于测试系统行为（离线），
> **不代表真实医学/康复结论**。所有 claims / evidence 均为确定性假数据。

输入提示词：
「我想做一个利用 AI 帮助独居老人居家康复的产品」

系统行为（离线 fixture 验证）：
1. Raw Idea（I0）创建
2. IdeaDecomposer（Fake provider）→ Structured Idea + Candidate Claims（默认 A/U）
3. ResearchIntegration（Fake provider）→ canonical evidence + relation
   （supports / contradicts / inconclusive）
4. Idea Truth projection + maturity I0→I1→I2
5. restore 后一致 / tenant+project isolation / lineage 可追溯 / audit 可查
