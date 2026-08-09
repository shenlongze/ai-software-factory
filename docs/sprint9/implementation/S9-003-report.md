# S9-003 — UX/UI Review Interface（Completion Report）

> 日期: 2026-08-09 | 状态: 完成 (待人工审核) | pytest 6416 + vitest 121
> 目标: 人工在 Console 上评审 AI 产物 (Product 6 节 / UX-UI 7 节 + 线框预览) 并 approve/reject 带意见

## 功能实现（Review 页面 + 审批意见数据流）

```
1. Product Review 页 (ProductReview, 6 节):
   PRD 契约载荷 6 节渲染 (市场分析/用户画像/用户旅程/功能列表/MVP 范围/用户故事)
   — 字符串直出 / 数组列表 / 对象 JSON 保留结构; 缺节跳过, 全缺 → 空态

2. UX/UI Review 页 (UXUIReview, 7 节):
   信息架构/用户流程/线框图/屏幕规格/组件定义/设计令牌/原型说明
   + wireframe 节特殊渲染: ASCII 布局 <pre> 原样预览 (机器可读线框 →
     可视化) + Screen 卡片 (组件 skill-tag + 交互动作列表)
   + 结构缺失 → 回退通用渲染 (宽容失败安全)

3. approve/reject/comment 表单 (ReviewPage):
   pending 审批门 → 意见 textarea + Approve/Reject → POST body
   {reviewer:"console", comment} (空意见不发 comment 键 — S9-002 兼容)
   → 决定后自动刷新详情 (门状态即时更新) + 成功/失败提示 (409 终态冲突可读)
   终态门 → 只读展示决定结果 (不可撤销 — 审计铁律)

4. 导航: Artifacts 页新增「评审」入口列 → ReviewPage (← 返回产物)
   AppState Page 新增 { name:'review', artifactId } + App 渲染分支
```

## 数据流（意见 → 下一轮重生成输入）

```
评审意见 → POST approve|reject body.comment → org.approval 决定 (S9-001 复用)
  → ApprovalGate.comment 落库 (org ApprovalGateStore 既有字段, 零新存储)
  → GET /api/artifacts/{id} detail.review.comment 可读 (持久化可见)
  → 驳回后重生成: 读取 gate.comment 为反馈输入 (org 查询接口, 数据流可达)
  → 产物 metadata 回注 review_feedback (标注为输入; 不改 Agent 核心)
仅数据流接线 — Workflow/Artifact/Approval 状态机零改动 (S9-001 复用)
```

## API 扩展（后端 S9-003 先行完成）

```
GET  /api/artifacts/{id}    (新: metadata 契约载荷 + review 审批门; 404 映射)
POST /api/approvals/{id}/approve|reject  (增强: body.comment 透传落库; 无 body 兼容)
```

## 前端结构

```
pages/ReviewPage.tsx (新建) + ReviewSections.tsx (新建: SectionCard/SectionValue/
  WireframePreview/ProductReview/UXUIReview/GenericReview)
pages/ArtifactsPage.tsx (增强: 评审入口列)
api/client.ts (artifact(id) + approve/reject comment 可选参数) + App.tsx (review 分支)
models/types.ts (S9-003 先行: ArtifactDetail/PRODUCT_SECTIONS 6 节/UXUI_SECTIONS 7 节)
utils/wireframe.ts (S9-003 先行: parseWireframeScreens ASCII→组件, 宽容失败安全)
```

## 测试结果

```
后端: pytest 6416 (6402 + 14) 全绿
  tests/console/test_console_s9_003.py: gate comment 持久化 3 / 详情查询 6 /
  approve/reject with comment HTTP 4 / 反馈数据流 1
前端: vitest 121 (105 + 16) 全绿
  ReviewPage 11 (PRD 6 节渲染/approve+comment POST/reject+comment POST/
  空意见兼容/UXUI 7 节+wireframe 预览/回退渲染/终态门/无门/空态/404/409)
  wireframe 4 (解析全字段/畸形→空/空屏跳过+字段过滤/非字符串跳过)
  ArtifactsPage +1 (评审入口导航) + api.client 接口清单 +artifact
tsc --noEmit: 零错误
修复: SectionValue 对 React 元素 JSON.stringify 循环引用崩溃 (isValidElement 直渲)
```

## 限制（MVP 范围, 诚实）

```
1. 无线框图 → 图片/Figma 集成 (ASCII 文本预览 — 视觉设计仍需人工脑补)
2. 无图片生成/上传 (产物仍为文本契约 JSON; 无附件)
3. 审批无二次确认 (同 S9-002; 决定即终态, 不可撤销)
4. wireframe 预览仅结构化 screens 数组; 非结构 wireframe 回退 JSON 文本
5. 未实现 Dart/Flutter 验证 (S9-004 范围, 见下)
```

## S9-004 接入说明

```
S9-004 (Cost Ledger): 数据源 11A CostSummary 已在 ConsoleDashboard 七域返回
  (total_cost/calls/success_rate/by_provider) — Console 侧零后端改动即可新增
  成本页; 若需按项目/时间维度明细, 后端 11A cost 域需扩展 (S9-004 任务内定)。
Review 页 UI 组件 (SectionCard/WireframePreview) 可复用于成本报表卡片。
```
