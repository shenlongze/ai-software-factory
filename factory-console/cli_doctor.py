"""factory-console/cli_doctor.py — S10-026 P1: factory doctor 可扩展诊断框架。

用户需求 (S10-026 §2.2): `factory doctor` 一键诊断环境/Provider/模型/运行时/
Router, 输出人类可读表格或 --json 结构化结果 (不新增 AI 能力, 零新依赖)。

架构 (Checker Registry — 非硬编码五维, 未来模块注册即自动发现):
    DoctorCheck (Protocol):  id / label / run(ctx) -> CheckResult
    CheckResult:             {id, status: PASS|WARN|FAIL, message, details?}
    register() / list_checks() / get_check(): 注册表 — rag/governance/
    agent-policy 等未来检查器只需实现 DoctorCheck + register()。

内置检查器 (全部复用现有资产, 零新逻辑):
    environment → Python/Node 版本 + venv/node_modules 依赖 + workspace 目录
                  (复用 cli_factory.MIN_PYTHON/MIN_NODE/_node_version)
    provider    → providers.json 存在/enabled/api_key 可解析 (复用 LLMControlPlane)
    model       → models.json 存在/种子写入/enabled 模型数 (复用 ModelCatalog)
    runtime     → 后端 8011 / 前端 5180 端口探测 (复用 cli_factory._port_in_use)
    router      → LLMRouter.route() 无参数能否命中 (复用 LLMRouter)

退出码: 全 PASS → 0; 有 WARN → 0 (带 ⚠ 提示); 有 FAIL → 1; 检查器不存在 → 2。

零副作用铁律: doctor 不写任何数据文件 — ModelCatalog 的种子自举 (缺失文件
自动写入) 只在检查器确认 models.json 已存在后才构造 ModelCatalog; providers.json
缺失场景绝不触发任何写入。

basename: cli_doctor.py 全仓库唯一 (tests/console 用 importlib 加载)。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .cli_factory import MIN_NODE, MIN_PYTHON, _node_version, _port_in_use
from .config import DEFAULT_FRONTEND_PORT, DEFAULT_PORT
from .llm_control import LLMControlPlane, ProviderFileError
from .llm_router import LLMRouter
from .model_catalog import ModelCatalog, ModelCatalogError

# ------------------------------------------------------------------ 状态常量

STATUS_PASS = "PASS"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"

#: environment 检查器检查的工作目录 (~/.factory 下; 与 S10-026 init 一致)
WORKSPACE_DIRS = ("agents", "skills", "projects", "providers", "workspace")


# ------------------------------------------------------------------ 协议与结果


class DoctorCheck(Protocol):
    """诊断检查器协议 (可扩展框架核心)。

    未来新模块 (rag/governance/agent-policy/ai-provider) 实现该协议 →
    register() → factory doctor 自动发现, 无需改动本模块。
    """

    id: str  # 检查器唯一 id ("environment" / "provider" / ...)
    label: str  # 人类可读名

    def run(self, ctx: "DoctorContext") -> "CheckResult": ...


@dataclass
class CheckResult:
    """单检查器结果: 状态 + 人类可读消息 + 可选结构化详情。"""

    id: str
    status: str  # PASS / WARN / FAIL
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON 输出形状: {id, status, message, details?}。"""
        out: dict[str, Any] = {
            "id": self.id,
            "status": self.status,
            "message": self.message,
        }
        if self.details is not None:
            out["details"] = self.details
        return out


# ------------------------------------------------------------------ 上下文


