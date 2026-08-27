"""factory-console/external_executor/gateway.py — 执行器网关编排 (S10-127 网关 G1+G4).

把外部委派串成状态机: 选执行器 → 建任务注册 → 执行 → 记录 → 验证 → 重试 → 回写。
复用: registry(适配器) / router.route(选执行器) / executor.run / record_invocation /
      auto_verify / verify_invocation / task_registry(控制面) / sandbox(命令校验) /
      handoff(Spine closure) + project_memory(经验)。

契约返回 {ok, task_id, result_id, verify, retry_count, output, error}。
失败安全: 任一步异常 → 任务 failed + 诚实错误, 不抛。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def _pick_executor(data_dir, agent_id: str, task: str, project_id: str) -> tuple[str, str]:
    """选执行器 → (executor_id, host_agent)。显式 agent_id 优先, 否则路由。"""
    from .registry import build_registry
    from .router import route

    adapters = build_registry(data_dir).list()
    # 导入的 agents (host_agent 映射)
    agents = []
    try:
        import json as _json

        d = _json.loads((Path(data_dir) / "agents" / "agents.json").read_text(encoding="utf-8"))
        ag = d.get("agents") if isinstance(d, dict) else None
        if isinstance(ag, dict):
            agents = [v for v in ag.values() if isinstance(v, dict)]
    except Exception:  # noqa: BLE001
        agents = []
    rr = route(str(task), adapters, agents, data_dir, explicit_agent=agent_id)
    pick = str(rr.get("pick") or "").strip()
    if not pick:
        return "", ""
    if "." in pick:
        executor_id, host_agent = pick.split(".", 1)
    else:
        executor_id, host_agent = pick, ""
    return executor_id, host_agent


def _verify_output(data_dir: str, result_id: str, project_dir: str, work_type: str,
                   verify_hook: dict[str, Any] | None) -> dict[str, Any]:
    """执行后验证 → {method, result, score, reason} (失败安全 unknown)。"""
    try:
        from .executor import auto_verify, verify_invocation

        v = auto_verify(project_dir, work_type, verify_hook=verify_hook)
        if result_id:
            try:
                verify_invocation(data_dir, result_id, method=str(v.get("method") or ""),
                                  result=str(v.get("result") or "unknown"),
                                  score=v.get("score"), reason=str(v.get("reason") or "")[:500])
            except Exception:  # noqa: BLE001
                pass
        return v
    except Exception:  # noqa: BLE001 — 验证失败 → unknown (诚实)
        return {"method": "", "result": "unknown", "score": None, "reason": "验证执行异常"}


def _write_back(data_dir: str, project_id: str, task_id: str, title: str,
                ok: bool, verify: dict[str, Any], output: str) -> None:
    """回填 (G4): Spine closure + 项目记忆 (只对 done 且项目存在)。"""
    if not ok or not project_id:
        return
    try:
        from factory_console.session.handoff import ProjectSpine

        sp = ProjectSpine.load(data_dir, project_id)
        sp.add_closure(task_id=task_id, title=title[:120],
                       summary=f"外部执行完成 · 验证 {verify.get('result')}: {str(output or '')[:200]}",
                       source="verified_state")
        sp.save(data_dir)
    except Exception:  # noqa: BLE001 — 回填失败不阻断
        pass
    try:
        from factory_console.session.project_memory import MemoryStore

        mem = MemoryStore.load(data_dir, project_id)
        mem.add(f"任务[{title[:80]}] 外部执行完成, 验证 {verify.get('result') or 'unknown'}",
                source="gateway", kind="learning", authority="verified_state")
        mem.save(data_dir)
    except Exception:  # noqa: BLE001
        pass


def gateway_execute(
    task: str,
    *,
    data_dir: str | Path,
    project_id: str = "",
    agent_id: str = "",
    skills: list[str] | None = None,
    max_retry: int = 1,
    verify_hook: dict[str, Any] | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """网关编排: 选执行器 → 注册 → 执行 → 验证 → 重试 → 回写。

    返回 {ok, task_id, result_id, verify, retry_count, output, error, executor}。
    """
    data_dir = str(data_dir or "")
    if not data_dir:
        return {"ok": False, "error": "数据目录不可用", "task_id": ""}
    task = str(task or "").strip()
    if not task:
        return {"ok": False, "error": "任务为空", "task_id": ""}
    from .registry import build_registry
    from .task_registry import ExternalTaskRegistry
    from . import executor as _exec

    # 1) 选执行器
    executor_id, host_agent = _pick_executor(data_dir, agent_id, task, project_id)
    if not executor_id:
        return {"ok": False, "error": "无可用外部执行器 (设置→外部AI 配置)", "task_id": ""}
    adapters = build_registry(data_dir).list()
    adapter = next((a for a in adapters if a.id == executor_id), None)
    if adapter is None:
        return {"ok": False, "error": f"执行器未注册: {executor_id}", "task_id": ""}

    # 2) 任务注册 (控制面)
    reg = ExternalTaskRegistry.load(data_dir)
    tid = reg.create(task=task, owner=executor_id, project_id=project_id,
                     verify_plan=str((verify_hook or {}).get("name") or "auto"))
    reg.audit(tid, "picked", f"executor={executor_id} host={host_agent}")

    # 3) 权限检查 (网关 G3): 工作目录白名单 + 命令黑名单
    _perm = adapter.permissions
    project_dir = ""
    if project_id:
        try:
            from factory_console.session.code_scan import locate_repo

            project_dir = str(locate_repo(data_dir, project_id) or "")
        except Exception:  # noqa: BLE001
            project_dir = ""
    if _perm.allowed_project_dirs:
        _ok_dir = any(str(project_dir).startswith(str(d)) for d in _perm.allowed_project_dirs)
        if not _ok_dir:
            reg.update(tid, status="failed", finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
            reg.audit(tid, "denied", f"project_dir 不在白名单: {project_dir}")
            return {"ok": False, "error": f"权限拒绝: 项目目录不在执行器白名单 (网关 G3)",
                    "task_id": tid, "result_id": "", "verify": {"result": "denied"},
                    "retry_count": 0, "executor": executor_id, "output": ""}
    prompt = task
    if skills:
        prompt = f"技能: {', '.join(skills)}\n任务: {task}"
    output, error, exit_code, result_id = "", "", -1, ""
    verify = {"method": "", "result": "unknown", "score": None, "reason": ""}
    retry_count = 0
    for attempt in range(max_retry + 1):
        if attempt > 0:
            reg.audit(tid, "retry", f"第 {attempt} 次重试")
            retry_count += 1
        _t0 = time.monotonic()
        _dcmd = next((c for c in _perm.disallowed_commands if c and c in prompt), None)
        if _dcmd:
            reg.audit(tid, "denied", f"命令黑名单命中: {_dcmd}")
            r = {"exit_code": -1, "output": "", "error": f"权限拒绝: 任务含执行器黑名单片段 ({_dcmd})", "command": ""}
        else:
            try:
                r = _exec.run(adapter, prompt, project_dir, agent=host_agent,
                              skills=skills or None, timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                r = {"exit_code": -1, "output": "", "error": f"执行异常: {exc}", "command": ""}
        duration_ms = int((time.monotonic() - _t0) * 1000)
        exit_code = int(r.get("exit_code", -1))
        output = str(r.get("output") or "").strip()
        error = str(r.get("error") or "").strip()
        try:
            _mode = "borrowed-shell" if str(getattr(adapter.invocation, "project_dir", "") or "") == "cwd" else "blackbox"
            rec = _exec.record_invocation(
                data_dir, executor_id=executor_id, mode=_mode,
                host_agent=host_agent, prompt=prompt[:200], project_dir=project_dir,
                exit_code=exit_code, output=output, error=error,
                command=str(r.get("command") or ""), duration_ms=duration_ms,
            )
            result_id = str(rec.get("result_id") or "")
        except Exception:  # noqa: BLE001 — 记录失败不阻断
            pass
        # 验证
        verify = _verify_output(data_dir, result_id, project_dir,
                                str(getattr(adapter, "work_type", "") or ""), verify_hook)
        passed = exit_code == 0 and verify.get("result") != "fail"
        if passed:
            break
        if attempt < max_retry:
            continue
    # 4) 回写控制面
    final_ok = exit_code == 0 and verify.get("result") != "fail"
    reg.update(tid, status="done" if final_ok else "failed",
               finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
               result_id=result_id, retry_count=retry_count, verify=verify)
    reg.audit(tid, "finished", f"ok={final_ok} verify={verify.get('result')} retries={retry_count}")
    # 5) G4 回填 (Spine closure + 记忆)
    _write_back(data_dir, project_id, tid, task, final_ok, verify, output)
    return {
        "ok": final_ok, "task_id": tid, "result_id": result_id,
        "verify": verify, "retry_count": retry_count, "executor": executor_id,
        "output": (output or "")[:2000], "error": error[:1000],
    }
