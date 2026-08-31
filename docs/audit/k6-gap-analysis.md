# K6 Gap Analysis — Human Console & Real User Usability

> 日期: 2026-08-29 | HEAD: 589296b4 (v1.1.357)

## 12 项审计
| # | 能力 | 现状 | 判定 |
|---|------|------|------|
| 1 | Web UI 能做什么 | 5 导航 (dashboard/projects/monitor/audit/settings), 真实 API | PARTIAL |
| 2 | Conversation 唯一主要入口 | 后端 conversation_os REAL; **前端无 Conversation 页** | PARTIAL |
| 3 | Web 发起真实任务 | 无 Conversation 入口, 不能从 UI 发起 | MISSING |
| 4 | Conversation→Work 全链运行 | 后端 K1-K5 REAL; 前端未接 | PARTIAL |
| 5 | 实时执行状态可见 | control_tower/operational_state REAL (K4); 前端无 Tower 页 | PARTIAL |
| 6 | Control Tower 反映 Operational State | 后端 REAL (K4); 前端无 | PARTIAL |
| 7 | Task Tree 可追踪 | 后端 REAL (K2); 前端无 Task Detail | PARTIAL |
| 8 | Approval 在 UI 完成 | 后端 REAL (K3); 前端无 | PARTIAL |
| 9 | 失败/blocked/waiting/running 清晰呈现 | 后端 REAL (K4 why 链); 前端无 | PARTIAL |
| 10 | 互相 drill-down | 后端 REAL (K4); 前端无 | PARTIAL |
| 11 | UI 依赖统一 API Contract | api/client.ts fetch → /api/* (统一) | REAL |
| 12 | UI 自己维护状态 | 无 (全 API) | OK |

## 结论
- 后端全链 REAL (K1-K5); **前端缺 Conversation 默认页 + Control Tower 页 + Work/Task 视图**
- 核心 GAP = **Human Console 前端层**

## K6 设计 (前端最小三入口, 不扩 Core)
```
1. Conversation 页 (默认首页, 接 /api/conversations):
   - 新建/列表/消息发送 (send_message → Intent → 回复)
   - Work 状态内嵌 (work_items 状态行)
   - drill-down 到 Task (链接 /work/task/:id)
2. Work 页 (Projects/Sprints/Tasks):
   - 项目列表 (/api/projects-os 后端有, 前端接 projects)
   - Task Detail (operational_state drill → task→run→evidence)
3. Control Tower 页:
   - global_overview (/api/ops/overview)
   - who_is_working (/api/ops/who-working)
   - drill (/api/ops/drill/:project)
4. Approval: Conversation/Work 页内嵌 [批准/拒绝] (经 governance, 不直接执行)
```

## 禁止
- 第二套状态/Event/SSOT; UI 维护业务状态; 绕过 Governance; 扩 Core
