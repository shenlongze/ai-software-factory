# S10-007 阶段二 — factory CLI MVP (start/stop/status)

> 日期: 2026-08-10 | 状态: 已实现 (MVP) | 基线: 3ab7ef5 (pytest 6630 / vitest 284)
> 范围: `bin/factory` 入口 + `factory-console/cli_factory.py` + 测试 + 文档
> 约束: 零新增依赖 (纯标准库); 不修改 Core / fastapi_adapter; 不读取 ~/.hermes; 不打印 key 明文

## 1. 交付内容

| 文件 | 说明 |
|---|---|
| `bin/factory` | 项目统一入口 (薄包装: 定位 .venv 解释器 → exec 为 cli_factory.main; 用户零配置, 不懂 uvicorn/vite/PYTHONPATH/npm 也能用) |
| `factory-console/cli_factory.py` | CLI 逻辑模块: 流程编排 + 模块级 IO 函数 (测试可 monkeypatch) |
| `tests/console/test_console_cli.py` | 追加 19 个测试 (S10-007 段注释分隔; 原有 14 个不动) |
| `docs/sprint10/implementation/S10-007-phase2-cli.md` | 本文档 |

## 2. CLI 设计

```
./bin/factory start [--no-browser] [--port N] [--frontend-port N]   # 一键启动
./bin/factory stop                                                  # 干净停止
./bin/factory status                                                # 端口/进程/数据/LLM
./bin/factory init|config|project|run                               # 预留 stub (阶段三)
```

### start 流程 (按序, 任一失败即停)

1. **环境检查**: python ≥3.10 (运行时 `sys.version_info`) / node ≥18 (`node --version` 解析) — 缺失/过低给清晰提示
2. **依赖检查**: `.venv/bin/python` 存在? 前端 `node_modules` 存在? — 缺失给 install 命令指引
3. **配置检查**: `ConfigProvider.get_llm()` key 缺失 → 提示 `.env.example` 指引, **不阻断**
4. **幂等**: pid 文件 + `kill(pid, 0)` 判活, 前后端均在 → "已在运行" 不重复起
5. **端口预检**: `socket.connect_ex` 探测 (仅检查需启动一侧); 占用 → 明确提示 + 配置修改指引 (PORT/FRONTEND_PORT)
6. **后端**: importlib 加载 `factory-console.web.backend.fastapi_adapter` (包名含连字符) → `create_app(factory_root=<data_dir>)` → `uvicorn.run`; bootstrap 经 base64 传子进程 (免引号转义); `start_new_session=True` (独立进程组, stop 整组杀)
7. **健康检查**: 轮询 `GET /api/projects` → 200 (30s 超时, 0.5s 间隔); 失败 → 打印 `backend.log` 尾部 30 行 + 清理 pid + rc 1
8. **前端**: `npm run dev -- --port <port> --strictPort --host 127.0.0.1` (strictPort: 端口被占立即失败而非换端口 — ScorePocket 5173-5177 冲突经验); 就绪检查 `GET /` 200; 失败 → 回滚停后端
9. **打开浏览器**: `open http://127.0.0.1:<frontend_port>/#/workspace` (`--no-browser` 跳过, headless/CI)

### stop

- 读 `<data_dir>/run/{backend,frontend}.pid` → SIGTERM → 等 2s → SIGKILL; 无 pid 文件/进程已死 → `lsof -ti tcp:<port>` 兜底按端口找
- 最后统一清理 pid 文件 (修复过: 循环内清理会吞掉后续服务的 pid 文件, 前端永远杀不掉 — 测试 test_stop_kills_pids_and_cleans_files 捕获)

### status

数据目录 / LLM (provider/model/api_key **只显示 已配置|未配置**, 不打印明文) / 前后端 (进程 + 端口监听) 四态: 运行中 / 进程在端口未监听 / 未托管进程占用 / 未运行

### 运行数据

- pid 文件 + 日志: `<data_dir>/run/backend.pid|frontend.pid|backend.log|frontend.log`
- 数据目录默认 `~/.factory` (ConfigProvider 分层: env > .env > ~/.factory/config.json > 默认; HOME 隔离即冒烟隔离)
- 端口默认: 后端 8011 / 前端 5180 (避开 5173-5177); `PORT`/`FRONTEND_PORT` 可配置

## 3. 测试 (19 个新增, 不真起服务)

- **argparse 结构**: 7 子命令全部注册 / start flags 解析 / 4 个 stub (init/config/project/run) rc 1 + "尚未实现"
- **环境检查**: python 过低 (MIN_PYTHON 提升触发) / node 缺失 / node 过低
- **依赖检查**: 假 root 无 node_modules → "npm install" 指引
- **配置检查**: key 缺失 → ".env.example" 提示但继续启动 (happy path mock 全通 rc 0)
- **生命周期**: pid 文件路径 / 幂等不重复起 / 端口占用提示 / 健康检查轮询 (0→0→200) / 超时 False / 启动失败日志尾部透出 / stop 杀 pid + 清文件 / status 输出 (key 不明文)

## 4. 真实验证 (干净环境 HOME 隔离, 真实起服务)

| 步骤 | 结果 |
|---|---|
| `HOME=$(mktemp -d) ./bin/factory start --no-browser` | rc 0; 环境检查过; key 缺失提示但继续; 后端 PID 45109 + 前端 PID 45111 后台起 |
| `curl /api/projects` | **HTTP 200** |
| `curl http://127.0.0.1:5180/` | **HTTP 200** |
| pid 文件 | `$HOME/.factory/run/{backend,frontend}.pid` 落盘 |
| `./bin/factory status` | 后端/前端 运行中 + 端口监听; provider=deepseek; api_key=未配置 (无明文) |
| 再次 `start` | "已在运行" rc 0, 不重复起 |
| `./bin/factory stop` | "已停止: 后端 (PID 45109), 前端 (PID 45111)" rc 0 |
| 端口释放 | 8011 / 5180 均连接拒绝; pid 文件已清理 |
| 端口占用场景 | 8011 被 http.server 占 → "✗ 端口已被占用" rc 1 + 配置指引; `stop` 无 pid 兜底 lsof 杀掉占用进程, 端口释放 |

## 5. 验证证据

- pytest 全量: **6649 passed** (6630 + 19), vitest 不动 (284)
- ruff check + ruff format 全过; py_compile OK

## 6. 未来扩展 (架构预留)

- `init` (阶段三): 初始化 ~/.factory + 配置向导 (幂等)
- `config`: 查看/编辑分层配置
- `project` / `run`: 委托现有 org CLI / workflow 引擎 (cli-design.md 十命令愿景)
- 预留点: argparse subparsers 已注册, 未来加子子命令 (project list 等) 零破坏; FactoryCLI 流程步骤独立成方法, 可按需拆 --skip-* 旗标
