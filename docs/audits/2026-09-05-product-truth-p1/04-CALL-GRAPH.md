# 04 — CALL GRAPH (P1 AUDIT, 2026-09-05)

> Product 链真实调用路径 (定位 source/function/writer)

---

## 1. 真实生产路径 (Web 会话)

```
POST /api/sessions/{id}/messages (fastapi_adapter)
  ├── 消息含 "制定开发计划" → plan_development (agent_loop:358, LLM 拆任务)
  │     → PLAN-{hex8} (fastapi_adapter:7438, Web 层临时 id)
  │     → 存 console_sessions / session_topics / session_plans (dict)
  │     → 待批准 (ask_approval=true)
  └── 批准/继续 → chain_start (agent_loop:443)
        ├── Requirement 落盘 (859-877): req_{hex12} → requirements.json
        │     (session_id/project_id, status=VALIDATED 硬编码)
        ├── plan → create_task (447-472): TASK-* + plan_id 注入
        └── → P0 execution (run-* → EXS → …)

Discovery/PRD 路径 (M3 项目域, 独立于上):
  actions/board 驱动: 项目 draft → discovery 会话 → complete_discovery
    (service:1598) → product-definition.md + lifecycle product_defined
  generate_prd (actions:511) → PRD.md (规则) + product.json status
    (该路径 0 真实 product_defined; PRD.md 6 个属 M3 legacy 项目)
```

## 2. 定位清单

| 步骤 | source:fn | writer | 持久化 |
|---|---|---|---|
| Plan 生成 | agent_loop:358 plan_development | fastapi_adapter:7438 | console_sessions/session_plans dict |
| Requirement | agent_loop:859-877 | agent_loop 内联 | requirements.json |
| Task 创建 | service.create_task (3969) | chain_start:472 | backlog task.json |
| Discovery | service.complete_discovery:1598 | 同上 | discovery/*.md (0 真实) |
| PRD | actions.generate_prd:511 | 规则 | projects/*/PRD.md |

## 3. 关键结论

- Plan→Task→P0 有真实调用链 (chain_start)
- Requirement 在 chain_start 内联产生 (与 plan 同函数) — 是 plan 的"标签"非上游
- Discovery/PRD 是**平行 M3 项目域**, 与 Web 会话主链 (req/plan/task) 不相交
- 无 User Intent → Idea → Discovery → Requirement 的连续调用链
