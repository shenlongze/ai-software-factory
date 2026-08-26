"""factory-console/external_executor/executor.py — 通用执行器 (M1)。

设计依据: 设计文档 §5 (GenericExecutor: discover→probe→invoke→record)。
只依赖适配器 Schema, 不依赖产品名。

- discover: 按 discovery 顺序定位二进制 (which + 路径)
- probe: 跑 version_probe/probe_help → {ok, usage, error} (诚实: 能跑 ≠ 任务真实成功)
- build_invocation: 按 invocation 模板渲染 (占位符替换 + shlex 转义)
- run: 统一 {exit_code, output, error, command}
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from .schema import ExternalExecutorAdapter

PLACEHOLDERS = ("{prompt}", "{project_dir}", "{agent}", "{skills}")


def discover_binary(adapter: ExternalExecutorAdapter) -> str | None:
    """按 discovery 顺序定位二进制 (PATH + 绝对/家目录路径; 找不到 → None)。"""
    for entry in adapter.discovery:
        e = str(entry or "").strip()
        if not e:
            continue
        if e == "PATH":
            found = shutil.which(adapter.binary)
            if found:
                return found
            continue
        p = Path(e).expanduser()
        if p.is_dir():
            cand = p / adapter.binary
            if cand.is_file():
                return str(cand)
            continue
        if p.is_file():
            return str(p)
    return None


def probe(adapter: ExternalExecutorAdapter, path: str | None = None) -> dict[str, Any]:
    """探测可用性: 跑 version_probe/probe_help → {ok, usage, version, error}。

    诚实: 二进制可执行 + 帮助/版本命令退出 0 → ok; 否则 ok=false (可展示不可委派)。"""
    path = path or discover_binary(adapter)
    if not path:
        return {"ok": False, "usage": "", "version": "", "error": f"未找到二进制: {adapter.binary}"}
    version = ""
    usage = ""
    for args, is_version in ((list(adapter.version_probe), True), (list(adapter.probe_help or adapter.version_probe), False)):
        try:
            r = subprocess.run([path, *args], capture_output=True, text=True, timeout=15)
            text = (r.stdout or r.stderr or "").strip()
            first = text.splitlines()[0][:120] if text else ""
            if is_version and first:
                version = first
            else:
                usage = first
            if r.returncode == 0 and (is_version or not adapter.probe_help):
                if is_version and version:
                    return {"ok": True, "usage": "", "version": version, "error": ""}
        except Exception:  # noqa: BLE001 — 探测失败 → 继续下一个
            continue
    # 组合判定: version 或 usage 任一成功即认为二进制可执行
    ok = bool(version or usage)
    return {"ok": ok, "usage": usage, "version": version,
            "error": "" if ok else "probe 失败 (--version/--help 均未返回)"}


def build_invocation(
    adapter: ExternalExecutorAdapter,
    prompt: str,
    project_dir: str = "",
    *,
    agent: str = "",
    skills: list[str] | None = None,
) -> list[str]:
    """按 invocation 模板渲染命令 (占位符替换 + shlex 转义)。

    规则 (§4.2): {prompt} 必替换; project_dir 按模式 (cwd 不插入 / flag: 插入参数名);
    agent/skills 仅在对应 flag 声明时插入; 无 {prompt} 的模板在 Schema 校验时已拒绝。"""
    template = list(adapter.invocation.non_interactive) + list(adapter.invocation.extra or [])
    mode = str(adapter.invocation.project_dir or "cwd")
    pdir = str(project_dir or "").strip()

    def esc(value: str) -> str:
        return shlex.quote(value)

    out: list[str] = []
    for part in template:
        part = str(part)
        if "{prompt}" in part:
            part = part.replace("{prompt}", esc(prompt))
        if "{project_dir}" in part:
            part = part.replace("{project_dir}", esc(pdir or "."))
        if "{agent}" in part:
            part = part.replace("{agent}", esc(agent))
        if "{skills}" in part:
            part = part.replace("{skills}", esc(",".join(skills or [])))
        out.append(part)
    # project_dir flag 模式: 在模板后插入 "<参数名> <目录>" (codex: -C <dir>)
    if mode.startswith("flag:"):
        flag = mode.split(":", 1)[1].strip()
        if flag:
            out.extend([flag, esc(pdir or ".")])
    # 借壳: agent/skills 指定时插入声明的 flag (§4.2 agent_flag/skills_flag)
    if agent and adapter.invocation.agent_flag:
        for part in adapter.invocation.agent_flag:
            out.append(str(part).replace("{agent}", esc(agent)))
    if skills and adapter.invocation.skills_flag:
        for part in adapter.invocation.skills_flag:
            out.append(str(part).replace("{skills}", esc(",".join(skills))))
    return out


def run(
    adapter: ExternalExecutorAdapter,
    prompt: str,
    project_dir: str = "",
    *,
    agent: str = "",
    skills: list[str] | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """委派真实执行 (统一契约 {exit_code, output, error, command})。"""
    path = discover_binary(adapter)
    if not path:
        return {"exit_code": -1, "output": "", "error": f"未找到二进制: {adapter.binary}", "command": ""}
    # 命令 = [二进制路径, *模板渲染] (模板不含路径 — 防 -p 被当可执行文件)
    cmd = [path, *build_invocation(adapter, prompt, project_dir, agent=agent, skills=skills)]
    mode = str(adapter.invocation.project_dir or "cwd")
    use_cwd = mode == "cwd" and project_dir
    cwd = str(project_dir or "").strip() if use_cwd else None
    timeout = timeout or adapter.invocation.timeout
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd if cwd and Path(cwd).is_dir() else None,
        )
        return {
            "exit_code": r.returncode,
            "output": (r.stdout or "")[-8000:],
            "error": (r.stderr or "")[-3000:] if r.returncode != 0 else "",
            "command": " ".join(cmd)[:400],
        }
    except FileNotFoundError as exc:
        return {"exit_code": -1, "output": "", "error": f"CLI 不存在: {exc}", "command": " ".join(cmd)[:400]}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "output": "", "error": f"执行超时 ({timeout}s)", "command": " ".join(cmd)[:400]}
    except Exception as exc:  # noqa: BLE001 — 执行失败 → 诚实错误
        return {"exit_code": -1, "output": "", "error": f"执行失败: {exc}", "command": " ".join(cmd)[:400]}


# ------------------------------------------------------------------ M3: 统一执行记录 + 验证回路

def record_invocation(
    data_dir: str | Path,
    *,
    executor_id: str,
    mode: str,
    host_agent: str,
    prompt: str,
    project_dir: str,
    exit_code: int,
    output: str,
    error: str,
    command: str,
    duration_ms: int,
    trace_id: str = "",
    cost_usd: float | None = None,
) -> dict[str, Any]:
    """追加统一执行记录 (execution_records.json, EXS-* result_id) + report.md 证据。

    设计文档 §7: EXS 扩展字段 executor_id/mode/host_agent/duration_ms/first_pass/
    verify/rework — 监控/路由/审计统一消费, 不区分内部/外部执行器。"""
    from datetime import datetime, timezone

    from factory_console.session.audit import record_execution

    rid = f"EXS-{uuid.uuid4().hex[:8]}"
    record = {
        "intent": "external_ai.invoke",
        "action": "external_ai.invoke",
        "agent": f"{executor_id}.{host_agent}" if host_agent else executor_id,
        "task": str(prompt or "")[:200],
        "result": "success" if exit_code == 0 else "failed",
        "result_id": rid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": str(trace_id or ""),
        # M3 扩展字段 (设计文档 §7)
        "executor_id": str(executor_id),
        "mode": str(mode),                # blackbox | borrowed-shell
        "host_agent": str(host_agent or ""),
        "project_dir": str(project_dir or ""),
        "duration_ms": int(duration_ms or 0),
        "exit_code": int(exit_code or 0),
        "command": str(command or "")[:400],
        "error": str(error or "")[:3000],
        "output_snippet": str(output or "")[:1000],
        "first_pass": True,               # 首次通过 (无回修); verify fail 后置 False
        "verify": {"method": "", "result": "unknown", "score": None},
        "rework": {"count": 0, "reasons": []},
        "cost_usd": cost_usd,             # 成本 (宿主未报告 → None = unknown, 诚实)
    }
    try:
        record_execution(
            record,
            records_file=Path(data_dir) / "exec" / "execution_records.json",
        )
        # 证据包 (T-9 溯源: EXS-*.report.md)
        report = Path(data_dir) / "exec" / f"{rid}.report.md"
        try:
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                f"# 外部执行器委派记录 {rid}\n\n"
                f"- executor: {executor_id} · mode: {mode}"
                + (f" · host_agent: {host_agent}" if host_agent else "")
                + f"\n- exit_code: {exit_code} · duration_ms: {duration_ms}\n"
                + f"- command: {command}\n\n"
                + (f"## 输出\n```\n{str(output or '')[:3000]}\n```\n" if output else "")
                + (f"## 错误\n```\n{error}\n```\n" if error else ""),
                encoding="utf-8",
            )
        except OSError:
            pass
    except Exception:  # noqa: BLE001 — 记录失败不阻断委派
        pass
    return record


def verify_invocation(
    data_dir: str | Path,
    result_id: str,
    *,
    method: str,
    result: str,
    score: float | None = None,
    reason: str = "",
) -> dict[str, Any] | None:
    """验证回写: 更新执行记录的 verify + rework (设计文档 §8)。

    result: pass|fail|unknown; fail → first_pass=False + rework.count+1 + reason。"""
    from factory_console.session.audit import load_records

    records_file = Path(data_dir) / "exec" / "execution_records.json"
    records = load_records(records_file)
    found = None
    for rec in records:
        if isinstance(rec, dict) and str(rec.get("result_id") or "") == result_id:
            found = rec
            break
    if found is None:
        return None
    method = str(method or "").strip() or "manual"
    result = str(result or "unknown").strip().lower()
    if result not in ("pass", "fail", "unknown"):
        result = "unknown"
    score = float(score) if score is not None else None
    found["verify"] = {"method": method, "result": result, "score": score}
    if result == "fail":
        found["first_pass"] = False
        rework = found.setdefault("rework", {"count": 0, "reasons": []})
        rework["count"] = int(rework.get("count", 0)) + 1
        if reason:
            rework["reasons"].append(str(reason)[:200])
    # 原子直写整表 (不能用 record_execution — 那是 append, 会嵌套)
    try:
        records_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = records_file.with_suffix(records_file.suffix + ".tmp")
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(records_file)
    except OSError:
        pass
    return found


def record_cost(
    data_dir: str | Path,
    result_id: str,
    cost_usd: float,
    *,
    currency: str = "USD",
) -> dict[str, Any] | None:
    """给执行记录附加成本 (宿主 CLI 报告/估算后回填; 失败安全)。

    设计: 成本默认 unknown (不编造); 有来源才记录。"""
    import json as _json

    from factory_console.session.audit import load_records

    records_file = Path(data_dir) / "exec" / "execution_records.json"
    records = load_records(records_file)
    found = None
    for rec in records:
        if isinstance(rec, dict) and str(rec.get("result_id") or "") == result_id:
            found = rec
            break
    if found is None:
        return None
    try:
        found["cost_usd"] = float(cost_usd)
        found["cost_currency"] = str(currency or "USD")
    except (TypeError, ValueError):
        return None
    try:
        records_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = records_file.with_suffix(records_file.suffix + ".tmp")
        tmp.write_text(_json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(records_file)
    except OSError:
        pass
    return found
