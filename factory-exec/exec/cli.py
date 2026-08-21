"""factory-exec/exec/cli.py — 执行 CLI (`factory-exec` console script + 主 CLI 共享命令)。

命令 (Phase A 任务清单):
```
factory-exec exec run --project DIR --task T [--objective O] [--requirement R]
                      [--employee EID] [--agent AID] [--provider P] [--test-cmd CMD]
factory-exec exec status [--id RESULT_ID]
factory-exec exec providers [--provider P]
factory-exec exec approval approve --id APR --by NAME [--comment C]
factory-exec exec approval deny    --id APR --by NAME [--comment C]
factory-exec exec approval apply   --id APR [--project DIR]
factory-exec exec approval list [--status pending|approved|rejected]
```

架构 (同 factory-org/org/cli.py):
- cmd_* 函数签名 (root: Path, args) → dict — 主 CLI (factory-core/cli) 延迟
  import 本模块后复用同一实现 (exec 命令并入主 CLI, 单一实现零复制)。
- 每命令在 logger_scope 内打开事件库 (root/factory.db) + EventLogger,
  event_seq 在块内取 (WAL 关闭陷阱)。
- 错误映射: NotFoundError 类 → exit_code 7 (未找到), 其余业务错误 → 1;
  cmd_* 捕获返回错误 dict, 不抛。
- 只读命令发审计事件 (ADR-0002: 所有 CLI 行为必须产生 Event —
  exec status/approval list 发 org.execution.viewed)。

Removal Isolation: 本模块只依赖 factory-core events/intelligence 层 + 可选
factory-org (Employee 解析); factory-core 零顶层 imports 本包。
"""

from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from events.logger import EventLogger
from events.models import EventType
from events.store import EventStore

from . import events as exec_events
from .agent_runtime import AgentRuntime
from .approval import ApprovalError, ApprovalGate
from .experience import ExperienceRecorder
from .models import AgentInstance, ExecutionRequest, new_id
from .provider import ProviderRegistry
from .store import ExecStore

DEFAULT_ROOT = Path.home() / ".factory"


class ExecCliError(Exception):
    """CLI 业务错误 (携带退出码; 未找到=7 / 其余=1)。"""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


@contextmanager
def _logger_scope(root: Path) -> Iterator[EventLogger]:
    """打开事件库 + EventLogger 作用域 (退出关闭连接, 同 ctx.logger_scope)。"""
    store = EventStore(root / "factory.db")
    try:
        yield EventLogger(store)
    finally:
        store.close()


def _exec_store(root: Path) -> ExecStore:
    return ExecStore(root / "exec")


def _error(message: str, exit_code: int = 1) -> dict:
    return {"ok": False, "error": message, "exit_code": exit_code}


def _import_llm_control_module() -> Any:
    """加载 LLMControlPlane 模块 (双名解析: wheel → factory_console / 源码 → factory-console)。

    S10-031 (First User Release): 发布包经 package_dir 映射为合法包名 factory_console
    (目录 factory-console 含连字符, 无法直接 import); 源码运行仍用 factory-console.
    两者取其一, 失败回退 (调用方失败安全)。
    """
    import importlib

    for name in ("factory_console.llm_control", "factory-console.llm_control"):
        try:
            return importlib.import_module(name)
        except (ImportError, ModuleNotFoundError):
            continue
    raise ImportError("LLMControlPlane unavailable (factory_console/factory-console)")


def _default_provider_id() -> str:
    """默认 provider id: ControlPlane 选中 (providers.json enabled+key) → 回退 anthropic.

    S10-031 (First User Release): exec run 未显式 --provider 时, 用用户配置的
    provider (如 deepseek), 而非硬编码 anthropic — 用户 init 配置即生效。
    """
    try:
        return _import_llm_control_module().LLMControlPlane().selected_provider_id() or "anthropic"
    except Exception:  # noqa: BLE001 — 失败安全: ControlPlane 不可用 → 默认 anthropic
        return "anthropic"


# ------------------------------------------------------------------ 装配点

