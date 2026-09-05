# 02 — IDENTITY / OWNERSHIP (P1 IMPL, 2026-09-05)

## 1. Identity 落地

IDEA-*/DISC-*/REQ-*/PRD-*/PLAN-*/TASK-* (P0) — 前缀唯一, 测试 test_ids_unique_prefix 实证。
旧 PI-*/req_* = legacy 未迁移 (D2/D19)。

## 2. Single Writer

每个 Entity 唯一函数 writer (见 01 表)。无 WebUI/Agent 直写 canonical store
(收敛点见 08)。Task 仍 service.create_task (P0, 未建第二 writer)。

## 3. 无第二个 canonical ledger

PLAN-* 唯一 plans store; session_plans (orchestration legacy) 保留未动。
