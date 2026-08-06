"""tests/console/console_helpers.py — Human Console Layer 测试 helper (唯一名)。

工厂函数用固定 id/时间戳, 保证确定性断言 (created_at 默认时间戳的 round-trip
相等断言必失败 — 断言逐字段或只断派生值, 不断默认时间戳相等)。本目录自洽
(不跨目录依赖 helper), basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

from types import SimpleNamespace

from agents.models import Agent, AgentStatus
from intelligence.models import (
    Decision,
    DecisionStatus,
    Evidence,
    ExperienceDomain,
    ExperienceRecord,
    ExperienceResult,
    Recommendation,
)
from product.models import ApprovalRequest, Artifact, ProductIdea
from providers.models import ProviderDefinition, ProviderStatus
from providers.usage import ProviderUsage
from workspace.models import ProjectDefinition

#: 固定时间戳 (TS_FORMAT, 6 位微秒 — parse_timestamp 可解析; 字符串排序 == 时间排序)
TS_OLD = "2026-01-01T00:00:00.000000Z"
TS_MID = "2026-01-15T00:00:00.000000Z"
TS_LATE = "2026-03-02T00:00:00.000000Z"


def make_evidence(
    source_id: str = "evt-1",
    source_type: str = "event",
    description: str = "execution succeeded",
    confidence: float = 0.9,
    timestamp: str = TS_OLD,
) -> Evidence:
    return Evidence(
        source_type=source_type,
        source_id=source_id,
        description=description,
        confidence=confidence,
        timestamp=timestamp,
    )


def make_project(
    project_id: str = "demo",
    name: str = "Demo Project",
    status: str = "active",
    tech_stack: list[str] | None = None,
    repository: str = "https://example.com/demo.git",
) -> ProjectDefinition:
    return ProjectDefinition(
        id=project_id,
        name=name,
        description="demo project",
        language="python",
        repository=repository,
        tech_stack=tech_stack or ["python", "flask"],
        status=status,
    )


class FakeWorkspace:
    """极简 workspace 桩: 只实现 ConsoleService 用到的 list_projects()。

    失败安全测试: list_projects 抛异常 → Console 返回空 (不拖垮 Dashboard)。
    """

    def __init__(self, projects: list[ProjectDefinition] | None = None, *, broken: bool = False):
        self._projects = projects or []
        self._broken = broken

    def list_projects(self) -> list[ProjectDefinition]:
        if self._broken:
            raise RuntimeError("workspace corrupt (simulated)")
        return list(self._projects)


def make_idea(
    idea_id: str = "idea-1",
    project_id: str | None = "demo",
    title: str = "Build Demo",
) -> ProductIdea:
    context = {}
    if project_id is not None:
        context["project"] = project_id
    return ProductIdea(id=idea_id, title=title, description="demo idea", context=context)


def make_artifact(
    artifact_id: str = "art-1",
    artifact_type: str = "prd",
    confidence: float = 0.8,
    idea_id: str | None = None,
    evidence: list[str] | None = None,
) -> Artifact:
    content: dict = {}
    if idea_id is not None:
        content["idea_id"] = idea_id
    if evidence:
        content["evidence"] = evidence
    return Artifact(id=artifact_id, type=artifact_type, content=content, confidence=confidence)


def make_request(
    request_id: str = "req-1",
    artifact_id: str = "art-1",
    gate: str = "prd",
    status: str = "pending",
    idea_id: str | None = "idea-1",
    by: str = "human",
    comment: str | None = None,
) -> ApprovalRequest:
    return ApprovalRequest(
        id=request_id,
        artifact_id=artifact_id,
        gate=gate,
        status=status,
        idea_id=idea_id,
        by=by,
        comment=comment,
        artifact_version=1,
    )


def make_decision(
    decision_id: str = "dec-1",
    subject_id: str = "task-1",
    created_at: str = TS_OLD,
    status: str = "recommended",
    **kw,
) -> Decision:
    base = dict(
        decision_type="provider_selection",
        subject_id=subject_id,
        description="choose provider for task",
        options=[
            {"id": "a", "name": "Option A", "score": 0.9,
             "factors": {"capability": 0.9, "cost": 0.8},
             "reasoning": ["capability match"], "evidence": []},
            {"id": "b", "name": "Option B", "score": 0.4,
             "factors": {"capability": 0.4, "cost": 0.9},
             "reasoning": ["cheap"], "evidence": []},
        ],
        recommendation="a",
        confidence=0.8,
        risk=0.2,
        risk_level="medium",
        requires_approval=True,
        evidence=[make_evidence()],
        created_at=created_at,
        status=DecisionStatus(status) if isinstance(status, str) else status,
    )
    base.update(kw)
    return Decision(id=decision_id, **base)


def make_recommendation(
    rec_id: str = "rec-1",
    target_type: str = "provider",
    target_id: str = "hermes",
    created_at: str = TS_OLD,
    **kw,
) -> Recommendation:
    base = dict(
        target_type=target_type,
        target_id=target_id,
        score=0.92,
        reasoning=["capability match", "low cost"],
        evidence=[make_evidence()],
        confidence=0.7,
        risk=0.1,
        created_at=created_at,
    )
    base.update(kw)
    return Recommendation(id=rec_id, **base)


def make_experience(
    exp_id: str = "exp-1",
    domain: str = "provider",
    subject_id: str = "hermes",
    result: str = "success",
    score: float = 0.95,
    confidence: float = 0.9,
    created_at: str = TS_OLD,
    freshness: float = 1.0,
    **kw,
) -> ExperienceRecord:
    base = dict(
        domain=ExperienceDomain(domain) if isinstance(domain, str) else domain,
        subject_id=subject_id,
        result=ExperienceResult(result) if isinstance(result, str) else result,
        score=score,
        confidence=confidence,
        created_at=created_at,
        freshness=freshness,
        capability=["code"],
    )
    base.update(kw)
    return ExperienceRecord(id=exp_id, **base)


def make_agent(
    agent_id: str = "agent-1",
    name: str = "Builder",
    role: str = "backend",
    status: str = "AVAILABLE",
    skills: list[str] | None = None,
    current_task: str | None = None,
) -> Agent:
    return Agent(
        id=agent_id,
        name=name,
        role=role,
        status=AgentStatus.parse(status),
        skills=skills or ["python"],
        current_task=current_task,
    )


def make_provider(
    provider_id: str = "hermes",
    name: str = "Hermes Agent",
    status: str = "ACTIVE",
    capabilities: list[str] | None = None,
    models: list[str] | None = None,
) -> ProviderDefinition:
    return ProviderDefinition(
        id=provider_id,
        name=name,
        type="agent",
        description=f"{provider_id} provider",
        capabilities=capabilities or ["chat", "generation"],
        models=models or ["hermes-default"],
        version="1.0.0",
        status=ProviderStatus.parse(status),
        config_schema={},
        metadata={},
    )


def make_usage(
    provider_id: str = "hermes",
    *,
    estimated_cost: float = 0.01,
    success: bool = True,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> ProviderUsage:
    return ProviderUsage(
        provider_id=provider_id,
        estimated_cost=estimated_cost,
        success=success,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def snapshot_files(root) -> dict[str, str]:
    """目录树文件内容快照 (零写断言: Console 操作前后内容必须逐字节一致)。"""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
    return out


def snapshot_domain_files(root) -> dict[str, str]:
    """域数据空间文件快照 (排除 events.db — CLI 审计事件是唯一允许的写)。"""
    return {
        name: content
        for name, content in snapshot_files(root).items()
        if name != "events.db"
    }


# ------------------------------------------------------------------ 事件断言


def event_types_of(store) -> list[str]:
    """事件类型列表 (断言审计链)。"""
    return [e.type.value for e in store.query()]


def payload_of(store, event_type: str) -> dict:
    """最后一条指定类型事件的 payload。"""
    events = [e for e in store.query() if e.type.value == event_type]
    assert events, f"no event of type {event_type!r}"
    return events[-1].payload


def event_sequence(store) -> list[str]:
    """全部事件类型序列 (按 seq 升序, 断言链序)。"""
    return [e.type.value for e in store.query()]
