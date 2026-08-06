"""AIPD-OS 手册视觉语义审计。

该审计是语义级（结构/角色/叙事/参数事实/中文真文字/禁伪），而非仅像素统计
（白占比/熵/aHash）。人物与 CMF 等需要真实视觉模型的维度不会假装通过，
而是标记 ``requiring_vision``。
"""
from aipd_os.visual_audit.auditor import VisualAuditor, audit_batch
from aipd_os.visual_audit.providers import VisionAuditProvider, VisionAuditUnavailable

__all__ = ["VisualAuditor", "audit_batch", "VisionAuditProvider", "VisionAuditUnavailable"]