def _provider_registry() -> ProviderRegistry:
    """Provider 注册表装配点 (延迟 import; 测试 monkeypatch 注入 mock)。

    S10-023 (Phase 3): 装配优先级 ControlPlane > legacy registry > fallback。
    1. LLMControlPlane (providers.json) 选中 provider (selected_provider_id)
       → resolve_runtime_config → 构造对应 Adapter 注册:
       deepseek/openai/ollama → OpenAIProvider (OpenAI 兼容端点);
       anthropic → AnthropicProvider。Adapter 的 provider_id 类属性硬编码
       (openai/anthropic), 装配时实例级覆盖为配置的 provider id — 不改
       openai.py/anthropic.py, registry.get(配置 id) 命中, usage 记录正确。
    2. 未命中 (无 providers.json / enabled 无 key / 全 disabled) → 回退 legacy
       default_registry() (anthropic+openai, 回归保护)。
    3. 异常安全: ControlPlane import 失败 (factory-console 包名带连字符, 仅经
       importlib 可加载, 依赖 PYTHONPATH 挂仓库根) / providers.json 损坏 /
       装配异常 → 一律回退不抛。
    """
    try:
        import importlib

        llm_control = _import_llm_control_module()
        plane = llm_control.LLMControlPlane()
        pid = plane.selected_provider_id()
        if pid is not None:
            cfg = plane.resolve_runtime_config(pid)
            if cfg:
                registry = ProviderRegistry()
                if pid == "anthropic":
                    from .providers.anthropic import (
                        DEFAULT_BASE_URL,
                        DEFAULT_MODEL,
                        AnthropicProvider,
                    )

                    provider = AnthropicProvider(
                        api_key=cfg.get("api_key") or None,
                        model=cfg.get("model") or DEFAULT_MODEL,
                        base_url=cfg.get("base_url") or DEFAULT_BASE_URL,
                    )
                else:
                    # deepseek/openai/ollama → OpenAI 兼容 Chat Completions 端点
                    from .providers.openai import (
                        DEFAULT_BASE_URL,
                        DEFAULT_MODEL,
                        OpenAIProvider,
                    )

                    kwargs: dict[str, Any] = {
                        "model": cfg.get("model") or DEFAULT_MODEL,
                        "base_url": cfg.get("base_url") or DEFAULT_BASE_URL,
                        "input_rate_per_1k": cfg.get("input_rate_per_1k"),
                        "output_rate_per_1k": cfg.get("output_rate_per_1k"),
                    }
                    if pid == "ollama":
                        kwargs["api_key"] = "ollama"  # 本地占位 (同 workflow_runner)
                    else:
                        kwargs["api_key"] = cfg.get("api_key") or None
                    provider = OpenAIProvider(**kwargs)
                provider.provider_id = pid  # 实例级覆盖 → registry.get(pid) 命中
                registry.register(provider)
                return registry
    except Exception:  # noqa: BLE001 — 失败安全: ControlPlane 不可用 → 回退不抛
        pass
    from .provider import default_registry

    return default_registry()


def _open_experience_analyzer(root: Path, logger: Any) -> Any:
    """10A-4 ExperienceAnalyzer 装配点 (intelligence 缺失 → None, 失败安全)。"""
    try:
        from intelligence.experience import ExperienceAnalyzer
        from intelligence.store import ExperienceStore

        return ExperienceAnalyzer(ExperienceStore(root / "intelligence"), logger=logger)
    except ImportError:
        return None


def _resolve_employee(root: Path, employee_ref: str) -> Any:
    """员工解析 (org store; factory-org 缺失/员工不存在 → ExecCliError 7)。"""
    try:
        from org.store import OrgStore
    except ImportError:
        raise ExecCliError("factory-org 未安装 (缺 factory-org/ 包)", exit_code=7)
    employee = OrgStore(root / "org").get_employee(employee_ref)
    if employee is None:
        raise ExecCliError(f"employee not found: {employee_ref}", exit_code=7)
    return employee


# ------------------------------------------------------------------ exec run

