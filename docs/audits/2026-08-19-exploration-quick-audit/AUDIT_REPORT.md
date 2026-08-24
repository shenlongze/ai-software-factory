# AI Software Factory — 探索 + 快速审查报告

> 日期: 2026-08-19 | 模式: quick (超大仓库, 先快速扫描) | 方法: 代码事实 + 实测, 非文档声明
> 范围: 探索性全貌 + 健康度实测 + 顶层问题清单。全量深度审计待确认后执行。

---

## 一、这是什么 (探索结论)

**AI Software Factory (v1.1.4)** — "AI 员工操作系统 / AI 软件公司操作系统"。
治理驱动的 AI 软件生产平台: 把 AI 从问答聊天变成有岗位/流程/审批/审计/成本账单的员工。

### 技术栈 (实测)
| 层 | 技术 |
|---|---|
| 语言 | Python 3.12+ (requires-python >=3.12) |
| 后端 | FastAPI + uvicorn (localhost:8011), pydantic v2, rich, httpx |
| 前端 | React 18 + TypeScript + Vite (19 页面, 43+ 组件) |
| 桌面 | Tauri 2 壳 (WebView Host, 明确不做业务层) |
| 存储 | JSON 落盘 + SQLite (事件审计 append-only) |
| CLI | `factory` 统一入口, 18 个子命令 |

### 结构
```
factory-core/    冻结 Core (events/tasks/workflows/agents/... 27 子包)
factory-console/ 会话/意图/动作/CLI/API/Web (session/* 是最活跃层)
factory-exec/    Agent Runtime 执行引擎
factory-org/     组织/项目管理
factory-runtime/ 进程生命周期 + watchdog
desktop/         Tauri 壳
tests/           436 测试文件, 11774+ 测试
```

### 规模与健康
- git 跟踪 1575 文件; 生产代码 ~125K 行, 测试 ~160K 行 (既有审计口径)
- 79 个 FastAPI 端点 (63 个唯一 /api 路由) + /health /ready /version
- 前端 `npm run build` ✅ (1 个 CSS minify 警告); ruff: **157 错误**
- 全量测试实测: **11774 passed / 64 failed / 5 errors** (详见下)

### 近期活动
- S10-082 会话智能 (v1.1.1) → S10-083 真实执行+可观测 (v1.1.2) → S10-084 产品智能管线 (v1.1.4, 审查期间被提交 9aca34f)
- 工作区有一组未跟踪的诚实自审文档 docs/architecture/capability-audit/ (区分真实能力 vs 占位能力)

---

## 二、健康度实测 (本机运行结果)

```
python -m pytest -q           → 11774 passed, 64 failed, 5 errors (204s)
pytest (console script)       → 另有 3 个 tests/api/* 文件收集失败
ruff check factory-*          → 157 errors (101 unused-import, 24 E402, 10 F841, ...)
npm run build (frontend)      → 成功 (CSS minify 1 警告)
```

失败分类 (64 failed + 5 errors):
| 数量 | 位置 | 根因 | 性质 |
|---|---|---|---|
| 14 | test_frt_watchdog | `rt_pkg.watchdog` 属性不存在 (conftest 只预载 .cli, 未预载 .watchdog) | **真实 bug** |
| 5 | test_session_team_decision | `ConflictResolver()` 默认写真实 `~/.factory` (测试未注入 tmp 路径) | **真实隔离 bug** |
| 2 | llm router (全量才挂) | 顺序依赖/状态污染 | **真实脆弱性** |
| 31+8+5 | factory_runtime manager/cli/health | 沙箱禁子进程/socket (EPERM) | 环境限制 |
| 1 | test_s10_074_deployment | 测试需要 pip 网络下载 | 环境限制 |
| 1+1 | test_cli_init / test_cli_doctor | 依赖环境变量 (~/.factory 写入) | 环境/隔离 |

结论: **"全仓库 11768 passed" 的提交声明不可复现**; 至少 21 个失败是代码/测试本身的真实问题, 会污染真实用户数据或在 CI/干净机器上暴露。

---

## 三、Top 发现 (按影响排序)

### P1-1 测试全绿声称不成立 (健康度)
提交 9aca34f / CHANGELOG 声称 "全仓库 11768 passed", 实测 64 failed + 5 errors。
其中 watchdog 14 个 AttributeError 是确定性的: `tests/factory_runtime/conftest.py`
预载 `.cli` 却不预载 `.watchdog`, `rt_pkg.watchdog` 依赖别的测试先触发 manager
懒加载才存在。修复: conftest 加 `importlib.import_module("factory_runtime_pkg.watchdog")`。

