"""factory-console/session/agents.py — Agent Workforce Intelligence (S10-055 Task 001-003)。

AgentRegistry 2.0 + AgentMatcher + AgentMetrics:
- AgentRegistry — agents.json 读取 (失败安全 → 默认注册表) + Registry 2.0 扩展字段
  (supported_tasks / cost_profile 缺省推导: role→tasks, 无则默认)
- AgentMatcher  — task → best agent: skill 匹配 (必备技能命中率) × 历史成功率
  (metrics) × 成本归一化。注册表驱动 — 决策基于 skills 集合匹配 + 真实执行数据,
  无硬编码关键词最终决策 (关键词仅用于 task.type/required_skills 推导)。
- AgentMetrics  — execution_records → agent_metrics.json 绩效聚合
  (total_tasks/success_count/failed_count/avg_cost/avg_duration/success_rate/by_task_type)

设计: docs/sprint10/S10-055-workforce-design.md §2-§3
边界:
- 只读/聚合数据, 不执行业务; 失败安全 (缺失/损坏 → 默认值, 永不抛)
- 纯标准库 (json/pathlib/re), 零新依赖; 不 import actions/pipeline (避免循环依赖)
- 数据源复用 agents.json + execution_records.json (不造新数据源)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from .audit import DEFAULT_RECORDS_FILE, load_records

#: 默认 Agent 注册表文件 (~/.factory/agents/agents.json — 与既有数据空间同口径)
DEFAULT_AGENTS_FILE = Path.home() / ".factory" / "agents" / "agents.json"

#: 默认绩效文件 (~/.factory/exec/agent_metrics.json — 与 execution_records 同空间)
DEFAULT_METRICS_FILE = Path.home() / ".factory" / "exec" / "agent_metrics.json"

#: 缺省成本 (cost_profile.avg_cost 缺省推导值 — 成本归一化基准)
DEFAULT_AVG_COST = 1000.0

#: 中性成功率 (Agent 无历史记录时的成功率因子 — 不偏向未知 Agent)
NEUTRAL_SUCCESS_RATE = 0.5

#: 默认注册表 (Registry 2.0 兜底 — agents.json 缺失/损坏时使用)。
#: role/skills 口径同设计 §1 现状: backend-1 (Backend Engineer: python/api/database) /
#: flutter-dev (Frontend Engineer: flutter/react/ui) / tester-1 (QA Engineer: test/qa)。
#: S10-058: DEFAULT_AGENTS 保持 3 Agent 基线 (既有测试锁定常量); frontend-agent
#: 经 FRONTEND_AGENT/FULLSTACK_AGENTS 注册 (load_fullstack 默认兜底含它)。
DEFAULT_AGENTS: dict[str, dict[str, Any]] = {
    "backend-1": {
        "id": "backend-1",
        "name": "backend-1",
        "role": "Backend Engineer",
        "description": "后端开发: Python/API/数据库",
        "skills": ["python", "api", "database"],
        "supported_tasks": ["backend_api", "database_schema", "test"],
        "cost_profile": {"avg_cost": 1000, "cost_unit": "tokens"},
        "status": "available",
        "current_task": None,
    },
    "flutter-dev": {
        "id": "flutter-dev",
        "name": "Flutter Dev",
        "role": "Frontend Engineer",
        "description": "前端开发: Flutter/React/UI",
        "skills": ["flutter", "dart", "ui", "frontend"],
        "supported_tasks": ["frontend_page", "ui_interaction"],
        "cost_profile": {"avg_cost": 900, "cost_unit": "tokens"},
        "status": "available",
        "current_task": None,
    },
    "tester-1": {
        "id": "tester-1",
        "name": "tester-1",
        "role": "QA Engineer",
        "description": "质量保障: 测试/QA",
        "skills": ["test", "qa"],
        "supported_tasks": ["test_suite", "test"],
        "cost_profile": {"avg_cost": 500, "cost_unit": "tokens"},
        "status": "available",
        "current_task": None,
    },
}

#: Frontend Agent 规格 (S10-058 设计 §2): 前端主执行者 — UI/组件/前端生产。
#: role=Frontend Engineer, skills=[frontend, flutter, react, typescript, ui],
#: capabilities=[ui_architecture, component_design, frontend_implementation,
#: frontend_testing], supported_tasks=[frontend_page, ui_interaction, component, screen]。
#: required_role=\"frontend\" → RoleSystem.role_matches 命中 (role 含 \"frontend\")。
FRONTEND_AGENT: dict[str, Any] = {
    "id": "frontend-agent",
    "name": "frontend-agent",
    "role": "Frontend Engineer",
    "description": "前端开发: Flutter/React/TypeScript/UI 组件与页面生产",
    "skills": ["frontend", "flutter", "react", "typescript", "ui"],
    "supported_tasks": ["frontend_page", "ui_interaction", "component", "screen"],
    "capabilities": [
        "ui_architecture",
        "component_design",
        "frontend_implementation",
        "frontend_testing",
    ],
    "cost_profile": {"avg_cost": 950, "cost_unit": "tokens"},
    "status": "available",
    "current_task": None,
}

#: Full Stack 注册表 (S10-058): 3 Agent 基线 + frontend-agent。
#: load_fullstack 默认兜底 (agents.json 缺失/损坏) 与显式 agents.json 缺 frontend-agent
#: 时的合并源 — Full Stack Team 前端任务匹配的注册面。
#: S10-058: 完整 7 角色团队注册 (pm/architect/frontend/qa/reviewer + 基线)。
FULLSTACK_AGENTS: dict[str, dict[str, Any]] = {
    **DEFAULT_AGENTS,
    "frontend-agent": dict(FRONTEND_AGENT),
    "pm-agent": {
        "id": "pm-agent", "name": "PM Agent", "role": "Product Manager",
        "description": "产品经理: 需求/PRD/确认",
        "skills": ["pm", "analysis", "requirement"],
        "supported_tasks": ["product_planning", "requirement_analysis", "prd_writing"],
        "status": "AVAILABLE", "current_task": None,
    },
    "architect-agent": {
        "id": "architect-agent", "name": "Architect Agent", "role": "Architect",
        "description": "架构师: 系统设计/技术选型",
        "skills": ["architecture", "design", "system"],
        "supported_tasks": ["system_design", "architecture_decision"],
        "status": "AVAILABLE", "current_task": None,
    },
    "qa-agent": {
        "id": "qa-agent", "name": "QA Agent", "role": "QA Engineer",
        "description": "测试: pytest/验证",
        "skills": ["test", "qa", "pytest"],
        "supported_tasks": ["test_suite", "test"],
        "status": "AVAILABLE", "current_task": None,
    },
    "reviewer-agent": {
        "id": "reviewer-agent", "name": "Reviewer Agent", "role": "Reviewer",
        "description": "评审: 代码审查/质量检查",
        "skills": ["review", "quality", "code_review"],
        "supported_tasks": ["code_review", "quality_gate"],
        "status": "AVAILABLE", "current_task": None,
    },
}

#: role 关键词 → supported_tasks 缺省推导 (role→tasks, 设计 §3)
ROLE_TASK_DEFAULTS: dict[str, tuple[str, ...]] = {
    "backend": ("backend_api", "database_schema", "test"),
    "frontend": ("frontend_page", "ui_interaction"),
    "qa": ("test_suite", "test"),
    "tester": ("test_suite", "test"),
    "test": ("test_suite", "test"),
    "developer": ("backend_api", "frontend_page"),
}

#: skills 关键词 → supported_tasks 推导 (无 role 匹配时的技能兜底)
SKILL_TASK_DEFAULTS: dict[str, tuple[str, ...]] = {
    "frontend": ("frontend_page", "ui_interaction"),
    "flutter": ("frontend_page", "ui_interaction"),
    "dart": ("frontend_page", "ui_interaction"),
    "ui": ("frontend_page", "ui_interaction"),
    "backend": ("backend_api", "database_schema", "test"),
    "python": ("backend_api", "database_schema", "test"),
    "test": ("test_suite", "test"),
    "qa": ("test_suite", "test"),
}

#: 任务类型 → 必备技能 (task.type 推导 — 仅推导 required_skills, 非最终决策)
TASK_TYPE_SKILLS: dict[str, tuple[str, ...]] = {
    "frontend": ("flutter", "dart", "ui", "frontend"),
    "ui": ("flutter", "dart", "ui", "frontend"),
    "flutter": ("flutter", "dart", "ui", "frontend"),
    "backend": ("python", "api", "database"),
    "api": ("python", "api", "database"),
    "database": ("python", "api", "database"),
    "db": ("python", "api", "database"),
    "test": ("test", "qa"),
    "qa": ("test", "qa"),
    "tester": ("test", "qa"),
}

#: 任务名/目标文本 → 任务类型 (关键词仅作 task.type 推导 — 同 select_agent 口径)
_FRONTEND_HINTS: tuple[str, ...] = ("前端", "flutter", "ui", "界面", "交互")
_TEST_HINTS: tuple[str, ...] = ("测试", "test", "用例", "qa")
_QA_HINTS: tuple[str, ...] = _TEST_HINTS


def _derive_task_type(text: str) -> str:
    """任务名/目标文本 → 任务类型 (frontend/test/backend; 未命中 → backend 默认)。

    关键词只用于 task.type 推导 — AgentMatcher 最终决策仍由 skills 集合匹配驱动。
    """
    lowered = str(text or "").lower()
    if any(hint in lowered for hint in _FRONTEND_HINTS):
        return "frontend"
    if any(hint in lowered for hint in _TEST_HINTS):
        return "test"
    return "backend"


def _parse_cost(value: Any) -> float:
    """执行记录 cost 字段 → float (缺失/非数字 → 0.0, 失败安全)。

    cost 可能是 "0.0012" 或摘要 "0.5 · 320 tokens" — 取第一个数字 token。
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):  # noqa: BLE001 — 失败安全
            return 0.0
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if not match:
        return 0.0
    try:
        return float(match.group())
    except (TypeError, ValueError):  # noqa: BLE001 — 失败安全
        return 0.0


