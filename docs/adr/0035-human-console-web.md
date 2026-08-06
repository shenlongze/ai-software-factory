# ADR-0035 — Phase 11B: Human Console Web (Web UI + FastAPI Adapter)

> 日期: 2026-08-06 | 状态: Accepted
> 前置: ADR-0034 (Phase 11A Human Console Layer)

## 背景

11A 建立了只读 Console API 层 (7 域 dashboard + 8 个读接口)。11B 需要把它
变成普通用户可用的产品入口: 浏览器 Web UI + HTTP 挂载。约束: 不污染
factory-core (零修改); 不修改 factory-console/models.py + service.py + api/**
(只读适配); 保持 Permission Boundary (零写路径)。

## 决策

### 1. factory-console/web/ 独立 Web 层 (backend + frontend)

```
factory-console/web/
├── backend/fastapi_adapter.py   # 最薄 FastAPI 绑定 (只读 + 静态托管)
└── frontend/                    # React 18 + TypeScript + Vite
    ├── src/pages/               # Dashboard/Projects/Lifecycle/Approval/Decisions/Intelligence/Providers
    ├── src/components/          # Card/Badge/ScoreBar/State/Table/EvidenceChain/ModeToggle
    ├── src/api/client.ts        # 只读 fetch 客户端 (全部 GET)
    ├── src/models/types.ts      # 11A 响应模型 TS 投影
    ├── src/state/AppState.tsx   # mode + page 轻量状态 (无外部路由依赖)
    └── src/hooks/useAsync.ts    # loading/data/error 三态
```

- Adapter 只做 HTTP 绑定 (参数解析/JSON 序列化/静态托管), 零 UI 逻辑;
  延迟 import 11A 路由函数与 Core 包 (Removal Isolation)。
- 依赖隔离: fastapi/uvicorn 仅装 console 侧 venv, 不触碰 pyproject.toml。

### 2. 只读铁律: 全部端点 GET, 无写路由

Adapter 只注册 8 个 GET 端点 (dashboard/projects/lifecycle/approvals/
decisions/recommendations/experience/providers), 不注册任何
POST/PUT/PATCH/DELETE。前端 api client 只暴露读取方法。审批/决定/创建等
执行权永远在既有引擎 (9c Approval 状态机 / CLI)。UI 上动作按钮仅弹出
只读指引 Modal (见 human-console-ui-model.md §5)。测试锁定:
test_only_get_routes_registered + client 无写方法断言。

### 3. 普通/专业双模式 (Simple-Expert)

默认普通模式 (项目→状态→需决定→为什么推荐), 专业模式展开
Provider/Cost/Agent/Evidence/Event。模式为前端状态 (刷新回默认 —
安全默认)。Providers 导航仅专家模式可见。

### 4. 审计集成

端点经 11A 路由函数注入 EventLogger → console.viewed /
console.dashboard.viewed 写入 events.db (与 ADR-0002 读审计同语义);
logger 缺失 → 静默 (失败安全)。

### 5. 静态托管与 SPA

frontend build 产物 dist/ 存在 → adapter 挂 StaticFiles (html=True)
托管 SPA; 缺失 → 纯 API 模式 (前端测试/开发走 vite dev proxy → 8011)。

### 6. 测试策略

- 后端: TestClient 冒烟 (8 端点 200/404) + Permission Boundary + 审计 +
  静态托管 (19 个用例, fastapi 缺失时跳过 HTTP 部分)
- 前端: Vitest + jsdom + Testing Library ≥80% 覆盖 (component 渲染 /
  Simple-Expert 切换 / Approval 交互 / Decision 渲染 / API mock / permission)
- 冒烟: uvicorn 起 adapter (临时工厂根) → /api/dashboard 200 JSON

## 边界 (不实现)

用户系统 / 支付 / SaaS 多租户 / Marketplace — 商业化阶段 (架构预留见
human-console-ui-model.md §6)。

## 验证

- pytest 全绿 (≥4090, 含 test_console_web_adapter 19 例)
- npm test 全绿 (覆盖率 ≥80%)
- npm run build 成功 (tsc --noEmit + vite build)
- 冒烟: uvicorn → /api/dashboard 200 + JSON; GET / 返回 index.html
- Core 零修改; models.py/service.py/api/** 零修改
