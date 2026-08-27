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
    # S10-127 P2.2: 系统级沙箱最小版 — 危险命令校验 (fail-closed)
    try:
        from factory_console.session.sandbox import validate_command

        ok_v, reason = validate_command(cmd)
        if not ok_v:
            return {"exit_code": -1, "output": "",
                    "error": f"沙箱拦截: {reason} (S10-127 P2.2)", "command": " ".join(cmd)[:400]}
    except Exception:  # noqa: BLE001 — 沙箱不可用 → 放行 (外部执行器不受阻)
        pass
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


def auto_verify(
    project_dir: str,
    work_type: str,
    *,
    verify_hook: dict[str, Any] | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    """自动验证 (设计文档 §4.5 verify_hook + §8 验证): 委派后跑验证 → 效果分。

    优先级:
    ① 适配器 extensions.verify_hook (显式命令, 如 pytest/自定义)
    ② 默认: test/developer 任务且项目有 pytest → pytest -q
    ③ 无钩子/不适用 → unknown (诚实: 需人工或审查验证, 不编造)

    返回 {method, result(pass|fail|unknown), score, reason}。"""
    project = str(project_dir or "").strip()
    if not project or not Path(project).is_dir():
        return {"method": "", "result": "unknown", "score": None,
                "reason": "无项目目录, 无法验证"}
    # ① 显式 verify_hook
    if verify_hook and verify_hook.get("command"):
        cmd = [str(x) for x in verify_hook["command"]]
        name = str(verify_hook.get("name") or "verify_hook")
        try:
            r = subprocess.run(cmd, cwd=project, capture_output=True, text=True, timeout=timeout)
            ok = r.returncode == 0
            return {"method": name, "result": "pass" if ok else "fail",
                    "score": 1.0 if ok else 0.0,
                    "reason": "" if ok else (r.stdout or r.stderr or "")[-300:]}
        except Exception as exc:  # noqa: BLE001 — 验证失败 → unknown 诚实
            return {"method": name, "result": "unknown", "score": None,
                    "reason": f"验证执行失败: {exc}"}
    # ② 默认 pytest (test/developer 任务, 项目有 pytest 迹象)
    has_pytest = (
        (Path(project) / "pytest.ini").is_file()
        or (Path(project) / "pyproject.toml").is_file()
        or (Path(project) / "tests").is_dir()
    )
    if work_type in ("test", "developer") and has_pytest:
        try:
            r = subprocess.run(["pytest", "-q"], cwd=project, capture_output=True, text=True, timeout=timeout)
            ok = r.returncode == 0
            return {"method": "pytest", "result": "pass" if ok else "fail",
                    "score": 1.0 if ok else 0.0,
                    "reason": "" if ok else (r.stdout or r.stderr or "")[-300:]}
        except Exception as exc:  # noqa: BLE001 — pytest 不可用 → unknown
            return {"method": "pytest", "result": "unknown", "score": None,
                    "reason": f"pytest 不可用: {exc}"}
    # ③ 无自动钩子 → 诚实 unknown (人工/审查验证)
    return {"method": "", "result": "unknown", "score": None,
            "reason": "无自动验证钩子 (需人工或审查验证, 不编造)"}


def reviewer_verify(
    data_dir: str | Path,
    adapters: list[Any],
    agents: list[dict[str, Any]],
    task: str,
    project_dir: str,
    primary_output: str,
    work_type: str,
    *,
    preferred_adapter: str = "",
    timeout: int = 900,
) -> dict[str, Any]:
    """审查验证钩子 (M7.2): 主 agent 产出后, 再派一个 reviewer 交叉审查 → PASS/FAIL。

    - 选 reviewer: 候选池 role=reviewer 的 agent (优先同适配器家族, 其次任意 reviewer);
      无 reviewer → unknown (诚实, 不硬凑)
    - prompt: 任务 + 产出, 只答 PASS/FAIL + 一句理由
    - 审查委派本身也记一条 EXS (可审计 + 贡献该 reviewer 的历史效果分)
    - 解析: 输出含 FAIL → fail; 含 PASS → pass; 否则 unknown (不编造)"""
    from .registry import ExternalExecutorRegistry
    from . import router as _router

    # 候选 reviewer: role=reviewer 的 agent (external), 同家族优先
    reviewers: list[dict[str, Any]] = []
    for ag in agents:
        if not ag.get("source"):
            continue
        if str(ag.get("role") or "") == "reviewer":
            reviewers.append(ag)
    if not reviewers:
        return {"method": "", "result": "unknown", "score": None,
                "reason": "无 reviewer agent (未导入), 无法交叉审查"}
    if preferred_adapter:
        same_family = [r for r in reviewers if str(r.get("id") or "").startswith(preferred_adapter + ".")]
        if same_family:
            reviewers = same_family
    reviewer = reviewers[0]
    rid = str(reviewer.get("id") or "")
    adapter_id = rid.split(".")[0]
    host_agent = rid[len(adapter_id) + 1:] if "." in rid else ""
    registry = ExternalExecutorRegistry(data_dir)
    adapter = registry.get(adapter_id)
    if adapter is None:
        return {"method": "", "result": "unknown", "score": None,
                "reason": f"适配器不存在: {adapter_id}"}
    if host_agent and not adapter.invocation.agent_flag:
        host_agent = ""
    prompt = (
        "你是验证者 (reviewer)。下面是某次任务的产出，请严格审查是否达标。\n"
        f"任务: {str(task)[:500]}\n"
        f"产出:\n{str(primary_output)[:4000]}\n\n"
        "只回答一行: PASS 或 FAIL（可加一句理由）。"
    )
    result = run(adapter, prompt, project_dir=project_dir, agent=host_agent, timeout=timeout)
    out = str(result.get("output") or "")
    up = out.upper()
    if "FAIL" in up:
        verdict, score = "fail", 0.0
    elif "PASS" in up:
        verdict, score = "pass", 1.0
    else:
        verdict, score = "unknown", None
    # 审查委派也记录 (可审计 + reviewer 历史)
    try:
        record_invocation(
            data_dir, executor_id=adapter_id,
            mode="borrowed-shell" if host_agent else "blackbox", host_agent=host_agent,
            prompt=prompt, project_dir=project_dir,
            exit_code=int(result.get("exit_code")) if result.get("exit_code") is not None else -1,
            output=out, error=str(result.get("error") or ""),
            command=str(result.get("command") or ""), duration_ms=0,
        )
    except Exception:  # noqa: BLE001
        pass
    return {"method": f"reviewer:{rid}", "result": verdict, "score": score,
            "reason": "" if verdict != "unknown" else "reviewer 未给出 PASS/FAIL (诚实 unknown)",
            "review_output": out[:500]}