class DoctorContext:
    """检查器上下文: 数据目录 + 仓库根 + 端口 + 资产惰性装配。

    - data_dir: ~/.factory 等价物 (测试注入 tmp_path 完全隔离)
    - root: 仓库根 (environment 检查 .venv/node_modules)
    - control_plane / model_catalog: 惰性装配 (零副作用铁律 — 仅在
      对应数据文件存在时才安全构造; 见各检查器前置检查)
    - environ: key 解析环境 (缺省 os.environ; 测试注入 dict 隔离)
    """

    def __init__(
        self,
        *,
        data_dir: str | Path,
        root: str | Path | None = None,
        backend_port: int = DEFAULT_PORT,
        frontend_port: int = DEFAULT_FRONTEND_PORT,
        control_plane: LLMControlPlane | None = None,
        model_catalog: ModelCatalog | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.root = Path(root).resolve() if root is not None else None
        self.backend_port = int(backend_port)
        self.frontend_port = int(frontend_port)
        self._environ = os.environ if environ is None else environ
        self._control_plane = control_plane
        self._model_catalog = model_catalog

    @property
    def control_plane(self) -> LLMControlPlane:
        """providers.json 读取面 (缺失 → 空配置, 不写文件 — 零副作用)。"""
        if self._control_plane is None:
            self._control_plane = LLMControlPlane(
                providers_file=self.data_dir / "providers.json", environ=self._environ
            )
        return self._control_plane

    @property
    def model_catalog(self) -> ModelCatalog:
        """models.json 读取面 — 仅文件已存在时构造 (缺省会触发种子写入)。

        零副作用铁律: 调用方 (ModelCheck/RouterCheck) 必须先确认
        models.json 存在, 再访问本属性。
        """
        if self._model_catalog is None:
            self._model_catalog = ModelCatalog(models_file=self.data_dir / "models.json")
        return self._model_catalog


def build_context(
    *,
    data_dir: str | Path | None = None,
    root: str | Path | None = None,
    backend_port: int | None = None,
    frontend_port: int | None = None,
    control_plane: LLMControlPlane | None = None,
    model_catalog: ModelCatalog | None = None,
    environ: dict[str, str] | None = None,
) -> DoctorContext:
    """默认上下文: data_dir=~/.factory, 端口取配置默认 (CLI 可覆盖注入)。"""
    return DoctorContext(
        data_dir=data_dir if data_dir is not None else Path.home() / ".factory",
        root=root,
        backend_port=DEFAULT_PORT if backend_port is None else backend_port,
        frontend_port=DEFAULT_FRONTEND_PORT if frontend_port is None else frontend_port,
        control_plane=control_plane,
        model_catalog=model_catalog,
        environ=environ,
    )


# ------------------------------------------------------------------ 注册表


#: 检查器注册表 (id → DoctorCheck)。非硬编码五维 — 未来模块 register 即被发现。
_CHECKS: dict[str, DoctorCheck] = {}


def register(check: DoctorCheck) -> None:
    """注册检查器; id 缺失/重复 → 响亮 ValueError (不静默覆盖)。"""
    if not isinstance(getattr(check, "id", None), str) or not check.id:
        raise ValueError(f"cli_doctor: check id must be a non-empty string, got {check!r}")
    if check.id in _CHECKS:
        raise ValueError(f"cli_doctor: duplicate check id {check.id!r}")
    _CHECKS[check.id] = check


def list_checks() -> list[DoctorCheck]:
    """全部已注册检查器 (按注册序; 未来模块注册后自动出现)。"""
    return list(_CHECKS.values())


def get_check(checker_id: str) -> DoctorCheck | None:
    """按 id 取检查器; 不存在 → None。"""
    return _CHECKS.get(checker_id)


# ------------------------------------------------------------------ 内置检查器


class EnvironmentCheck:
    """environment: Python ≥3.10 / Node ≥18 / venv / node_modules / workspace 目录。

    复用 cli_factory.MIN_PYTHON / MIN_NODE / _node_version; Python 版本过低
    → FAIL (阻断), 其余缺失 → WARN (可修复, 提示 init/install)。
    """

    id = "environment"
    label = "环境检查 (Python/Node/依赖/工作目录)"

    def run(self, ctx: DoctorContext) -> CheckResult:
        problems: list[str] = []
        py = sys.version_info[:2]
        if py < MIN_PYTHON:
            problems.append(
                f"Python 版本过低: {py[0]}.{py[1]} (需要 ≥{MIN_PYTHON[0]}.{MIN_PYTHON[1]})"
            )
        node = _node_version()
        if node is None:
            problems.append(f"未找到 Node.js — 请安装 ≥{MIN_NODE[0]} (https://nodejs.org)")
        elif node < MIN_NODE:
            problems.append(f"Node.js 版本过低: {node[0]}.{node[1]} (需要 ≥{MIN_NODE[0]})")
        if ctx.root is None:
            problems.append("仓库根未知 — 无法检查 venv/node_modules 依赖")
        elif not (ctx.root / "pyproject.toml").is_file():
            # S10-078: wheel 安装模式 (无源码仓库) — 前端 dist 已打包, 无需 venv/node_modules
            pass
        else:
            venv_py = ctx.root / ".venv" / "bin" / "python"
            if not venv_py.is_file():
                problems.append(
                    f"未找到虚拟环境: {venv_py} — 请运行 python3 -m venv .venv "
                    "&& .venv/bin/pip install -e '.[dev]'"
                )
            node_modules = ctx.root / "factory-console" / "web" / "frontend" / "node_modules"
            if not node_modules.is_dir():
                problems.append(
                    f"前端依赖缺失: {node_modules} — 请运行 cd {node_modules.parent} && npm install"
                )
        missing = [name for name in WORKSPACE_DIRS if not (ctx.data_dir / name).is_dir()]
        details: dict[str, Any] = {
            "python": f"{py[0]}.{py[1]}",
            "node": f"{node[0]}.{node[1]}" if node else None,
            "missing_workspace_dirs": missing,
        }
        if missing:
            problems.append(
                f"工作目录缺失: {', '.join(missing)} — 请运行 factory init"
            )
        if not problems:
            return CheckResult(self.id, STATUS_PASS, "环境正常 (Python/Node/依赖/工作目录)", details)
        # Python 版本过低 → FAIL (阻断); 其余可修复项 → WARN
        status = STATUS_FAIL if any(p.startswith("Python 版本过低") for p in problems) else STATUS_WARN
        return CheckResult(self.id, status, "; ".join(problems), details)


class ProviderCheck:
    """provider: providers.json 存在? enabled provider? api_key 可解析?

    复用 LLMControlPlane (get_provider/is_enabled/resolve_api_key);
    缺失 providers.json → FAIL (提示先 factory init); 损坏 → FAIL;
    无 enabled / key 缺失 → WARN; 全就绪 → PASS。
    """

    id = "provider"
    label = "Provider 配置 (providers.json)"

    def run(self, ctx: DoctorContext) -> CheckResult:
        providers_file = ctx.data_dir / "providers.json"
        try:
            plane = ctx.control_plane
        except ProviderFileError as exc:
            return CheckResult(
                self.id,
                STATUS_FAIL,
                f"providers.json 损坏: {exc}",
                {"path": str(providers_file)},
            )
        if not providers_file.exists():
            return CheckResult(
                self.id,
                STATUS_FAIL,
                f"providers.json 不存在 ({providers_file}) — 请先运行 factory init 配置 LLM Provider",
                {"path": str(providers_file)},
            )
        providers = plane.list_providers()
        enabled = plane.enabled_providers()
        details: dict[str, Any] = {
            "path": str(providers_file),
            "providers": len(providers),
            "enabled": len(enabled),
            "enabled_ids": [p.id for p in enabled],
        }
        if not enabled:
            return CheckResult(
                self.id,
                STATUS_WARN,
                "providers.json 存在但无 enabled provider — 请启用至少一个 provider (factory init)",
                details,
            )
        missing_key = [
            p.id for p in enabled if p.id != "ollama" and not plane.resolve_api_key(p.id)
        ]
        details["missing_api_key"] = missing_key
        if missing_key:
            return CheckResult(
                self.id,
                STATUS_WARN,
                f"enabled provider 缺少 API key: {', '.join(missing_key)} — "
                "请配置 api_key_ref (如 env:DEEPSEEK_API_KEY)",
                details,
            )
        return CheckResult(
            self.id, STATUS_PASS, f"{len(enabled)} 个 enabled provider, API key 均可解析", details
        )


class ModelCheck:
    """model: models.json 存在? 种子写入? enabled 模型数?

    复用 ModelCatalog.list_models (include_disabled 对比); 缺失 → WARN
    (提示 init 后自动 seed, 且不触发种子写入 — 零副作用); 损坏 → FAIL。
    """

    id = "model"
    label = "模型目录 (models.json)"

    def run(self, ctx: DoctorContext) -> CheckResult:
        models_file = ctx.data_dir / "models.json"
        if not models_file.exists():
            return CheckResult(
                self.id,
                STATUS_WARN,
                f"models.json 不存在 ({models_file}) — 运行 factory init 后 "
                "ModelCatalog 将自动写入内置种子",
                {"path": str(models_file), "seeded": False},
            )
        try:
            catalog = ctx.model_catalog  # 文件已存在 → 无种子写入副作用
            enabled = catalog.list_models()
            total = catalog.list_models(include_disabled=True)
        except ModelCatalogError as exc:
            return CheckResult(
                self.id, STATUS_FAIL, f"models.json 损坏: {exc}", {"path": str(models_file)}
            )
        details: dict[str, Any] = {
            "path": str(models_file),
            "models": len(total),
            "enabled": len(enabled),
        }
        if not enabled:
            return CheckResult(
                self.id,
                STATUS_WARN,
                "models.json 存在但无 enabled 模型 — 请启用至少一个模型",
                details,
            )
        return CheckResult(self.id, STATUS_PASS, f"{len(enabled)}/{len(total)} 个模型 enabled", details)


class RuntimeCheck:
    """runtime: 后端 8011 / 前端 5180 是否在运行 (端口探测)。

    复用 cli_factory._port_in_use (等价端口探测); 全在 → PASS;
    任一未运行 → WARN (服务未启动可修复, 提示 factory start)。
    """

    id = "runtime"
    label = "运行时服务 (后端/前端端口)"

    def run(self, ctx: DoctorContext) -> CheckResult:
        backend = _port_in_use(ctx.backend_port)
        frontend = _port_in_use(ctx.frontend_port)
        details: dict[str, Any] = {
            "backend_port": ctx.backend_port,
            "backend_running": backend,
            "frontend_port": ctx.frontend_port,
            "frontend_running": frontend,
        }
        if backend and frontend:
            return CheckResult(
                self.id,
                STATUS_PASS,
                f"后端 ({ctx.backend_port}) 与前端 ({ctx.frontend_port}) 均在运行",
                details,
            )
        down = []
        if not backend:
            down.append(f"后端 {ctx.backend_port}")
        if not frontend:
            down.append(f"前端 {ctx.frontend_port}")
        return CheckResult(
            self.id,
            STATUS_WARN,
            "未运行: " + ", ".join(down) + " — 请运行 factory start",
            details,
        )


class RouterCheck:
    """router: LLMRouter.route() 无参数能否命中。

    复用 LLMRouter (构造 control_plane + model_catalog; models.json 不存在时
    不传 catalog — 避免种子写入且 L4 跳过, 只走 L5 fallback); 命中 → PASS
    显示 source; 无可用 provider → WARN; 决策异常/数据损坏 → FAIL。
    """

    id = "router"
    label = "LLM Router 决策链"

    def run(self, ctx: DoctorContext) -> CheckResult:
        try:
            plane = ctx.control_plane
            catalog = None
            if (ctx.data_dir / "models.json").exists():
                catalog = ctx.model_catalog  # 文件存在 → 无种子写入副作用
            router = LLMRouter(
                control_plane=plane,
                model_catalog=catalog,
                agents_dir=ctx.data_dir / "agents",
                skills_dir=ctx.data_dir / "skills",
            )
            choice = router.route()
        except Exception as exc:  # noqa: BLE001 — 诊断失败安全: 任何异常 → FAIL 不崩溃
            return CheckResult(self.id, STATUS_FAIL, f"Router 决策异常: {exc}", {"error": str(exc)})
        if choice is None:
            return CheckResult(
                self.id,
                STATUS_WARN,
                "Router 无可用 provider — 请先 factory init 配置并启用 provider",
                {"hit": False},
            )
        return CheckResult(
            self.id,
            STATUS_PASS,
            f"Router 可命中: {choice.provider_id}/{choice.model_id or '(默认模型)'} "
            f"(source={choice.source})",
            {
                "hit": True,
                "provider_id": choice.provider_id,
                "model_id": choice.model_id,
                "source": choice.source,
            },
        )


def _register_builtin() -> None:
    """内置 5 检查器注册 (模块加载时; 未来模块各自 register, 本函数不动)。"""
    for check in (
        EnvironmentCheck(),
        ProviderCheck(),
        ModelCheck(),
        RuntimeCheck(),
        RouterCheck(),
    ):
        register(check)


_register_builtin()


# ------------------------------------------------------------------ 输出


def _print_human(results: list[CheckResult], summary: dict[str, int], verbose: bool) -> None:
    """人类可读表格输出 (stdout; FAIL 汇总提示走 stderr)。"""
    icons = {STATUS_PASS: "✓", STATUS_WARN: "⚠", STATUS_FAIL: "✗"}
    print("=== AI Factory Doctor ===")
    if not results:
        print("  (注册表为空 — 无可用检查器)")
    for r in results:
        icon = icons.get(r.status, "?")
        print(f"  {icon} [{r.status}] {r.id}: {r.message}")
        if verbose and r.details:
            for key, value in r.details.items():
                print(f"      {key}: {value}")
    print(f"  汇总: {summary['pass']} PASS / {summary['warn']} WARN / {summary['fail']} FAIL")
    if summary["warn"]:
        print("  ⚠ 存在 WARN 项 — 建议按上方提示处理 (不影响退出码)")
    if summary["fail"]:
        print("  ✗ 存在 FAIL 项 — 请先修复后重试 (退出码 1)", file=sys.stderr)


def run_doctor(
    checkers: list[str] | None = None,
    *,
    ctx: DoctorContext | None = None,
    json_mode: bool = False,
    verbose: bool = False,
) -> int:
    """运行诊断并输出; 返回退出码。

    - checkers: 指定检查器 id 列表 (缺省全部已注册); 未知 id → 打印可用
      列表到 stderr 并返回 2
    - json_mode: 输出 {checks: [{id,status,message,details}], summary}
    - 退出码: 全 PASS → 0; 有 WARN → 0; 有 FAIL → 1; 检查器不存在 → 2
    """
    ctx = ctx if ctx is not None else build_context()
    if checkers:
        selected: list[DoctorCheck] = []
        for cid in checkers:
            check = get_check(cid)
            if check is None:
                print(
                    f"未知检查器: {cid} (可用: {', '.join(sorted(_CHECKS))})",
                    file=sys.stderr,
                )
                return 2
            selected.append(check)
    else:
        selected = list_checks()

    results = [check.run(ctx) for check in selected]
    summary = {
        "pass": sum(1 for r in results if r.status == STATUS_PASS),
        "warn": sum(1 for r in results if r.status == STATUS_WARN),
        "fail": sum(1 for r in results if r.status == STATUS_FAIL),
    }
    if json_mode:
        print(
            json.dumps(
                {"checks": [r.to_dict() for r in results], "summary": summary},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_human(results, summary, verbose)
    return 1 if summary["fail"] else 0


__all__ = [
    "STATUS_FAIL",
    "STATUS_PASS",
    "STATUS_WARN",
    "WORKSPACE_DIRS",
    "CheckResult",
    "DoctorCheck",
    "DoctorContext",
    "EnvironmentCheck",
    "ModelCheck",
    "ProviderCheck",
    "RouterCheck",
    "RuntimeCheck",
    "build_context",
    "get_check",
    "list_checks",
    "register",
    "run_doctor",
]
