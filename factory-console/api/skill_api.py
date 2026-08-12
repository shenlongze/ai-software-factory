"""factory-console/api/skill_api.py — S10-019 Task 001 Skill API 路由函数。

AI Employee Skill System Foundation: Skill 清单 + Agent 技能分配 —
GET /api/skills (SkillRegistry 当前可用 Skill) + GET /api/agents/{id}/skills
(Agent 技能解析: agent.skills 已注册 id 优先 → 系统映射兜底 → 空列表)。
Domain (exec.skill 已 GREEN: Skill/SkillRegistry/SkillContext + 权限链 +
SYSTEM_AGENT_SKILLS); Service 层 (ConsoleService.list_skills/agent_skills)
做失败安全装配 (注入优先 → with_system_skills 自装配 → []/None 兜底);
本模块只做路由函数 (无 Web 依赖, FastAPI 薄层做 HTTP 绑定 — 同
api/tool_api.py 模式)。

路由函数 (HTTP 端点由 fastapi_adapter 绑定):
- list_skills: GET /api/skills — {skills: [{id, name, description, version,
  category, tools, enabled}]} (id 排序; 未装配 → 空清单 — GET 永不失败)
- agent_skills: GET /api/agents/{agent_id}/skills — {agent_id, skills:
  [skill_id, ...]}; agent 不存在 → None (HTTP 404 — 明确错误); store/exec
  未装配 → None (HTTP 404 — 失败安全)

审计: 端点命中 → console.viewed (view=skills / view=agent_skills) — ADR-0002
读审计同语义; logger=None 静默 (失败安全)。
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed

__all__ = ["agent_skills", "list_skills"]


def list_skills(service: Any, *, logger: Any = None) -> dict[str, Any]:
    """GET /api/skills — Skill 清单 (SkillRegistry 当前可用 Skill)。

    → {skills: [...]} (id 排序 — registry.list 契约; 含 disabled — 注册表
    全量, 由前端/调用方过滤); 未装配 → [] (失败安全 — GET 永不失败)。
    审计: console.viewed (view=skills)。
    """
    record_console_viewed(logger, view="skills", count=1)
    return service.list_skills()


def agent_skills(
    service: Any, agent_id: str, *, logger: Any = None
) -> dict[str, Any] | None:
    """GET /api/agents/{agent_id}/skills — Agent 技能分配 (系统映射兜底)。

    → {agent_id, skills: [skill_id, ...]} (resolve_agent_skills: agent.skills
    已注册 id 优先 → SYSTEM_AGENT_SKILLS 兜底 → 空列表); agent 不存在 →
    None (HTTP 404 — 明确错误, 不静默); store/exec 未装配 → None (HTTP 404
    失败安全)。
    审计: console.viewed (view=agent_skills)。
    """
    record_console_viewed(logger, view="agent_skills", count=1)
    return service.agent_skills(agent_id)
