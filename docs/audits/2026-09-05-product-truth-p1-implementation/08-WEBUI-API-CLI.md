# 08 — WEBUI / API / CLI (P1 IMPL, 2026-09-05)

## 1. CLI (新增, 读 canonical)

- factory product idea|discovery|requirement|prd|plan list|get — 真实数据 rc=0
- factory ptrace TASK-* — reverse trace (LEGACY 任务诚实提示)

## 2. 收敛 (agent/API 直写 → canonical 同步)

- agent_loop: requirement 内联 req_* (legacy 兼容) + 同步 REQ-*
- fastapi_adapter: plan 生成 + 同步 PLAN-*
- 两处均失败安全 (except → 不阻断原流程)

## 3. WebUI

未改前端; 现有会话路径经 backend service (boundary 保持)。
