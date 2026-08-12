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
from .agent_executor import execute_runtime_task
from .artifacts import get_artifact, get_artifact_content, list_artifacts
from .backlog import (
    create_epic,
    create_feature,
    create_story,
    create_task,
    delete_task,
    get_task,
    list_backlog,
    update_task,
)
from .decisions import get_decision
from .intelligence import list_experience, list_recommendations
from .lifecycle import get_project_lifecycle
from .mcp_api import (
    create_mcp_connection,
    list_mcp_connections,
    list_mcp_tools,
)
from .projects import (
    complete_discovery,
    confirm_project_route,
    create_draft_project,
    create_project,
    delete_project,
    list_projects,
    save_discovery_answer,
    suggest_project,
    update_project,
)
from .providers import list_providers
from .review_feedback import list_review_feedback, save_review_feedback
from .runtime import (
    SSE_EVENT_MAP,  # noqa: F401 — SSE 事件映射常量 (测试/前端引用; 非路由不进 __all__)
    capture_runtime_screenshot,
    create_runtime,
    get_project_timeline,
    get_project_workflow,
    get_runtime,
    get_workflow_stages,
    iter_sse_events,
    list_runtimes,
    start_runtime,
    stop_runtime,
)
from .runtime_session import (
    append_runtime_session_event,
    cancel_runtime_session,
    complete_runtime_session,
    create_runtime_session,
    get_runtime_session,
    get_task_runtime_sessions,
    list_runtime_sessions,
    start_runtime_session,
)
from .skill_api import agent_skills, list_skills
from .sprint import (
    add_roadmap_milestone_ref,
    create_milestone,
    create_sprint,
    delete_milestone,
    delete_sprint,
    get_milestone,
    get_roadmap,
    get_sprint,
    list_milestones,
    list_sprints,
    plan_sprint,
    update_milestone,
    update_sprint,
)
from .tool_api import execute_tool, list_tools
from .workflows import get_workflow, list_workflows
from .workflow_start import chat_route, run_status_route, start_project_workflow_route

__all__ = [
    "add_roadmap_milestone_ref",
    "agent_skills",
    "append_runtime_session_event",
    "approve_approval",
    "cancel_runtime_session",
    "capture_runtime_screenshot",
    "chat_route",
    "complete_discovery",
    "complete_runtime_session",
    "confirm_project_route",
    "create_draft_project",
    "create_epic",
    "create_feature",
    "create_mcp_connection",
    "create_milestone",
    "create_project",
    "create_runtime",
    "create_runtime_session",
    "create_sprint",
    "create_story",
    "create_task",
    "delete_milestone",
    "delete_project",
    "delete_sprint",
    "delete_task",
    "execute_runtime_task",
    "execute_tool",
    "get_artifact",
    "get_artifact_content",
    "get_decision",
    "get_milestone",
    "get_project_lifecycle",
    "get_project_timeline",
    "get_project_workflow",
    "get_roadmap",
    "get_runtime",
    "get_runtime_session",
    "get_sprint",
    "get_task",
    "get_task_runtime_sessions",
    "get_workflow",
    "get_workflow_stages",
    "iter_sse_events",
    "list_approval_gates",
    "list_approvals",
    "list_artifacts",
    "list_backlog",
    "list_experience",
    "list_mcp_connections",
    "list_mcp_tools",
    "list_milestones",
    "list_projects",
    "list_providers",
    "list_recommendations",
    "list_review_feedback",
    "list_runtime_sessions",
    "list_runtimes",
    "list_skills",
    "list_sprints",
    "list_tools",
    "list_workflows",
    "plan_sprint",
    "reject_approval",
    "run_status_route",
    "save_discovery_answer",
    "save_review_feedback",
    "start_project_workflow_route",
    "start_runtime",
    "start_runtime_session",
    "stop_runtime",
    "suggest_project",
    "update_milestone",
    "update_project",
    "update_sprint",
    "update_task",
]
