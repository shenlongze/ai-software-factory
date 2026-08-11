# S10-015 Task 005 Completion Report — Runtime Timeline + Task Detail Adapter

> 日期: 2026-08-12 | 状态: 完成 (待人工审核) | 范围: AI Factory Runtime 可视化 + 统一 Task Detail 数据模型
> 关联: S10-015-architecture-review.md / AF-UI-Architecture.md §8 (Runtime Monitor)

---

## 1. 实现内容

```
Part 1 — Runtime Timeline UI (AI 正在做什么):
  AfRuntimeTimeline.tsx      — 当前执行卡 (8 项) + 事件流 (AfTimeline 倒序) + 失败原因 + 空态
  AfRuntimePage.tsx          — 真实 GET workflow + timeline (Promise.all) → Adapter → 渲染; 四态
  runtime 路由接入           — #/project/{id}/runtime → AfRuntimePage (替换 placeholder)

Part 2 — Task Detail Adapter (统一数据模型):
  toRuntimeActivity 增强     — 真实事件 → 人话动作 (event_type→action), actor (agent→人话/无→系统),
                              result (OK→通过), stageId/eventType 透传
  toTaskDetail 统一          — backlog 定位 + children 反向关联 Epic/Feature/Story (为什么存在)
  AfTaskDetailPanel.tsx      — TaskDetail 全字段展示 + 缺失降级 + 历史 + 关闭
  Todo Tree 闭环接入         — 点击任务 → toTaskDetail → 右侧面板 (Task→Workflow→Runtime→Audit 链路)
```

## 2. 架构变化

```
新增 (前端, 后端零改动):
  pages/project/AfRuntimePage.tsx       — Runtime 页面 (数据获取 + 四态)
  components/af/AfRuntimeTimeline.tsx   — Runtime 可视化组件 (8 项展示 + 事件流)
  components/af/AfTaskDetailPanel.tsx   — Task Detail 统一面板 (Context Panel 基础)
  api/domain.ts 增强                    — toRuntimeActivity + toTaskDetail (双模式: backlog/实体)
  models/domain.ts 扩展                 — RuntimeActivity/TaskDetail 字段 (stageId/eventType/priority/...)

未改动:
  ✅ 后端 Domain (零修改)
  ✅ Workflow 核心模型
  ✅ 既有状态系统 (复用 DomainStatus 6 态)
  ✅ console 组件/页面
```

## 3. 数据流说明

```
Runtime Timeline:
  Backend Domain (workflow + timeline API)
    ↓ GET /api/projects/{id}/workflow + /timeline (Promise.all)
  Frontend Domain Adapter (toWorkflowPipeline + toRuntimeActivity)
    ↓ 人话映射 (Agent 名/动作/状态/结果)
  Runtime Timeline UI (8 项 + 事件流)

Task Detail:
  Backlog (Task API)
    ↓ GET /api/projects/{id}/backlog
  Frontend Domain Adapter (toTaskDetail)
    ↓ backlog 定位 + Epic/Feature/Story 反向关联
  Task Detail Panel (统一: Todo Tree / Workflow Viewer / Runtime 共用)
```

## 4. UI 说明 (浏览器实测)

```
#/project/P-806fe6e8/runtime → ScorePocket · 运行状态 (真实数据):

  当前执行:   失败 (AfStatusBadge)
  当前 Agent: 开发工程师 Agent        (真实 role 映射, 非假名)
  Workflow Stage: 开发
  开始时间:   2026-08-12 02:42
  持续时间:   41 分钟
  最近事件:   工作流失败: DeveloperError: provider response...
  下一步:     等待 测试工程师 开始「测试」
  失败原因:   DeveloperError: provider response contains no parseable
              patch or operations (after 1 retry)   ← 真实 failed_reason
  事件流:     29 条真实事件 (阶段就绪/开始/完成/失败/产物生成/验证)

#/project/P-806fe6e8/todo → 点击任务 "实现注册 API":
  右侧面板: 实现注册 API / 待办 / 所属: 计分核心→用户系统→用户注册 /
           优先级 P1 / 下一步: 等待开始执行 / 开始时间 / 历史
```

## 5. API 使用情况

| API | 用途 | 状态 |
|---|---|---|
| GET /api/projects/{id}/workflow | Workflow Instance (is_mock/failed_reason/stages) | ✅ 真实 |
| GET /api/projects/{id}/timeline | Runtime Event (29 条, 14 字段) | ✅ 真实 |
| GET /api/projects/{id}/backlog | Task Detail 定位 + Epic/Feature/Story 关联 | ✅ 真实 |
| GET /api/projects | Project 定位 | ✅ 真实 |

## 6. 测试结果

```
前端 vitest:  609 passed (51 files)  — 含新增:
  af-runtime-timeline.test.tsx   (8 项展示/失败原因/事件流/空态)
  af-runtime-page.test.tsx       (四态/重试/并行拉取)
  af-task-detail-panel.test.tsx  (全字段/缺失降级/历史)
  af-todo-tree-page.test.tsx     (闭环: 点击任务→面板→关闭)
  api-domain.test.ts             (toRuntimeActivity/toTaskDetail 映射/降级)
tsc:          0 error
build:        ✓
后端 pytest:  7507 passed (零影响)
```

## 7. 已知限制

```
1. TaskDetail.sprintName/workflowName 未填充 — 后端 backlog API 不含 sprint/workflow
   关联字段 (Sprint 是独立 API), 需 S10-016+ 组合 /api/projects/{id}/sprints 补充
2. Runtime 当前 Agent/Task 从 workflow failed/running 阶段推导 — 后端无独立
   "当前任务" 绑定; Task 级输入/输出 (用户示例的 "Created UserController.java")
   待真实 Agent executor 接入后从 runtime/ 提取
3. 失败场景为真实后端行为 (provider 无 parseable patch) — 非前端问题, 如实展示
4. is_mock workflow (旧项目 markpad) 明确标记 "演示数据 — 非真实执行", 不冒充
```

## Commit chain

```
6616dab  feat(S10-015): runtime timeline + task detail adapter (8 项展示 + TaskDetail 面板 + 测试)
713761e  feat(S10-015): todo tree task click → Task Detail panel (闭环: Task→Workflow→Runtime→Audit)
31c290f  fix: Lifecycle 404 优雅降级 (项目无生命周期记录 → 空态)
```

## 用户流程验收 (闭环)

```
✅ 1. 打开真实 Project      → #/project/P-806fe6e8 (ScorePocket)
✅ 2. 进入 Todo Tree        → #/project/P-806fe6e8/todo (真实 backlog 树)
✅ 3. 点击 Task             → 实现注册 API
✅ 4. 打开 Task Detail      → 右侧面板 (所属/优先级/下一步/历史)
✅ 5. 查看 Workflow         → #/project/P-806fe6e8/workflow (真实实例三层)
✅ 6. 查看 Runtime Timeline → #/project/P-806fe6e8/runtime (8 项 + 失败原因 + 事件流)
✅ 7. 完整链路              → Task → Workflow → Runtime → Audit
```

---

> 状态: 完成 | 下一步: 等待人工审核 (Task 006+ 不自动进入)
