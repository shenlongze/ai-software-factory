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


__all__ = ["RUNTIMES", "run_execution"]