class AgentRegistry:
    """Agent Registry 2.0 (设计 §3): agents.json 读取 + 扩展字段推导 + 查询。

    load(agents_file) → dict: 读 agents.json (缺失/损坏/空 → 默认注册表, 失败安全);
    每个 Agent 补全 Registry 2.0 扩展字段:
    - supported_tasks: 缺省推导 (role→tasks; 无 → skills→tasks; 再无 → 后端默认)
    - cost_profile:   缺省 {avg_cost: 1000, cost_unit: "tokens"}
    兼容旧式扁平格式 (无扩展字段) 与 Registry 2.0 格式。
    """

    DEFAULT_FILE = DEFAULT_AGENTS_FILE

    @classmethod
    def load(cls, agents_file: Optional[Path] = None) -> dict[str, dict[str, Any]]:
        """读 agents.json → 规范化注册表 dict; 缺失/损坏/空 → 默认注册表 (失败安全)。"""
        path = Path(agents_file) if agents_file is not None else cls.DEFAULT_FILE
        data: Any = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 默认注册表
            data = None
        return cls._normalize(data)

    @classmethod
    def load_fullstack(cls, agents_file: Optional[Path] = None) -> dict[str, dict[str, Any]]:
        """Full Stack 注册表 (S10-058): agents.json 读取 + frontend-agent 兜底。

        - agents.json 缺失/损坏/空 → FULLSTACK_AGENTS 默认兜底 (含 frontend-agent);
        - 有效 agents.json 缺 frontend-agent → 合并 FRONTEND_AGENT 规格 (团队前端匹配
          注册面完整 — 真实 agents.json 未注册时 frontend-agent 仍可用);
        - 有效 agents.json 已含 frontend-agent → 以文件为准 (规范化)。
        """
        path = Path(agents_file) if agents_file is not None else cls.DEFAULT_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → fullstack 默认
            data = None
        if not isinstance(data, dict) or not data:
            return {aid: dict(agent) for aid, agent in FULLSTACK_AGENTS.items()}
        result = cls._normalize(data)
        if "frontend-agent" not in result:
            result["frontend-agent"] = cls._normalize(
                {"frontend-agent": dict(FRONTEND_AGENT)}
            )["frontend-agent"]
        return result

    @classmethod
    def _normalize(cls, data: Any) -> dict[str, dict[str, Any]]:
        """任意结构 → {id: agent} (扩展字段缺省推导; 非 dict/空 → 默认注册表)。"""
        if not isinstance(data, dict) or not data:
            return {aid: dict(agent) for aid, agent in DEFAULT_AGENTS.items()}
        result: dict[str, dict[str, Any]] = {}
        for aid, agent in data.items():
            if not isinstance(agent, dict):
                agent = {"id": str(aid)}
            raw = agent
            skills = raw.get("skills") or []
            normalized: dict[str, Any] = {
                "id": str(aid),
                "name": str(raw.get("name") or aid),
                "role": str(raw.get("role") or "Developer"),
                "description": str(raw.get("description") or ""),
                "status": str(raw.get("status") or "available"),
                "current_task": raw.get("current_task"),
                "skills": (
                    [str(s) for s in skills] if isinstance(skills, list) else []
                ),
            }
            # Registry 2.0 扩展: supported_tasks / cost_profile 缺省推导
            if raw.get("supported_tasks"):
                st = raw["supported_tasks"]
                normalized["supported_tasks"] = (
                    [str(s) for s in st] if isinstance(st, list) else [str(st)]
                )
            else:
                normalized["supported_tasks"] = cls.derive_supported_tasks(normalized)
            # S10-058: capabilities 显式透传 (frontend-agent 规格 —
            # RoleSystem.capabilities_for 显式优先; 无 → 仍由 role/skills 推导)
            if raw.get("capabilities"):
                caps = raw["capabilities"]
                normalized["capabilities"] = (
                    [str(c) for c in caps] if isinstance(caps, list) else [str(caps)]
                )
            if raw.get("cost_profile"):
                normalized["cost_profile"] = dict(raw["cost_profile"])
            else:
                normalized["cost_profile"] = cls.derive_cost_profile(normalized)
            result[str(aid)] = normalized
        return result

    @classmethod
    def derive_supported_tasks(cls, agent: dict[str, Any]) -> list[str]:
        """supported_tasks 缺省推导: 具体 role→tasks; 无 → skills→tasks;
        泛化 role (developer) → 通用任务; 再无 → 后端默认。

        顺序保证: flutter-dev (role=developer + skills flutter/dart) → 前端任务,
        而非泛化 developer 任务 (具体技能优先于泛化 role)。
        """
        role = str(agent.get("role") or "").lower()
        for keyword in ("backend", "frontend", "qa", "tester", "test"):
            if keyword in role:
                return list(ROLE_TASK_DEFAULTS[keyword])
        skills = [str(s).lower() for s in (agent.get("skills") or [])]
        for skill, tasks in SKILL_TASK_DEFAULTS.items():
            if skill in skills:
                return list(tasks)
        if "developer" in role or "engineer" in role:
            return list(ROLE_TASK_DEFAULTS["developer"])
        return list(ROLE_TASK_DEFAULTS["backend"])

    @classmethod
    def derive_cost_profile(cls, agent: dict[str, Any]) -> dict[str, Any]:
        """cost_profile 缺省推导 (无 → 默认 avg_cost, 同设计 §3)。"""
        return {"avg_cost": DEFAULT_AVG_COST, "cost_unit": "tokens"}

    @classmethod
    def get(
        cls, agent_id: str, agents_file: Optional[Path] = None
    ) -> Optional[dict[str, Any]]:
        """按 id 取 Agent; 未注册 → None。"""
        return cls.load(agents_file).get(str(agent_id))

    @classmethod
    def list(cls, agents_file: Optional[Path] = None) -> list[dict[str, Any]]:
        """全部 Agent, 按 id 排序 (list 稳定性)。"""
        registry = cls.load(agents_file)
        return [registry[aid] for aid in sorted(registry)]

    @classmethod
    def all_roles(cls, agents_file: Optional[Path] = None) -> list[str]:
        """全部唯一 role (按首现顺序 — 注册表遍历序), 去重。"""
        roles: list[str] = []
        for agent in cls.load(agents_file).values():
            role = str(agent.get("role") or "Developer")
            if role not in roles:
                roles.append(role)
        return roles


