"""factory-console — Human Console Backend API Layer (Phase 11A, ADR-0034)。

Human Layer 产品入口: 统一只读 API (为未来 Web UI 11B 准备)。
架构: Core → Extension → Console — factory-console/ 独立目录 (不污染
factory-core), Console 只读各域 (Event/Artifact/Decision/Recommendation/
Experience/Approval/Provider)。

边界铁律 (phase11a-status.md §禁止):
- Core 零修改: 本包只读 Core/Extension 数据, 唯一允许的 Core 改动是
  events/models.py EventType 纯增量枚举扩展 (console.*, ADR-0001 路径)。
- 只读: 零写操作 — 不自动执行/不自动批准/不修改 Decision/权重/不替代
  Human (决策权永远在 9c Approval 状态机)。
- 无 Database/Web API 依赖: api/ 路由函数为纯函数 (未来 11B 挂 FastAPI
  薄层); 本包不 import FastAPI/任何 Web 框架。
- Removal Isolation: 删除本包 Factory 照常运行 (Core 零感知); 反向删除
  Core 包也不影响本层加载 (service/api 全部函数内延迟导入 Core 包)。

模块:
- models.py: ConsoleDashboard 七域 + 各 API 响应模型 (Pydantic v2)
- service.py: ConsoleService — 只读聚合各域 (workspace → product lifecycle
  → 9c approvals → intelligence → providers)
- api/: 6 个路由函数模块 (projects/lifecycle/approvals/decisions/
  intelligence/providers)
- events.py: console.* 事件辅助 (console.viewed / console.approval.opened /
  console.dashboard.viewed, 经 EventLogger)
"""

from .events import (
    SOURCE,
    record_console_approval_opened,
    record_console_dashboard_viewed,
    record_console_viewed,
)
from .models import (
    AgentSummary,
    ApprovalSummary,
    ConsoleDashboard,
    CostSummary,
    DecisionSummary,
    EventSummary,
    ExperienceSummary,
    ExperienceSummaryModel,
    LifecycleSummary,
    ProjectSummary,
    ProviderSummary,
    RecommendationSummary,
)
from .service import ConsoleService

__all__ = [
    # service
    "ConsoleService",
    # models
    "AgentSummary",
    "ApprovalSummary",
    "ConsoleDashboard",
    "CostSummary",
    "DecisionSummary",
    "EventSummary",
    "ExperienceSummary",
    "ExperienceSummaryModel",
    "LifecycleSummary",
    "ProjectSummary",
    "ProviderSummary",
    "RecommendationSummary",
    # events
    "SOURCE",
    "record_console_approval_opened",
    "record_console_dashboard_viewed",
    "record_console_viewed",
]

# S10-074: 运行时版本单一来源 (pyproject.toml [project].version)
try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("ai-software-factory")
except Exception:  # noqa: BLE001 — 非安装态 (源码运行) → 读 pyproject
    import tomllib
    from pathlib import Path as _P
    _pp = _P(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        __version__ = tomllib.loads(_pp.read_text(encoding="utf-8"))["project"]["version"]
    except Exception:  # noqa: BLE001
        __version__ = "0.0.0-dev"
