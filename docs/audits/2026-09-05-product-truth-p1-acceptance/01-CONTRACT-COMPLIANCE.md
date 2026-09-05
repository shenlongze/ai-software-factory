# 01 — CONTRACT COMPLIANCE (P1 FINAL ACCEPTANCE, 2026-09-05)

> D1-D20 逐项合规矩阵 (代码证据)

---

| Contract | Requirement | Evidence | PASS/FAIL | Risk |
|---|---|---|---|---|
| D1 | Idea/Discovery/Requirement/PRD/Plan domain + Task P0; Intent 非 entity | product_truth.py 5 实体; 无 INTENT-*; Task 未动 (git diff 空) | **PASS** | — |
| D2 | IDEA-*/DISC-*/REQ-*/PRD-*/PLAN-*/TASK-* | 各 create 函数 _new_id 前缀; 测试 test_ids_unique_prefix | **PASS** | PI-*/req_* legacy 保留 (P2 观察) |
| D3 | 每域唯一 writer | create_* 唯一函数 (模块级); 外部调用仅 agent_loop REQ-* + fastapi PLAN-* 收敛 (均调本模块); 无直写 store (grep 零命中) | **PASS** | — |
| D4 | 独立 lifecycle; 状态=domain truth | _*_T 转换表 (受控, 非法拒绝); 状态存 store 非 event/doc 推断 | **PASS** | — |
| D5-D6 | Idea→Disc 1:N, Disc→Req 1:N, Req→PRD N:1, PRD→Plan 1:N, Plan→Task 1:N; prd_id nullable | FK 字段: disc.idea_id / req.discovery_id / prd.requirement_ids[] / plan.prd_id+version / task.plan_id; plan.requirement_id MVP 直连 (prd_id 空允许) | **PASS** | — |
| D7 | PRD version; Task 经 Plan 达 version; Plan immutable | approve_prd → current_version+1 + versions[]; plan.prd_version; 无 plan update API (grep 零命中) | **PASS** | — |
| D8 | PRD-* truth; PRD.md projection; 无反向 | product_truth 不写 md (测试); 无 md→domain 读回 (grep 零命中) | **PASS** | — |
| D9 | Plan SSOT = plans store; session_plans = orchestration | product_truth/plans.json 唯一; session_plans 读取仅旧 M3 API 投影 (1569) | **PASS** | P2: 旧 API 仍显示 legacy plans |
| D10 | TASK-* canonical 不变; 历史不 backfill | git diff P0 零改动; reverse_trace 无 plan_id → 诚实断链 (测试) | **PASS** | — |
| D11 | Intent 输入事实; 无 INTENT-* | 未新增 entity | **PASS** | — |
| D12 | Discovery truth = DISC-* | create/complete_discovery 持久化; conversation.json/md/event 未作 truth | **PASS** | — |
| D13-D15 | Requirement domain; PRD entity+version+req refs; FK trace | REQ-* store + lifecycle; PRD versions + requirement_ids; forward/reverse_trace 纯 FK | **PASS** | — |
| D16-D20 | Legacy 隔离; 无迁移; event 观察; P1→P0 边界; P0 chain 保持 | 见 06-LEGACY-ISOLATION + 04-P0-BOUNDARY | **PASS** | — |

**D1-D20 全 PASS — 无 P0/P1 契约违规**
