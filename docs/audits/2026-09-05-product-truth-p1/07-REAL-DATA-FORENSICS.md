# 07 — REAL DATA FORENSICS (P1 AUDIT, 2026-09-05)

> 真实数据矩阵 (只读, 2026-09-05)

---

## 1. 数量矩阵

| 对象 | 数量 | 说明 |
|---|---|---|
| Projects (org) | 27 | lifecycle: idea 12 / discovery 1 / confirmed 13 / development 1 — **零 product_defined** |
| Ideas | 2 | PI-001/PI-002 (Test Idea/Demo — 测试性质, S9 product 域) |
| Discoveries (产物) | 0 | 零 project 有 discovery/product-definition.md (complete_discovery 从未真实完成) |
| Requirements | 7 | req_* 全 VALIDATED (飞机大战 ×4 等; 硬编码 VALIDATED) |
| PRD.md | 6 | ai-factory-self + 5 M3 legacy 项目 (番茄钟/密码管理…) — 无 req 关联 |
| Plans (session_plans) | 16 | session keyed; 4 带 requirement_id; 无独立 plan_id 键 |
| PLAN-* (Web 生成) | ≥1 | PLAN-d84e51ba (life-e2e) 存 session_topics+session_plans+console_sessions |
| Tasks | 156+9+… | ai-factory-self 156 (零 plan_id); life-e2e 9 (全 plan_id) |
| console_sessions | 78 | 全无 product_intent/goal/topic 字段 (仅 title/summary) |
| session_topics | 81 | 话题标签 (非 Product entity) |

## 2. 关键观察

- **零 product_defined**: 系统设计的正式 Discovery→product-definition→confirmed
  主链从未有项目真实走完 — confirmed 13 项目走的是旧版 (M3/直接 confirmed)
- PRD.md 6 个中至少 5 个属 M3 legacy (product.json 无 idea_id, 有 execution_plan/
  tasks.json)
- 7 requirements 全 VALIDATED (无 created/pending/draft) — status 无生命周期
- requirements.json 里 req_d4256a957b4f 等 3 个与 session_plans 里 4 个 req_id
  有交集吗: sess-c7ec7c5aad→req_d4256a957b4f — 需确认存在 (requirements.json 7
  条中 id 抽样见 00; 部分 req 可能孤儿)

## 3. 数据断链

- 27 项目 ↔ 7 requirements: requirement.project_id 多为 P-b0adfaa6 (飞机大战)
  或空 — 仅覆盖少数项目
- PRD.md ↔ requirements: 零关联
- Idea (PI-*) ↔ Requirement (req_*): 零关联 (两套 id 体系)
