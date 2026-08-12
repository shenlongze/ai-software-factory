# S10-015 Task 007 Completion Report — Quality Gate Interface

> 日期: 2026-08-12 | 状态: 完成 (待人工审核) | 范围: AI 生产交付标准 — AI 员工与人类的责任边界
> 关联: docs/design/AF-UI-Architecture.md / S10-015-architecture-review.md

---

## 1. 实现内容

```
Quality Gate Adapter (toQualityGateViewModel):
  组合 approvals + workflow + timeline 真实数据 → QualityGateViewModel
  (currentGate / checks / decision / approval / history)

AfQualityGate 组件 — 5 模块:
  ① Current Quality Gate   当前 Gate 卡 (名称/状态/artifact/confidence/risk)
  ② Required Checks        交付检查 (PRD/Architecture/Tests/Build/Human Approval)
  ③ Quality Decision       质量决策 (WAITING_FOR_REVIEW/APPROVED/FAILED/UNKNOWN)
  ④ Human Approval         人工审批 (Waiting/Approved by/Rejected reason)
  ⑤ Decision History       历史决策 (复用 AfTimeline)

AfQualityGatePage + 路由 (#/project/{id}/quality) + Dashboard 入口 (查看质量门 →)
```

## 2. Quality Gate 产品定位

```
传统: Developer → CI 检查 → Merge
AI Factory: AI Employee 生产软件 → 自动验证 → 质量评估 → Human Decision

Quality Gate = AI 员工和人类之间的责任边界:
  - AI 执行 + 产物生成 + 自动检查 (真实)
  - 人类审批 + 决策 (Waiting for approval)
  - 未达交付标准 → 如实展示 (Unavailable / Not available)
```

## 3. 数据来源

| 模块 | 数据源 | 真实 |
|---|---|---|
| Current Gate | GET /api/approvals (APR-001) | ✅ prd gate pending |
| Required Checks | approval + workflow 阶段 + timeline | ✅ 5 检查真实推导 |
| Quality Decision | approval.status → 决策态 | ✅ 等待人工审核 |
| Human Approval | approval by/comment/requested_at | ✅ auto-requested comment |
| Decision History | timeline org.approval/artifact 事件 | ✅ 真实事件 |

## 4. Adapter 设计

```
toQualityGateViewModel(approvals, workflow, timeline, projectId) 纯函数:
  currentGate: 主审批门 pending 优先 + requested_at 倒序 (无 → null)
  checks: 5 项真实推导:
    PRD Exists      ← approval artifact_type=prd → "PRD v7 已生成, 待审批"
    Architecture    ← workflow 有 architect 阶段? 无 → Unavailable (不编造)
    Tests Passed    ← testing 阶段状态 (待进行 → 待审核)
    Build Available ← release 阶段状态
    Human Approval  ← approval.status (等待人工审核)
  decision: approval.status → WAITING_FOR_REVIEW/APPROVED/FAILED/UNKNOWN
  approval: by/comment/requested_at (无 → null → "Not available")
  history: timeline org.approval.* / org.artifact.* 事件倒序 (无 → [])
缺失 → null/[]/Unavailable, 不崩溃 (§6.3 降级)
```

## 5. UI 模块说明 (浏览器实测 #/project/P-806fe6e8/quality)

```
Quality Gate
① Current Quality Gate: PRD (待审核)
② Required Checks:
   PRD Exists:         PRD v7 已生成, 待审批 → 待审核  ← 真实 (artifact_version 7)
   Architecture Review: 无架构阶段记录 → Unavailable    ← 诚实
   Tests Passed:       测试待进行 → 待审核              ← 真实 (testing pending)
   Build Available:    发布待进行 → 待审核              ← 真实 (release pending)
   Human Approval:     等待人工审核 → 待审核
③ Quality Decision: 等待人工审核
   auto-requested after prd generation (mandatory gate) ← 真实 comment
④ Human Approval: Waiting for approval · 请求时间 2026-08-06 18:40
⑤ Decision History: (真实 timeline 事件)
Dashboard: "查看质量门 →" → #/project/{id}/quality (闭环入口实测通过)
```

## 6. 测试结果

```
前端 vitest:  659 passed (55 files) — 含新增:
  quality-gate-adapter.test.ts  (13 测试: APR-001 映射/4 态决策/checks/降级/history)
  af-quality-gate.test.tsx      (10 测试: 5 模块/Current Gate/Checks/Approval/History)
tsc:          0 error
build:        ✓ (317KB JS)
后端 pytest:  7507 passed (零影响)
```

## 7. 当前限制

```
1. Decision History 当前较少 (后端无 org.approval.* 事件 — 审批流未完整执行)
2. Architecture Review 检查显示 Unavailable (当前 workflow 无 architect 阶段 — 诚实)
3. Quality Gate 页面未在 Project Sidebar 导航 (从 Dashboard 或 URL 进入;
   后续可在 Sidebar 增加入口)
4. Human Approval 仅展示 (审批操作属 Human Console 权限 — 执行权在人工一侧)
```

## Commit

```
2847c77  feat(S10-015): implement quality gate interface (AI 生产交付标准 — 5 模块 + Quality Gate Adapter + 真实审批 APR-001 + Unavailable 诚实态 + Dashboard 入口闭环)
```

## 闭环验收 (用户流程)

```
✅ Dashboard (Quality Summary) → 点击 "查看质量门" → Quality Gate
✅ Project → Workflow → Runtime → Quality Gate (URL 直达)
✅ Quality Gate → Current Gate / Checks / Decision / Approval / History (真实)
✅ 无数据 → Unavailable / Not available (不编造)
```

---

> 状态: 完成 | S10-015 全部 7 Task 完成 | 下一步: 等待人工审核 (S10-016 / Capability Center / LLM Center / Human Console 重构 不自动进入)
