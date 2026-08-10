# S10-006 — Review Workflow（Completion Report）

> 日期: 2026-08-10 | 状态: 完成 (待人工审核) | pytest 6559 + vitest 267 + tsc 零错

## 交付内容

```
1. Review 三栏工作台 (ReviewWorkflowPanel, FactoryPanel Review Tab):
   - 左 Queue: 待审门列表 (Product/UXUI/Arch/Release 阶段标签 + 待审核徽章 + 产物 ref)
   - 中 Content: Artifact 类型化渲染 (复用 ReviewSections/artifactBody:
     product 6 节 / ux_ui Screen Card + wireframe ASCII / arch / code / test / release)
   - 右 Decision: ✅ Approve / ❌ Reject + Comment 输入 + review_feedback 历史

2. UX/UI Review 重点: Screen Card (页面名/Components/Actions) + wireframe ASCII 预览

3. Feedback Loop: Reject + 意见 → POST /api/review-feedback 保存
   {reviewer, artifact_id, comment, timestamp, round} → "反馈已保存, 将作为下一轮 Agent 输入"
   (round 按 artifact 递增; 空意见不落库)

4. Approval Gate 集成 (S9-001 复用): PENDING → approve/reject → 队列自动刷新落下一门

5. Timeline 联动: review 节点 "去审核" → Review 视图定位 gate (focusGateId + nonce)

6. 后端: ReviewFeedback 模型 + ReviewFeedbackStore (原子写) + GET/POST /api/review-feedback
   (过滤/400 空意见/503 缺 store 失败安全)
```

## 测试

```
后端 +30 (store/service/HTTP/adapter 装配: round 递增/空意见拒绝/持久化/404/审计)
前端 +10 (review-workflow.test.tsx: Queue/Content/Approve POST/Reject+Comment 保存/
  反馈提示/空态/mock/纯函数) + client +2
共 pytest 6559 (6531+28) + vitest 267 (257+10)
```

## 验收场景（Review Loop 闭环）

```
用户: 开发一个记账 App → AI: 生成 Product → 暂停 [🟡 Waiting Human Review]
用户: 审核需求 → Approve → AI: 生成 UX/UI → 暂停
用户: 看到页面设计 (Screen Card) → 意见 "按钮改大" → Reject
AI: 重新生成 UI (feedback 作为输入) → 再次审核 → Approve → 继续开发
→ 发布前: Release 审核 → Approve → 下载
```

## 截图

```
/tmp/s10-006-shots/review-workflow.png (1600×950, Review 三栏)
```

## 下一步 S10-007

```
CLI MVP: 统一 factory 命令 (init/start/status/create/review/approve/artifact/release)
— 与 UI 共用同一 Runtime API
```

## 限制（诚实）

```
1. Feedback Loop 数据流已通 (保存 + 展示); Agent 消费 feedback 重生成由真实 workflow 驱动 (S10-007/后续)
2. mock 队列用于演示 (真实 gate 来自 S9-001 workflow)
3. 历史记录: 当前会话内展示 (持久化查询 GET /review-feedback 已通)
```
