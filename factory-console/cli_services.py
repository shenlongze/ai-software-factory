"""factory-console/cli_services.py — S10-026 P3: Runtime Manager (factory start 服务注册表)。

用户需求 (S10-026 §2.4): `factory start` 从硬编码 backend/frontend 重构为
Services Registry — start/stop/status 改调注册表, 新增 `factory service list`。
未来 vector-db/gateway 等服务只需实现 ServiceDef 协议 + register() 即被发现。

架构 (Service Registry — 不硬编码 backend/frontend):
    ServiceDef (Protocol):  id / label / start(ctx)->ServiceHandle /
                            stop(handle) / status(ctx)->ServiceStatus
    ServiceHandle:          {id, ok, pid, pid_file, port, detail} — start 返回,
                            stop 消费 (stop 由句柄自含 pid_file+port, 不依赖 ctx)
    ServiceStatus:          {id, state: running|stopped, detail, pid, port, url}
    register() / list_services() / get_service(): 注册表 — 未来模块
                            register 即被发现, 本模块零改动。

内置 3 服务 (本 Sprint):
    backend  → uvicorn + create_app(factory_root) — 包装现有
               cli_factory._start_backend (复用代码体, 不重复实现)
    frontend → 默认托管 dist (uvicorn + create_app(static_dir=dist), SPA
               同源 /api 可用); --dev 走 vite dev — 包装现有
               cli_factory._start_frontend(dev=...)
    runtime  → 沙箱 runtime 状态探测 (S10-023 能力; 无独立常驻进程 —
               start 占位提示, status 报按需调度)

退出码: factory service list → 0 (列表展示); 服务不存在 → 2 (由
cli_factory 解析层返回)。

依赖方向: cli_services 只复用 cli_factory 的模块级 IO 函数
(_read_pid/_pid_alive/_port_in_use/_stop_one) 与 FactoryCLI 原语
(经 ServiceContext.cli 鸭子类型包装调用); cli_factory 在方法内惰性
import 本模块 — 无循环导入 (同 cli_doctor 模式)。

basename: cli_services.py 全仓库唯一 (tests/console 用 importlib 加载)。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from . import cli_factory as _factory  # 调用时解析模块属性 — monkeypatch 兼容
from .config import DEFAULT_FRONTEND_PORT, DEFAULT_PORT

# ------------------------------------------------------------------ 状态常量

STATE_RUNNING = "running"
STATE_STOPPED = "stopped"

#: 服务注册表 (id → ServiceDef)。非硬编码三服务 — 未来模块 register 即被发现。
_SERVICES: dict[str, "ServiceDef"] = {}


# ------------------------------------------------------------------ 协议与数据


class ServiceDef(Protocol):
    """服务定义协议 (Runtime Manager 核心)。

    未来新服务 (vector-db/gateway/...) 实现该协议 → register() →
    `factory service list` / `factory start <id>` 自动支持, 无需改动
    cli_factory 与 cli_services。内置服务另有可选扩展:
    - wait_ready(ctx, handle) -> bool: 启动后健康检查 (缺省跳过)
    - current_handle(ctx) -> ServiceHandle: stop-all 时按当前状态构造句柄
    - port(ctx) -> int | None: 端口预检/stop 端口告警用
    - log_path(ctx) -> Path | None: 健康检查失败时日志尾部
    - rollback: "all" (停全部已起服务) | "pids" (仅清理 pid 文件)
    - short_label: `factory status`/预检输出中文短名 (与旧 CLI 一致)
    """

    id: str  # 服务唯一 id ("backend" / "frontend" / "runtime" / ...)
    label: str  # 人类可读名

    def start(self, ctx: "ServiceContext") -> "ServiceHandle": ...
    def stop(self, handle: "ServiceHandle") -> None: ...
    def status(self, ctx: "ServiceContext") -> "ServiceStatus": ...


@dataclass
class ServiceHandle:
    """服务句柄: start 返回 / stop 消费。

    stop 自含 pid_file+port+cli (停止原语提供者) — 不依赖 ctx, 满足
    ServiceDef.stop(handle) 协议签名; cli 为 FactoryCLI 实例 (鸭子类型),
    使停止路径复用同一 _stop_one 实例方法 (monkeypatch 兼容)。
    """

    id: str
    ok: bool = False  # 启动调用是否成功 (含"已在运行"幂等成功)
    pid: int | None = None
    pid_file: Path | None = None
    port: int | None = None
    detail: str = ""
    cli: Any = None


@dataclass
class ServiceStatus:
    """服务状态: running/stopped + 多视图信息。

    - detail: `factory status` 人类可读行 (中文, 与旧 CLI 输出一致)
    - pid / port / url: `factory service list` 结构化展示
    - note: 列表视图补充说明 (如 runtime 的按需调度提示)
    """

    id: str
    state: str  # STATE_RUNNING / STATE_STOPPED
    detail: str = ""
    pid: int | None = None
    port: int | None = None
    url: str | None = None
    note: str = ""


class ServiceContext:
    """服务上下文: 目录/端口/CLI 原语装配。

    - data_dir: ~/.factory 等价物 (测试注入 tmp_path 完全隔离)
    - root: 仓库根 (frontend dist 定位)
    - backend_port / frontend_port: 端口 (配置/--port 覆盖)
    - dev_mode: frontend 是否走 vite dev (缺省 False → 托管 dist)
    - cli: FactoryCLI 实例 (鸭子类型) — 提供 _start_backend/_start_frontend/
      _wait_backend/_wait_frontend/backend_pid/frontend_pid/backend_log/
      frontend_log 等原语; 测试可注入假对象
    """

    def __init__(
        self,
        *,
        data_dir: str | Path,
        root: str | Path | None = None,
        backend_port: int = DEFAULT_PORT,
        frontend_port: int = DEFAULT_FRONTEND_PORT,
        dev_mode: bool = False,
        cli: Any = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.root = Path(root).resolve() if root is not None else None
        self.backend_port = int(backend_port)
        self.frontend_port = int(frontend_port)
        self.dev_mode = bool(dev_mode)
        self.cli = cli


# ------------------------------------------------------------------ 注册表


def register(service: ServiceDef) -> None:
    """注册服务; id 缺失/重复 → 响亮 ValueError (不静默覆盖)。"""
    if not isinstance(getattr(service, "id", None), str) or not service.id:
        raise ValueError(f"cli_services: service id must be a non-empty string, got {service!r}")
    if service.id in _SERVICES:
        raise ValueError(f"cli_services: duplicate service id {service.id!r}")
    _SERVICES[service.id] = service


def list_services() -> list[ServiceDef]:
    """全部已注册服务 (按注册序; 未来模块注册后自动出现)。"""
    return list(_SERVICES.values())


def get_service(service_id: str) -> ServiceDef | None:
    """按 id 取服务; 不存在 → None。"""
    return _SERVICES.get(service_id)


# ------------------------------------------------------------------ 内置服务


class BackendService:
    """backend: uvicorn + create_app(factory_root) — 现有 _start_backend 迁入。"""

    id = "backend"
    label = "后端 (uvicorn + FastAPI)"
    short_label = "后端"
    rollback = "pids"  # 健康检查失败 → 仅清理 pid 文件 (前端未起, 无需全停)
    fail_message = "  ✗ 后端启动失败 (健康检查超时, 详见上方日志尾部)"

    def port(self, ctx: ServiceContext) -> int:
        return ctx.backend_port

    def log_path(self, ctx: ServiceContext) -> Path | None:
        return ctx.cli.backend_log if ctx.cli is not None else None

    def start(self, ctx: ServiceContext) -> ServiceHandle:
        # 包装现有 _start_backend (代码体不重复实现; 幂等提示在内部)
        ok = bool(ctx.cli._start_backend(ctx.backend_port))
        return ServiceHandle(
            id=self.id,
            ok=ok,
            pid=_factory._read_pid(ctx.cli.backend_pid),
            pid_file=ctx.cli.backend_pid,
            port=ctx.backend_port,
            cli=ctx.cli,
        )

    def wait_ready(self, ctx: ServiceContext, handle: ServiceHandle) -> bool:
        return bool(ctx.cli._wait_backend(ctx.backend_port))

    def current_handle(self, ctx: ServiceContext) -> ServiceHandle:
        """stop-all 时按当前状态构造句柄 (读 pid 文件 + 记停止原语提供者)。"""
        return ServiceHandle(
            id=self.id,
            pid=_factory._read_pid(ctx.cli.backend_pid),
            pid_file=ctx.cli.backend_pid,
            port=ctx.backend_port,
            cli=ctx.cli,
        )

    def stop(self, handle: ServiceHandle) -> int | None:
        """经句柄携带的 FactoryCLI 原语停止 (pid 文件优先, 兜底按端口)。"""
        return handle.cli._stop_one(handle.pid_file, handle.port or 0)

    def status(self, ctx: ServiceContext) -> ServiceStatus:
        return _process_status(
            self,
            ctx,
            port=ctx.backend_port,
            pid_file=ctx.cli.backend_pid,
            running_check=lambda: bool(ctx.cli._backend_running()),
        )


class FrontendService:
    """frontend: 默认托管 dist (SPA, 同源 /api), --dev 走 vite — 现有 _start_frontend 改造。"""

    id = "frontend"
    label = "前端 (dist 托管 / vite dev)"
    short_label = "前端"
    rollback = "all"  # 健康检查失败 → 停全部已起服务 (回滚后端, 与旧行为一致)
    fail_message = "  ✗ 前端启动失败 (详见上方日志尾部)"

    def port(self, ctx: ServiceContext) -> int:
        return ctx.frontend_port

    def log_path(self, ctx: ServiceContext) -> Path | None:
        return ctx.cli.frontend_log if ctx.cli is not None else None

    def start(self, ctx: ServiceContext) -> ServiceHandle:
        # 包装现有 _start_frontend; dev=False 时不传 dev kwarg —
        # 兼容既有 monkeypatch (lambda port: True) 与旧调用面
        if ctx.dev_mode:
            ok = bool(ctx.cli._start_frontend(ctx.frontend_port, dev=True))
        else:
            ok = bool(ctx.cli._start_frontend(ctx.frontend_port))
        return ServiceHandle(
            id=self.id,
            ok=ok,
            pid=_factory._read_pid(ctx.cli.frontend_pid),
            pid_file=ctx.cli.frontend_pid,
            port=ctx.frontend_port,
            cli=ctx.cli,
        )

    def wait_ready(self, ctx: ServiceContext, handle: ServiceHandle) -> bool:
        return bool(ctx.cli._wait_frontend(ctx.frontend_port))

    def current_handle(self, ctx: ServiceContext) -> ServiceHandle:
        return ServiceHandle(
            id=self.id,
            pid=_factory._read_pid(ctx.cli.frontend_pid),
            pid_file=ctx.cli.frontend_pid,
            port=ctx.frontend_port,
            cli=ctx.cli,
        )

    def stop(self, handle: ServiceHandle) -> int | None:
        return handle.cli._stop_one(handle.pid_file, handle.port or 0)

    def status(self, ctx: ServiceContext) -> ServiceStatus:
        return _process_status(
            self,
            ctx,
            port=ctx.frontend_port,
            pid_file=ctx.cli.frontend_pid,
            running_check=lambda: bool(ctx.cli._frontend_running()),
        )


def _process_status(
    svc: Any,
    ctx: ServiceContext,
    *,
    port: int,
    pid_file: Path,
    running_check=None,
) -> ServiceStatus:
    """后端/前端通用状态探测: pid + 端口 → running/stopped + 多视图字段。

    状态机与旧 cli_factory.status 完全一致:
    pid 存活+端口监听 → 运行中; pid 存活但端口未监听 → 进程在; 仅端口监听 →
    未托管进程占用; 否则 → 未运行。running_check 缺省走 pid 文件判活
    (经 cli_factory 模块属性调用 — monkeypatch 兼容)。
    """
    pid = _factory._read_pid(pid_file)
    if running_check is not None:
        alive = bool(running_check())
    else:
        alive = pid is not None and bool(_factory._pid_alive(pid))
    listening = bool(_factory._port_in_use(port))
    url = f"http://127.0.0.1:{port}"
    if alive and listening:
        return ServiceStatus(
            svc.id, STATE_RUNNING, f"运行中 (PID {pid}) — 端口 {port} 监听中", pid, port, url
        )
    if alive:
        return ServiceStatus(
            svc.id, STATE_RUNNING, f"进程在但端口未监听 (PID {pid}) — 端口 {port} 空闲", pid, port, url
        )
    if listening:
        return ServiceStatus(
            svc.id, STATE_STOPPED, f"未托管进程占用端口 — 端口 {port} 监听中", pid, port
        )
    return ServiceStatus(svc.id, STATE_STOPPED, f"未运行 — 端口 {port} 空闲", pid, port)


class RuntimeService:
    """runtime: 沙箱 runtime 状态探测 (S10-023 能力; 无独立常驻进程)。

    start 占位提示 (按需调度, 不拉起进程); status 报按需调度。
    """

    id = "runtime"
    label = "沙箱运行时 (S10-023, 按需调度)"
    short_label = "运行时"

    def start(self, ctx: ServiceContext) -> ServiceHandle:
        print("  ⚠ runtime 服务无独立常驻进程 — 沙箱按需调度 (执行项目时自动拉起)。")
        return ServiceHandle(id=self.id, ok=True, detail="按需调度")

    def stop(self, handle: ServiceHandle) -> None:
        return None

    def status(self, ctx: ServiceContext) -> ServiceStatus:
        return ServiceStatus(
            self.id,
            STATE_STOPPED,
            "按需调度 (无常驻进程 — 执行项目时自动拉起)",
            note="按需调度 (无常驻进程)",
        )


class BoardService:
    """board: 任务监控面板 — 懒加载服务 (无常驻进程)。

    随 factory start 注册（`factory service list` 可见）; 能力:
    - 会话 /board 命令（文本面板, 已有 commands.py）
    - /api/board Web 端点（懒加载 — 首次访问才渲染, 不常驻资源）
    生命周期: 注册✅ 发现✅ 运行✅(懒加载) 执行✅(/board+/api/board)
              治理✅(service start/stop) 监控✅(service status)
    """

    id = "board"
    label = "任务监控面板 (todolist/依赖图/生命线, 懒加载)"
    short_label = "监控面板"
    rollback = "none"

    def port(self, ctx: ServiceContext) -> int | None:
        return None  # 无独立端口（懒加载端点）

    def start(self, ctx: ServiceContext) -> ServiceHandle:
        # 懒加载: 不启动进程, 注册端点即可（首次 /api/board 访问渲染）
        return ServiceHandle(
            id=self.id,
            ok=True,
            pid=None,
            pid_file=None,
            port=None,
            detail="懒加载（/board 会话命令 + /api/board 端点, 首次访问渲染）",
        )

    def stop(self, handle: ServiceHandle) -> None:
        return None  # 无进程, 无操作

    def status(self, ctx: ServiceContext) -> ServiceStatus:
        base = f"http://127.0.0.1:{ctx.backend_port}"
        return ServiceStatus(
            self.id,
            STATE_RUNNING,
            "懒加载服务 (会话 /board + Web /api/board, 首次访问渲染)",
            url=f"{base}/api/board",
            note="访问: 会话 /board · Web /api/board (需 backend 运行)",
        )


def _register_builtin() -> None:
    """内置 3 服务注册 (模块加载时; 未来服务各自 register, 本函数不动)。"""
    for service in (
        BackendService(),
        FrontendService(),
        RuntimeService(),
        BoardService(),  # S10-1xx: 监控面板懒加载服务（随启动注册）
    ):
        register(service)


_register_builtin()


# ------------------------------------------------------------------ 输出


def run_service_list(ctx: ServiceContext) -> int:
    """`factory service list`: 每个已注册服务一行状态 (验收 A 输出结构)。

    示例:
        factory service list:
          backend   running   (PID 12345, http://127.0.0.1:8011)
          frontend  stopped
          runtime   stopped
    """
    print("factory service list:")
    for svc in list_services():
        st = svc.status(ctx)
        if st.state == STATE_RUNNING:
            if st.url:
                extra = f"(PID {st.pid}, {st.url})"
            else:
                extra = f"(PID {st.pid})" if st.pid else ""
        else:
            extra = st.note
        print(f"  {st.id:<10}{st.state:<10}{extra}".rstrip())
    return 0


__all__ = [
    "STATE_RUNNING",
    "STATE_STOPPED",
    "BackendService",
    "FrontendService",
    "RuntimeService",
    "ServiceContext",
    "ServiceDef",
    "ServiceHandle",
    "ServiceStatus",
    "get_service",
    "list_services",
    "register",
    "run_service_list",
]
