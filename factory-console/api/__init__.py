"""factory-console/api/ — Human Console 只读 API 路由函数 (无 Web 依赖)。

设计依据 (phase11a-status.md):
- 6 个路由函数模块: projects/lifecycle/approvals/decisions/intelligence/
  providers — 纯函数返回响应模型 (Pydantic), 无 FastAPI/Web 依赖; 未来
  11B 挂 FastAPI 薄层时, 路由函数即 handler 主体 (FastAPI 只做 HTTP 绑定)。
- 只读铁律: 全部函数只调用 ConsoleService 读接口, 返回模型不携带任何
  执行/修改指令 (不自动批准/不修改 Decision/权重)。
- 每个路由函数可选注入 EventLogger — 有 logger 时发 console.viewed 审计
  (ADR-0002: 所有 CLI 行为必须产生 Event; API 层读审计同语义)。
"""

from .approvals import (
    approve_approval,
    conflict_status,
    list_approval_gates,
    list_approvals,
    reject_approval,
)
from .artifacts import get_artifact, list_artifacts
from .decisions import get_decision
from .intelligence import list_experience, list_recommendations
from .lifecycle import get_project_lifecycle
from .projects import list_projects
from .providers import list_providers
from .runtime import (
    SSE_EVENT_MAP,
    get_project_timeline,
    get_project_workflow,
    get_workflow_stages,
    iter_sse_events,
)
from .workflows import get_workflow, list_workflows

__all__ = [
    "SSE_EVENT_MAP",
    "approve_approval",
    "get_artifact",
    "get_decision",
    "get_project_lifecycle",
    "get_project_timeline",
    "get_project_workflow",
    "get_workflow",
    "get_workflow_stages",
    "iter_sse_events",
    "list_approval_gates",
    "list_approvals",
    "list_artifacts",
    "list_experience",
    "list_projects",
    "list_providers",
    "list_recommendations",
    "list_workflows",
    "reject_approval",
]
