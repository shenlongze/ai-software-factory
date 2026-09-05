# 00 — P1 IMPLEMENTATION (2026-09-05)

> Sprint: P1 Product Truth Implementation | Status: PASS
> 基线: 69ca3367 (P0-F4) | 依据: P1 Contract Freeze (GO, D1-D20)
> 范围: 5 Product Domain + Plan→Task provenance + traceability + 收敛违规点

---

## 1. 实现内容

### 新文件
- factory-console/product_truth.py — P1 Product Truth domain (唯一 canonical writer)
  - Idea (IDEA-*) / Discovery (DISC-*) / Requirement (REQ-*) / PRD (PRD-*+version) /
    Plan (PLAN-*) — 独立 store `<root>/product_truth/*.json`
  - 独立 lifecycle (受控转换表) / 幂等 (idempotency_key + 锁内原子写)
  - FK 链: idea_id → discovery_id → requirement_ids → prd_id/version → plan_id
  - forward_trace / reverse_trace (纯 FK 查询, 无 audit/filename 推断)
- tests/console/test_p1_product_truth.py (15)

### 收敛 (违规点 → canonical)
- agent_loop chain_start: requirement 内联 req_* (legacy 保留) + 新增 canonical
  REQ-* 同步写 (plan.req_canonical_id)
- fastapi_adapter plan 生成: PendingPlanStore (orchestration 保留) + 新增
  canonical PLAN-* plans store 同步写
- cli_factory: product (list/get 5 domain) + ptrace (TASK 反查上游) 命令

### 未动 (P0)
- Task = TASK-* canonical (P0) — 零修改
- P0 Execution chain 零修改

## 2. 目标链 (达成)

IDEA-* → DISC-* → REQ-* → PRD-* → PLAN-* → TASK-* → (P0) run-* → EXS-* → art-* → ver-* → EVD-*

真实 E2E-1 实证 + 反向 trace 全链。

## 3. 报告目录

docs/audits/2026-09-05-product-truth-p1-implementation/ (本目录 00-13)
