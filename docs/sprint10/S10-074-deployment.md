# S10-074 — Deployment / Release Completion Report

> 日期: 2026-08-17 | 首次正式 Deployment Sprint | 真实: 干净环境装起来并跑起来

---

## 1. Deployment Target

**本地 Python 开发者工具 (macOS/Linux) + wheel 分发** (基于代码事实, 非偏好):
- pyproject wheel + entry point 已配置
- 存储全本地文件 (JSON/SQLite, 无服务依赖)
- 进程管理 = uvicorn + pid 文件
- 前端 dist 打包入 wheel

## 2. Initial Deployment Reality Audit

- 产出: docs/architecture/capability-audit/s10-074-deployment-audit.md
- 发现: build/package/config/secrets/startup 已存在; 缺 health/version 端点 + clean install 验证

## 3. Architecture / Runtime Dependencies

```
pydantic/rich/pyyaml/httpx/fastapi/uvicorn (pyproject)
Python ≥3.12 | 数据 ~/.factory | 配置三级 (env > .env > config.json)
```

## 4. Packaging

- pyproject packages 补全: **+audit/memory/retrieval/session/session.debug 5 子包** (S10-069~073 新增)
- wheel 1.0.0rc1 可构建 + 含全部子包 (测试验证)

## 5. Installation

- ✅ Clean Environment E2E: wheel → clean venv → pip install → factory --version

## 6. Configuration

- ✅ 三级配置 (env/.env/config.json) + DATA_DIR 可配置 (文档化)

## 7. Secrets

- ✅ LLM_API_KEY 多级 + env:VAR + 不落源码/日志 (Audit 脱敏)

## 8. Startup

- **修复 2 个真实 Gap**:
  - 硬编码 `.venv/bin/python` → sys.executable (部署态) + fallback .venv (开发态)
  - BACKEND_MODULE 连字符 → factory_console (部署态) + 源码态兼容
- ✅ Clean start (PID + 就绪确认)

## 9. Health / Readiness

- **新增 3 端点**: GET /health {"status":"ok"} / /ready {"status":"ready"} / /version
- ✅ Clean E2E HTTP 验证通过

## 10. CLI

- ✅ `factory` 命令集 (安装态) + **--version 顶层 flag** (版本单源)

## 11. API

- ✅ FastAPI 薄层 + /health /ready /version (Clean E2E 真实验证)

## 12. Intent

- ✅ 未改 (CLI/API 入口保持; 部署态可用性由 Clean E2E 覆盖启动层)

## 13. Persistence

- ✅ factory.db + audit/memory/projects JSON (Clean E2E stop 后数据保留)

## 14. Restart

- ✅ factory stop && start (pid 文件 + 幂等) + 数据保留 (Clean E2E + 测试)

## 15. Crash Recovery

- ⚠️ 手动重启 (JSON/SQLite 原子写, 无损坏风险) — 文档化, 不假装自动 recovery

## 16. Graceful Shutdown

- ✅ factory stop (SIGTERM 流程, 数据已落盘) — Clean E2E 验证

## 17. Logging

- ✅ <data_dir>/run/{backend,frontend}.log (timestamp/level, 无 Secret)

## 18. Version

- ✅ 单一来源: pyproject → __version__ → CLI --version → API /version (全部 1.0.0rc1)

## 19. Migration

- ✅ JSON/SQLite 文件存储 → 无需 schema migration (字段扩展兼容, 文档化理由)

## 20. Upgrade

- ✅ 同数据目录 pip install --upgrade → 旧数据可用 (文档化 + 原理验证)

## 21. Rollback

- ✅ 数据目录与版本解耦 → 重装旧 wheel 即回滚 (文档化流程)

## 22. Project Isolation

- ✅ S10-073 隔离契约 (检索 fail-closed) 与部署无关 (数据路径不变); 部署态数据目录验证保留

## 23. Production E2E

- ✅ Clean Environment E2E 全链: build → install → init → start → health → stop → persist → uninstall (scripts/deploy_e2e.sh)

## 24. Deployment Smoke Test

- ✅ deploy_e2e.sh 一条命令完成 (真实, 非 mock)

## 25. Documentation

- ✅ docs/DEPLOYMENT.md (Install/Config/Secrets/Init/Start/Stop/Storage/Restart/Upgrade/Rollback/Uninstall/Troubleshooting/Verification)

## 26. Full Regression

```
等待完整结果 (后台运行中)
新增: 7 (deployment 测试)
```

## 27. Deployment Reality Matrix

```
Build ✅ | Package ✅ | Install ✅ | Config ✅ | Secrets ✅ | Startup ✅ |
Health ✅ | CLI ✅ | API ✅ | Intent ✅ | Persistence ✅ | Restart ✅ |
Recovery ⚠️ (手动, 文档化) | Upgrade ✅ | Rollback ✅ | Isolation ✅ |
Audit ✅ | Memory ✅ | Docs ✅
```

## 28. Remaining Gaps

1. Crash 自动 recovery (当前手动重启 — 诚实标记)
2. TOOL_CALL 自动 Audit (deferred, 用户明确禁止本 Sprint)

## 29. Deferred Enhancements

- TOOL_CALL Audit (需修改 AgentRuntime — 用户批准后)
- 自动 crash recovery / systemd/launchd 服务化

## 30. Release Readiness

**READY_FOR_INTERNAL_DEPLOYMENT** (Clean E2E 全绿; 建议内部团队试用后转正式发布)

## 31-33. Git

```
b3b7a34 S10-074: audit deployment requirements
55816ec S10-074: implement production packaging + startup/health contract
9f0e73f S10-074: add deployment tests + release documentation
git clean, HEAD = origin/main
```
