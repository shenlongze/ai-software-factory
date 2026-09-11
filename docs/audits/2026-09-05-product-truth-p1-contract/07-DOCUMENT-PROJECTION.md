# 07 — DOCUMENT PROJECTION (P1 CONTRACT, 2026-09-05)

> D8: Domain Truth → Document Projection (禁止反向)

---

## 1. 冻结分类

| 文件 | 分类 | 处置 |
|---|---|---|
| PRD.md (6) | **LEGACY document** (M3 规则生成) | 保留; P1 后新 PRD → PRD-* truth + PRD.md 由 service 再生 (projection) |
| product-definition.md | **PROJECTION** (Discovery 输出 doc) | 真实 Discovery truth 存 DISC-* entity; md 可再生 |
| session_plans.json | **ORCHESTRATION STATE** | 降级为投影/会话状态; canonical plan 进 plans store |
| session_topics / console_sessions | **ORCHESTRATION / SESSION STATE** | 非 domain |
| requirements.json | **LEGACY-CURRENT** (req_* 7 条) | 新链 REQ-* 写同文件 schema 升级 或 新 store; 旧 req_* 不迁移 (见 10) |
| discovery/conversation.json | **SESSION STATE** (discovery 对话记录) | 保留作会话历史; DISC-* 为收敛事实 |
| engineering.json / tasks.json / execution_plan.json | **M3 LEGACY** | 隔离 |

## 2. 冻结方向

```
Domain Truth (DISC-*/REQ-*/PRD-*/PLAN-* store)
      ↓ (service 投影)
Document (PRD.md / product-definition.md / 计划渲染)
```

**禁止**: 从 PRD.md / session_plans 反推 domain truth;
PRD.md 存在 ≠ PRD domain 存在。

## 3. PRD.md 现状 = 不可替代 SSOT?

否 — generate_prd 是确定性规则生成 (pipeline.ProductDocument 从 product
字段拼装), 无人工编辑痕迹依赖 → 可安全抽象为 projection (决策质量 §31)。
