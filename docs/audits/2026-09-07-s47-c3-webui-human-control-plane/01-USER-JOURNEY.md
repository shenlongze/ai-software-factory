# 01 — USER JOURNEY (READ-ONLY, 逐项 A-J 判定)

| 步骤 | UI | 可进入 | 真 Backend | canonical | 知状态 | 知下一步 | 回退/前进 | 失败理解 | mock | dead |
|---|---|---|---|---|---|---|---|---|---|---|
| Idea 输入 | AfSidebar/AfContextNav createProject | ✓ | POST /api/projects | org ✓ | ✓ | ✓(chat 引导) | ✓ | ✓ | 无 | 无 |
| Create Project | AfProjectsView | ✓ | 真 | org ✓ | ✓ | ✓ | ✓ | ✓ | 无 | 无 |
| Conversation | workspace conversation | ✓ | 真 chat | session ✓ | ✓ | ✓ | ✓ | ✓ | 无 | 无 |
| 需求理解 | Conversation + overview | ✓ | chat/org | session | ✓ | ✓ | ✓ | ✓ | 无 | 无 |
| PRD/Workflow | workflow 页 (8 阶段) | ✓ | org workflow | M3/org (canonical P1 未接) | ✓ | ✓ | ✓ | 部分 | runtimeClient fallback 诚实 | 无 |
| Task Tree | todo 页 | ✓ | /tasks backlog | backlog ✓ | ✓ | ✓ | ✓ | ✓ | 无 | 无 |
| **Start 生产** | **chat 首消息 auto-start** (后端 chat_route: 未启动→start) | 隐式 | POST /chat | 真 | △(无显式按钮/提示) | △ | ✓ | ✓ | 无 | **显式入口缺** |
| Active Runtime | runtime 页 LIVE (S47-C1) | ✓ | SSE 真 | events db ✓ | ✓ | ✓ | ✓ | ✓ | 诚实 is_mock | 无 |
| Run Detail | AfRunDetail (S47-C2) | ✓(面板) | run detail API | progress+report ✓ | ✓ | ✓ | ✓ | ✓ | 无 | 无 |
| Stage 展开 | AfRunDetail 时间线 | ✓ | 同上 | ✓ | ✓ | ✓ | ✓ | ✓ | 无 | 无 |
| Repair/Retest | run detail 人话徽章 | ✓ | 真实 stage (repair 1/retest 1) | ✓ | ✓ | ✓ | ✓ | ✓ | 无 | 无 |
| Artifact | workspace 产物 + review art id | ✓ | /artifacts/{id} | M3+canonical 混合 | ✓ | △ | ✓ | ✓ | 无 | canonical art 不可点 |
| Verification | quality 页 + review ver id | ✓ | quality API | org gate; canonical ver-* id 经 release | ✓ | ✓ | ✓ | ✓ | 无 | 部分 |
| Evidence | — | ✗ | 无 REST | canonical EVD 存在 | ✗ | ✗ | ✗ | ✗ | 无 | TRACEABILITY_GAP |
| Acceptance | review 页 (S47-B) | ✓ | approve/request-change | ACC-* ✓ | ✓ | ✓ | ✓ | ✓ | 无 | 无 |
| Request Change | review 页 comment | ✓ | request-change API | ACC CHANGE_REQUESTED ✓ | ✓ | △(无"下一步=新 run"指引) | ✓ | ✓ | 无 | 编排提示缺 |
| Release Gate | review 页 | ✓ | create release→gate | RELEASE-* ✓ | ✓ | ✓ | ✓ | ✓ | 无 | 无 |
| Release | review 页 | ✓ | execute | RELEASE-* RELEASED ✓ | ✓ | ✓ | ✓ | ✓ | 无 | 无 |
| **Delivery** | review 页 artifact 列表 | **△** | 无下载端点 | dist zip 真存在 | △(看到 ID) | ✗(无取物指引) | ✓ | ✓ | 无 | **P1: 下载/打开缺** |

结论: 旅程 Idea→RELEASE 全程真实可走; **Delivery 终点断在取物**;
PRD/Evidence canonical 下钻缺失 (P2)。
