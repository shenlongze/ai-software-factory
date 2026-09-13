"""factory-core/product — Product Intelligence Layer (Phase 9A/9B, ADR-0026/0027)。

独立 Extension: 独立数据空间 <root>/product/ (ideas.json/artifacts.json/
approvals.json/workflows.json/experience.json), 只读复用 events/EventLogger
(唯一事实源) 与 providers/Registry + CostAwareSelector (9b 生成框架)。
Core 零修改: 本包纯新增, 删除本包不影响 Factory 其余功能 (Removal Isolation)。

导出 (供 CLI/Dashboard/测试):
- models: Artifact/ProductIdea/ApprovalGate/ApprovalRequest/ApprovalDecision/
  ProductWorkflow + ApprovalRequired/ApprovalStatus/WorkflowStatus
- store: ProductStore/ProductStoreError/CorruptProductStoreError
- service: ProductService/ProductError/ProductNotFoundError + DEFAULT_GATES/DEFAULT_STAGES
- experience (Phase 9b): GenerationExperience/ExperienceStore/ExperienceStoreError
- generation (Phase 9b): GeneratedArtifactContext/GenerationResult/ProductGenerator/
  ProductGenerationError/ProductGenerationNoProviderError/GENERATION_TYPES

注: generation 模块是 providers 的专用消费方 (TaskRequirement → CostAwareSelector
→ ProviderAdapter, 禁硬编码), 故 __init__ 不顶层导入 generation — 删除 providers
包后 `import product` 仍成功 (product 其余命令零影响), `product generate` 由 CLI
延迟导入点响亮 rc 1 (配置缺口, 同 dashboard --view provider 模式)。
"""

from __future__ import annotations

from .experience import ExperienceStore, ExperienceStoreError, GenerationExperience
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
    "ExperienceStore",
    "ExperienceStoreError",
    "GenerationExperience",
    "ProductError",
    "ProductIdea",
    "ProductNotFoundError",
    "ProductService",
    "ProductStore",
    "ProductStoreError",
    "ProductWorkflow",
    "WorkflowStatus",
]
