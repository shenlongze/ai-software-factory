"""factory-core/product — Product Intelligence Layer (Phase 9A, ADR-0026)。

独立 Extension: 独立数据空间 <root>/product/ (ideas.json/artifacts.json/
approvals.json/workflows.json), 只读复用 events/EventLogger (唯一事实源) 与
providers/Registry (9b 接入)。Core 零修改: 本包纯新增, 删除本包不影响
Factory 其余功能 (Removal Isolation)。

导出 (供 CLI/Dashboard/测试):
- models: Artifact/ProductIdea/ApprovalGate/ApprovalRequest/ApprovalDecision/
  ProductWorkflow + ApprovalRequired/ApprovalStatus/WorkflowStatus
- store: ProductStore/ProductStoreError/CorruptProductStoreError
- service: ProductService/ProductError/ProductNotFoundError + DEFAULT_GATES/DEFAULT_STAGES
"""

from __future__ import annotations

from .models import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalRequest,
    ApprovalRequired,
    ApprovalStatus,
    Artifact,
    ProductIdea,
    ProductWorkflow,
    WorkflowStatus,
)
from .service import (
    DEFAULT_GATES,
    DEFAULT_STAGES,
    ProductError,
    ProductNotFoundError,
    ProductService,
)
from .store import CorruptProductStoreError, ProductStore, ProductStoreError

__all__ = [
    "ApprovalDecision",
    "ApprovalGate",
    "ApprovalRequest",
    "ApprovalRequired",
    "ApprovalStatus",
    "Artifact",
    "CorruptProductStoreError",
    "DEFAULT_GATES",
    "DEFAULT_STAGES",
    "ProductError",
    "ProductIdea",
    "ProductNotFoundError",
    "ProductService",
    "ProductStore",
    "ProductStoreError",
    "ProductWorkflow",
    "WorkflowStatus",
]