def cmd_exec_run(root: Path, args: Any) -> dict:
    """exec run — 执行请求 → Runtime (沙箱 + patch + 产物 + org.execution.* 链)。"""
    with _logger_scope(root) as logger:
        store = _exec_store(root)
        project_dir = Path(getattr(args, "project", "") or "")
        if not project_dir.is_dir():
            return _error(f"project dir not found: {project_dir}", exit_code=1)
        employee = None
        if getattr(args, "employee", None):
            try:
                employee = _resolve_employee(root, args.employee)
            except ExecCliError as exc:
                return _error(exc.message, exit_code=exc.exit_code)
        agent = AgentInstance(id=getattr(args, "agent", None) or "developer-1")
        try:
            registry = _provider_registry()
            provider_id = getattr(args, "provider", None) or _default_provider_id()
            provider = registry.get(provider_id)
        except ImportError:
            return _error("provider registry unavailable (factory-exec providers 缺失)", exit_code=1)
        if provider is None:
            return _error(
                f"provider not found: {provider_id} "
                f"(available: {registry.ids()})",
                exit_code=1,
            )
        capabilities = list(getattr(employee, "capabilities", None) or [])
        request = ExecutionRequest(
            id=new_id("EXR"),
            task_id=getattr(args, "task", "") or "",
            objective=getattr(args, "objective", None) or f"Complete task {args.task}",
            requirement=getattr(args, "requirement", "") or "",
            input={
                "project_dir": str(project_dir),
                "provider_id": provider.provider_id,
                "employee_id": getattr(employee, "id", "") or "",
                "capabilities": capabilities,
            },
        )
        experience = ExperienceRecorder(_open_experience_analyzer(root, logger))
        runtime = AgentRuntime(
            provider,
            store=store,
            logger=logger,
            validation_command=getattr(args, "test_cmd", None),
            artifacts_dir=store.dir,
            experience=experience,
        )
        result = runtime.execute(request, employee=employee, agent_instance=agent)
        terminal = (
            EventType.ORG_EXECUTION_COMPLETED
            if result.is_success
            else EventType.ORG_EXECUTION_FAILED
        )
        event_seq = exec_events.last_seq(logger, terminal)
    return {
        "ok": True,
        "command": "run",
        "request_id": request.id,
        "result_id": result.id,
        "status": result.status.value,
        "error": result.error,
        "artifacts": [a.to_dict() for a in result.artifacts],
        "usage": result.usage,
        "report": result.report,
        "event_seq": event_seq,
        "exit_code": 0 if result.is_success else 1,
    }


# ------------------------------------------------------------------ exec status

def cmd_exec_status(root: Path, args: Any) -> dict:
    """exec status — 执行结果清单/详情 (发 org.execution.viewed 审计)。"""
    with _logger_scope(root) as logger:
        store = _exec_store(root)
        result_id = getattr(args, "id", None)
        if result_id:
            result = store.get_result(result_id)
            if result is None:
                return _error(f"result not found: {result_id}", exit_code=7)
            results = [result]
        else:
            results = store.list_results()
        approvals = store.list_approvals()
        exec_events.record_execution_viewed(
            logger, count=len(results) + len(approvals)
        )
        event_seq = exec_events.last_seq(logger, EventType.ORG_EXECUTION_VIEWED)
    return {
        "ok": True,
        "command": "status",
        "count": len(results),
        "results": [r.to_dict() for r in results],
        "approval_count": len(approvals),
        "event_seq": event_seq,
        "exit_code": 0,
    }


def cmd_exec_providers(root: Path, args: Any) -> dict:
    """exec providers — Provider 配置预检 (key 缺失 → 明确提示 + 指引, BLOCKED 标注)。

    检查内置 Provider 的 API key 环境变量是否设置 (不假装成功: configured=True
    仅表示 key 已设置, 真实调用仍需 run/Benchmark 验证)。发 org.execution.viewed
    审计 (ADR-0002 只读命令)。
    """
    from .provider import ProviderConfigChecker

    with _logger_scope(root) as logger:
        checker = ProviderConfigChecker()
        statuses = checker.check(getattr(args, "provider", None) or None)
        summary = checker.summary()
        exec_events.record_execution_viewed(logger, count=len(statuses))
        event_seq = exec_events.last_seq(logger, EventType.ORG_EXECUTION_VIEWED)
    return {
        "ok": True,
        "command": "providers",
        "providers": summary["providers"],
        "configured_ids": summary["configured_ids"],
        "blocked": summary["blocked"],
        "any_configured": summary["any_configured"],
        "message": summary["message"],
        "event_seq": event_seq,
        "exit_code": 0,
    }


