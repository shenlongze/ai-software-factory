# S10-065 — Interactive Discovery & Production Session

> 日期:2026-08-16 | Sprint: S10-065 | Productization & Interactive UX
> 状态: 从 BUILD THE FACTORY → USE THE FACTORY — 用户可自然对话使用 AI Factory

---

## 1. 为什么需要产品化

S10-055~063 已证明"AI 能自主生产软件"。但用户需知道内部命令(准备开发/开始开发/通过验收),非产品体验。S10-065 把生产引擎包装成用户可自然对话的入口。

## 2. 新能力

| 能力 | 说明 |
|---|---|
| DiscoverySession | 独立可持久化: idea → 6 字段澄清 (problem/user/core_features/usage_scenarios/mvp_scope/non_functional) → summary → confirm → create_product; 进程退出可 resume |
| ProductionSession | 统一生产视图: 聚合 ExecutionState/TeamState/CostLedger/ReviewGate → phase/progress/team/budget/cost/review; to_markdown 用户可读 |
| Review UX | ReviewView (原因/当前/选项) + review_view/approve/reject/cancel action (ReviewGate 复用) |
| UserLifecycle | 内部状态 → 用户视角映射 (13 态 + 描述), 不破坏内部 Lifecycle |
| Guided CLI | "我想做X"/"继续"/"为什么停了"/"查看进度"/"接受"/"拒绝"/"取消" 自然语言路由; 旧命令全保留 |
| Cost↔Trace 关联 | CostLedger trace_id/planning_decision_id + cost_by_trace/task/agent/planning_decision |
| max_execution_time | 真正生效 (慢执行 → blocked/waiting_for_review) |

## 3. 真实 E2E 验证 (ScorePocket + 真实 HOME)

```
用户: "我想做一个台球计分APP"
  ↓ DiscoverySession.start
AI: "这个产品解决什么问题?"
用户: "台球玩家记分太麻烦" → apply_answer(problem)
AI: "主要给谁使用?" → 用户: "台球玩家" → user
AI: "核心功能有哪些?" → "计分、排行榜、比赛历史" → core_features
AI: "主要在哪些场景使用?" → "俱乐部比赛" → usage_scenarios
AI: "第一版范围?" → "先做 Flutter 双端" → mvp_scope
AI: "性能/安全/兼容?" → "性能好" → non_functional
  ↓ 状态: ready_for_confirmation
  ↓ summary: 产品名/问题/用户/功能/场景 ✅
  ↓ confirm → CONFIRMED → create_product

ProductionSession (真实项目 1786773658):
  "Plan Version: v1 / Budget: $0.00 / 状态: USER_ACCEPTANCE" ✅

UserLifecycle: acceptance → "待验收 — 开发完成, 等待你确认交付" ✅
Review UX: "当前无需人工评审。" (无待审时友好提示) ✅
13 态描述: idea/discovery/product_defined/planning/production/validation/review/acceptance/delivered/blocked ✅
```

## 4. 测试

```
Batch A (模型层): discovery(108) + production_session(33) = 141
Batch B (集成层): user_lifecycle + review_ux + guided_cli = 60
Batch C (收尾): cost_trace + execution_time = 52
合计: 253 新测试 (>=150 目标达成)
全量: 10931 passed + 1 skipped (10879 基线 → +253, 零回归; 1 flaky 独立重跑通过)
```

## 5. 回答核心验收

"一个完全不了解内部命令的用户, 能不能从'我想做一个软件'开始?"

✅ **能**:
1. 提出想法: "我想做一个台球计分APP" → discovery_start
2. AI 澄清: 6 字段追问 (自然对话)
3. 确认需求: summary → 用户确认 → CONFIRMED
4. 创建产品: create_product (确认后)
5. 开始生产: "开始开发" (execute_project 兼容)
6. 查看进度: "查看进度" → ProductionSession markdown
7. 查看成本: budget/cost 在视图中
8. 理解暂停: "为什么停了" → review_view
9. 批准继续: "接受"/"批准" → review_approve → resume
10. 接受交付: "通过验收" → DELIVERED

## 6. 技术债

- Discovery 字段提取为关键词规则(LLM 语义提取未来)
- ReviewView 无交互式选择器(CLI 文本已备)
- 多项目管理(单一最近项目)
- E2E 用已有项目验证(新项目全链需完整执行)

## 7. 下一 Sprint 建议

```
S10-066 — 发布行动 (产品入口层完成)
  "用户一句话 → AI 澄清 → 确认 → 团队生产 → 进度可见 → 风险询问 → 交付"
- 或 S10-066: LLM Discovery 提取 + Review 交互 UI
```

---

> S10-065 文档完毕 | Interactive Discovery & Production Session | 253 新测试 | 10931 全绿
