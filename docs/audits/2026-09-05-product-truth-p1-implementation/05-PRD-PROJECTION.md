# 05 — PRD PROJECTION (P1 IMPL, 2026-09-05)

## 1. 边界落地

- PRD-* entity + versions (canonical) — product_truth/prds.json
- PRD.md = projection (renderer 职责; 本域不产生 md — test_prd_truth_not_document)
- 单向: domain truth → document

## 2. Version

approve_prd 生成新 version (content + created_at + actor); current_version 递增;
Task 经 plan.prd_version 锁定 PRD version (reverse_trace 返回 @vN)。
