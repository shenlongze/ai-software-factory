"""factory-console/session/external_tools.py — 外部能力动态工具面 (v1.1.209).

Founder 2026-08-27: 外部 codex/claude/hermes 的 agent/skill 应像内置工具一样可被会话 Agent
调用; 设计必须通用 — 新增外部 agent/执行器无需改代码, 工具面自动更新。

- external_tool_schema(data_dir): 动态生成 delegate_external 工具 schema
  (候选 = registry 已注册执行器 + agents.json 已导入 agent; 无候选 → None 不加工具)
- delegate_external(data_dir, agent_id, task, skills): 真实委派执行 (executor.run 统一契约)
  + record_invocation 落审计/监控 (EXS-*)

失败安全: registry/agents.json 缺失/坏 → 诚实错误, 不假装; 执行失败 → 返回 error 不抛。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json_map(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def imported_agents(data_dir: str | Path | None) -> list[dict[str, Any]]:
    """已导入的外部 agent (host_assets 产物: <data_dir>/agents/agents.json)。

    返回 [{id, name, role, description, skills, source, kind, prompt, host}]。"""
    if not data_dir:
        return []
    d = _load_json_map(Path(data_dir) / "agents" / "agents.json")
    ag = d.get("agents") if isinstance(d, dict) else None
    if not isinstance(ag, dict):
        return []
    out: list[dict[str, Any]] = []
    for v in ag.values():
        if isinstance(v, dict) and v.get("id"):
            out.append(v)
    return out


def _candidate_lines(data_dir: str | Path | None) -> list[str]:
    """候选行 (给工具描述, 让模型知道能选谁; 截断避免 schema 爆炸)。"""
    lines: list[str] = []
    for a in imported_agents(data_dir)[:24]:
        role = str(a.get("role") or "assistant")
        desc = str(a.get("description") or a.get("name") or "").replace("\n", " ")[:80]
        lines.append(f"- {a.get('id')} ({role}): {desc}")
    return lines


def external_tool_schema(data_dir: str | Path | None) -> dict[str, Any] | None:
    """动态生成 delegate_external 工具 schema; 无候选 → None (不加工具, 不膨胀)。"""
    lines = _candidate_lines(data_dir)
    if not lines:
        return None
    cand = "\n".join(lines)
    return {
        "type": "function",
        "function": {
            "name": "delegate_external",
            "description": (
                "委派外部 AI agent 执行专业任务 (codex/claude/hermes 等; 真实调用宿主 CLI)。"
                "适合: 架构审查/安全评估/UX 审查/竞品分析/深度代码任务 等外部专业能力。\n"
                "候选 agent (agent_id 必须从下面选):\n" + cand + "\n"
                "敏感任务/耗时任务执行前可先说明将委派给谁。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "外部 agent id (如 codex.architect)"},
                    "task": {"type": "string", "description": "给外部 agent 的任务描述 (具体/可执行)"},
                    "skills": {"type": "array", "items": {"type": "string"},
                               "description": "可选: 要附带的 skill 列表 (宿主支持时)"},
                },
                "required": ["agent_id", "task"],
            },
        },
    }


def delegate_external(
    data_dir: str | Path | None,
    agent_id: str,
    task: str,
    *,
    project_id: str = "",
    skills: list[str] | None = None,
) -> dict[str, Any]:
    """委派外部 agent 真实执行 (统一契约 {ok, output, error})。

    匹配: agent_id 前缀 → registry 执行器 (codex.architect → adapter id=codex);
    agents.json 找 host_agent 名; executor.run 真实调用 + record_invocation 落监控。"""
    agent_id = str(agent_id or "").strip()
    task = str(task or "").strip()
    if not agent_id or not task:
        return {"ok": False, "error": "需要 agent_id + task"}
    if not data_dir:
        return {"ok": False, "error": "数据目录不可用 (无法定位外部执行器)"}
    try:
        from ..external_executor.registry import build_registry
        from ..external_executor import executor as _exec

        adapters = build_registry(data_dir).list()
        prefix = agent_id.split(".")[0]
        adapter = next((a for a in adapters if str(getattr(a, "id", "")) == prefix), None)
        if adapter is None:
            return {"ok": False, "error": f"未注册外部执行器: {prefix} (去 设置→外部AI 配置)"}
        # 导入 agent 元数据 (skills 未显式给 → 用导入时带的)
        meta = next((a for a in imported_agents(data_dir) if str(a.get("id")) == agent_id), None)
        agent_skills = skills or (meta or {}).get("skills") or []
        # 任务 prompt: 用导入的 agent prompt 作系统上下文 (若有), 再拼任务
        base = str((meta or {}).get("prompt") or "").strip()
        prompt = (f"{base}\n\n" if base else "") + f"任务: {task}"
        project_dir = ""
        if project_id:
            try:
                from .code_scan import locate_repo

                project_dir = str(locate_repo(data_dir, project_id) or "")
            except Exception:  # noqa: BLE001
                project_dir = ""
        result = _exec.run(adapter, prompt, project_dir, agent=agent_id, skills=agent_skills or None)
        ok = int(result.get("exit_code", -1)) == 0
        output = str(result.get("output") or "").strip()
        error = str(result.get("error") or "").strip()
        if ok and not output:
            output = "（外部 agent 执行完成, 无 stdout 输出）"
        # 统一执行记录 (监控/路由/审计消费)
        try:
            _exec.record_invocation(
                data_dir,
                executor_id=prefix,
                mode=str(getattr(adapter.invocation, "project_dir", "cwd") or "cwd"),
                host_agent=agent_id,
                prompt=prompt[:400],
                project_dir=project_dir,
                exit_code=int(result.get("exit_code", -1)),
                output=output[:1000],
                error=error[:3000],
                command=str(result.get("command") or ""),
                duration_ms=0,
            )
        except Exception:  # noqa: BLE001 — 记录失败不阻断执行结果
            pass
        if ok:
            return {"ok": True, "output": output[:2000], "agent": agent_id}
        return {"ok": False, "error": error or f"外部 agent {agent_id} 执行失败 (exit {result.get('exit_code')})",
                "output": output[:800]}
    except Exception as exc:  # noqa: BLE001 — 任何异常 → 诚实错误
        return {"ok": False, "error": f"委派外部 agent 失败: {exc}"}
