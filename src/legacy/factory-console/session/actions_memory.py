"""factory-console/session/actions_memory.py — 记忆动作 (R1, v1.1.254).

从 actions.py 拆出: 记忆检索/学习/统计/分析/导出 (自包含)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .action import (
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_OK,
    ActionResult,
    ExecutionContext,
)


def _memory_params(context) -> dict:
    """取 memory action 参数 (intent.params 优先; 兼容测试 FakeContext.params)。"""
    intent = getattr(context, "intent", None)
    if intent is not None and getattr(intent, "params", None):
        return intent.params
    return getattr(context, "params", None) or {}


def _memory_workspace(context) -> Path:
    """memory action 工作区 (context.workspace 缺省 → ~/.factory)。"""
    return Path(getattr(context, "workspace", None) or DEFAULT_WORKSPACE)


def _memory_lines(records: list, header: str, limit: int = 20) -> list[str]:
    """经验记录 → 展示行 (类型/问题/结果/置信)。"""
    lines = [f"{header} ({len(records)} 条):"]
    for r in records[:limit]:
        subject = r.problem or r.task or "(无问题)"
        outcome = r.result or r.action or "-"
        lines.append(f"• [{r.type}] {subject} → {outcome} (conf {r.confidence})")
    if not records:
        lines.append("无记录。")
    return lines


def memory_search(context: ExecutionContext) -> ActionResult:
    """经验检索 (S10-067): "搜索经验/查找经验" → 关键词检索 (query/type 参数)。"""
    context.require("user")
    params = _memory_params(context)
    query = str(params.get("query") or "")
    record_type = params.get("type") or None
    try:
        from ..memory.experience_store import ExperienceStore
        from ..retrieval.unified import retrieve_experience
        ws = _memory_workspace(context)
        store = ExperienceStore.from_workspace(ws)
        # S10-072 P0-A: 统一检索入口 (经 RetrievalOrchestrator)
        # S10-073 P0-A: 强制项目 scope (fail-closed — 无 project 上下文 → 仅全局经验)
        project = str(getattr(context, "project", "") or params.get("project") or "")
        hits, _stats = retrieve_experience(
            query, store=store, top_k=20, project=project,
            record_type=str(record_type) if record_type else None)
        lines = _memory_lines(hits, f"经验检索「{query}」" if query else "全部经验")
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"经验检索失败: {exc}", error=str(exc))


def memory_learn(context: ExecutionContext) -> ActionResult:
    """触发学习 (S10-067): "学习经验/经验学习" → 提取 → 模式/Agent 画像 → 审计。"""
    context.require("user")
    try:
        from ..memory.learning_engine import LearningEngine
        from ..memory.learning_loop import refresh_agent_profiles
        ws = _memory_workspace(context)
        result = LearningEngine(workspace=ws).run(ws)
        # S10-119 M4-5: 画像落盘 (capability_router 画像分来源; 护栏内失败安全)
        refresh_agent_profiles(ws)
        lines = [
            f"学习完成: 提取 {result.extracted_count} 条经验"
            f" → {len(result.patterns)} 个模式 + {len(result.agent_profiles)} 个 Agent 画像",
        ]
        for p in result.patterns[:10]:
            lines.append(f"• 模式 {p['pattern_id']}: {p['description']} (conf {p['confidence']})")
        for a in result.agent_profiles[:10]:
            lines.append(
                f"• Agent {a['agent_id']}: {a['total_tasks']} 任务, "
                f"成功率 {a['success_rate']:.0%}"
            )
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"经验学习失败: {exc}", error=str(exc))


def memory_stats(context: ExecutionContext) -> ActionResult:
    """经验统计 (S10-067): "经验统计" → 按类型/成功/Agent 统计。"""
    context.require("user")
    try:
        from ..memory.experience_store import ExperienceStore
        ws = _memory_workspace(context)
        stats = ExperienceStore.from_workspace(ws).stats()
        lines = [f"经验统计 (共 {stats['total']} 条):"]
        by_type = stats["by_type"] or {}
        if by_type:
            lines.append("按类型: " + ", ".join(f"{k}={v}" for k, v in by_type.items()))
        else:
            lines.append("按类型: 无")
        lines.append(f"按结果: 成功 {stats['by_success']['success']}, "
                     f"失败 {stats['by_success']['failed']}")
        by_agent = stats["by_agent"] or {}
        if by_agent:
            lines.append("按Agent: " + ", ".join(f"{k}={v}" for k, v in by_agent.items()))
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"经验统计失败: {exc}", error=str(exc))


def memory_analyze_agent(context: ExecutionContext) -> ActionResult:
    """Agent 画像 (S10-067): "分析Agent/Agent成长" → 能力画像 (agent_id 参数)。"""
    context.require("user")
    params = _memory_params(context)
    agent_id = str(params.get("agent_id") or "").strip()
    try:
        from ..memory.experience_store import ExperienceStore
        from ..memory.extraction import ExperienceExtractor
        from ..memory.learning_engine import PatternLearner
        ws = _memory_workspace(context)
        records = ExperienceExtractor.extract_all(ws)
        profiles = PatternLearner().learn_agent(records)
        if not agent_id and profiles:
            agent_id = profiles[0].agent_id
        profile = next((p for p in profiles if p.agent_id == agent_id), None)
        if profile is None:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message=f"未找到 Agent {agent_id!r} 的经验画像 (共 {len(profiles)} 个画像)",
                error="agent profile not found",
            )
        lines = [
            f"Agent 画像: {profile.agent_id} ({profile.role or '角色未知'})",
            f"任务数: {profile.total_tasks} | 成功: {profile.success_count} "
            f"| 成功率: {profile.success_rate:.0%}",
        ]
        if profile.common_problems:
            lines.append("常见问题: " + "; ".join(profile.common_problems[:3]))
        if profile.best_domains:
            lines.append("最佳领域: " + ", ".join(profile.best_domains[:5]))
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"Agent 画像失败: {exc}", error=str(exc))


def memory_export(context: ExecutionContext) -> ActionResult:
    """导出经验 (S10-067): "导出经验" → 全量经验 → workspace/memory/experience_export.json。"""
    context.require("user")
    try:
        from ..memory.experience_store import ExperienceStore
        import json as _json
        ws = _memory_workspace(context)
        store = ExperienceStore.from_workspace(ws)
        export_path = store.path.parent / "experience_export.json"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(
            _json.dumps([r.to_dict() for r in store.records()],
                        ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return ActionResult(
            ok=True, status=STATUS_OK,
            message=f"已导出 {len(store.records())} 条经验 → {export_path}",
            data={"count": len(store.records()), "path": str(export_path)},
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"经验导出失败: {exc}", error=str(exc))


# ================================================================== S10-068 Debug Intelligence CLI
