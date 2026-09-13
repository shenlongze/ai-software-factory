"""factory-console/os_core_runtime.py — OS Execution Adapter (MU-CORE-10).

把 OS Execution Record 接入真实执行机制 (最薄 adapter; 不重写 node_runtime/production_run)。

默认 runtime = "local": 通过 subprocess 真实执行命令, 捕获 stdout/stderr/exit code,
写入 <root>/execution/outputs/{execution_id}.json 并把 runtime_ref / output_refs /
最终状态写回 OS Execution。

可插槽: executor_fn(input)->{ok, output, error, name, returncode} 供后续接入
node_runtime / external executor (本 MU 不接, 记录 UNMIGRATED)。

边界: Execution ≠ Verification ≠ Evidence ≠ Outcome (分别由各自 SSOT 记录)。
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

RUNTIMES: tuple[str, ...] = ("local",)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _output_file(root: str | Path, execution_id: str) -> Path:
    return Path(root) / "execution" / "outputs" / f"{execution_id}.json"


def _write_output(root: str | Path, execution_id: str, payload: dict[str, Any]) -> str:
    p = _output_file(root, execution_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with __import__("os").fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        __import__("os").fsync(f.fileno())
    __import__("os").replace(tmp, p)
    return f"execution/outputs/{execution_id}.json"


_RUNNING_PROCESSES: dict[str, Any] = {}
_CANCELLING: set[str] = set()


def mark_cancelling(execution_id: str) -> None:
    """标记取消中 (消除 cancel 写终态与 worker finalize 的竞态)。"""
    _CANCELLING.add(str(execution_id))


def is_cancelling(execution_id: str) -> bool:
    return str(execution_id) in _CANCELLING


def clear_cancelling(execution_id: str) -> None:
    _CANCELLING.discard(str(execution_id))

def _terminate_process(proc: Any, grace: float = 2.0) -> dict[str, Any]:
    """SIGTERM → grace → SIGKILL; 返回真实 pid/exit_code/signal。"""
    import signal as _signal

    pid = proc.pid
    used = None
    if proc.poll() is None:
        proc.terminate()                      # SIGTERM
        used = int(_signal.SIGTERM)
        try:
            proc.wait(timeout=grace)
        except Exception:  # noqa: BLE001 — grace 到期 → SIGKILL
            proc.kill()
            used = int(_signal.SIGKILL)
            try:
                proc.wait(timeout=grace)
            except Exception:  # noqa: BLE001
                pass
    return {"terminated": True, "pid": pid, "exit_code": proc.returncode, "signal": used}


def terminate_running_process(root: str | Path, execution_id: str) -> dict[str, Any]:
    """真实终止某 Execution 的 subprocess (供 cancel/timeout 使用)。"""
    proc = _RUNNING_PROCESSES.get(str(execution_id))
    if proc is None:
        return {"terminated": False, "pid": None, "exit_code": None, "signal": None,
                "reason": "no tracked process"}
    info = _terminate_process(proc)
    info["reason"] = "terminated"
    return info


def run_execution(root: str | Path, execution_id: str, *, command: str,
                  runtime: str = "local", timeout: int = 30,
                  executor_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
                  plugin_id: str = "", provider: str = "",
                  usage: dict[str, Any] | None = None,
                  pricing: dict[str, Any] | None = None) -> dict[str, Any]:
    """真实执行一次 OS Execution (queued→running→terminal) + 真实 termination + usage 回写。

    本地 runtime 使用 Popen + 进程注册表: timeout/cancel 会真实 SIGTERM→SIGKILL。
    """
    from .os_core_execution import get_execution, set_execution_status
    from .os_core_usage import record_usage

    rec = get_execution(root, execution_id)
    if rec is None:
        raise ValueError(f"Execution 不存在: {execution_id}")
    if rec["status"] != "queued":
        raise ValueError(f"Execution 非 queued 状态 ({rec['status']}) — 不可执行")
    command = str(command or "")
    if not command and executor_fn is None:
        raise ValueError("必须提供 command 或 executor_fn — 仅创建 Execution Record 不算真实执行")
    if runtime not in RUNTIMES and executor_fn is None:
        raise ValueError(f"未知 runtime: {runtime} (可选: {RUNTIMES})")

    set_execution_status(root, execution_id, "running", timeout_seconds=timeout)
    started = time.time()
    ok, stdout, stderr, returncode = False, "", "", 1
    pid: int | None = None
    sig: int | None = None
    termination = "unknown"
    runtime_ref = ""
    if executor_fn is not None:
        result = executor_fn({"execution_id": execution_id, "command": command})
        ok = bool(result.get("ok"))
        stdout = str(result.get("output") or "")
        stderr = str(result.get("error") or "")
        returncode = int(result.get("returncode", 0 if ok else 1))
        runtime_ref = f"executor_fn:{result.get('name', 'custom')}"
        termination = "success" if ok else "runtime_failure"
    else:
        proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, cwd=str(root))
        _RUNNING_PROCESSES[str(execution_id)] = proc
        pid = proc.pid
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            returncode = proc.returncode if proc.returncode is not None else 1
        except subprocess.TimeoutExpired:
            timed_out = True
            term = _terminate_process(proc)
            sig = term["signal"]
            pid = term["pid"]
            try:
                stdout, stderr = proc.communicate(timeout=2)
            except Exception:  # noqa: BLE001
                stdout, stderr = "", ""
            returncode = term["exit_code"] if term["exit_code"] is not None else 124
        finally:
            _RUNNING_PROCESSES.pop(str(execution_id), None)
        runtime_ref = "runtime:local-command"
        ok = (not timed_out) and returncode == 0
        termination = "timeout" if timed_out else ("success" if ok else "runtime_failure")
    elapsed_ms = int((time.time() - started) * 1000)
    output_ref = _write_output(root, execution_id, {
        "execution_id": execution_id, "command": command, "runtime_ref": runtime_ref,
        "returncode": returncode, "stdout": stdout, "stderr": stderr,
        "pid": pid, "signal": sig, "termination_reason": termination,
        "elapsed_ms": elapsed_ms, "at": _now_iso()})

    current = get_execution(root, execution_id) or {}
    already_cancelled = (current.get("status") == "cancelled"
                         or is_cancelling(execution_id))
    if not already_cancelled:
        if ok:
            set_execution_status(root, execution_id, "succeeded", output_refs=[output_ref],
                                 runtime_ref=runtime_ref, termination_reason="success",
                                 duration_ms=elapsed_ms, pid=pid, exit_code=returncode,
                                 signal=sig, timeout_seconds=timeout)
        else:
            set_execution_status(root, execution_id, "failed",
                                 error=(stderr or f"exit {returncode}")[:500],
                                 output_refs=[output_ref], runtime_ref=runtime_ref,
                                 termination_reason=termination, duration_ms=elapsed_ms,
                                 pid=pid, exit_code=returncode, signal=sig,
                                 timeout_seconds=timeout)
    else:
        termination = "user_cancelled"
    done = get_execution(root, execution_id)
    clear_cancelling(execution_id)
    usage_rec = record_usage(root, execution_id=execution_id, provider=provider or (done or {}).get("provider", ""),
                             plugin_id=plugin_id or (done or {}).get("plugin_id", ""),
                             node_run_id=(done or {}).get("node_run_id", ""),
                             duration_ms=elapsed_ms, status=(done or {}).get("status", ""),
                             termination_reason=termination, exit_code=returncode,
                             usage=usage, pricing=pricing)
    return {"execution": done, "ok": ok, "runtime_ref": runtime_ref, "output_ref": output_ref,
            "returncode": returncode, "stdout": stdout, "stderr": stderr,
            "pid": pid, "signal": sig, "termination_reason": termination,
            "duration_ms": elapsed_ms, "usage_id": usage_rec["usage_id"]}


# ================================================================ Runtime Integration (MU-CORE-11)

def _provider_adapter(provider: str) -> Any:
    """从 external_executor 内置模板取 adapter (codex/claude); 未注册 -> ValueError。"""
    from .external_executor.registry import BUILTIN_ADAPTERS
    from .external_executor.schema import ExternalExecutorAdapter

    spec = BUILTIN_ADAPTERS.get(str(provider))
    if not spec:
        raise ValueError(f"未知 provider: {provider} (可用: {sorted(BUILTIN_ADAPTERS)})")
    return ExternalExecutorAdapter(**spec)


def _provider_executor_fn(provider: str, prompt: str, project_dir: str,
                          timeout: int) -> Callable[[dict[str, Any]], dict[str, Any]]:
    adapter = _provider_adapter(provider)

    def _fn(_input: dict[str, Any]) -> dict[str, Any]:
        from .external_executor.executor import run as _ext_run

        res = _ext_run(adapter, prompt, project_dir or "", timeout=timeout)
        return {"ok": int(res.get("exit_code", 1)) == 0,
                "output": str(res.get("output") or ""),
                "error": str(res.get("error") or ""),
                "artifact_type": "report",
                "provider_command": str(res.get("command") or ""),
                "provider_exit_code": int(res.get("exit_code", 1))}

    return _fn



def _plugin_runtime_provider(root: str | Path, plugin_id: str, task_node_id: str,
                            company_id: str) -> tuple[str, dict[str, Any]]:
    """Plugin governance + implementation 解析 (不执行): 必须 ENABLED + capability 匹配 + scope 合法。"""
    from .os_core_plugin import get_plugin_contract
    from .os_core_task_node import get_task_node

    contract = get_plugin_contract(root, plugin_id)
    if contract is None:
        raise ValueError(f"Plugin 不存在: {plugin_id}")
    if contract["status"] != "ENABLED":
        raise ValueError(f"Plugin 非 ENABLED: {plugin_id} ({contract['status']})")
    node = get_task_node(root, task_node_id) or {}
    required = set(node.get("required_capability_refs") or [])
    if required and not (set(contract["capability_refs"]) & required):
        raise ValueError(f"Plugin {plugin_id} capability 与 TaskNode {task_node_id} 不匹配")
    if contract["scope"] == "company" and contract["company_id"] != str(company_id):
        raise ValueError(f"Plugin {plugin_id} 属于 company {contract['company_id']}, 与 {company_id} 不匹配")
    impl = contract["implementation_ref"]
    if not impl.startswith("provider:"):
        raise ValueError(f"Plugin implementation 暂只支持 provider: (got {impl!r})")
    return impl.split(":", 1)[1], contract


def run_execution_via_node_runtime(root: str | Path, execution_id: str, *, prompt: str,
                                   project_dir: str = "", provider: str = "codex",
                                   timeout: int = 300, plugin_id: str = "",
                                   executor_fn: Callable[[dict[str, Any]], dict[str, Any]]
                                   | None = None) -> dict[str, Any]:
    """Runtime Integration: OS Execution -> node_runtime.NodeRun -> executor/provider -> 回写。

    - Execution 必须 queued 且已有 TaskNode/Resolution 因果链 (MU-CORE-09/10 校验);
    - 每个 Execution 注册独立 node + NodeRun (retry = 新 Execution + 新 NodeRun);
    - provider in {codex, claude} 经 external_executor.run 真实调用; 也可注入 executor_fn;
    - 回写: node_run_id / provider / runtime_ref / output_refs / 最终状态。
    """
    from .os_core_execution import get_execution, set_execution_status
    from .os_core_task import resolve_task
    from .os_core_task_node import get_task_node
    from .node_runtime import create_node_run, execute_node_run, get_node_run, register_node

    rec = get_execution(root, execution_id)
    if rec is None:
        raise ValueError(f"Execution 不存在: {execution_id}")
    if rec["status"] != "queued":
        raise ValueError(f"Execution 非 queued 状态 ({rec['status']}) — 不可执行")
    node_def = get_task_node(root, rec["task_node_id"])
    if node_def is None:
        raise ValueError(f"TaskNode 不存在: {rec['task_node_id']}")
    chain = resolve_task(root, node_def["task_id"])
    project_id = str(chain["project"]["id"])
    company_id = str(chain["project"].get("company_id") or "")
    plugin_contract: dict[str, Any] | None = None
    if plugin_id:
        provider, plugin_contract = _plugin_runtime_provider(root, plugin_id,
                                                             rec["task_node_id"], company_id)
    set_execution_status(root, execution_id, "running")
    os_node_id = f"osnode-{execution_id}"
    register_node(root, node_id=os_node_id, name=f"OS {node_def['name']}",
                  node_type="task",
                  input_contract={"prompt": "str"}, output_contract={"output": "str"})
    node_run = create_node_run(root, os_node_id, input_data={"prompt": prompt},
                               trigger="os-execution",
                               task_id=str(node_def["task_id"]), project_id=project_id)
    fn = executor_fn or _provider_executor_fn(provider, prompt, project_dir, timeout)
    _t0 = time.time()
    executed = execute_node_run(root, node_run["run_id"], executor_fn=fn,
                                executor_name=f"provider:{provider}" if executor_fn is None
                                else "executor_fn:custom",
                                artifact_root=root)
    _elapsed_ms = int((time.time() - _t0) * 1000)
    state = str(executed.get("state") or "")
    ok = state == "COMPLETED"
    _fail_text = str(executed.get("failure_reason") or "")
    _term_reason = "success" if ok else (
        "timeout" if ("超时" in _fail_text or "timeout" in _fail_text.lower())
        else "provider_failure")
    output_ref = _write_output(root, execution_id, {
        "execution_id": execution_id, "node_run_id": node_run["run_id"],
        "provider": provider if executor_fn is None else "custom",
        "node_run_state": state, "artifact_id": executed.get("artifact_id"),
        "verification": executed.get("verification"),
        "failure_reason": executed.get("failure_reason"),
        "elapsed_ms": None, "at": _now_iso()})
    runtime_ref = f"node_run:{node_run['run_id']}:{provider if executor_fn is None else 'custom'}"
    eff_provider = provider if executor_fn is None else "custom"
    plugin_trace = {"plugin_id": plugin_id if plugin_contract else "",
                    "implementation_ref": (plugin_contract or {}).get("implementation_ref", "")}
    if ok:
        set_execution_status(root, execution_id, "succeeded", output_refs=[output_ref],
                             runtime_ref=runtime_ref, node_run_id=node_run["run_id"],
                             provider=eff_provider, termination_reason=_term_reason,
                             duration_ms=_elapsed_ms, timeout_seconds=timeout, **plugin_trace)
    else:
        set_execution_status(root, execution_id, "failed",
                             error=str(executed.get("failure_reason") or state)[:500],
                             output_refs=[output_ref], runtime_ref=runtime_ref,
                             node_run_id=node_run["run_id"], provider=eff_provider,
                             termination_reason=_term_reason, duration_ms=_elapsed_ms,
                             timeout_seconds=timeout, **plugin_trace)
    from .os_core_usage import record_usage

    _usage = record_usage(root, execution_id=execution_id, provider=eff_provider,
                          plugin_id=plugin_id if plugin_contract else "",
                          node_run_id=node_run["run_id"], duration_ms=_elapsed_ms,
                          status=str((get_execution(root, execution_id) or {}).get("status", "")),
                          termination_reason=_term_reason,
                          exit_code=int((executed.get("verification") or {}).get("exit_code", -1))
                          if isinstance(executed.get("verification"), dict) else None)
    return {"execution": get_execution(root, execution_id), "duration_ms": _elapsed_ms,
            "termination_reason": _term_reason, "usage_id": _usage["usage_id"],
            "node_run": get_node_run(root, node_run["run_id"]), "ok": ok,
            "runtime_ref": runtime_ref, "output_ref": output_ref, "provider": provider}


def resolve_node_run_execution(root: str | Path, node_run_id: str) -> dict[str, Any] | None:
    """NodeRun -> OS Execution 反向映射 (Execution.node_run_id == node_run_id)。"""
    from .os_core_execution import list_executions

    for ex in list_executions(root):
        if ex.get("node_run_id") == str(node_run_id):
            return ex
    return None
