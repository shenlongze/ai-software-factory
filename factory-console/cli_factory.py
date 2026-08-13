"""factory-console/cli_factory.py — S10-007 阶段二: factory CLI MVP (start/stop/status)。

用户需求 (S10-007): 一条 `./bin/factory` 命令即可启动本地开发环境, 不要求
用户懂 uvicorn/vite/PYTHONPATH/npm:

    factory start   环境检查 (python ≥3.10 / node ≥18) → 依赖检查 (.venv /
                    node_modules, 缺失给 install 提示) → 配置检查 (LLM key
                    缺失仅提示 .env.example 指引, 不阻断) → 后端 (uvicorn,
                    后台, pid 文件) → 前端 (默认托管 dist, --dev 走 vite
                    --strictPort, 后台, pid 文件) → 健康检查 (轮询
                    /api/projects 200) → 打开浏览器
    factory stop    读 pid 文件杀前后端 (干净); 无 pid → 按端口 (lsof) 找
    factory status  端口 / 进程 / 数据目录 / LLM provider 状态

S10-026 P3 (Runtime Manager): start/stop/status 内部改调 Services Registry
(cli_services — ServiceDef 协议 + backend/frontend/runtime 三服务), CLI 契约
不变: `factory start` 无参数 = 启动全部内置服务 (backend+frontend), 行为与
旧版完全一致 (幂等/端口预检/健康检查/打开浏览器); 新增 `factory start
<service_id>` 只启动指定服务; 新增 `factory service list` 展示注册表状态。

S10-026 Task C (命令组骨架): 新增 agent/skill/task/router/rag/audit 六子命令
(§2.0 CLI 命令组命名空间第一步 — 只建结构 + 薄代理, 不实现新业务逻辑):
    factory agent   只读列出现有 agents (agents.json: id/name/role/skills)
    factory skill   只读列出现有 skills (skills.json / skills/*.json)
    factory task    只读列出 tasks (tasks/*.json: id/title/status)
    factory router  展示 LLMRouter 五层链可用性 + route() 当前决策 (只读)
    factory rag     明确占位 ("RAG 未实现 — 规划中", 不实现功能)
    factory audit   只读查询事件库 (events.db/factory.db 的 events 表:
                    最近事件列表 + 按类型计数)
约束: 全部只读展示, 失败安全 (缺失/损坏 → 空列表提示, 永不抛); 不引入
新依赖 (仅标准库 sqlite3); 不改动 llm_router/llm_control/model_catalog 等。

S10-026 Task D (config 转正, §2.3 Factory Runtime Configuration 修订 ①):
    factory config show   显示运行时配置 (脱敏: key 不显示值, 只显示
                          已配置/未配置状态) + 只读展示 LLM 状态 (不打印 key)
    factory config set <key> <value>  写 config.json 白名单键 (core.data_dir /
                          core.port / core.frontend_port); llm.* → 明确拒绝
                          (红线 ①: config.json 禁存 LLM 偏好 — LLM 配置归
                          providers.json / models.json / agent.yaml·skill.yaml·
                          project.yaml); 未知键/非法端口值 → 拒绝
    factory config check  校验配置: config.json 状态 + providers.json 只读检查
                          (复用 LLMControlPlane list_providers/enabled_providers/
                          resolve_api_key), 输出 OK/WARN, 零副作用
    factory config path   显示配置文件路径 (ConfigProvider 注入可见)

S10-026 Task E (init 转正, §2.1 P0 factory init — 首次运行初始化):
    factory init [--force] [--non-interactive] [--provider <id>] [--model <m>]
    流程: 环境检测 (复用 _env_problems/_dep_problems, 缺失 → 明确提示先装依赖)
    → workspace 初始化 (~/.factory/{agents,skills,projects,providers,workspace}
    幂等创建) → LLM 配置引导 (无 providers.json → 交互向导或参数直写; 已存在
    → 显示当前 + 询问修改, 非交互跳过; --force 重新引导) → 校验 (复用
    LLMControlPlane: enabled? key 可解析? model 列表?) → 下一步提示 (factory
    doctor / factory start)。
    红线: providers.json 只写 api_key_ref 引用 (env:VAR 格式), 绝不写明文 key;
    交互输入非 env: 引用 → 拒绝并回退默认引用; 除 providers.json 外不碰任何文件
    (config.json 归 config 命令管)。

架构预留: project/run 注册为 argparse stub (阶段三实现), 未来可加子子命令
(project list 等) — 不限制扩展。

设计:
- 纯标准库 (argparse/subprocess/socket/urllib) — 零新增依赖。
- 模块级 IO 函数 (测试可 monkeypatch) + FactoryCLI 类 (流程编排)。
- pid 文件 / 日志: <data_dir>/run/{backend,frontend}.pid 与 *.log。
- 后端启动: importlib 加载 factory-console.web.backend.fastapi_adapter
  (包名含连字符, 唯一导入方式) → create_app(factory_root=<data_dir>) →
  uvicorn.run — bootstrap 经 base64 传给子进程, 免引号转义。
- 前端默认托管 dist: 第二个 uvicorn + create_app(static_dir=<frontend>/dist)
  (SPA 同源 /api, 与 vite 代理等价); dist 缺失 → 回退 vite dev 并提示;
  --dev 强制 vite dev (现有 npm run dev 逻辑保留)。
- 幂等: pid 文件 + kill(0) 判活 → 已运行提示, 不重复起。
- 错误处理: 端口预检 (占用 → 明确提示, 含修改配置指引); 启动失败 →
  打印日志尾部 + 回滚已起服务。
- 铁律: 不打印 API key 明文 (status 只显示 已配置/未配置); 不读取任何
  ~/.hermes 路径 (S10-007 P0, 同 config.py); 不修改 Core / fastapi_adapter。

basename: cli_factory.py 全仓库唯一 (tests/console 用 importlib 加载)。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from .config import DEFAULT_PROVIDER, PROVIDER_DEFAULTS, ConfigProvider

# ------------------------------------------------------------------ 常量

#: 最低 Python 版本 (环境检查)
MIN_PYTHON = (3, 10)
#: 最低 Node.js 版本 (环境检查; vite 5 要求 ≥18)
MIN_NODE = (18, 0)
#: 后端 FastAPI adapter (包名含连字符 — 唯一导入方式是 importlib)
BACKEND_MODULE = "factory-console.web.backend.fastapi_adapter"
#: 打开浏览器默认路径 (SPA 工作台)
FRONTEND_PATH = "/#/workspace"
#: pid/日志子目录 (相对数据目录)
RUN_SUBDIR = "run"
#: 后端健康检查端点 (GET → 200 即就绪)
HEALTH_PATH = "/api/projects"
#: 健康检查总超时 (秒)
HEALTH_TIMEOUT = 30.0
#: 前端就绪总超时 (秒, vite 冷启动较快)
FRONTEND_TIMEOUT = 15.0
#: 健康检查轮询间隔 (秒)
HEALTH_INTERVAL = 0.5
#: 架构预留子命令 (阶段三实现; 注册为 stub 不限制扩展; config 已于 Task D 转正,
#: init 已于 Task E 转正)
STUB_COMMANDS = ("project", "run")

#: init 引导的 provider 选择项 (与 config.PROVIDER_DEFAULTS 键集对齐)
INIT_PROVIDERS = ("deepseek", "openai", "anthropic", "ollama")
#: workspace 初始目录 (S10-026 §2.1 step 2; 与 cli_doctor.EnvironmentCheck 同口径)
WORKSPACE_DIRS = ("agents", "skills", "projects", "providers", "workspace")

#: config 白名单 (可写运行时键 — S10-026 Task D §2.3; workspace 等未来扩展位暂不开放)
CONFIG_KEYS = ("core.data_dir", "core.port", "core.frontend_port")
#: 红线键 (S10-026 修订 ①): config.json 禁存 LLM 偏好 — 明确拒绝 + 引导
CONFIG_FORBIDDEN_KEYS = ("llm.provider", "llm.model", "llm.base_url", "llm.api_key_ref")


# ------------------------------------------------------------------ 模块级 IO (可 monkeypatch)


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """TCP 连接测试: 端口已被监听 → True (预检/status/stop 兜底共用)。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def _capture(cmd: Sequence[str]) -> str:
    """运行命令并捕获 stdout (失败/超时/缺失 → 空串; 永不抛)。"""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001 — 环境探测失败安全
        return ""
    return (proc.stdout or "").strip()


