# 02 — IDENTITY CONTRACT (P1 CONTRACT, 2026-09-05)

> D2: 唯一 ID 冻结

---

## 1. 冻结 ID

| Entity | Canonical ID | 旧/legacy ID | 判定 |
|---|---|---|---|
| Idea | **IDEA-{hex8}** (新) | PI-{3-digit} (S9, 2 测试条) / create_feature idea (任务树) / product.json raw | PI-* = LEGACY (S9 审批域历史); 禁止作为新链 identity; 新 Idea 必须 IDEA-* |
| Discovery | **DISC-{hex8}** (新) | (无独立 id — conversation.json 无 id) | 无旧 id 冲突 |
| Requirement | **REQ-{hex8}** (新) | req_{hex12} (7 条, 内联) | req_* = LEGACY (session 内联历史); 禁止继续作为 domain identity |
| PRD | **PRD-{hex8}** (新) | (无 — PRD.md filename) | filename 永不作为 domain identity |
| Plan | **PLAN-{hex8}** (规范化) | PLAN-{hex8} (Web 生成, 3 处快照) | PLAN-* 前缀保留但必须单 store; session key / session_id 禁止作为 plan identity |
| Task | **TASK-{hex8}** (P0 冻结) | — | 保持 |

## 2. 禁止

- session_id 冒充 domain identity (session_plans 当前以 session key)
- filename (PRD.md) 作为 PRD identity
- req_*/PI-* 继续作为新 canonical id 生成
- 同一实体多个 id 别名

## 3. Identity Graph 冲突检查

IDEA-*/DISC-*/REQ-*/PRD-*/PLAN-*/TASK-* 前缀各一, 无重复/别名/隐藏 id;
PLAN-* 需收敛多快照 (见 08-PLAN-CONTRACT) — 无 P0 conflict。
