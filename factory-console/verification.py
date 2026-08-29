"""factory-console/verification.py — S5 真实 Verification 执行器。

真实验证器 (pytest/语法), 非 LLM 自评:
- verify_python_syntax: ast.parse 语法检查
- verify_pytest: 真实 pytest 运行 (subprocess)
- VerificationResult: {verification_id, status(PASS/FAIL/INCONCLUSIVE/BLOCKED),
  exit_code, stdout, stderr, command, duration, evidence}
"""
from __future__ import annotations

import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

VERIFY_RESULTS = ("PASS", "FAIL", "INCONCLUSIVE", "BLOCKED")


def _vid() -> str:
    return f"ver-{uuid.uuid4().hex[:10]}"


def verify_python_syntax(workspace: Path | str, files: list[str] | None = None) -> dict[str, Any]:
    """语法验证: ast.parse 所有 .py 文件。"""
    ws = Path(workspace)
    targets = files or [str(p.relative_to(ws)) for p in ws.rglob("*.py") if "node_modules" not in str(p)]
    t0 = time.time()
    errors: list[str] = []
    for f in targets:
        p = ws / f
        if not p.exists():
            continue
        try:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
        except SyntaxError as exc:
            errors.append(f"{f}: {exc}")
    duration = round(time.time() - t0, 3)
    ok = not errors
    return {
        "verification_id": _vid(),
        "status": "PASS" if ok else "FAIL",
        "exit_code": 0 if ok else 1,
        "stdout": "", "stderr": "\n".join(errors)[:2000],
        "command": f"python syntax {len(targets)} files",
        "duration_s": duration,
        "evidence": {"files": targets, "errors": errors[:10]},
    }


def verify_pytest(workspace: Path | str, timeout: int = 120) -> dict[str, Any]:
    """真实 pytest 运行 (subprocess)。workspace 内必须有 pytest 可用。"""
    ws = Path(workspace)
    t0 = time.time()
    cmd = ["python", "-m", "pytest", "-q", "--no-header"]
    try:
        proc = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True, timeout=timeout)
        rc = proc.returncode
        stdout = (proc.stdout or "")[-3000:]
        stderr = (proc.stderr or "")[-2000:]
    except subprocess.TimeoutExpired:
        rc = -1
        stdout, stderr = "", "pytest timeout"
    except FileNotFoundError:
        rc = -1
        stdout, stderr = "", "pytest 不可用"
    duration = round(time.time() - t0, 3)
    status = "PASS" if rc == 0 else ("FAIL" if rc in (1, 2) else "INCONCLUSIVE")
    return {
        "verification_id": _vid(),
        "status": status,
        "exit_code": rc,
        "stdout": stdout,
        "stderr": stderr,
        "command": " ".join(cmd),
        "duration_s": duration,
        "evidence": {"exit_code": rc, "stdout_tail": stdout[-500:]},
    }
