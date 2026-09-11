# 00 — S47 WEBUI REALITY (2026-09-06, READ-ONLY)

> HEAD 503d3828。WebUI = Human Control Plane 现实审计。禁改代码。

## Executive Verdict
WebUI 是真功能集成的 React/Vite 单页 (35 af 组件 + ds 设计系统 + 700 行
真实 API client + 路由表驱动 2 级 IA), 大部分数据走真实后端
(/api/projects /tasks /workspace /artifacts /workflow /approvals ...)。
核心缺口 = **主链后端 (S44-S46 canonical) 已闭环, 但 WebUI 验收/发布
面 (ACC-*/RELEASE-*) 零接入** + 部分运行时视图依赖诚实 mock fallback。

## 8 问
1. 已完成: Conversation/Project/Workspace/TaskTree/Workflow 查看/审批
   gate 查看/Preview iframe — 真 API 投影
2. 真功能: 项目 CRUD、会话流、backlog 任务树、workspace 文件/产物/git、
   org workflow 详情、approval gate 查看+Approve(os 域)、preview
3. 假/mock/fallback: runtimeClient.getWorkflow/getTimeline/listRuntimes →
   真 API 失败→mock fallback (is_mock 诚实徽章, 非冒充); 无假 PASS
4. Idea→Product 主线覆盖: 前端到 EXECUTION 可见 (workflow 详情), 但
   canonical ACC-*/RELEASE-* (S45/S46) 无 UI → 主线验收段断开
5. 最大 P0/P1 缺口: P0 无 (无假真相/无第二逻辑); P1 = 验收/发布控制面
   未接 (ACC approve/request-change/release 全后端有前端无)
6. IA 调整: 基本合理 (workspace/project 2 级), 不重构; 需在项目页补
   "验收/发布" 入口
7. S47 做: 见 05 roadmap (接 S45/S46 能力 + 真时监控 + 旅程补全)
8. 不做: Agent Runtime/MCP/Workforce/Knowledge/前端架构迁移/UI 美化
