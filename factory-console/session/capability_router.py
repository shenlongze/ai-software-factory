"""factory-console/session/capability_router.py — K-1 B-4 统一能力路由层 (S10-116)。

设计: docs/sprint10/S10-116-k1-capability-router-plan.md §1.1-§1.4 (CTO 权威)。

统一"任务能力需求 → 资源"匹配底座, 覆盖 agent / skill / mcp 三类资源:

```
CapabilityResource{id, type, capabilities[], status, load, priority, version}
CapabilityRequest{objective, capabilities}
CapabilityRouter.route(request) -> Optional[RouteDecision{resource_id, reason}]
```

确定性契约 (纯规则, 不调 LLM):
- 候选 = capabilities 交集非空 (请求能力 ⊆ 资源能力标签)
- 排序: (priority desc, quality desc [None 中性], version desc, load asc, id asc) — 稳定可复现
- 取首个 status=ready; 无交集 / 全部 disabled → None
- reason 可解释: 命中 capabilities + 排序依据 (为什么选它)

B-1/B-2/B-3 资源域辅助 (同模块, 供 exec/console 双向使用, 零第三方依赖):
- derive_capabilities(objective): objective 关键词规则表 → 能力需求 (确定性)
- route_skills(objective, skills): skills.json 外部注册 + 内置表 → 路由选中;
  无匹配 → (全量, 兜底) — 向后兼容全注入
- build_agent_resources(agents): AgentRegistry dict → CapabilityResource
  (capabilities = skills + supported_tasks 推导, 只读)
- route_mcp(objective, tools): objective 工具关键词 → MCP tool 选择
  (MockMCPClient 可, 诚实标注)

边界:
- status/load 只挂字段 (K-2 执行质量分 / K-3 负载均衡不做实现)
- 纯标准库 (dataclasses/json/pathlib/re), 不 import session 业务模块 (防循环)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

#: 资源类型白名单 (CapabilityResource.type 校验)
RESOURCE_TYPES = ("agent", "skill", "mcp")

#: status 取值白名单 (ready=可用 / degraded=降级 / disabled=禁用; K-2 挂点)
RESOURCE_STATUSES = ("ready", "degraded", "disabled")

#: 默认版本 (资源未声明 version 时使用)
DEFAULT_VERSION = "1.0.0"

#: objective 关键词 → 能力需求 (确定性规则表; 顺序即推导顺序, 命中即追加)。
#: 关键词一律小写匹配 (objective 先 lower); 中文原样 (已是小写语义)。
#: 规则表是"能力路由"的确定性输入 — 不调 LLM, 同一 objective 永远同需求。
OBJECTIVE_CAPABILITY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("frontend_ui", ("前端", "flutter", "ui", "界面", "frontend", "react", "页面", "组件")),
    ("database", ("数据库", "database", "schema", "sql", "数据表", "表结构")),
    ("api", ("api", "接口", "后端", "backend", "服务端", "server")),
    ("test", ("测试", "test", "qa", "验证", "用例", "quality")),
    ("code_generation", ("代码", "code", "实现", "implement", "功能", "开发", "编写", "写")),
    ("documentation", ("文档", "documentation", "readme", "注释", "说明")),
    ("data_analysis", ("分析", "统计", "数据", "data", "报表")),
    ("design", ("设计", "design", "架构", "architecture")),
)

#: 内置 skill 能力表 (skill id → capabilities; 与 expert_factory.EXPERT_SKILLS
#: 能力口径同源, 独立维护避免循环依赖 — exec/console 双向可加载)。
#: 覆盖系统 Skill (exec.skill SYSTEM_AGENT_SKILLS) 与常见职业 skill。
BUILTIN_SKILL_CAPABILITIES: dict[str, list[str]] = {
    "backend_development": ["api", "database", "code_generation", "backend"],
    "backend.development": ["api", "database", "code_generation", "backend"],
    "software_testing": ["test", "qa"],
    "testing": ["test", "qa"],
    "flutter_development": ["frontend_ui", "frontend"],
    "flutter.development": ["frontend_ui", "frontend"],
    "frontend_development": ["frontend_ui", "frontend"],
    "product_strategy": ["product_positioning", "value_proposition", "business_model", "design"],
    "market_research": ["market_size", "user_trend", "opportunity_window", "data_analysis"],
    "competitor_analysis": ["competitor_mapping", "differentiation", "substitution", "data_analysis"],
    "ux_design": ["user_flow", "information_architecture", "wireframe", "frontend_ui"],
    "system_architecture": ["tech_selection", "system_design", "data_modeling", "risk_analysis", "design"],
    "backend_engineering": ["backend_api", "database_schema", "service_design", "api", "database"],
    "quality_assurance": ["test_plan", "test_case", "quality_gate", "test", "qa"],
    "prd_writing": ["prd_structure", "user_story", "acceptance_criteria", "documentation"],
    "python_development": ["api", "code_generation"],
}

#: skill id 关键词 → 能力 (未命中内置表时的确定性兜底推导 — 外部注册 skill 无
#: capabilities 字段时按 id 关键词推导, 保证路由仍可用)。
_SKILL_ID_KEYWORD_CAPABILITIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("frontend_ui", ("flutter", "react", "frontend", "ui", "vue", "dart", "typescript")),
    ("database", ("database", "sql", "schema", "db", "mongo", "postgres")),
    ("api", ("api", "backend", "server", "service")),
    ("test", ("test", "qa", "testing", "quality", "verify")),
    ("code_generation", ("python", "code", "development", "engineering", "implementation", "programming")),
    ("documentation", ("doc", "writing", "prd", "spec")),
)

#: MCP tool 关键词 → 能力 (objective 工具关键词 → MCP 路由; Mock 诚实标注)。
MCP_TOOL_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mcp.github", ("github", "issue", "pull request", "pr ", "仓库", "代码评审")),
    ("mcp.slack", ("slack", "消息通知", "群聊")),
    ("mcp.echo", ("echo", "mcp tool", "工具调用")),
    ("mcp.generic", ("工具", "tool", "mcp")),
)


@dataclass
class CapabilityResource:
    """能力资源 (agent | skill | mcp): id/type/capabilities + 路由挂点字段。

    status: ready | degraded | disabled (K-2 挂点, 本战役只挂字段不实现优选)
    load:   负载值 (K-3 负载均衡挂点, 本战役只挂字段; 排序 load asc 已落位)
    priority: 高=优先 (确定性排序第一键)
    quality_score: 资源质量分 (0-1; None=中性 — 排序 tiebreaker 在 priority 之后、
    version 之前; K-1 无分 fixture → 行为零变化)
    version:  版本 (确定性排序第三键, 语义化比较)
    """

    id: str
    type: str
    capabilities: list[str] = field(default_factory=list)
    status: str = "ready"
    load: float = 0.0
    priority: int = 0
    quality_score: Optional[float] = None
    version: str = DEFAULT_VERSION

    def __post_init__(self) -> None:
        """id/type/status/load 校验 (响亮, 不静默接受脏资源)。"""
        if not str(self.id or "").strip():
            raise ValueError("CapabilityResource.id 必填 (资源标识不能为空)")
        if self.type not in RESOURCE_TYPES:
            raise ValueError(
                f"CapabilityResource.type 非法: {self.type!r} "
                f"(允许: {', '.join(RESOURCE_TYPES)})"
            )
        if self.status not in RESOURCE_STATUSES:
            raise ValueError(
                f"CapabilityResource.status 非法: {self.status!r} "
                f"(允许: {', '.join(RESOURCE_STATUSES)})"
            )
        try:
            load = float(self.load)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"CapabilityResource.load 非法: {self.load!r}") from exc
        if load < 0:
            raise ValueError(f"CapabilityResource.load 不能为负: {load!r}")
        self.load = load
        if self.quality_score is not None:
            try:
                qs = float(self.quality_score)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"CapabilityResource.quality_score 非法: {self.quality_score!r}"
                ) from exc
            if not (0.0 <= qs <= 1.0):
                raise ValueError(
                    f"CapabilityResource.quality_score 越界: {qs!r} (须 0-1)"
                )
            self.quality_score = qs
        self.capabilities = [str(c) for c in (self.capabilities or [])]
        if not self.version:
            self.version = DEFAULT_VERSION


@dataclass
class CapabilityRequest:
    """任务需求: objective (原始任务描述) + capabilities (能力需求交集匹配)。"""

    objective: str = ""
    capabilities: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.objective = str(self.objective or "")
        self.capabilities = [str(c) for c in (self.capabilities or [])]


@dataclass
class RouteDecision:
    """路由决策: resource_id + 可解释 reason (为什么选它, 不黑盒)。"""

    resource_id: str
    reason: str


def _version_key(version: Any) -> tuple[int, ...]:
    """版本 → 排序键 (语义化: 数字段逐段比较; 非数字段降级为 0)。

    "1.2.0" → (1, 2, 0); "1.10" > "1.9" (数字比较, 非字典序)。
    """
    text = str(version or "")
    parts: list[int] = []
    for seg in re.split(r"[.\-+]", text):
        m = re.match(r"^(\d+)", seg.strip())
        parts.append(int(m.group(1)) if m else 0)
    return tuple(parts)


def _capability_key(resource: CapabilityResource) -> tuple:
    """路由排序键: (priority desc, quality desc [None 中性], version desc,
    load asc, id asc) — 确定性; quality_score=None 与 0 区分 (None 中性不压分)。"""
    # None 中性: 排序键 has_quality=0 (不参与); 有分者 quality desc (高分优先)
    quality = float(resource.quality_score) if resource.quality_score is not None else 0.0
    has_quality = 1 if resource.quality_score is not None else 0
    return (
        -int(resource.priority),
        -has_quality,  # 有分者优先于无分 (tiebreaker 语义; None 中性不压分)
        -quality,
        tuple(-v for v in _version_key(resource.version)),
        float(resource.load),
        str(resource.id),
    )


class CapabilityRouter:
    """统一能力路由器: capabilities 交集 → 排序 → 首个 ready (确定性)。

    route(request) -> Optional[RouteDecision]:
    - 候选 = capabilities 交集非空的资源 (请求 capability 命中资源标签)
    - 排序: (priority desc, quality desc [None 中性], version desc, load asc, id asc)
    - 首个 status=ready → RouteDecision (reason 含命中集合 + 排序依据)
    - 无交集 / 全部 disabled → None (调用方按兜底策略处理)
    """

    def __init__(self, resources: Optional[Iterable[CapabilityResource]] = None) -> None:
        self._resources: list[CapabilityResource] = list(resources or [])

    @property
    def resources(self) -> list[CapabilityResource]:
        """只读资源列表 (路由依据; 排序稳定 — 构造后不变)。"""
        return list(self._resources)

    def route(self, request: CapabilityRequest) -> Optional[RouteDecision]:
        """确定性路由 (纯规则, 不调 LLM)。"""
        wanted = [str(c) for c in (request.capabilities or [])]
        if not wanted:
            return None
        wanted_set = set(wanted)
        candidates: list[CapabilityResource] = []
        for resource in self._resources:
            if wanted_set & set(resource.capabilities):
                candidates.append(resource)
        if not candidates:
            return None
        candidates.sort(key=_capability_key)
        # 排序依据 (可解释): 前三名描述 + 全量候选 id 序
        ranked_desc = ", ".join(
            f"{r.type} '{r.id}' (priority={r.priority}, "
            f"quality={r.quality_score if r.quality_score is not None else '-'}, "
            f"version={r.version}, load={r.load:g})"
            for r in candidates[:3]
        )
        all_ids = ", ".join(f"'{r.id}'" for r in candidates)
        for resource in candidates:
            if resource.status != "ready":
                continue
            matched = sorted(wanted_set & set(resource.capabilities))
            reason = (
                f"{resource.type} '{resource.id}' 命中 capabilities "
                f"{{{', '.join(matched)}}} (共 {len(candidates)} 候选: {all_ids}; "
                f"排序按 priority desc → quality desc (None 中性) → "
                f"version desc → load asc → id: {ranked_desc})"
            )
            return RouteDecision(resource_id=resource.id, reason=reason)
        return None  # 全部候选 disabled → 无可用资源

    # ------------------------------------------------------------------ 资源构建

    @staticmethod
    def from_dict(resource: dict[str, Any]) -> CapabilityResource:
        """dict → CapabilityResource (只取白名单键; 缺省字段兜底)。"""
        quality_raw = resource.get("quality_score")
        quality_score: Optional[float] = None
        if quality_raw is not None:
            try:
                quality_score = float(quality_raw)
            except (TypeError, ValueError):  # noqa: BLE001 — 损坏 → None 中性 (失败安全)
                quality_score = None
        return CapabilityResource(
            id=str(resource.get("id") or ""),
            type=str(resource.get("type") or ""),
            capabilities=[str(c) for c in (resource.get("capabilities") or [])],
            status=str(resource.get("status") or "ready"),
            load=float(resource.get("load") or 0.0),
            priority=int(resource.get("priority") or 0),
            quality_score=quality_score,
            version=str(resource.get("version") or DEFAULT_VERSION),
        )


# ================================================================== objective → 能力需求 (确定性)


def derive_capabilities(objective: str) -> list[str]:
    """objective 关键词规则表 → 能力需求列表 (确定性; 保序去重)。

    命中规则即追加能力标签; 同一 objective 永远同输出 (可复现, 可测试)。
    """
    text = str(objective or "").lower()
    caps: list[str] = []
    for capability, keywords in OBJECTIVE_CAPABILITY_RULES:
        if any(keyword in text for keyword in keywords):
            if capability not in caps:
                caps.append(capability)
    return caps


# ================================================================== B-1 skill 路由


def _load_external_skills(skills_file: Optional[Path]) -> dict[str, dict[str, Any]]:
    """skills.json 外部注册表 → {id: skill dict} (失败安全 → {}; 只读不写)。"""
    path = Path(skills_file) if skills_file is not None else None
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 损坏 → 空 (失败安全)
        return {}
    registry = data.get("skills") if isinstance(data, dict) and isinstance(
        data.get("skills"), dict
    ) else data
    if not isinstance(registry, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for sid, entry in registry.items():
        if isinstance(entry, dict):
            result[str(sid)] = entry
        else:
            result[str(sid)] = {"id": str(sid)}
    return result


def _infer_skill_capabilities(skill_id: str) -> list[str]:
    """skill id 关键词 → 能力 (确定性兜底推导; 未命中 → [] — 不臆造)。"""
    text = str(skill_id or "").lower()
    caps: list[str] = []
    for capability, keywords in _SKILL_ID_KEYWORD_CAPABILITIES:
        if any(keyword in text for keyword in keywords):
            if capability not in caps:
                caps.append(capability)
    return caps


def build_skill_resources(
    skill_ids: Iterable[str],
    *,
    skills_file: Optional[Path] = None,
) -> list[CapabilityResource]:
    """skill ids → CapabilityResource 列表 (skills.json 外部注册 + 内置表, 只读)。

    能力来源优先级: 外部注册 capabilities → 内置表 → id 关键词推导 (确定性)。
    status: 外部 enabled=false → disabled; priority/version 外部可覆盖 (缺省 0/1.0.0)。
    """
    external = _load_external_skills(skills_file)
    resources: list[CapabilityResource] = []
    for sid in skill_ids:
        sid = str(sid or "").strip()
        if not sid:
            continue
        info = external.get(sid) or {}
        caps = [str(c) for c in (info.get("capabilities") or [])]
        if not caps:
            caps = list(BUILTIN_SKILL_CAPABILITIES.get(sid) or [])
        if not caps:
            caps = _infer_skill_capabilities(sid)
        resources.append(
            CapabilityResource(
                id=sid,
                type="skill",
                capabilities=caps,
                status=(
                    "disabled"
                    if info.get("enabled") is False
                    else "ready"
                ),
                load=float(info.get("load") or 0.0),
                priority=int(info.get("priority") or 0),
                version=str(info.get("version") or DEFAULT_VERSION),
            )
        )
    return resources


def route_skills(
    objective: str,
    skills: Iterable[str],
    *,
    skills_file: Optional[Path] = None,
) -> tuple[list[str], str]:
    """objective + skills → 路由选中 (B-1)。

    返回 (选中 skill 列表, reason):
    - 有 capability 匹配 → ([选中 skill], 可解释 reason)
    - 无匹配 → (全量 skills, 兜底 reason) — 向后兼容全注入 (现状)

    确定性: 同 objective + 同 skills → 同结果 (规则表 + 排序, 不调 LLM)。
    """
    skills = [str(s) for s in (skills or []) if str(s).strip()]
    if not skills:
        return [], ""
    request = CapabilityRequest(
        objective=objective, capabilities=derive_capabilities(objective)
    )
    decision = CapabilityRouter(build_skill_resources(skills, skills_file=skills_file)).route(
        request
    )
    if decision is None:
        return list(skills), (
            "objective 与 skills capabilities 无交集 (或全 disabled) — "
            "按 B-1 设计兜底全注入 (向后兼容)"
        )
    return [decision.resource_id], decision.reason


# ================================================================== B-2 agent 资源化


def build_agent_resources(agents: dict[str, dict[str, Any]]) -> list[CapabilityResource]:
    """AgentRegistry dict → CapabilityResource (capabilities = skills +
    supported_tasks 推导, 只读; 显式 capabilities 透传并合并)。

    status: agent.status ∈ {disabled, offline} → disabled (K-2 挂点字段落位)。
    priority/version/load: agents.json 显式字段透传, 缺省 0 / 1.0.0 / 0.0。
    """
    resources: list[CapabilityResource] = []
    for aid in sorted(agents or {}):
        agent = agents[aid] or {}
        caps: list[str] = []
        for key in ("capabilities", "skills", "supported_tasks"):
            for item in agent.get(key) or []:
                val = str(item).strip()
                if val and val not in caps:
                    caps.append(val)
        status = str(agent.get("status") or "").lower()
        quality_raw = agent.get("quality_score")
        quality_score: Optional[float] = None
        if quality_raw is not None:
            try:
                quality_score = float(quality_raw)
            except (TypeError, ValueError):  # noqa: BLE001 — 损坏 → None 中性
                quality_score = None
        resources.append(
            CapabilityResource(
                id=str(aid),
                type="agent",
                capabilities=caps,
                status=("disabled" if status in ("disabled", "offline") else "ready"),
                load=float(agent.get("load") or 0.0),
                priority=int(agent.get("priority") or 0),
                quality_score=quality_score,
                version=str(agent.get("version") or DEFAULT_VERSION),
            )
        )
    return resources


# ================================================================== B-3 MCP 路由


def derive_mcp_capabilities(objective: str) -> list[str]:
    """objective 工具关键词 → MCP 能力需求 (确定性; 无工具意图 → [])。"""
    text = str(objective or "").lower()
    caps: list[str] = []
    for capability, keywords in MCP_TOOL_KEYWORD_RULES:
        if any(keyword in text for keyword in keywords):
            if capability not in caps:
                caps.append(capability)
    return caps


def build_mcp_resources(
    tools: Iterable[dict[str, Any]],
) -> list[CapabilityResource]:
    """MCP Tool 摘要 (service.mcp_tools 形状: {id, name, description, server})
    → CapabilityResource (type=mcp; capabilities = 工具关键词规则命中 + mcp_tool)。

    诚实标注: MockMCPClient 注册的 tool 同样参与路由 (id/name 即能力来源),
    server 字段透传进 version 无关 — 路由只按能力标签, 不冒充真实连接。
    """
    resources: list[CapabilityResource] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        tid = str(tool.get("id") or tool.get("name") or "").strip()
        if not tid:
            continue
        text = f"{tid} {tool.get('name') or ''} {tool.get('description') or ''}".lower()
        caps: list[str] = ["mcp_tool"]
        for capability, keywords in MCP_TOOL_KEYWORD_RULES:
            if any(keyword in text for keyword in keywords):
                if capability not in caps:
                    caps.append(capability)
        resources.append(
            CapabilityResource(
                id=tid,
                type="mcp",
                capabilities=caps,
                priority=int(tool.get("priority") or 0),
                version=str(tool.get("version") or DEFAULT_VERSION),
            )
        )
    return resources


def route_mcp(
    objective: str,
    tools: Iterable[dict[str, Any]],
) -> Optional[RouteDecision]:
    """objective 需工具 → 选 MCP tool (B-3; MockMCPClient 可, 诚实标注)。

    无工具意图 (objective 不含工具关键词) 或 无 MCP tools → None (不臆造)。
    """
    tools = [t for t in (tools or []) if isinstance(t, dict)]
    if not tools:
        return None
    wanted = derive_mcp_capabilities(objective)
    if not wanted:
        return None
    return CapabilityRouter(build_mcp_resources(tools)).route(
        CapabilityRequest(objective=objective, capabilities=wanted)
    )


__all__ = [
    "BUILTIN_SKILL_CAPABILITIES",
    "CapabilityRequest",
    "CapabilityResource",
    "CapabilityRouter",
    "MCP_TOOL_KEYWORD_RULES",
    "OBJECTIVE_CAPABILITY_RULES",
    "RESOURCE_STATUSES",
    "RESOURCE_TYPES",
    "RouteDecision",
    "build_agent_resources",
    "build_mcp_resources",
    "build_skill_resources",
    "derive_capabilities",
    "derive_mcp_capabilities",
    "route_mcp",
    "route_skills",
]
