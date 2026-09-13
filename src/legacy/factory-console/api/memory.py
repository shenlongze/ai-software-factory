"""factory-console/api/memory.py — S10-067 Memory Learning API 路由函数。

纯函数路由 (无 Web 依赖, 同 product_intelligence.py 模式 — 未来 FastAPI
薄层做 HTTP 绑定):

- memory_search:  POST /api/memory/search   {query, project?, type?} → [ExperienceRecord]
- memory_learn:   POST /api/memory/learn    {workspace?} → LearningResult (触发学习)
- memory_stats:   GET  /api/memory/stats    {workspace?} → 经验统计
- memory_agent:   GET  /api/memory/agent/{agent_id} {workspace?} → AgentProfile
- memory_export:  POST /api/memory/export   {workspace?} → 全量经验导出

错误语义 (失败安全铁律): 输入非法 (type 不在 TYPES / agent_id 为空) /
引擎异常 → {"ok": False, "error": str} — 绝不裸抛。

设计: docs/sprint10/S10-067-memory-learning-design.md §7
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..memory.experience import TYPES, ExperienceRecord
from ..memory.experience_store import (
    DEFAULT_WORKSPACE,
    ExperienceStore,
    experience_store_file,
)
from ..memory.extraction import ExperienceExtractor
from ..memory.learning_engine import LearningEngine, PatternLearner
from ..memory.retrieval import ExperienceRetriever

__all__ = [
    "MemoryAgentRequest",
    "MemoryExportRequest",
    "MemoryLearnRequest",
    "MemoryResponse",
    "MemorySearchRequest",
    "memory_agent",
    "memory_export",
    "memory_learn",
    "memory_search",
    "memory_stats",
]


# ---------------------------------------------------------------- Schemas

class MemorySearchRequest(BaseModel):
    """POST /api/memory/search 请求体: query + 可选 project/type 过滤。"""

    query: str = ""
    project: Optional[str] = None
    type: Optional[str] = None


class MemoryLearnRequest(BaseModel):
    """POST /api/memory/learn 请求体: workspace (缺省 → ~/.factory)。"""

    workspace: Optional[str] = None


class MemoryAgentRequest(BaseModel):
    """GET /api/memory/agent/{agent_id} 请求体: agent_id + workspace。"""

    agent_id: str = ""
    workspace: Optional[str] = None


class MemoryExportRequest(BaseModel):
    """POST /api/memory/export 请求体: workspace (缺省 → ~/.factory)。"""

    workspace: Optional[str] = None


class MemoryResponse(BaseModel):
    """统一响应包装: ok + data (成功) / error (失败) — HTTP 层可映射。"""

    ok: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None


# ---------------------------------------------------------------- 内部

def _to_response(data: Any, error: Optional[str] = None) -> dict[str, Any]:
    """响应模型 → dict (Pydantic v2 model_dump — HTTP 层直接序列化)。"""
    return MemoryResponse(ok=error is None, data=data, error=error).model_dump()


def _workspace(workspace: Any = None) -> Path:
    """workspace → Path (None/空 → 默认工厂根 ~/.factory)。"""
    return Path(workspace) if workspace else DEFAULT_WORKSPACE


def _store(workspace: Any = None) -> ExperienceStore:
    """workspace 经验库 (workspace/memory/experience_store.json)。"""
    return ExperienceStore(experience_store_file(_workspace(workspace)))


def _all_records(workspace: Any = None) -> list[ExperienceRecord]:
    """全量经验视图: 提取 (可提取数据源) + 存储 (去重, 存储覆盖)。

    export/agent 端点口径: 永远反映 workspace 当前全部经验。
    """
    merged: dict[str, ExperienceRecord] = {}
    for r in ExperienceExtractor.extract_all(_workspace(workspace)):
        merged[r.id] = r
    for r in _store(workspace).records():
        merged[r.id] = r
    return list(merged.values())


# ---------------------------------------------------------------- 5 端点

def memory_search(
    query: str = "",
    project: Optional[str] = None,
    type: Optional[str] = None,
    workspace: Any = None,
) -> dict[str, Any]:
    """POST /api/memory/search — 经验检索 (G5)。

    {query, project?, type?} → {ok, data: [ExperienceRecord.to_dict()], error}。
    type 非法 (不在 TYPES) → {"ok": False, "error": ...} (schema 校验)。
    """
    try:
        if type is not None and str(type) not in TYPES:
            raise ValueError(f"未知经验类型: {type!r} (合法: {', '.join(TYPES)})")
        # S10-072 P0-A: 统一检索入口 (经 RetrievalOrchestrator)
        from ..retrieval.unified import retrieve_experience
        hits, _stats = retrieve_experience(
            str(query or ""), store=_store(workspace),
            top_k=20, project=str(project) if project else None,
            record_type=str(type) if type else None)
        return _to_response([r.to_dict() for r in hits])
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律: 异常 → 明确错误
        return _to_response(None, f"经验检索失败: {exc}")


def memory_learn(workspace: Any = None) -> dict[str, Any]:
    """POST /api/memory/learn — 触发学习循环 (提取 → 存储 → 模式/画像 → 审计)。

    {workspace?} → {ok, data: LearningResult.to_dict(), error}。
    """
    try:
        result = LearningEngine(workspace=_workspace(workspace)).run(
            _workspace(workspace)
        )
        return _to_response(result.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"经验学习失败: {exc}")


def memory_stats(workspace: Any = None) -> dict[str, Any]:
    """GET /api/memory/stats — 经验统计 (按类型/成功/Agent)。

    {workspace?} → {ok, data: {total, by_type, by_success, by_agent, file}}。
    """
    try:
        return _to_response(_store(workspace).stats())
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"经验统计失败: {exc}")


def memory_agent(agent_id: str = "", workspace: Any = None) -> dict[str, Any]:
    """GET /api/memory/agent/{agent_id} — Agent 能力画像 (G6)。

    {agent_id, workspace?} → {ok, data: AgentProfile.to_dict(), error}。
    agent_id 为空 → 校验错误; 无该 Agent 经验 → 明确错误 (不静默)。
    """
    try:
        if not str(agent_id or "").strip():
            raise ValueError("agent_id 不能为空")
        records = _all_records(workspace)
        profiles = PatternLearner().learn_agent(records)
        for profile in profiles:
            if profile.agent_id == str(agent_id).strip():
                return _to_response(profile.to_dict())
        raise ValueError(f"未找到 Agent {agent_id!r} 的经验画像 (共 {len(profiles)} 个画像)")
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"Agent 画像查询失败: {exc}")


def memory_export(workspace: Any = None) -> dict[str, Any]:
    """POST /api/memory/export — 全量经验导出 (提取 + 存储, 去重)。

    {workspace?} → {ok, data: [ExperienceRecord.to_dict()], error}。
    """
    try:
        records = _all_records(workspace)
        return _to_response([r.to_dict() for r in records])
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"经验导出失败: {exc}")
