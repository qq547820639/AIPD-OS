"""research 测试夹具（确定性检索数据）。

v5.7 Commit 7D：本地确定性数据不再作为生产默认（production ``StandardsRetriever``
等默认 external_dependency）；测试通过 :class:`TestRetriever` 显式注入本夹具。
"""