def _node_version() -> tuple[int, int] | None:
    """`node --version` → (major, minor); node 缺失/解析失败 → None。"""
    out = _capture(["node", "--version"])  # 形如 v26.4.0
    if not out.startswith("v"):
        return None
    parts = out[1:].split(".")
    try:
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None


def _lsof_pids(port: int) -> list[int]:
    """lsof -ti tcp:<port> → 监听该端口的 PID 列表 (stop 兜底, 无 pid 文件时)。"""
    out = _capture(["lsof", "-ti", f"tcp:{port}"])
    return [int(line.strip()) for line in out.splitlines() if line.strip().isdigit()]


def _pid_alive(pid: int) -> bool:
    """kill(pid, 0) 判活 (进程不存在 → False; 存在 → True)。"""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_pid(pid: int, grace: float = 2.0) -> None:
    """SIGTERM → 等待 grace → SIGKILL (进程已退出/无权限 → 静默容错)。"""
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _open_url(url: str) -> None:
    """打开浏览器 (macOS `open`; 其他平台打印 URL 提示手动打开)。"""
    if sys.platform == "darwin":
        subprocess.run(["open", url], check=False)
    else:
        print(f"  请手动打开浏览器: {url}")


def _read_pid(path: Path) -> int | None:
    """读 pid 文件 (缺失/损坏/非数字 → None, 失败安全)。"""
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:  # noqa: BLE001
        return None


def _write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")


def _http_status(url: str, timeout: float = 2.0) -> int:
    """GET url → 状态码; 网络错误/超时 → 0 (健康检查轮询用)。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:  # noqa: BLE001
        return 0


# ------------------------------------------------------------------ 检查 (环境/依赖/配置)


def _env_problems() -> list[str]:
    """环境检查: python ≥3.10 + node ≥18 (缺失/过低 → 清晰提示列表)。"""
    problems: list[str] = []
    if sys.version_info[:2] < MIN_PYTHON:
        problems.append(
            f"Python 版本过低: {sys.version_info.major}.{sys.version_info.minor}"
            f" (需要 ≥{MIN_PYTHON[0]}.{MIN_PYTHON[1]})"
        )
    node = _node_version()
    if node is None:
        problems.append(f"未找到 Node.js — 请安装 ≥{MIN_NODE[0]} (https://nodejs.org)")
    elif node < MIN_NODE:
        problems.append(f"Node.js 版本过低: {node[0]}.{node[1]} (需要 ≥{MIN_NODE[0]})")
    return problems


def _dep_problems(root: Path) -> list[str]:
    """依赖检查: .venv 存在? 前端 node_modules 存在? (缺失 → install 指引)。"""
    problems: list[str] = []
    venv_py = root / ".venv" / "bin" / "python"
    if not venv_py.is_file():
        problems.append(
            f"未找到虚拟环境: {venv_py}\n"
            "  请先安装依赖: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'"
        )
    frontend = root / "factory-console" / "web" / "frontend"
    if not (frontend / "node_modules").is_dir():
        problems.append(
            f"前端依赖缺失: {frontend / 'node_modules'}\n  请先安装: cd {frontend} && npm install"
        )
    return problems


def _config_hints(config: ConfigProvider) -> list[str]:
    """配置检查: LLM key 缺失 → .env.example 指引 (仅提示, 不阻断启动)。"""
    llm = config.get_llm()
    if llm["api_key"]:
        return []
    return [
        f"LLM API key 未配置 (provider={llm['provider']}, model={llm['model']}) — "
        "继续启动, 但项目执行功能不可用。\n"
        "  配置方法: 复制 factory-console/.env.example 为 factory-console/.env "
        "并填写 LLM_API_KEY (或编辑 ~/.factory/config.json)"
    ]


# ------------------------------------------------------------------ init (S10-026 Task E: 首次运行初始化 IO)


def _stdin_is_tty() -> bool:
    """stdin 是否为交互终端 (无 TTY 自动降级非交互; 探测失败 → False)。"""
    try:
        return sys.stdin.isatty()
    except Exception:  # noqa: BLE001 — 失败安全
        return False


def _ask(prompt: str) -> str:
    """交互输入 (模块级 IO — 测试可 monkeypatch); EOF/异常 → 空串。"""
    try:
        return input(prompt)
    except (EOFError, OSError):
        return ""


def _parse_choice(raw: str, count: int) -> int | None:
    """交互选择解析: 空/非法 → None (调用方用默认); 1..count → 索引。"""
    text = raw.strip()
    if not text:
        return None
    try:
        number = int(text)
    except ValueError:
        return None
    return number if 1 <= number <= count else None


def _ensure_workspace(data_dir: Path) -> list[str]:
    """确保 workspace 目录就位 (幂等, mkdir parents=True)。返回新建目录名列表。"""
    created: list[str] = []
    for name in WORKSPACE_DIRS:
        path = data_dir / name
        if not path.is_dir():
            path.mkdir(parents=True, exist_ok=True)
            created.append(name)
    return created


def _default_api_key_ref(provider_id: str) -> str | None:
    """provider 的 api_key_ref 默认建议 (env:VAR 格式; 本地模型无 key → None)。"""
    env_name = PROVIDER_DEFAULTS.get(provider_id, {}).get("api_key_env")
    return f"env:{env_name}" if env_name else None


def _init_validation(data_dir: Path) -> list[str]:
    """校验 LLM 配置 (只读, 零副作用; 复用 LLMControlPlane): providers.json
    存在? enabled? model 列表? key 可解析? 返回问题列表 (空 → 全就绪)。"""
    from .llm_control import LLMControlPlane, ProviderFileError

    providers_file = data_dir / "providers.json"
    try:
        plane = LLMControlPlane(providers_file=providers_file, environ=os.environ)
    except ProviderFileError as exc:
        return [f"providers.json 损坏: {exc}"]
    if not providers_file.exists():
        return ["providers.json 不存在 — 尚未配置 LLM Provider"]
    enabled = plane.enabled_providers()
    if not enabled:
        return ["providers.json 存在但无 enabled provider"]
    no_model = [p.id for p in enabled if not p.models]
    if no_model:
        return [f"enabled provider 缺模型列表: {', '.join(no_model)}"]
    missing_key = [
        p.id for p in enabled if p.id != "ollama" and not plane.resolve_api_key(p.id)
    ]
    if missing_key:
        return [
            "enabled provider 缺少 API key: "
            f"{', '.join(missing_key)} — 请配置对应环境变量 (如 DEEPSEEK_API_KEY)"
        ]
    return []


# ------------------------------------------------------------------ 命令组骨架 IO (S10-026 Task C: 只读数据读取)

#: 事件库候选文件名 (audit 按序探测; factory.db 内含 events 表)
EVENTS_DB_NAMES = ("events.db", "factory.db")


def _load_json_safe(path: Path) -> Any | None:
    """fail-safe JSON 读取 (缺失/损坏 → None; 永不抛)。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 只读展示失败安全
        return None


def _read_config_file(path: Path) -> dict[str, Any] | None:
    """读 config.json → dict; 缺失 → {}; 损坏/非 JSON 对象 → None。

    None 语义: 文件存在但损坏 — 调用方拒绝覆盖 (保护用户数据); 缺失文件
    视为空配置 (首次运行, 可安全创建)。
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 损坏由调用方决策
        return None
    return data if isinstance(data, dict) else None


def _write_config_file(path: Path, data: dict[str, Any]) -> None:
    """原子写 config.json (临时文件 + os.replace — 同 providers/store 模式)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)


