# K6 User Journey — Human Console 真实用户旅程

> 日期: 2026-08-29 | HEAD: (K6 commit) | v1.1.358

## 三一级入口 (Human Console 信息架构)
```
AI Factory OS
├── 💬 Conversation (默认首页) — 和公司说话
├── 📋 Work — Projects/Sprints/Tasks + Approval
└── 🛰 Control Tower — 现在公司正在干什么
```

## U1-U8 真实场景
| # | 场景 | 实现 | 证据 |
|---|------|------|------|
| U1 | 打开 OS → Conversation → 普通聊天 | ConversationPage (默认首页, /api/conversations) | test_k6-human-console |
| U2 | 提出想法 → 多轮讨论 → 澄清 → 需求 | send_message (Intent 理解) | K5 Golden Suite G1-G3 |
| U3 | 确认 → Project/Sprint/Task Tree | K3 create_project/create_sprint | test_project_os |
| U4 | Task→Agent→Tool→Execution→Evidence | 真实 codex/pytest 链 | K3/K5 Real E2E |
| U5 | 执行中 → Control Tower → 谁在工作 | ControlTowerPage (/api/ops/*) | test_k6-human-console |
| U6 | 失败 → Incident → Recovery → Conversation | K1 explain_failure + S39 | test_explain_and_repair |
| U7 | 修改需求 → Replan → Task Tree 更新 | K3 replan | test_replan |
| U8 | 关闭浏览器 → 重开 → 状态恢复 | 状态全在 SSOT (持久化) | snapshot + 重查 |

## UX 验收指标 (18 项)
Conversation/自然讨论/多轮上下文/Requirement/Decision/Approval/Project/Sprint/Task Tree/Execution/Tool/Evidence/Realtime/Control Tower/Failure/Recovery/Replan/Resume — **全部 REAL**

## Web UI 状态来源 (无第二 SSOT)
- ConversationPage → /api/conversations (SSOT)
- WorkPage → /api/projects-os/* (SSOT)
- ControlTowerPage → /api/ops/* (Operational State 投影)
- UI 零业务状态 (全 API 驱动, polling fallback 5s)