# ------------------------------------------------------------------ exec approval

def _approval_gate(root: Path, logger: Any) -> ApprovalGate:
    return ApprovalGate(_exec_store(root), logger=logger)


def _decide(root: Path, args: Any, decision: str) -> dict:
    """approve|deny 共用: 动词 → 语义终态 (approved|rejected), 服务层零动词。"""
    with _logger_scope(root) as logger:
        try:
            record = _approval_gate(root, logger).decide(
                args.id,
                "approved" if decision == "approve" else "rejected",
                decided_by=getattr(args, "by", "") or "",
                comment=getattr(args, "comment", "") or "",
            )
        except ApprovalError as exc:
            code = 7 if "not found" in str(exc) else 1
            return _error(str(exc), exit_code=code)
        event_type = EventType.ORG_EXECUTION_APPROVED
        event_seq = exec_events.last_seq(logger, event_type)
    return {
        "ok": True,
        "command": f"approval {decision}",
        "approval": record.to_dict(),
        "event_seq": event_seq,
        "exit_code": 0,
    }


def cmd_exec_approval_approve(root: Path, args: Any) -> dict:
    """exec approval approve — 审批通过 (org.execution.approved)。"""
    return _decide(root, args, "approve")


def cmd_exec_approval_deny(root: Path, args: Any) -> dict:
    """exec approval deny — 审批拒绝 (comment 反馈; 不发 approved 事件)。"""
    return _decide(root, args, "deny")


def cmd_exec_approval_apply(root: Path, args: Any) -> dict:
    """exec approval apply — 应用已批准 patch (未批 → 硬拒绝; org.execution.applied)。"""
    with _logger_scope(root) as logger:
        store = _exec_store(root)
        approval = store.get_approval(args.id)
        if approval is None:
            return _error(f"approval not found: {args.id}", exit_code=7)
        target = getattr(args, "project", None)
        if not target:
            request = store.get_request(approval.request_id)
            if request is not None:
                target = request.input.get("project_dir", "")
        if not target:
            return _error("target project dir unknown: pass --project", exit_code=1)
        try:
            record, patch_text = _approval_gate(root, logger).apply(args.id, target)
        except ApprovalError as exc:
            code = 7 if "not found" in str(exc) else 1
            return _error(str(exc), exit_code=code)
        event_seq = exec_events.last_seq(logger, EventType.ORG_EXECUTION_APPLIED)
    return {
        "ok": True,
        "command": "approval apply",
        "approval": record.to_dict(),
        "patch_lines": len(patch_text.splitlines()),
        "event_seq": event_seq,
        "exit_code": 0,
    }


def _approval_dict_with_bundle(store: ExecStore, record: Any) -> dict:
    """审批记录 → dict + bundle_id (T4 交叉引用: 请求 input.evidence_bundle_id)。

    无关联证据包 → bundle_id "" (兼容非 backlog 审批/旧数据, 不伪造)。
    """
    data = record.to_dict()
    try:
        req = store.get_request(str(record.request_id or ""))
        data["bundle_id"] = str(((req.input or {}).get("evidence_bundle_id") or "")) if req is not None else ""
    except Exception:  # noqa: BLE001 — 交叉引用失败安全
        data["bundle_id"] = ""
    return data