### P1-2 S10-084 "7 角色资产链" 生产路径不接 LLM (产品诚实性)
`actions.product_pipeline` 以 `ProductPipeline(context.workspace, slug)` (llm_fn=None)
运行 → 7 个角色全部走 deterministic 模板, 输出内容自标 "规则占位, LLM 可细化"。
但基础设施已存在 (`ReasoningProvider` 可自建默认 llm_fn), 只是未接线。
用户看到 "产品管线完成: 7 个资产" 会误以为真实 AI 分析。这与既有审计
"名义/占位能力 ~15%" 是同一模式, 需在界面/文案诚实标注或真正接线 LLM。

### P1-3 测试写真实用户数据目录 (隔离性)
`test_session_team_decision.py` 的 `ConflictResolver()` 无参实例化 → 写
`~/.factory/teams/conflict_resolution.json`。正常机器会污染真实用户配置; 应注入 tmp 路径。

### P2-1 tests/api/* 用 `pytest` 直跑收集失败
`test_api_debug.py` / `test_api_memory.py` / `test_api_product_intelligence.py`
用 `import_module("factory-console.api...")` 但缺 sys.path 引导 (其余 132 个
文件都有)。CI 用 `python -m pytest` 侥幸通过, 开发者用 `pytest` 即红。
修复: 与 tests/llm 一致, 文件头部插入仓库根到 sys.path。

### P2-2 API 无认证/CSRF 防护
63 个 /api 路由含写操作 (POST create/delete/approve/chat/runtime execute),
仅绑定 127.0.0.1。本地任意进程或恶意网页可调用写端点, 无 token/Origin 校验。
对"治理/审计"定位产品, 这是需要明确的风险声明 (至少加 localhost token 或 Origin 校验)。

### P2-3 能力面落后于内核 (HTTP 缺口)
`api/product_intelligence.py`、`api/debug.py`、`api/memory.py`、`api/audit.py`
路由函数存在但**未挂 HTTP** (79 个 @app 装饰器中无对应端点)。旧审计
"接口层 100%" 的声明仍不成立; Product Intelligence 只能 CLI/会话触发。

### P2-4 lint 无门禁
ruff 157 错误 (101 unused-import / 24 E402 / 10 F841), CI 只跑 pytest 不跑 ruff。
建议: CI 加 ruff check; 清理 F401 (多为历史残留)。

### P3 文档/版本/残留
- README 严重过时: 页头 v0.1.0、"测试基线 8148 全绿" vs 实际 v1.1.4 / 11774+
- 版本单一来源脆弱: pyproject 1.1.4 但 PATH 上的 `factory` (~/factory-venv) 显示 1.1.3
  (运行时不重装不更新; 已装元数据 1.1.3 陈旧)
- 残留: `unused/teams/teams.json`、`demo/team_execution_state.json` (status=running 垃圾)、`$SMOKE_ROOT/`
- 前端 CSS minify 告警 (注释含 `=`)

---

## 四、做对的地方 (诚实加分项)

- **自审文化**: docs/architecture/capability-audit/ 明确区分真实能力 vs 占位能力, 不粉饰
- **失败安全**: 全链 fallback (LLM 失败→deterministic; 审计失败不中断; 单角色失败不中断管线)
- **密钥处理正确**: api_key_ref 只存 env: 引用, 不落明文; 有 redaction 测试
- **架构**: Core 冻结 + Extension 声明式注册 + 事件溯源为唯一事实源; 分层职责清晰
- **前端状态完备**: 31/43+ 组件含 loading/empty/error 态; 构建通过
- **CLI 面完整**: 18 子命令, doctor/init/start/stop/demo 全有
- **S10-083 真实交付**: patch 白名单→git apply→0 文件 FAILED 已接入 orchestrator (此前审计的 P0 断点已闭合)

---

## 五、建议下一步

1. 修 P1-1 (watchdog conftest) + P1-3 (~/.factory 注入) → 复跑全量确认可复现绿
2. P1-2 二选一: 真正接线 ReasoningProvider llm_fn, 或在输出/文案标注 "模板初稿"
3. P2-1/P2-4 顺手清理 (sys.path 引导 + ruff F401)
4. 然后运行全量深度审计 (product-professor full, 仓库 >800 文件, 10+ 子代理分类审查)
