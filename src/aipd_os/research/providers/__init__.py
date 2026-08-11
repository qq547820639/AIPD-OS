"""research providers 包（v5.8.1 Commit 10）。"""
from __future__ import annotations

from .researchstudio import (
    MIT_ATTRIBUTION,
    ArxivEngine,
    OpenAlexEngine,
    ResearchStudioEngine,
    ResearchStudioPaperSearchProvider,
    SemanticScholarEngine,
    default_engines,
    normalize_arxiv_id,
    normalize_doi,
    normalize_title,
    register_researchstudio,
)

__all__ = [
    "MIT_ATTRIBUTION",
    "ResearchStudioEngine",
    "ArxivEngine",
    "OpenAlexEngine",
    "SemanticScholarEngine",
    "default_engines",
    "normalize_title",
    "normalize_doi",
    "normalize_arxiv_id",
    "ResearchStudioPaperSearchProvider",
    "register_researchstudio",
]
