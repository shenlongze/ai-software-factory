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


def run_execution(root: str | Path, execution_id: str, *, command: str,
                  runtime: str = "local", timeout: int = 30,
                  executor_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None
                  ) -> dict[str, Any]:
    """真实执行一次 OS Execution: queued -> running -> succeeded/failed (+ runtime_ref/output_ref)。"""
    from .os_core_execution import get_execution, set_execution_status

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

    set_execution_status(root, execution_id, "running")
    started = time.time()
    ok, stdout, stderr, returncode, runtime_ref = False, "", "", 1, ""
    if executor_fn is not None:
        result = executor_fn({"execution_id": execution_id, "command": command})
        ok = bool(result.get("ok"))
        stdout = str(result.get("output") or "")
        stderr = str(result.get("error") or "")
        returncode = int(result.get("returncode", 0 if ok else 1))
        runtime_ref = f"executor_fn:{result.get('name', 'custom')}"
    else:
        try:
            proc = subprocess.run(command, shell=True, capture_output=True, text=True,
                                  timeout=timeout, cwd=str(root))
            ok, stdout, stderr, returncode = (proc.returncode == 0, proc.stdout,
                                              proc.stderr, proc.returncode)
        except subprocess.TimeoutExpired:
            stderr, returncode = f"timeout after {timeout}s", 124
        runtime_ref = "runtime:local-command"
    elapsed_ms = int((time.time() - started) * 1000)
    output_ref = _write_output(root, execution_id, {
        "execution_id": execution_id, "command": command, "runtime_ref": runtime_ref,
        "returncode": returncode, "stdout": stdout, "stderr": stderr,
        "elapsed_ms": elapsed_ms, "at": _now_iso()})
    if ok:
        set_execution_status(root, execution_id, "succeeded", output_refs=[output_ref],
                             runtime_ref=runtime_ref)
    else:
        set_execution_status(root, execution_id, "failed",
                             error=(stderr or f"exit {returncode}")[:500],
                             output_refs=[output_ref], runtime_ref=runtime_ref)
    return {"execution": get_execution(root, execution_id), "ok": ok,
            "runtime_ref": runtime_ref, "output_ref": output_ref,
            "returncode": returncode, "stdout": stdout, "stderr": stderr}


__all__ = ["RUNTIMES", "resolve_node_run_execution", "run_execution",
           "run_execution_via_node_runtime"]


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
    executed = execute_node_run(root, node_run["run_id"], executor_fn=fn,
                                executor_name=f"provider:{provider}" if executor_fn is None
                                else "executor_fn:custom",
                                artifact_root=root)
    state = str(executed.get("state") or "")
    ok = state == "COMPLETED"
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
                             provider=eff_provider, **plugin_trace)
    else:
        set_execution_status(root, execution_id, "failed",
                             error=str(executed.get("failure_reason") or state)[:500],
                             output_refs=[output_ref], runtime_ref=runtime_ref,
                             node_run_id=node_run["run_id"], provider=eff_provider,
                             **plugin_trace)
    return {"execution": get_execution(root, execution_id),
            "node_run": get_node_run(root, node_run["run_id"]), "ok": ok,
            "runtime_ref": runtime_ref, "output_ref": output_ref, "provider": provider}


def resolve_node_run_execution(root: str | Path, node_run_id: str) -> dict[str, Any] | None:
    """NodeRun -> OS Execution 反向映射 (Execution.node_run_id == node_run_id)。"""
    from .os_core_execution import list_executions

    for ex in list_executions(root):
        if ex.get("node_run_id") == str(node_run_id):
            return ex
    return None
