# S10-074 — Repository Deployment Reality Audit

> 日期: 2026-08-17 | 第一步: 先审计, 不先写 Docker/installer

---

## 一、当前真实依赖 (代码事实)

| 项 | 现状 | 位置 |
|---|---|---|
| 打包元数据 | ✅ pyproject.toml (0.1.0, setuptools) | pyproject.toml |
| 依赖 | pydantic/rich/pyyaml/httpx/fastapi/uvicorn | pyproject.toml |
| CLI 入口 | `factory` (factory_console.cli_factory:main) | pyproject [project.scripts] |
| API | FastAPI 薄层 + uvicorn | service.py + api/ |
| Web | 前端 dist 打包入 wheel (免 node) | factory_console.web.frontend.dist |
| 数据目录 | ~/.factory (DATA_DIR 可配置) | config.py DEFAULT_DATA_DIR |
| 配置 | config.json + .env + 环境变量 (三级) | config.py |
| Secrets | LLM_API_KEY 多级 (env > .env > config.json > provider 兜底) | config.py |
| 进程管理 | pid 文件 + lsof 兜底 + start/stop/restart 幂等 | cli_factory.py |
| 健康检查 | CLI start 轮询 (后端/前端) | cli_factory.py |
| 版本 | pyproject 0.1.0 (无运行时 __version__ 常量) | pyproject.toml |

## 二、Deployment Reality Matrix

| Capability | 现状 | Required | 状态 |
|---|---|---|---|
| Build (wheel) | pyproject 完整 | pip wheel 可构建 | ✅ DONE |
| Package | wheel 含 dist/前端 | 可 pip install | ✅ DONE |
| Install (clean) | 未验证 | clean venv pip install | ⚠️ 未验证 |
| Configuration | 三级配置 ✅ | 环境变量文档 | ✅ DONE |
| Secrets | 多级 + 不落源码 ✅ | redaction 测试 | ✅ DONE |
| Initialization | factory init | clean init | ✅ DONE (待 clean 验证) |
| Startup | factory start (uvicorn) | clean start | ✅ DONE (待 clean 验证) |
| Health Check | CLI 轮询 | **HTTP /health /ready** | ⚠️ MISSING |
| Version | pyproject 0.1.0 | **CLI --version + API /version 单源** | ⚠️ MISSING |
| CLI | factory 命令集 | 部署后可用 | ✅ DONE |
| API | FastAPI 薄层 | 部署后可用 | ✅ DONE |
| Intent | actions+intent | 部署后可用 | ✅ DONE |
| Persistence | JSON 落盘 (data_dir) | 重启保留 | ✅ 设计 ✅ (待 E2E) |
| Restart | stop/start | 状态恢复 | ✅ 设计 ✅ (待 E2E) |
| Crash Recovery | kill → start | 手动恢复 (JSON 原子写) | ⚠️ 文档化 |
| Graceful Shutdown | SIGTERM/SIGINT | flush audit/memory | ⚠️ 待验证 |
| Logging | 日志文件 (<data_dir>/run/*.log) | 分级 | ✅ DONE |
| Upgrade | 同目录升级 | 数据保留 | ⚠️ 待 E2E |
| Rollback | 旧 wheel 重装 | 文档化 | ⚠️ 待文档 |
| Uninstall | pip uninstall | 数据保留 (data_dir) | ⚠️ 待文档 |
| Isolation | S10-073 fail-closed | 部署后保持 | ✅ (待 E2E) |
| Docs | README + docs | 安装/升级/回滚 | ⚠️ 待补 |

## 三、Gap 排序

| Priority | Gap | 方案 |
|----------|-----|------|
| P0-1 | 无 HTTP /health /ready /version | service 层加端点 (FastAPI 薄层) |
| P0-2 | 无运行时单一版本源 | __version__ 常量 + CLI --version + API /version |
| P0-3 | Clean Environment 安装未验证 | Clean E2E: venv → pip install wheel → factory init → start |
| P0-4 | Persistence/Restart 未验证 | Restart E2E: Run A → stop → start → Run B 状态保留 |
| P1-1 | 升级/回滚未文档化 | Upgrade E2E + Rollback 文档 |
| P1-2 | Graceful shutdown 未验证 | SIGTERM 测试 |
| P1-3 | 部署文档 | Installation/QuickStart/Upgrade/Rollback |

## 四、Deployment Target 选择

**结论: 本地 Python 开发者工具形态 (macOS/Linux) + wheel 分发。**

依据 (代码事实):
- pyproject 已配置 wheel + entry point (非容器形态)
- 存储全 JSON 本地文件 (无 DB 服务依赖)
- 启动 = uvicorn 子进程 + pid 文件 (本地进程管理)
- 前端 dist 打包入 wheel (免 node)

→ 不选 Docker (无服务依赖, 容器无收益); 不选云 (无外部服务)。

## 五、结论

核心缺口: **health/version 端点 + clean install E2E + restart/persistence E2E + 部署文档**。
其余 (build/package/config/secrets/startup/cli/api/进程管理) 已真实存在。
