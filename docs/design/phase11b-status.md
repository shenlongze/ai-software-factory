# AI Software Factory — Phase 11B: Human Console Web UI

> 日期: 2026-08-06
> 前置: Phase 11A (227c414, 4069 tests)
> 目标: 用户交互层 — Human Console Web UI (基于 11A 只读 API)

## 架构

```
Browser → Web UI (React+TS) → Console API Layer (11A) → Factory Data
Web UI 只消费 Console API; 禁止修改 factory-core/console backend UI 逻辑
```

## 范围

- factory-console/web/frontend/ (React+TS: pages Dashboard/Projects/Lifecycle/Approval/Decisions/Intelligence/Providers + components/api/models)
- factory-console/web/backend/fastapi_adapter.py (最薄 FastAPI Adapter 挂 11A API)
- 产品体验: Dashboard 普通模式 / Project Workspace / Approval Center / Decision View / Intelligence View / Simple-Expert 切换
- 测试: 前端 Vitest ≥80 覆盖 (component/API integration/rendering/approval interaction/decision rendering/mode switching/permission)
- docs/human-console-ui-model.md + ADR-0035

## 边界 (不实现)

用户系统 / 支付 / SaaS 多租户 / Marketplace (商业化阶段)