def cmd_exec_approval_list(root: Path, args: Any) -> dict:
    """exec approval list — 审批记录清单 (发 org.execution.viewed 审计)。

    T4: 每行附 bundle_id (证据包交叉引用; 无 → "")。
    """
    with _logger_scope(root) as logger:
        store = _exec_store(root)
        records = _approval_gate(root, logger).list(
            status=getattr(args, "status", None) or None
        )
        exec_events.record_execution_viewed(logger, count=len(records))
        event_seq = exec_events.last_seq(logger, EventType.ORG_EXECUTION_VIEWED)
    return {
        "ok": True,
        "command": "approval list",
        "count": len(records),
        "approvals": [_approval_dict_with_bundle(store, r) for r in records],
        "event_seq": event_seq,
        "exit_code": 0,
    }


# ------------------------------------------------------------------ 独立 CLI

def _json_opt(parser: argparse.ArgumentParser) -> None:
    """每个子命令也接受 --json (全局选项须在子命令前, 此处双保险)。

    default 必须为 SUPPRESS: Python 3.12 的 _SubParsersAction.__call__ 会把子
    解析器结果解析进全新 namespace 再整体拷贝回原 namespace — 子解析器任何非
    SUPPRESS 默认值都会无条件覆盖已解析的全局 --json 值 (同主 CLI json_opt)。
    """
    parser.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="JSON 输出"
    )


def build_parser() -> argparse.ArgumentParser:
    """factory-exec 独立 CLI parser (与主 CLI exec 命令组同构)。"""
    parser = argparse.ArgumentParser(prog="factory-exec", description="AI Software Factory — 执行闭环 CLI")
    parser.add_argument("--root", default=None, help="工厂数据根 (默认 ~/.factory)")
    sub = parser.add_subparsers(dest="command", required=True)
    _json_opt(parser)

    p_run = sub.add_parser("run", help="执行请求 → Runtime (沙箱 + patch + 产物)")
    _json_opt(p_run)
    p_run.add_argument("--project", required=True, help="项目目录 (沙箱副本源)")
    p_run.add_argument("--task", required=True, help="任务 ID (Task 锚点)")
    p_run.add_argument("--objective", default=None, help="目标描述 (默认派生自 task)")
    p_run.add_argument("--requirement", default="", help="验收标准/约束")
    p_run.add_argument("--employee", default=None, help="员工 ID (org store 解析)")
    p_run.add_argument("--agent", default=None, help="Agent 实例 ID (默认 developer-1)")
    p_run.add_argument("--provider", default=None, help="Provider id (默认 anthropic)")
    p_run.add_argument("--test-cmd", default=None, help="沙箱内测试命令 (验证)")

    p_status = sub.add_parser("status", help="执行结果清单/详情")
    _json_opt(p_status)
    p_status.add_argument("--id", default=None, help="结果 ID (缺省列出全部)")

    p_providers = sub.add_parser("providers", help="Provider 配置预检 (key 缺失 → 明确提示)")
    _json_opt(p_providers)
    p_providers.add_argument("--provider", default=None, help="Provider id (缺省全部)")

    p_ap = sub.add_parser("approval", help="审批门禁 (应用 patch 前必批)")
    _json_opt(p_ap)
    asub = p_ap.add_subparsers(dest="approval_command", required=True)
    p_approve = asub.add_parser("approve", help="审批通过 (org.execution.approved)")
    _json_opt(p_approve)
    p_approve.add_argument("--id", required=True, help="审批记录 ID")
    p_approve.add_argument("--by", required=True, help="审批人 (Human 身份)")
    p_approve.add_argument("--comment", default="")
    p_deny = asub.add_parser("deny", help="审批拒绝 (comment 反馈)")
    _json_opt(p_deny)
    p_deny.add_argument("--id", required=True)
    p_deny.add_argument("--by", required=True)
    p_deny.add_argument("--comment", default="")
    p_apply = asub.add_parser("apply", help="应用已批准 patch (未批 → 硬拒绝)")
    _json_opt(p_apply)
    p_apply.add_argument("--id", required=True)
    p_apply.add_argument("--project", default=None, help="目标项目 (缺省取请求 project_dir)")
    p_list = asub.add_parser("list", help="审批记录清单")
    _json_opt(p_list)
    p_list.add_argument("--status", default=None, help="过滤: pending|approved|rejected")
    return parser