def _agent_rows(data_dir: Path) -> list[dict[str, Any]]:
    """agents/agents.json → 行 dict 列表 (id/name/role/skills); 缺失/损坏 → []。

    兼容 dict (按 id 索引) 与 list 两种存储形态; 只取展示字段, 不加工。
    """
    data = _load_json_safe(data_dir / "agents" / "agents.json")
    if isinstance(data, dict):
        data = list(data.values())
    if not isinstance(data, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "id": row.get("id", ""),
                "name": row.get("name", row.get("id", "")),
                "role": row.get("role", ""),
                "skills": ", ".join(row.get("skills") or []),
            }
        )
    return rows


def _skill_rows(data_dir: Path) -> list[dict[str, Any]]:
    """skills 注册表 → 行 dict 列表 (id/name/category/version); 无数据 → []。

    数据源: skills/skills.json (单文件注册表, dict 按 id 索引); 目录形态
    skills/*.json 兜底兼容 (exec skill 注册表). 只读, 失败安全。
    """
    rows: list[dict[str, Any]] = []

    def _row_from(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        return {
            "id": item.get("id", ""),
            "name": item.get("name", item.get("id", "")),
            "category": item.get("category", ""),
            "version": item.get("version", ""),
        }

    data = _load_json_safe(data_dir / "skills" / "skills.json")
    if isinstance(data, dict):
        data = list(data.values())
    if isinstance(data, list):
        for item in data:
            row = _row_from(item)
            if row is not None:
                rows.append(row)
        return rows
    for path in sorted((data_dir / "skills").glob("*.json")):
        row = _row_from(_load_json_safe(path))
        if row is not None:
            rows.append(row)
    return rows


def _task_rows(data_dir: Path) -> list[dict[str, Any]]:
    """tasks/*.json → 行 dict 列表 (id/title/status/project); 无数据 → []。

    每个文件一条任务; 损坏/无 id 的文件跳过 (失败安全)。
    """
    rows: list[dict[str, Any]] = []
    for path in sorted((data_dir / "tasks").glob("*.json")):
        row = _load_json_safe(path)
        if not isinstance(row, dict) or not row.get("id"):
            continue
        rows.append(
            {
                "id": row.get("id", ""),
                "title": row.get("title", ""),
                "status": row.get("status", ""),
                "project": row.get("project", ""),
            }
        )
    return rows


def _find_events_db(data_dir: Path) -> Path | None:
    """定位事件库: 优先 events.db, 兜底 factory.db (须含 events 表)。

    只读探测 (mode=ro); 未找到/无 events 表 → None。
    """
    for name in EVENTS_DB_NAMES:
        path = data_dir / name
        if not path.is_file():
            continue
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                has = conn.execute(
                    "SELECT 1 FROM sqlite_master"
                    " WHERE type='table' AND name='events'"
                ).fetchone()
            finally:
                conn.close()
            if has:
                return path
        except sqlite3.Error:
            continue
    return None


def _events_summary(db_path: Path, limit: int = 10) -> dict[str, Any]:
    """只读查询 events 表 → {counts: [(type, n)], recent: [行 dict]}。

    严格只读: mode=ro URI; WAL 库只读打开失败 (需 -shm 写权限) 时兜底普通
    连接 — 仍只执行 SELECT, 绝不写库。
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        counts = [
            (row["type"], row["n"])
            for row in conn.execute(
                "SELECT type, COUNT(*) AS n FROM events"
                " GROUP BY type ORDER BY n DESC"
            )
        ]
        recent = [
            dict(row)
            for row in conn.execute(
                "SELECT seq, event_id, timestamp, type, source, project_id,"
                " task_id, agent_id FROM events ORDER BY seq DESC LIMIT ?",
                (max(1, int(limit)),),
            )
        ]
    finally:
        conn.close()
    return {"counts": counts, "recent": recent}


# ------------------------------------------------------------------ FactoryCLI (流程编排)


class FactoryCLI:
    """CLI 命令编排: start / stop / status / service / doctor (+ 预留 stub)。

    S10-026 P3: start/stop/status 内部改调 Services Registry (cli_services),
    本类保留环境/依赖/配置检查 + 就绪输出/浏览器编排, 服务级原语
    (启动/健康检查/停止/状态) 由注册表服务经 ServiceContext.cli 包装调用。
    """

    def __init__(self, config: ConfigProvider, *, root: Path | None = None) -> None:
        self.config = config
        # cli_factory.py 位于 <root>/factory-console/ 下 → parents[1] 即仓库根
        self.root = (root or Path(__file__).resolve().parents[1]).resolve()
        self.data_dir = config.get_data_dir()
        self.run_dir = self.data_dir / RUN_SUBDIR
        self.backend_pid = self.run_dir / "backend.pid"
        self.frontend_pid = self.run_dir / "frontend.pid"
        self.backend_log = self.run_dir / "backend.log"
        self.frontend_log = self.run_dir / "frontend.log"

    # ------------------------------------------------------------- 入口

    def run(self, args: argparse.Namespace) -> int:
        if args.command == "start":
            return self.start(
                no_browser=args.no_browser,
                port=args.port,
                frontend_port=args.frontend_port,
                services=args.services or None,
                dev=args.dev,
            )
        if args.command == "stop":
            return self.stop()
        if args.command == "status":
            return self.status()
        if args.command == "doctor":
            return self.doctor(args)
        if args.command == "service":
            return self.service(args)
        if args.command in ("agent", "skill", "task", "router", "rag", "audit"):
            return getattr(self, args.command)(args)
        if args.command == "config":
            return self.config_cmd(args)
        if args.command == "init":
            return self.init(args)
        if args.command in STUB_COMMANDS:
            return self._stub(args.command)
        print(f"未知命令: {args.command}", file=sys.stderr)
        return 2

    # ------------------------------------------------------------- start

    def start(
        self,
        *,
        no_browser: bool = False,
        port: int | None = None,
        frontend_port: int | None = None,
        services: Sequence[str] | None = None,
        dev: bool = False,
    ) -> int:
        """Runtime Manager (S10-026 P3): 经 Services Registry 启动服务。

        无参数 → 全部内置服务 (backend+frontend), 行为与旧版完全一致:
        环境检查 → 依赖检查 → 配置提示 → 幂等 → 端口预检 → 后端启动+健康
        检查 → 前端启动+就绪检查 → 打开浏览器。`factory start <svc>...` 只
        启动指定服务 (未知服务 → exit 2)。`--dev` 前端走 vite dev (缺省
        托管 dist)。
        """
        from .cli_services import STATE_RUNNING, get_service, list_services

        backend_port = port or self.config.get_port()
        frontend_port = frontend_port or self.config.get_frontend_port()
        print("=== AI Factory 启动 ===")

        # 0. 目标服务解析 (缺省 → 全部内置 backend+frontend; 未知 → exit 2)
        if services:
            selected: list = []
            for sid in services:
                svc = get_service(sid)
                if svc is None:
                    print(
                        f"未知服务: {sid} (可用: {', '.join(s.id for s in list_services())})",
                        file=sys.stderr,
                    )
                    return 2
                selected.append(svc)
            all_builtin = False
        else:
            selected = [get_service("backend"), get_service("frontend")]
            all_builtin = True

        ctx = self._service_ctx(
            backend_port=backend_port, frontend_port=frontend_port, dev_mode=dev
        )

        # 1. 环境检查 (python / node)
        problems = _env_problems()
        if problems:
            for problem in problems:
                print(f"  ✗ {problem}", file=sys.stderr)
            print("  环境检查未通过, 请先修复上述问题。", file=sys.stderr)
            return 1

        # 2. 依赖检查 (.venv / node_modules)
        problems = _dep_problems(self.root)
        if problems:
            for problem in problems:
                print(f"  ✗ {problem}", file=sys.stderr)
            print("  依赖检查未通过, 请先安装。", file=sys.stderr)
            return 1

        # 3. 配置检查 (LLM key 缺失 → 仅提示, 不阻断)
        for hint in _config_hints(self.config):
            print(f"  ⚠ {hint}")

        # 4. 幂等: 目标服务均已运行 → 提示不重复起
        if all(svc.status(ctx).state == STATE_RUNNING for svc in selected):
            if all_builtin:
                print(f"  已在运行: http://127.0.0.1:{frontend_port}{FRONTEND_PATH}")
            else:
                print(
                    "  已在运行: "
                    + " / ".join(
                        f"{svc.id} (PID {svc.status(ctx).pid})" for svc in selected
                    )
                )
            return 0

        # 5. 端口预检 (仅检查需要启动的一侧; 占用 → 明确提示)
        busy: list[str] = []
        for svc in selected:
            if svc.status(ctx).state != STATE_RUNNING:
                svc_port = getattr(svc, "port", lambda c: None)(ctx)
                if svc_port and _port_in_use(svc_port):
                    busy.append(f"{getattr(svc, 'short_label', svc.id)}端口 {svc_port}")
        if busy:
            print("  ✗ 端口已被占用: " + " / ".join(busy), file=sys.stderr)
            print(
                "    请先释放端口, 或修改配置 (factory-console/.env 或 "
                "~/.factory/config.json 的 PORT/FRONTEND_PORT)。",
                file=sys.stderr,
            )
            return 1

        # 6. 按注册序启动: start → 健康检查; 失败 → 日志尾部 + 回滚
        started: list = []
        for svc in selected:
            handle = svc.start(ctx)
            if not handle.ok:
                if started:  # 回滚本次已起服务 (旧行为: 前端启动失败停后端)
                    self.stop()
                return 1
            started.append(svc)
            wait_ready = getattr(svc, "wait_ready", None)
            if wait_ready is None:  # 无独立进程的服务 (如 runtime) — 无需健康检查
                continue
            if not wait_ready(ctx, handle):
                log = getattr(svc, "log_path", lambda c: None)(ctx)
                if log:
                    self._show_log_tail(log)
                if getattr(svc, "rollback", None) == "all":
                    self.stop()
                else:
                    self._cleanup_pids()
                print(
                    getattr(svc, "fail_message", f"  ✗ {svc.label}启动失败"),
                    file=sys.stderr,
                )
                return 1

        # 7. 就绪输出 + 打开浏览器
        frontend_svc = get_service("frontend")
        frontend_running = (
            frontend_svc is not None
            and frontend_svc.status(ctx).state == STATE_RUNNING
        )
        if all_builtin:
            url = f"http://127.0.0.1:{frontend_port}{FRONTEND_PATH}"
            print(f"  ✓ 已就绪: {url}")
            print(f"    后端 API: http://127.0.0.1:{backend_port}{HEALTH_PATH}")
            if not no_browser:
                _open_url(url)
        else:
            for svc in selected:
                st = svc.status(ctx)
                print(f"  ✓ {svc.id} 已就绪: {st.url if st.url else svc.label}")
            if not no_browser and frontend_running:
                _open_url(f"http://127.0.0.1:{frontend_port}{FRONTEND_PATH}")
        return 0

    def _start_backend(self, port: int) -> bool:
        """后台启动 uvicorn (bootstrap 经 base64 传子进程); pid 写文件。"""
        if self._backend_running():
            print(f"  后端已在运行 (PID {_read_pid(self.backend_pid)})")
            return True
        self.run_dir.mkdir(parents=True, exist_ok=True)
        python = self.root / ".venv" / "bin" / "python"
        code = (
            "import importlib,uvicorn;"
            "m=importlib.import_module({mod!r});"
            "app=m.create_app(factory_root={root!r});"
            "uvicorn.run(app,host='127.0.0.1',port={port},log_level='info')"
        ).format(mod=BACKEND_MODULE, root=str(self.data_dir), port=port)
        b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
        cmd = [str(python), "-c", f"import base64;exec(base64.b64decode('{b64}').decode('utf-8'))"]
        try:
            log = open(self.backend_log, "ab")
        except OSError as exc:
            print(f"  ✗ 无法写后端日志 {self.backend_log}: {exc}", file=sys.stderr)
            return False
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=str(self.root),
                start_new_session=True,  # 独立进程组 — stop 整组杀, 不误伤
            )
        except OSError as exc:
            log.close()
            print(f"  ✗ 后端启动失败: {exc}", file=sys.stderr)
            return False
        _write_pid(self.backend_pid, proc.pid)
        print(f"  后端启动中 (PID {proc.pid}, http://127.0.0.1:{port})")
        return True

    def _start_frontend(self, port: int, *, dev: bool = False) -> bool:
        """后台启动前端: 默认托管 dist (SPA 同源 /api), --dev 走 vite dev。

        - 默认 (dev=False): <frontend>/dist 存在 → 第二个 uvicorn 挂
          create_app(static_dir=dist) (与 vite /api 代理等价的同源 API);
          dist 缺失 → 回退 vite dev 并提示 (未构建也能用)。
        - dev=True: 现有 vite --port --strictPort --host 逻辑 (开发热更)。
        pid 写文件 (stop 兼容)。
        """
        if self._frontend_running():
            print(f"  前端已在运行 (PID {_read_pid(self.frontend_pid)})")
            return True
        frontend = self.root / "factory-console" / "web" / "frontend"
        dist = frontend / "dist"
        if dev or not dist.is_dir():
            if not dev:
                print(
                    f"  ⚠ 未找到前端构建产物 {dist} — 回退 vite dev 模式 "
                    "(提示: 运行 `npm run build` 后 `factory start` 将托管静态产物)"
                )
            npm = shutil.which("npm")
            if not npm:
                print("  ✗ 未找到 npm — 请安装 Node.js ≥18", file=sys.stderr)
                return False
            cmd = [
                npm,
                "run",
                "dev",
                "--",
                "--port",
                str(port),
                "--strictPort",
                "--host",
                "127.0.0.1",
            ]
        else:
            # dist 托管: uvicorn + create_app(static_dir=dist) — bootstrap 同后端
            python = self.root / ".venv" / "bin" / "python"
            code = (
                "import importlib,uvicorn;"
                "m=importlib.import_module({mod!r});"
                "app=m.create_app(factory_root={root!r},static_dir={dist!r});"
                "uvicorn.run(app,host='127.0.0.1',port={port},log_level='info')"
            ).format(mod=BACKEND_MODULE, root=str(self.data_dir), dist=str(dist), port=port)
            b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
            cmd = [
                str(python),
                "-c",
                f"import base64;exec(base64.b64decode('{b64}').decode('utf-8'))",
            ]
        try:
            log = open(self.frontend_log, "ab")
        except OSError as exc:
            print(f"  ✗ 无法写前端日志 {self.frontend_log}: {exc}", file=sys.stderr)
            return False
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=str(frontend),
                start_new_session=True,
            )
        except OSError as exc:
            log.close()
            print(f"  ✗ 前端启动失败: {exc}", file=sys.stderr)
            return False
        _write_pid(self.frontend_pid, proc.pid)
        print(f"  前端启动中 (PID {proc.pid}, http://127.0.0.1:{port})")
        return True

    # ------------------------------------------------------------- 健康检查

    def _wait_http(self, url: str, timeout: float = HEALTH_TIMEOUT) -> bool:
        """轮询 GET url 直到 200 (幂等可重入; 超时 → False)。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _http_status(url) == 200:
                return True
            time.sleep(HEALTH_INTERVAL)
        return False

    def _wait_backend(self, port: int) -> bool:
        return self._wait_http(f"http://127.0.0.1:{port}{HEALTH_PATH}")

    def _wait_frontend(self, port: int) -> bool:
        return self._wait_http(f"http://127.0.0.1:{port}/", timeout=FRONTEND_TIMEOUT)

    # ------------------------------------------------------------- 进程状态

    def _backend_running(self) -> bool:
        pid = _read_pid(self.backend_pid)
        return pid is not None and _pid_alive(pid)

    def _frontend_running(self) -> bool:
        pid = _read_pid(self.frontend_pid)
        return pid is not None and _pid_alive(pid)

    def _kill_group(self, pid: int) -> None:
        """杀整个进程组 (start_new_session → pgid == pid); 容错静默。"""
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    def _stop_one(self, pid_file: Path, port: int) -> int | None:
        """停单个服务: pid 文件优先; 无 → 按端口 lsof 找。返回被杀 PID。

        S10-026 P3: cli_services 服务 stop(handle) 经 handle.cli 复用本方法 —
        停止路径单一实现, 且保留实例调用面 (monkeypatch 兼容)。
        """
        pid = _read_pid(pid_file)
        if pid is not None:
            if _pid_alive(pid):
                self._kill_group(pid)
                _kill_pid(pid, grace=3.0)
                return pid
            return None  # 陈旧 pid 文件 (进程已死) — 仅清理文件
        for found in _lsof_pids(port):
            _kill_pid(found, grace=3.0)
            return found
        return None

    def _cleanup_pids(self) -> None:
        for path in (self.backend_pid, self.frontend_pid):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------- stop

    def stop(self) -> int:
        """停止前后端服务 (pid 文件优先, 兜底按端口) — 经服务注册表。"""
        from .cli_services import get_service

        print("=== AI Factory 停止 ===")
        ctx = self._service_ctx()
        stopped: list[str] = []
        for svc in (get_service("backend"), get_service("frontend")):
            handle = svc.current_handle(ctx)
            killed = svc.stop(handle)
            if killed is not None:
                stopped.append(f"{svc.short_label} (PID {killed})")
        self._cleanup_pids()  # 统一清理 (循环内删会吞掉后续服务的 pid 文件)
        if stopped:
            print("  已停止: " + ", ".join(stopped))
        else:
            print("  未发现运行中的服务 (无 pid 文件 / 进程已退出)")
        for svc in (get_service("backend"), get_service("frontend")):
            svc_port = svc.port(ctx)
            if _port_in_use(svc_port):
                print(
                    f"  ⚠ {svc.short_label} 端口 {svc_port} 仍被占用 — 存在未托管进程, 请手动检查",
                    file=sys.stderr,
                )
        return 0

    # ------------------------------------------------------------- status

    def status(self) -> int:
        """端口/进程/数据目录/LLM 状态 — 经服务注册表 (输出与旧版一致)。"""
        from .cli_services import get_service

        llm = self.config.get_llm()
        print("=== AI Factory 状态 ===")
        print(f"数据目录: {self.data_dir}")
        print(
            f"LLM: provider={llm['provider']} model={llm['model']} "
            f"api_key={'已配置' if llm['api_key'] else '未配置'}"
        )
        ctx = self._service_ctx()
        for svc in (get_service("backend"), get_service("frontend")):
            st = svc.status(ctx)
            print(f"{svc.short_label}: {st.detail}")
        return 0

    # ------------------------------------------------------------- service

    def service(self, args: argparse.Namespace) -> int:
        """服务注册表子命令 (S10-026 P3): `factory service list`。

        薄代理 → cli_services.run_service_list (协议/注册表/状态全在
        cli_services; 未来 vector-db/gateway 注册即自动出现)。
        """
        from .cli_services import run_service_list

        if args.service_action == "list":
            return run_service_list(self._service_ctx())
        print(f"未知 service 动作: {args.service_action}", file=sys.stderr)
        return 2

    def _service_ctx(self, *, backend_port=None, frontend_port=None, dev_mode=False):
        """装配 ServiceContext (cli=self 提供启动/停止原语, 测试可注入)。"""
        from .cli_services import ServiceContext

        return ServiceContext(
            data_dir=self.data_dir,
            root=self.root,
            backend_port=(
                backend_port if backend_port is not None else self.config.get_port()
            ),
            frontend_port=(
                frontend_port
                if frontend_port is not None
                else self.config.get_frontend_port()
            ),
            dev_mode=dev_mode,
            cli=self,
        )

    # ------------------------------------------------------------- doctor

    def doctor(self, args: argparse.Namespace) -> int:
        """诊断检查 (S10-026 P1): 薄代理 → cli_doctor 注册表 + 5 内置检查器。

        协议/注册表/检查器全在 cli_doctor (可扩展: 未来 rag/governance/
        agent-policy 注册即被发现); 本方法只装配上下文并转交输出。
        """
        from .cli_doctor import build_context, run_doctor

        return run_doctor(
            args.checker,
            json_mode=args.json,
            verbose=args.verbose,
            ctx=build_context(
                data_dir=self.data_dir,
                root=self.root,
                backend_port=self.config.get_port(),
                frontend_port=self.config.get_frontend_port(),
            ),
        )

    # ------------------------------------------------------------- config (S10-026 Task D)

    def config_cmd(self, args: argparse.Namespace) -> int:
        """Factory Runtime Configuration (§2.3): show / set / check / path。

        白名单写入 (core.data_dir / core.port / core.frontend_port); 红线 ①:
        拒绝一切 llm.* 写入 — LLM 配置归 providers.json (LLMControlPlane) /
        models.json (ModelCatalog) / agent.yaml·skill.yaml·project.yaml (策略)。
        """
        action = args.config_action
        if action == "show":
            return self._config_show()
        if action == "set":
            if not args.key or args.value is None:
                print("用法: factory config set <key> <value>", file=sys.stderr)
                return 2
            return self._config_set(args.key, args.value)
        if action == "check":
            return self._config_check()
        if action == "path":
            print(f"配置文件: {self._config_file()}")
            return 0
        print(f"未知 config 动作: {action}", file=sys.stderr)
        return 2

    def _config_file(self) -> Path:
        """config.json 路径 (自 ConfigProvider 取 — 测试注入 tmp 文件时可见)。"""
        return Path(
            getattr(
                self.config,
                "_user_config_file",
                Path.home() / ".factory" / "config.json",
            )
        )

    def _config_show(self) -> int:
        """显示运行时配置 (脱敏: key 不显示值, 只显示 已配置/未配置 状态)。

        状态判定: ConfigProvider 分层取值 (env > .env > config.json) 为
        None → 未配置 (使用默认); 任一层有值 → 已配置。LLM 行只读展示
        状态, 不打印 key 明文 (铁律: 不打印 API key)。
        """
        print("=== Factory 运行时配置 ===")
        print(f"配置文件: {self._config_file()}")
        for key in CONFIG_KEYS:
            section, _, sub = key.partition(".")
            configured = self.config.get(section, sub, None) is not None
            print(f"  {key:<22} {'已配置' if configured else '未配置'}")
        llm = self.config.get_llm()
        print(
            f"LLM (只读状态): provider={llm['provider']} model={llm['model']} "
            f"api_key={'已配置' if llm['api_key'] else '未配置'}"
        )
        return 0

    def _config_set(self, key: str, value: str) -> int:
        """写运行时配置 (仅白名单); llm.* / 未知键 / 非法值 → 拒绝 + 明确错误。"""
        if key in CONFIG_FORBIDDEN_KEYS or key.startswith("llm."):
            print(
                f"拒绝写入 {key}: config.json 只存运行时配置 (红线 ①) — "
                "LLM 配置归 providers.json (Provider 生命周期) / models.json "
                "(模型元数据) / agent.yaml·skill.yaml·project.yaml (策略), "
                "请用对应管理命令配置。",
                file=sys.stderr,
            )
            return 1
        if key not in CONFIG_KEYS:
            print(
                f"未知配置键: {key} (允许: {', '.join(CONFIG_KEYS)})",
                file=sys.stderr,
            )
            return 1
        section, _, sub = key.partition(".")
        if sub in ("port", "frontend_port"):
            try:
                number = int(value.strip())
            except ValueError:
                print(
                    f"非法端口值: {value!r} — 需要 1-65535 的整数", file=sys.stderr
                )
                return 1
            if not 1 <= number <= 65535:
                print(
                    f"非法端口值: {value!r} — 需要 1-65535 的整数", file=sys.stderr
                )
                return 1
            typed: Any = number
        else:  # core.data_dir
            stripped = value.strip()
            if not stripped:
                print("非法 data_dir: 不能为空", file=sys.stderr)
                return 1
            typed = stripped
        path = self._config_file()
        data = _read_config_file(path)
        if data is None:
            print(
                f"config.json 损坏 ({path}) — 请人工修复后再执行 config set",
                file=sys.stderr,
            )
            return 1
        data.setdefault(section, {})[sub] = typed
        _write_config_file(path, data)
        print(f"已写入 {key} = {typed}")
        return 0

    def _config_check(self) -> int:
        """校验配置: config.json 状态 + providers.json 只读检查 (复用
        LLMControlPlane list_providers/enabled_providers/resolve_api_key)。

        输出 OK/WARN 行; 零副作用 (绝不创建/修改 providers.json 等文件)。
        """
        print("=== 配置校验 ===")
        # 1. 运行时配置 (config.json)
        path = self._config_file()
        data = _read_config_file(path)
        if data is None:
            print(f"  WARN config.json 损坏 ({path}) — 忽略并回退默认值")
        elif not data:
            print(
                f"  WARN config.json 不存在 ({path}) — 使用默认值"
                " (可用 factory config set 写入)"
            )
        else:
            print(f"  OK   config.json 可读 ({path})")
        # 2. LLM Provider (providers.json — LLMControlPlane 只读查询)
        providers_file = self.data_dir / "providers.json"
        from .llm_control import LLMControlPlane, ProviderFileError

        try:
            plane = LLMControlPlane(providers_file=providers_file, environ=os.environ)
        except ProviderFileError as exc:
            print(f"  WARN providers.json 损坏: {exc}")
            return 0
        if not providers_file.exists():
            print(
                "  WARN providers.json 不存在 — 请先运行 factory init 配置 LLM Provider"
            )
            return 0
        providers = plane.list_providers()
        enabled = plane.enabled_providers()
        if not enabled:
            print(
                "  WARN providers.json 存在但无 enabled provider — "
                "请启用至少一个 provider (factory init)"
            )
            return 0
        missing_key = [
            p.id for p in enabled if p.id != "ollama" and not plane.resolve_api_key(p.id)
        ]
        if missing_key:
            print(
                "  WARN enabled provider 缺少 API key: "
                f"{', '.join(missing_key)} — 请配置 api_key_ref (如 env:DEEPSEEK_API_KEY)"
            )
            return 0
        print(
            f"  OK   providers.json 就绪 ({len(providers)} provider, "
            f"{len(enabled)} enabled: {', '.join(p.id for p in enabled)}, "
            "API key 可解析)"
        )
        return 0

    # ------------------------------------------------------------- 命令组骨架 (S10-026 Task C)

    def agent(self, args: argparse.Namespace) -> int:
        """Agent 管理骨架 (只读): 列出现有 agents (id/name/role/skills)。

        数据源: <data_dir>/agents/agents.json; 缺失/损坏 → 空列表提示,
        不报错 (薄代理, 无新业务逻辑)。
        """
        print("=== Agent 管理 (骨架, 只读) ===")
        rows = _agent_rows(self.data_dir)
        if not rows:
            print("  无 agents 数据 (空列表)")
            return 0
        for row in rows:
            print(
                f"  - {row['id']} | {row['name']} | role={row['role']} "
                f"| skills=[{row['skills']}]"
            )
        print(f"  共 {len(rows)} 个 agent")
        return 0

    def skill(self, args: argparse.Namespace) -> int:
        """Skill 管理骨架 (只读): 列出现有 skills (id/name/category/version)。

        数据源: <data_dir>/skills/skills.json 或 skills/*.json; 无数据 → 空列表。
        """
        print("=== Skill 管理 (骨架, 只读) ===")
        rows = _skill_rows(self.data_dir)
        if not rows:
            print("  无 skills 数据 (空列表)")
            return 0
        for row in rows:
            print(
                f"  - {row['id']} | {row['name']} | category={row['category']} "
                f"| v{row['version']}"
            )
        print(f"  共 {len(rows)} 个 skill")
        return 0

    def task(self, args: argparse.Namespace) -> int:
        """Task 管理骨架 (只读): 列出 tasks (id/title/status/project)。

        数据源: <data_dir>/tasks/*.json (每文件一条任务); 无数据 → 空列表。
        """
        print("=== Task 管理 (骨架, 只读) ===")
        rows = _task_rows(self.data_dir)
        if not rows:
            print("  无 tasks 数据 (空列表)")
            return 0
        for row in rows:
            print(
                f"  - {row['id']} | {row['title']} | {row['status']} "
                f"| project={row['project']}"
            )
        print(f"  共 {len(rows)} 个 task")
        return 0

    def router(self, args: argparse.Namespace) -> int:
        """LLM Router 管理骨架 (只读): 五层决策链可用性 + 当前决策。

        复用 LLMRouter (同 cli_doctor.RouterCheck 装配: control_plane +
        可选 model_catalog), 调 route() 无参数展示当前命中层; 决策异常 →
        显示错误但仍 rc 0 (诊断性质, 不修改任何配置)。
        """
        print("=== LLM Router 状态 (骨架, 只读) ===")
        from .llm_control import LLMControlPlane
        from .llm_router import LLMRouter
        from .model_catalog import ModelCatalog

        agents_dir = self.data_dir / "agents"
        skills_dir = self.data_dir / "skills"
        print("  五层决策链:")
        print("    L1 用户显式: 可用 (调用参数显式指定)")
        print(
            "    L2 Agent/Skill 策略: "
            + (
                "策略目录就绪"
                if agents_dir.is_dir() or skills_dir.is_dir()
                else "无策略目录 (未配置 agent.yaml/skill.yaml)"
            )
        )
        print("    L3 项目规则: 未提供 project.yaml (无项目输入)")
        print(
            "    L4 系统推荐: "
            + (
                "models.json 就绪"
                if (self.data_dir / "models.json").is_file()
                else "缺失 (L4 跳过)"
            )
        )
        try:
            plane = LLMControlPlane(
                providers_file=self.data_dir / "providers.json", environ=os.environ
            )
            enabled = plane.enabled_providers()
        except Exception:  # noqa: BLE001 — 展示失败安全
            plane, enabled = None, []
        print(
            "    L5 兜底: "
            + (
                f"可用 ({len(enabled)} 个 enabled provider)"
                if enabled
                else "无 enabled provider"
            )
        )
        catalog = None
        if (self.data_dir / "models.json").is_file():
            catalog = ModelCatalog(models_file=self.data_dir / "models.json")
        router = LLMRouter(
            control_plane=plane,
            model_catalog=catalog,
            agents_dir=agents_dir,
            skills_dir=skills_dir,
        )
        try:
            choice = router.route()
        except Exception as exc:  # noqa: BLE001 — 决策异常 → 展示, 不崩溃
            print(f"  当前决策: 异常 — {exc}")
            return 0
        if choice is None:
            print(
                "  当前决策: 未命中 (无可用 provider — "
                "请先 factory init 配置并启用 provider)"
            )
            return 0
        print(
            f"  当前决策: {choice.provider_id}/{choice.model_id or '(默认模型)'} "
            f"(source={choice.source}, score={choice.score})"
        )
        return 0

    def rag(self, args: argparse.Namespace) -> int:
        """RAG 管理骨架: 明确占位 — 本 Sprint 不实现 RAG。"""
        print("RAG 未实现 — 规划中 (S10-026 Task C 命令组骨架占位, 不实现功能)")
        return 0

    def audit(self, args: argparse.Namespace) -> int:
        """审计查询骨架 (只读): events 最近事件列表 + 按类型计数。

        数据源: <data_dir>/events.db, 兜底 factory.db (含 events 表);
        仅 SELECT 查询, 绝不写库。缺失/空库 → 提示, rc 0。
        """
        print("=== 审计查询 (骨架, 只读) ===")
        db = _find_events_db(self.data_dir)
        if db is None:
            print(f"  未找到事件库 (期望 {self.data_dir / 'events.db'} 或 factory.db)")
            return 0
        summary = _events_summary(db, args.limit)
        print(f"  事件库: {db}")
        if not summary["counts"]:
            print("  无事件数据")
            return 0
        print("  按类型计数:")
        for typ, n in summary["counts"]:
            print(f"    {typ}: {n}")
        recent = summary["recent"]
        print(f"  最近 {len(recent)} 条事件:")
        for row in recent:
            scope = ", ".join(
                f"{k}={row[k]}" for k in ("project_id", "task_id", "agent_id") if row.get(k)
            )
            suffix = f" ({scope})" if scope else ""
            print(
                f"    #{row['seq']} [{row['timestamp']}] "
                f"{row['type']} <{row['source']}>{suffix}"
            )
        return 0

    # ------------------------------------------------------------- init (S10-026 Task E)

    def init(self, args: argparse.Namespace) -> int:
        """首次运行初始化 (§2.1 P0): 环境检测 → workspace 初始化 → LLM 配置
        引导 → 校验 → 下一步提示 (factory doctor / factory start)。

        支持 --force (已初始化也重新引导) / --non-interactive (无 TTY 自动
        降级; 用参数或默认) / --provider <id> / --model <model> (非交互指定)。
        红线: providers.json 只写 api_key_ref 引用, 绝不写明文 key; 除
        providers.json 外不修改任何文件 (config.json 归 config 命令管)。
        """
        print("=== AI Factory 初始化 ===")

        # 1. 环境检测 (python/venv/node_modules → 缺失 → 明确提示先装依赖)
        problems = _env_problems()
        if problems:
            for problem in problems:
                print(f"  ✗ {problem}", file=sys.stderr)
            print(
                "  环境检查未通过 — 请先修复上述问题再运行 factory init "
                "(安装指引见 README / setup.sh)。",
                file=sys.stderr,
            )
            return 1
        problems = _dep_problems(self.root)
        if problems:
            for problem in problems:
                print(f"  ✗ {problem}", file=sys.stderr)
            print(
                "  依赖检查未通过 — 请先安装依赖再运行 factory init "
                "(安装指引见 README / setup.sh)。",
                file=sys.stderr,
            )
            return 1
        print("  ✓ 环境检查通过 (Python/Node/依赖)")

        # 2. workspace 初始化 (幂等)
        created = _ensure_workspace(self.data_dir)
        if created:
            print("  ✓ 已创建 workspace 目录: " + ", ".join(created))
        else:
            print("  ✓ workspace 目录已就绪")

        # 3. LLM 配置引导 (providers.json — 经 LLMControlPlane, 只写引用)
        rc = self._init_llm_guide(args)
        if rc != 0:
            return rc

        # 4. 校验 (只读: enabled / model 列表 / key 可解析)
        self._init_validate()

        # 5. 下一步提示
        print("  初始化完成 — 下一步:")
        print("    factory doctor   — 全面诊断 (环境/Provider/模型/Router)")
        print("    factory start    — 启动 AI Factory")
        return 0

    def _init_llm_guide(self, args: argparse.Namespace) -> int:
        """LLM 配置引导 (step 3)。

        已存在 providers.json → 显示当前配置 + 交互询问是否修改 (非交互跳过,
        保持现状); --force → 无视已存在重新引导。--provider → 参数直写;
        无 TTY (或 --non-interactive) → 非交互 (用参数或默认 deepseek);
        其余 → 交互向导。
        """
        providers_file = self.data_dir / "providers.json"
        force = args.force
        non_interactive = args.non_interactive or not _stdin_is_tty()

        if providers_file.exists() and not force:
            self._show_provider_config()
            if non_interactive:
                print("  非交互模式: 保持现有 Provider 配置 (--force 可重新引导)")
                return 0
            answer = _ask("  是否重新配置 LLM Provider? [y/N]: ").strip().lower()
            if answer not in ("y", "yes"):
                print("  保持现有 Provider 配置。")
                return 0
            print("  开始重新配置…")
        elif force:
            print("  --force: 重新引导 LLM Provider 配置")

        if args.provider:
            if args.provider not in PROVIDER_DEFAULTS:
                print(
                    f"  未知 provider: {args.provider} "
                    f"(可用: {', '.join(PROVIDER_DEFAULTS)})",
                    file=sys.stderr,
                )
                return 1
            return self._init_write_noninteractive(args.provider, args.model)
        if non_interactive:
            provider_id = DEFAULT_PROVIDER
            if args.model:
                print(f"  --model {args.model} 应用于默认 provider {provider_id}")
            print(f"  非交互模式: 使用默认 provider {provider_id}")
            return self._init_write_noninteractive(provider_id, args.model)
        return self._init_wizard(args.model)

    def _init_wizard(self, model_arg: str | None) -> int:
        """交互向导: provider 选择 → base_url → api_key_ref → 模型 → 写入。

        api_key_ref 只接受 env:VAR 引用 — 输入明文 key 会被拒绝并回退默认
        引用 (红线: 明文 key 永不落盘)。无效选择回退默认, 不中断向导。
        """
        print("  配置 LLM Provider:")
        for i, pid in enumerate(INIT_PROVIDERS, 1):
            print(f"    {i}) {pid} (默认模型: {PROVIDER_DEFAULTS[pid]['model']})")
        choice = _parse_choice(_ask("  选择 [1-4, 回车=1]: "), len(INIT_PROVIDERS))
        provider_id = INIT_PROVIDERS[choice - 1] if choice else INIT_PROVIDERS[0]
        if choice is None:
            print(f"  (使用默认 provider: {provider_id})")
        defaults = PROVIDER_DEFAULTS[provider_id]
        suggested_ref = _default_api_key_ref(provider_id)

        raw = _ask(f"  base_url (回车默认 {defaults['base_url']}): ").strip()
        base_url = raw or defaults["base_url"]

        if suggested_ref:
            raw = _ask(
                f"  API key 引用 (env:VAR 格式, 回车默认 {suggested_ref}): "
            ).strip()
            api_key_ref = suggested_ref
            if raw:
                if raw.startswith("env:"):
                    api_key_ref = raw
                else:
                    print(
                        "  ⚠ 只接受 env:VAR 引用 — 明文 key 不会写入文件, "
                        f"已使用默认引用 {suggested_ref}",
                        file=sys.stderr,
                    )
        else:  # ollama 等本地模型 — 无需 key
            raw = _ask("  API key 引用 (本地模型无需 key, 回车留空): ").strip()
            api_key_ref = raw if raw.startswith("env:") else None
            if raw and not raw.startswith("env:"):
                print(
                    "  ⚠ 只接受 env:VAR 引用 — 明文 key 不会写入文件, 已留空",
                    file=sys.stderr,
                )

        if model_arg:
            model = model_arg
        else:
            raw = _ask(f"  模型 (回车默认 {defaults['model']}): ").strip()
            model = raw or defaults["model"]
        return self._write_provider(
            provider_id,
            {"models": [model], "base_url": base_url, "api_key_ref": api_key_ref},
        )

    def _init_write_noninteractive(self, provider_id: str, model: str | None) -> int:
        """非交互直写 (--provider 或默认 provider): 用参数/内置默认生成条目。

        api_key_ref 固定为内置默认 env:VAR 引用 (deepseek→env:DEEPSEEK_API_KEY
        等; ollama 无 key) — 参数面不接收任何 key 输入, 明文 key 无入口。
        """
        defaults = PROVIDER_DEFAULTS[provider_id]
        return self._write_provider(
            provider_id,
            {
                "models": [model or defaults["model"]],
                "base_url": defaults["base_url"],
                "api_key_ref": _default_api_key_ref(provider_id),
            },
        )

    def _write_provider(self, provider_id: str, overrides: dict[str, Any]) -> int:
        """经 LLMControlPlane 写 providers.json (enable: 创建/启用 + 覆盖字段)。

        只写 api_key_ref 引用; upsert 语义 — 其他既有 provider 条目保留。
        """
        from .llm_control import LLMControlPlane

        plane = LLMControlPlane(
            providers_file=self.data_dir / "providers.json", environ=os.environ
        )
        plane.enable(provider_id, **overrides)
        print(
            f"  ✓ 已写入 providers.json: {provider_id} "
            f"(enabled, models={overrides['models']}, "
            f"api_key_ref={overrides['api_key_ref']})"
        )
        return 0

    def _show_provider_config(self) -> None:
        """展示当前 providers.json 配置 (只读; api_key_ref 是 env: 引用, 非明文)。"""
        from .llm_control import LLMControlPlane, ProviderFileError

        providers_file = self.data_dir / "providers.json"
        print(f"  当前 Provider 配置 ({providers_file}):")
        try:
            plane = LLMControlPlane(providers_file=providers_file, environ=os.environ)
        except ProviderFileError as exc:
            print(f"    ⚠ providers.json 损坏: {exc}")
            return
        providers = plane.list_providers()
        if not providers:
            print("    (空)")
            return
        for pc in providers:
            print(
                f"    - {pc.id}: enabled={pc.enabled}, "
                f"models={pc.models or '(无)'}, api_key_ref={pc.api_key_ref or '(无)'}"
            )

    def _init_validate(self) -> None:
        """校验 (step 4, 只读): 输出 ✓ 通过 / ⚠ 问题列表 (不阻断, rc 0)。"""
        problems = _init_validation(self.data_dir)
        if not problems:
            print("  ✓ Provider 配置校验通过 (enabled provider, API key 可解析)")
            return
        for problem in problems:
            print(f"  ⚠ {problem}")

    # ------------------------------------------------------------- 杂项

    def _show_log_tail(self, path: Path, lines: int = 30) -> None:
        """打印日志尾部 (启动失败诊断; 缺失/空 → 静默)。"""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        tail = text.splitlines()[-lines:]
        if not tail:
            return
        print(f"  --- {path.name} 日志尾部 ({len(tail)} 行) ---", file=sys.stderr)
        for line in tail:
            print(f"  | {line}", file=sys.stderr)

    def _stub(self, cmd: str) -> int:
        print(f"`factory {cmd}` 尚未实现 — 架构预留子命令 (计划 S10-007 阶段三实现)。")
        return 1


# ------------------------------------------------------------------ argparse


def build_parser() -> argparse.ArgumentParser:
    """argparse 结构: start/stop/status + doctor/service/config/init + 预留 project/run。"""
    parser = argparse.ArgumentParser(
        prog="factory",
        description="AI Software Factory — 一键启动/停止/状态 (S10-007 阶段二 CLI MVP)",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="命令")
    p_start = sub.add_parser(
        "start", help="启动服务 (缺省 = 全部内置服务 backend+frontend)"
    )
    p_start.add_argument(
        "services",
        nargs="*",
        metavar="服务",
        help="只启动指定服务 (backend/frontend/runtime; 缺省 = backend+frontend)",
    )
    p_start.add_argument("--no-browser", action="store_true", help="不自动打开浏览器 (headless/CI)")
    p_start.add_argument("--port", type=int, default=None, help="后端端口 (默认取配置, 8011)")
    p_start.add_argument(
        "--frontend-port", type=int, default=None, help="前端端口 (默认取配置, 5180)"
    )
    p_start.add_argument(
        "--dev", action="store_true", help="前端走 vite dev (默认托管 dist 构建产物)"
    )
    sub.add_parser("stop", help="停止前后端服务 (pid 文件优先, 兜底按端口)")
    sub.add_parser("status", help="显示端口/进程/数据目录/LLM 状态")
    p_service = sub.add_parser("service", help="服务注册表管理 (S10-026 P3)")
    p_service.add_argument(
        "service_action",
        choices=["list"],
        metavar="动作",
        help="list — 列出全部已注册服务状态",
    )
    p_doctor = sub.add_parser("doctor", help="运行诊断检查 (环境/Provider/模型/运行时/Router)")
    p_doctor.add_argument(
        "checker", nargs="*", help="只运行指定检查器 (缺省全部; 如 provider)"
    )
    p_doctor.add_argument("--json", action="store_true", help="输出结构化 JSON")
    p_doctor.add_argument("--verbose", action="store_true", help="显示检查详情")
    p_config = sub.add_parser(
        "config", help="Factory 运行时配置 (show/set/check/path)"
    )
    p_config.add_argument(
        "config_action",
        choices=["show", "set", "check", "path"],
        metavar="动作",
        help="show — 显示运行时配置 (脱敏); set — 写白名单键; "
        "check — 校验配置 (OK/WARN); path — 显示配置文件路径",
    )
    p_config.add_argument(
        "key",
        nargs="?",
        metavar="键",
        help="配置键 (仅 core.data_dir / core.port / core.frontend_port)",
    )
    p_config.add_argument(
        "value", nargs="?", metavar="值", help="配置值 (set 动作使用)"
    )
    sub.add_parser(
        "agent", help="Agent 管理骨架 (只读: 列出现有 agents 的 id/name/role/skills)"
    )
    sub.add_parser(
        "skill", help="Skill 管理骨架 (只读: 列出现有 skills 的 id/name/category/version)"
    )
    sub.add_parser(
        "task", help="Task 管理骨架 (只读: 列出 tasks 的 id/title/status/project)"
    )
    sub.add_parser(
        "router", help="LLM Router 管理骨架 (只读: 五层决策链可用性 + 当前决策)"
    )
    sub.add_parser("rag", help="RAG 管理骨架 (占位 — 规划中, 不实现功能)")
    p_audit = sub.add_parser(
        "audit", help="审计查询骨架 (只读: events 最近事件列表 + 按类型计数)"
    )
    p_audit.add_argument(
        "--limit", type=int, default=10, metavar="N", help="最近事件条数 (默认 10)"
    )
    p_init = sub.add_parser(
        "init", help="首次运行初始化: 环境检测 + workspace 目录 + LLM Provider 引导"
    )
    p_init.add_argument(
        "--force",
        action="store_true",
        help="已初始化也重新引导 (重新配置 LLM Provider)",
    )
    p_init.add_argument(
        "--non-interactive",
        action="store_true",
        help="非交互模式 (无 TTY 自动降级; 用参数或默认值直接生成配置)",
    )
    p_init.add_argument(
        "--provider",
        metavar="ID",
        help="非交互指定 provider (deepseek/openai/anthropic/ollama)",
    )
    p_init.add_argument(
        "--model", metavar="MODEL", help="指定模型 (缺省用 provider 默认模型)"
    )
    for name in STUB_COMMANDS:
        sub.add_parser(name, help=f"[预留] factory {name} — 阶段三实现")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 入口 (bin/factory 经 importlib 调用; sys.argv[1:] 默认)。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    return FactoryCLI(ConfigProvider()).run(args)


if __name__ == "__main__":
    sys.exit(main())
