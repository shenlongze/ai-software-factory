"""factory-console/session/roles.py — Agent Role System (S10-056 批次 A)。

角色 → capabilities 推导 (设计 §2.2): 8 角色固定编制
(product_manager/architect/backend/frontend/qa/reviewer/devops/tester),
每角色 {skills, capabilities} 规格; 不破坏已有 agent (缺省推导: role →
capabilities; 无 role 命中 → skills → capabilities; 再无 → 空列表)。

组件:
- ROLES — 8 角色规格: {role: {skills: [...], capabilities: [...]}}
- RoleSystem — capabilities_for(agent) / role_matches(required_role, agent) /
  enrich_agent(agent) (返回新 dict, 不修改原字段)

设计: docs/sprint10/S10-056-team-design.md §2.2
边界:
- 纯推导/查询, 不执行业务; 失败安全 (缺字段 → 空推导, 永不抛)
- 纯标准库, 零模块依赖 (独立, 避免循环依赖)
"""

from __future__ import annotations

from typing import Any

#: 8 角色规格: {role: {skills, capabilities}} — 角色 → capabilities 推导源。
#: skills 为角色技能关键词 (skills→capabilities 兜底推导的匹配面);
#: capabilities 为角色能力清单 (role_matches 的匹配面 + enrich_agent 注入面)。
ROLES: dict[str, dict[str, list[str]]] = {
    "product_manager": {
        "skills": ["product", "prd", "requirement", "market"],
        "capabilities": [
            "product_planning",
            "requirement_analysis",
            "prd_writing",
            "stakeholder_communication",
        ],
    },
    "architect": {
        "skills": ["architecture", "design", "system", "technical"],
        "capabilities": [
            "system_design",
            "architecture_decision",
            "technical_planning",
            "design_review",
        ],
    },
    "backend": {
        "skills": ["python", "api", "database"],
        "capabilities": [
            "backend_api",
            "database_schema",
            "api_design",
            "service_implementation",
        ],
    },
    "frontend": {
        "skills": ["flutter", "dart", "react", "ui"],
        "capabilities": [
            "frontend_page",
            "ui_interaction",
            "component_design",
            "responsive_layout",
        ],
    },
    "qa": {
        "skills": ["test", "qa", "quality"],
        "capabilities": [
            "test_suite",
            "test_execution",
            "quality_assertion",
            "regression_testing",
        ],
    },
    "reviewer": {
        "skills": ["review", "quality", "audit"],
        "capabilities": [
            "code_review",
            "quality_gate",
            "defect_detection",
            "best_practice_audit",
        ],
    },
    "devops": {
        "skills": ["ci", "cd", "deploy", "docker"],
        "capabilities": [
            "ci_pipeline",
            "deployment",
            "containerization",
            "infrastructure",
        ],
    },
    "tester": {
        "skills": ["automation", "e2e", "regression"],
        "capabilities": [
            "test_automation",
            "e2e_testing",
            "test_reporting",
            "edge_case_analysis",
        ],
    },
}


class RoleSystem:
    """角色系统 (设计 §2.2): 角色 → capabilities 推导 + 匹配 + 注入。

    - capabilities_for(agent): ① agent.capabilities 显式; ② role 关键词命中
      (\"backend\" in \"backend engineer\") → ROLES 能力; ③ skills 兜底推导
      (skill 命中某角色 skills → 收集该角色 capabilities, 去重); 再无 → []。
    - role_matches(required_role, agent): agent.role 与 required 相等/互为子串
      (关键词匹配), 或 required 在 agent capabilities 中; required 空 → True。
    - enrich_agent(agent): 返回新 dict (原字段全保留, 不修改入参) + capabilities。
    """

    # ------------------------------------------------------------ 推导

    @staticmethod
    def capabilities_for(agent: dict[str, Any]) -> list[str]:
        """agent → capabilities 推导 (显式优先 → role → skills 兜底 → 空)。"""
        agent = agent or {}
        explicit = agent.get("capabilities")
        if isinstance(explicit, list) and explicit:
            return [str(cap) for cap in explicit]
        role = str(agent.get("role") or "").lower()
        for role_id, spec in ROLES.items():
            if role_id in role:
                return list(spec["capabilities"])
        skills = [str(s).lower() for s in (agent.get("skills") or [])]
        derived: list[str] = []
        for skill in skills:
            for spec in ROLES.values():
                if skill in [s.lower() for s in spec["skills"]]:
                    for cap in spec["capabilities"]:
                        if cap not in derived:
                            derived.append(cap)
        return derived

    # ------------------------------------------------------------ 匹配

    @staticmethod
    def role_matches(required_role: str, agent: dict[str, Any]) -> bool:
        """required_role 是否与 agent 匹配 (role 相等/子串 或 capabilities 含所需)。

        required_role 空/None → True (无要求放行); agent 缺 role → False。
        """
        agent = agent or {}
        required = str(required_role or "").strip().lower()
        if not required:
            return True
        role = str(agent.get("role") or "").lower()
        # 规范化: 空格/下划线/连字符等价 ("product manager" == "product_manager")
        norm = lambda s: str(s).replace("_", " ").replace("-", " ").strip()
        role_n, req_n = norm(role), norm(required)
        if role and (role_n == req_n or req_n in role_n or role_n in req_n):
            return True
        # capabilities 子串匹配 (显式 capabilities 如 "backend_api" 含 "backend")
        caps = RoleSystem.capabilities_for(agent)
        return any(required in str(cap).lower() for cap in caps)

    # ------------------------------------------------------------ 注入

    @staticmethod
    def enrich_agent(agent: dict[str, Any]) -> dict[str, Any]:
        """agent 副本 + capabilities (不修改原 dict, 原字段全保留)。"""
        enriched = dict(agent or {})
        enriched["capabilities"] = RoleSystem.capabilities_for(agent or {})
        return enriched
