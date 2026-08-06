"""CAD 人体工程学、几何、后端适配器与成熟度一致性数据包。"""

from __future__ import annotations

from aipd_os.cad.backends import (
    CadBackend,
    CadQueryBackend,
    ContractBackend,
    get_default_backend,
)
from aipd_os.cad.evidence import (
    artifact_hash,
    make_artifact_record,
    sha256_file,
    verify_artifact,
)
from aipd_os.cad.maturity import (
    EXTERNAL_DEPENDENCY,
    FULL,
    LEVELS,
    NOT_IMPLEMENTED,
    REQUIREMENTS,
    RUNTIME_MAX,
    evaluate_maturity,
    faceted_ceiling,
    honest_level_status,
    summarize_levels,
)
from aipd_os.cad.writeback import DEFAULT_DOWNSTREAM, propagate_cad_change

__all__ = [
    # backends
    'CadBackend', 'CadQueryBackend', 'ContractBackend', 'get_default_backend',
    # evidence
    'artifact_hash', 'make_artifact_record', 'sha256_file', 'verify_artifact',
    # maturity
    'LEVELS', 'REQUIREMENTS', 'RUNTIME_MAX',
    'FULL', 'EXTERNAL_DEPENDENCY', 'NOT_IMPLEMENTED',
    'evaluate_maturity', 'faceted_ceiling', 'honest_level_status', 'summarize_levels',
    # writeback
    'DEFAULT_DOWNSTREAM', 'propagate_cad_change',
]