class AgentMatcher:
    """AgentMatcher (设计 §2): task → best agent 综合评分。

    match(task, registry, metrics) -> {agent, score, reason}:
      评分 = skill 匹配 (必备技能命中率) × 成功率因子 (0.5+0.5×历史成功率)
      × 成本归一化 (1/avg_cost, 最便宜 Agent 成本因子 = 1.0)。
    无硬编码关键词最终决策 — 决策由 Registry skills 集合匹配 + 真实执行数据驱动;
    关键词仅用于 task.type → required_skills 推导 (derive_required_skills)。
    reason 可解释: "skill match 92% (python/api/database), 成功率 95%"。

    registry/metrics 缺省 → 惰性加载 (AgentRegistry.load / AgentMetrics.load_from_records),
    失败安全 (缺失 → 默认注册表 / 空 metrics, 不抛)。
    """

    def __init__(
        self,
        registry: Optional[dict[str, Any]] = None,
        metrics: Optional[dict[str, Any]] = None,
    ) -> None:
        self._registry = registry
        self._metrics = metrics
        self._registry_loaded = registry is not None
        self._metrics_loaded = metrics is not None

    # ------------------------------------------------------------ 数据源 (惰性)

    def _registry_data(self) -> dict[str, Any]:
        if not self._registry_loaded:
            self._registry = AgentRegistry.load()
            self._registry_loaded = True
        return self._registry or {}

    def _metrics_data(self) -> dict[str, Any]:
        if not self._metrics_loaded:
            self._metrics = AgentMetrics.load_from_records()
            self._metrics_loaded = True
        return self._metrics or {}

    # ------------------------------------------------------------ 技能推导

    @staticmethod
    def derive_required_skills(task: Optional[dict[str, Any]]) -> list[str]:
        """任务 → 必备技能列表 (决策输入推导, 非决策本身)。

        优先级: ① task.required_skills 显式; ② task.type 映射; ③ task.agent_type;
        ④ 任务名/目标文本关键词 (仅推导, 同 select_agent 口径)。
        """
        task = task or {}
        explicit = task.get("required_skills")
        if isinstance(explicit, list) and explicit:
            return [str(s) for s in explicit]
        ttype = str(task.get("type") or "").strip().lower()
        if ttype in TASK_TYPE_SKILLS:
            return list(TASK_TYPE_SKILLS[ttype])
        agent_type = str(task.get("agent_type") or "").strip().lower()
        if agent_type in ("frontend", "ui", "flutter"):
            return list(TASK_TYPE_SKILLS["frontend"])
        if agent_type in ("qa", "test", "tester"):
            return list(TASK_TYPE_SKILLS["test"])
        if agent_type in ("backend", "api", "database", "db"):
            return list(TASK_TYPE_SKILLS["backend"])
        name = str(task.get("name") or task.get("objective") or "")
        return list(TASK_TYPE_SKILLS[_derive_task_type(name)])

    # ------------------------------------------------------------ 评分

    @staticmethod
    def _success_rate(metrics: dict[str, Any], agent_id: str) -> float:
        """Agent 历史成功率; 无记录 → 中性 0.5 (不偏向未知 Agent)。"""
        entry = metrics.get(agent_id) if isinstance(metrics, dict) else None
        sr = (entry or {}).get("success_rate") if isinstance(entry, dict) else None
        if sr is None:
            return NEUTRAL_SUCCESS_RATE
        try:
            return float(sr)
        except (TypeError, ValueError):  # noqa: BLE001 — 失败安全
            return NEUTRAL_SUCCESS_RATE

    @staticmethod
    def _success_factor(sr: float) -> float:
        """成功率因子: 0.5 + 0.5×sr ∈ [0.5, 1.0]。

        设计 §2 评分 = skill 匹配 × 历史成功率 × 成本归一化; 成功率因子做
        [0.5, 1.0] 映射 — 保证技能匹配主导决策 (成功率 0 的 Agent 不因乘零
        而输给零技能匹配者), 同时高成功率仍可提升得分。
        """
        return 0.5 + 0.5 * sr

    @staticmethod
    def _cost_factor(agent: dict[str, Any], base_cost: float) -> float:
        """成本归一化 (1/avg_cost; 最便宜 Agent → 1.0; 上限 1.0)。"""
        try:
            avg = float((agent.get("cost_profile") or {}).get("avg_cost") or DEFAULT_AVG_COST)
        except (TypeError, ValueError):  # noqa: BLE001 — 失败安全
            avg = DEFAULT_AVG_COST
        if avg <= 0:
            return 1.0
        return min(1.0, base_cost / avg)

    @staticmethod
    def _build_reason(
        agent_id: str,
        agent: dict[str, Any],
        required: list[str],
        matched: list[str],
        metrics: dict[str, Any],
    ) -> str:
        """可解释 reason: "skill match 92% (python/api/database), 成功率 95%"。

        无必备技能 → skill match 100% (列全部技能); 零命中 → 0% (无匹配)。
        """
        if required:
            pct = round(len(matched) * 100 / len(required))
        else:
            pct = 100
        skills_str = ", ".join(matched) if matched else "无匹配"
        sr = AgentMatcher._success_rate(metrics, agent_id)
        return f"skill match {pct}% ({skills_str}), 成功率 {round(sr * 100)}%"

    def match(
        self,
        task: dict[str, Any],
        registry: Optional[dict[str, Any]] = None,
        metrics: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """task → {agent, score, reason} (综合评分决策, 注册表驱动)。"""
        reg = self._registry_data() if registry is None else (registry or {})
        met = self._metrics_data() if metrics is None else (metrics or {})
        required = self.derive_required_skills(task)
        candidates: list[dict[str, Any]] = []
        for aid, agent in reg.items():
            if not isinstance(agent, dict):
                continue
            skills = [str(s) for s in (agent.get("skills") or [])]
            if required:
                matched = [s for s in required if s in skills]
                skill_factor = len(matched) / len(required)
            else:
                matched = list(skills)
                skill_factor = 1.0
            sr = self._success_rate(met, aid)
            candidates.append(
                {
                    "agent_id": aid,
                    "agent": agent,
                    "matched": matched,
                    "skill_factor": skill_factor,
                    "sr": sr,
                }
            )
        if not candidates:
            return {"agent": None, "score": 0.0, "reason": "无可用 Agent (注册表为空)"}
        base_cost = min(
            self._cost_base(reg), default=DEFAULT_AVG_COST
        )
        scored: list[dict[str, Any]] = []
        for cand in candidates:
            cost_factor = self._cost_factor(cand["agent"], base_cost)
            score = (
                cand["skill_factor"]
                * self._success_factor(cand["sr"])
                * cost_factor
            )
            scored.append({**cand, "score": score, "cost_factor": cost_factor})
        scored.sort(
            key=lambda c: (
                -c["score"],
                -c["sr"],
                c["cost_factor"],
                c["agent_id"],
            )
        )
        best = scored[0]
        return {
            "agent": best["agent_id"],
            "score": round(best["score"], 4),
            "reason": self._build_reason(
                best["agent_id"],
                best["agent"],
                required,
                best["matched"],
                met,
            ),
        }

    @staticmethod
    def _cost_base(registry: dict[str, Any]) -> list[float]:
        """全部候选 Agent 的 avg_cost 列表 (成本归一化基准用)。"""
        costs: list[float] = []
        for agent in registry.values():
            if not isinstance(agent, dict):
                continue
            try:
                avg = float(
                    (agent.get("cost_profile") or {}).get("avg_cost") or DEFAULT_AVG_COST
                )
            except (TypeError, ValueError):  # noqa: BLE001 — 失败安全
                avg = DEFAULT_AVG_COST
            costs.append(avg)
        return costs

    def reason_for(
        self,
        agent_id: str,
        task: dict[str, Any],
        registry: Optional[dict[str, Any]] = None,
        metrics: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """为指定 Agent 计算 reason (计划生成时 agent 已由 select_agent 决定)。

        不改变决策 — 只产出该 Agent 在该任务上的可解释理由; Agent 未注册 →
        {agent, score: 0.0, reason: None} (失败安全)。
        """
        reg = self._registry_data() if registry is None else (registry or {})
        met = self._metrics_data() if metrics is None else (metrics or {})
        agent = reg.get(str(agent_id))
        if agent is None:
            return {"agent": str(agent_id), "score": 0.0, "reason": None}
        required = self.derive_required_skills(task)
        skills = [str(s) for s in (agent.get("skills") or [])]
        if required:
            matched = [s for s in required if s in skills]
            skill_factor = len(matched) / len(required)
        else:
            matched = list(skills)
            skill_factor = 1.0
        sr = self._success_rate(met, str(agent_id))
        cost_factor = self._cost_factor(agent, self._cost_factor_base(reg))
        score = skill_factor * self._success_factor(sr) * cost_factor
        return {
            "agent": str(agent_id),
            "score": round(score, 4),
            "reason": self._build_reason(
                str(agent_id), agent, required, matched, met
            ),
        }

    @staticmethod
    def _cost_factor_base(registry: dict[str, Any]) -> float:
        """候选最低成本 (成本归一化基准); 空 → 默认成本。"""
        costs = AgentMatcher._cost_base(registry)
        return min(costs) if costs else DEFAULT_AVG_COST


class AgentMetrics:
    """Agent 绩效聚合 (设计 §3): execution_records → agent_metrics.json。

    compute(records) -> {agent_id: {agent, total_tasks, success_count, failed_count,
    avg_cost, avg_duration, success_rate, by_task_type}}。
    - avg_cost: 记录 cost 均值 (数字解析, 失败安全 → 0.0)
    - avg_duration: 记录无 duration 字段 → 0.0 (失败安全)
    - success_rate: success_count / total_tasks
    - by_task_type: {task_type: {total, success}} (task_type 取记录显式字段,
      无 → 从 task 文本推导; 无 → "other")
    数据源复用 audit.load_records (缺失/损坏 → [], 失败安全)。
    """

    DEFAULT_FILE = DEFAULT_METRICS_FILE

    #: 成功结果别名 (result 字段取值 — 兼容 success/ok/passed/completed)
    _SUCCESS_RESULTS: frozenset[str] = frozenset(
        {"success", "ok", "passed", "completed", "done"}
    )

    @classmethod
    def compute(cls, records: list[dict]) -> dict[str, dict[str, Any]]:
        """执行记录 → 按 Agent 聚合绩效 (空记录/非 dict 记录 → 空聚合)。"""
        per: dict[str, dict[str, Any]] = {}
        for record in records or []:
            if not isinstance(record, dict):
                continue
            agent = str(record.get("agent") or "unknown")
            result = str(record.get("result") or "").lower()
            success = result in cls._SUCCESS_RESULTS
            task_type = str(record.get("task_type") or "") or _derive_task_type(
                str(record.get("task") or "")
            )
            cost = _parse_cost(record.get("cost"))
            entry = per.setdefault(
                agent,
                {
                    "agent": agent,
                    "total_tasks": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "avg_cost": 0.0,
                    "avg_duration": 0.0,
                    "success_rate": 0.0,
                    "by_task_type": {},
                },
            )
            entry["total_tasks"] += 1
            if success:
                entry["success_count"] += 1
            else:
                entry["failed_count"] += 1
            entry["_costs"] = entry.get("_costs", [])
            if cost:
                entry["_costs"].append(cost)
            by_type = entry["by_task_type"].setdefault(
                task_type, {"total": 0, "success": 0}
            )
            by_type["total"] += 1
            if success:
                by_type["success"] += 1
        # 收尾: 均值/成功率 + 清理内部字段
        for entry in per.values():
            costs = entry.pop("_costs", [])
            entry["avg_cost"] = round(sum(costs) / len(costs), 6) if costs else 0.0
            total = entry["total_tasks"]
            entry["success_rate"] = (
                round(entry["success_count"] / total, 4) if total else 0.0
            )
        return per

    @classmethod
    def load_from_records(
        cls, records_file: Optional[Path] = None
    ) -> dict[str, dict[str, Any]]:
        """execution_records.json → 聚合绩效 (缺失/损坏 → {}, 失败安全)。"""
        records_file = (
            Path(records_file) if records_file is not None else DEFAULT_RECORDS_FILE
        )
        return cls.compute(load_records(records_file))

    @classmethod
    def save(
        cls, metrics_file: Optional[Path], metrics: dict[str, Any]
    ) -> Path:
        """落盘 agent_metrics.json (父目录自动创建; 中文可读, 确定性无时间戳)。"""
        path = Path(metrics_file) if metrics_file is not None else cls.DEFAULT_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, metrics_file: Optional[Path] = None) -> dict[str, dict[str, Any]]:
        """读回 agent_metrics.json; 缺失/损坏/非 dict → {} (失败安全)。"""
        path = Path(metrics_file) if metrics_file is not None else cls.DEFAULT_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001 — 失败安全
            return {}


def workforce_snapshot(
    agents_file: Optional[Path] = None,
    records_file: Optional[Path] = None,
    metrics_file: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Workforce Dashboard 行 (Task 005): Registry + Metrics 合并。

    agents_file → AgentRegistry.load (缺省 → 默认注册表);
    metrics: metrics_file 显式 → AgentMetrics.load; 否则 records_file →
    AgentMetrics.load_from_records; 都缺省 → 真实 execution_records 聚合。
    每行: {id, name, role, status, success_rate, total_tasks, avg_cost}。
    """
    registry = AgentRegistry.load(agents_file)
    if metrics_file is not None and Path(metrics_file).is_file():
        metrics = AgentMetrics.load(metrics_file)
    elif records_file is not None and Path(records_file).is_file():
        metrics = AgentMetrics.load_from_records(records_file)
    else:
        metrics = AgentMetrics.load_from_records()
    rows: list[dict[str, Any]] = []
    for aid in sorted(registry):
        agent = registry[aid]
        entry = metrics.get(aid) or {}
        rows.append(
            {
                "id": aid,
                "name": str(agent.get("name") or aid),
                "role": str(agent.get("role") or ""),
                "status": str(agent.get("status") or "available"),
                "success_rate": entry.get("success_rate"),
                "total_tasks": entry.get("total_tasks", 0),
                "avg_cost": entry.get("avg_cost", 0.0),
            }
        )
    return rows