def _dispatch(root: Path, args: Any) -> dict:
    if args.command == "run":
        return cmd_exec_run(root, args)
    if args.command == "status":
        return cmd_exec_status(root, args)
    if args.command == "providers":
        return cmd_exec_providers(root, args)
    if args.command == "approval":
        if args.approval_command == "approve":
            return cmd_exec_approval_approve(root, args)
        if args.approval_command == "deny":
            return cmd_exec_approval_deny(root, args)
        if args.approval_command == "apply":
            return cmd_exec_approval_apply(root, args)
        if args.approval_command == "list":
            return cmd_exec_approval_list(root, args)
        return _error(f"unknown approval command: {args.approval_command}", exit_code=2)
    return _error(f"unknown exec command: {args.command}", exit_code=2)


def _print_result(args: Any, r: dict) -> None:
    """非 JSON 文本输出 (与主 CLI _print_exec 同构; 错误 dict → stderr)。"""
    if not r.get("ok"):
        print(f"error: {r.get('error')}", file=sys.stderr)
        return
    if r.get("command") == "run":
        print("✔ 执行完成" if r["status"] == "success" else "✘ 执行失败")
        print(f"  request_id  {r['request_id']}")
        print(f"  result_id   {r['result_id']}")
        print(f"  status      {r['status']}")
        if r.get("error"):
            print(f"  error       {r['error']}")
        for a in r.get("artifacts", []):
            print(f"  artifact    {a['type']:<12} {a['path']}")
        if r.get("usage"):
            print(f"  usage       {r['usage']}")
        if r.get("event_seq") is not None:
            print(f"  event_seq   {r['event_seq']}")
    elif r.get("command") == "status":
        print(f"执行结果 {r['count']} 条 (审批 {r.get('approval_count', 0)} 条)")
        for res in r.get("results", []):
            print(f"  {res['id']}  {res['status']:<8} {res['request_id']}")
        if r.get("event_seq") is not None:
            print(f"  event_seq   {r['event_seq']}")
    elif r.get("command") == "providers":
        print("Provider 配置预检:")
        for p in r.get("providers", []):
            mark = "✓" if p["configured"] else "✗"
            print(f"  [{mark}] {p['provider_id']:<10} key={p['key_var']}")
        for pid in r.get("blocked", []):
            print(f"      → {pid} 未配置: key 缺失 → 真实调用 BLOCKED (设置指引见 JSON 输出)")
        print(f"  → {r.get('message', '')}")
        if r.get("event_seq") is not None:
            print(f"  event_seq   {r['event_seq']}")
    elif r.get("command") in ("approval approve", "approval deny"):
        ap = r["approval"]
        print(f"审批 {ap['decision']}: {ap['id']}")
        print(f"  request_id  {ap['request_id']}")
        print(f"  decided_by  {ap['decided_by']}")
        if ap.get("comment"):
            print(f"  comment     {ap['comment']}")
        if r.get("event_seq") is not None:
            print(f"  event_seq   {r['event_seq']}")
    elif r.get("command") == "approval apply":
        ap = r["approval"]
        print(f"✔ patch 已应用: {ap['id']} (diff {r['patch_lines']} 行)")
        if r.get("event_seq") is not None:
            print(f"  event_seq   {r['event_seq']}")
    elif r.get("command") == "approval list":
        print(f"审批记录 {r['count']} 条")
        for ap in r.get("approvals", []):
            print(f"  {ap['id']}  {ap['decision']:<10} {ap['request_id']}  by {ap['decided_by']}")
        if r.get("event_seq") is not None:
            print(f"  event_seq   {r['event_seq']}")


def main(argv: list[str] | None = None) -> int:
    """factory-exec CLI 入口 (console script `factory-exec` 以返回值作退出码)。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else DEFAULT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    result = _dispatch(root, args)
    exit_code = int(result.get("exit_code", 0))
    if getattr(args, "json", False) and result.get("ok"):
        import json as _json

        print(_json.dumps(result, ensure_ascii=False, indent=2))
    elif exit_code != 2:
        _print_result(args, result)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
