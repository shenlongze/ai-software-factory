# 05 — S47 ROADMAP (PLAN ONLY, 不执行)

## S47-A (P0): 无 (审计未发现 P0 假真相/不一致)
注意: 若有 — run 视图 mock fallback 被误读为真实 → 需徽章强化 (P2)

## S47-B (P1 — 主流程补全, 接 S45/S46 canonical)
1. Acceptance 控制面: 项目验收视图 — 拉 ACC-* (GET /api/projects/{pid}/
   acceptances) → 展示 Artifact/version/ver/PASS → [Approve]
   (POST /api/acceptances/{id}/approve) + [Request Change] (comment →
   POST request-change → 触发新 run/repair 后端已备)
2. Release 控制面: RELEASE 候选视图 (release_truth list/gate 状态) +
   [Gate] + 审批状态 + Release 结果 + 交付物入口 (dist zip 下载/路径)
3. Conversation→项目运行触发后: 项目 overview/quality 自动出现
   "等待验收" 状态卡 (串 mainline 终点)

## S47-C (P2)
4. 真时监控: run-status → 后端运行中 run 的实时 Agent/Task 状态卡
   (workflow_runner _RUNNING/liveness API 已有; 补轮询/SSE 面)
5. workflow 详情 mock fallback 后接真实 S46 run 事件 (progress/report →
   前端 timeline)
6. 任务树 → 任务详情 → run/EXS/ver 下钻 (canonical ver-*/art-* 接
   quality/workspace 区)
7. Delivery: 产物下载 + release 版本化展示

## Future (明确不做)
- Agent Runtime/Workforce/MCP/Knowledge/Learning UI 建设
- 前端架构迁移 / apps/ 搬迁 / IA 重构
- UI 美化/动效/设计系统扩展
- canonical P1 (REQ/PRD/PLAN) 并入 WebUI 旅程 (待 S46 follow-up 主线
  定稿后再接)

## 实施顺序 (S47 主线)
Idea 入口(已有) → Project/Conversation(已有) → Production Progress
(quality/overview 已有) → **Acceptance/Release 接入 (S47-B)** → 真时
监控 → Workspace/Preview → Evidence 下钻

## 验证门 (每步)
frontend test + tsc + backend API 启动 + 真实 E2E (S45/S46 链 UI 可见)
