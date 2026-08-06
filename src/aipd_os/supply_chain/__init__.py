"""供应链与验证执行包。

提供报价解析/登记、供应商资质、实验室数据导入、验证阶段分析、
纠偏任务、回归分析、事实更新与 BOM/CAD 影响传播等真实、确定性逻辑。
"""

from __future__ import annotations

from aipd_os.supply_chain.quotes import (
    normalize_quote,
    parse_quote_file,
    QuoteVersion,
    QuoteRegistry,
)
from aipd_os.supply_chain.suppliers import SupplierProfile, SupplierRegistry
from aipd_os.supply_chain.lab import import_lab_csv, import_lab_json, import_lab_report, import_lab_xlsx
from aipd_os.supply_chain.analysis import (
    analyze_stage,
    create_correction_tasks,
    mark_regression,
    propagate_impact,
    update_facts,
)
from aipd_os.supply_chain.certification import (
    Certification,
    CertificationRegistry,
    import_certificate_file,
    expiring_certs,
)
from aipd_os.supply_chain.mail import (
    MailConnector,
    SmtpConnector,
    ImapConnector,
    LocalMailService,
    MailError,
    ExternalDependencyError,
    MailMessage,
    SendResult,
    retry_with_backoff,
)
from aipd_os.supply_chain.stages import (
    import_stage_report,
    extract_root_cause,
    propose_corrective_actions,
    verify_regression,
)
from aipd_os.supply_chain.persistence import SupplyChainStore
from aipd_os.supply_chain.writeback import PhysicalWriteback

__all__ = [
    "normalize_quote",
    "parse_quote_file",
    "QuoteVersion",
    "QuoteRegistry",
    "SupplierProfile",
    "SupplierRegistry",
    "import_lab_csv",
    "import_lab_json",
    "import_lab_report",
    "import_lab_xlsx",
    "analyze_stage",
    "create_correction_tasks",
    "mark_regression",
    "propagate_impact",
    "update_facts",
    "Certification",
    "CertificationRegistry",
    "import_certificate_file",
    "expiring_certs",
    "MailConnector",
    "SmtpConnector",
    "ImapConnector",
    "LocalMailService",
    "MailError",
    "ExternalDependencyError",
    "MailMessage",
    "SendResult",
    "retry_with_backoff",
    "import_stage_report",
    "extract_root_cause",
    "propose_corrective_actions",
    "verify_regression",
    "SupplyChainStore",
    "PhysicalWriteback",
]
