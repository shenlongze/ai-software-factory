# K8 WebUI & Human Console Architecture Audit — Completion Report

> 日期: 2026-08-29 | HEAD: 3c9f9016 (v1.1.359) | 纯审计 (HARD STOP, 零代码修改)

## 12 个最终问题
1. **/workspace 是否应成为默认入口?** YES — 已是 (K6: #/workspace → conversation), 验证 200
2. **Conversation 是否真正可用?** YES — 新建/继续/自然讨论/Work 状态内嵌/钻取 (K6 页面 + K7 Journey)
3. **当前页面负责什么?** 29 页: K6 三入口 (新) + 项目 8 页 + 旧 board 系 (Dashboard/Decisions/Intelligence/Lifecycle/Review/Providers/Workflow/Artifacts/Approval/Projects)
4. **哪些页面重复?** 项目列表 3 处 (AfProjectListView/AfProjectManage/ProjectsPage); AfMonitorPage ≡ ControlTowerPage
5. **/api/board 定位?** 历史遗留 HTML 控制台 (非 JSON API), 被旧页面消费, 建议 deprecate
6. **WebUI 是否消费 Unified Contract?** 新三页 YES (/api/conversations + projects-os + ops, S43 风格); 旧页面消费历史 API
7. **WebUI 是否存在第二套业务状态?** NO — K6 三页全 API 驱动, 零业务状态 (测试证明)
8. **Realtime 是否统一?** NO — 各页 polling/手动; SSE Contract 已定义未实现 (P3)
9. **Conversation/Work/Tower 边界?** Conversation=入口+讨论+决策; Work=项目/迭代/任务+审批; Tower=运营观察+钻取
10. **普通用户看到什么?** Conversation (默认) + Work
11. **专业用户看到什么?** + Control Tower + 项目 Detail + (HIDE 区: Audit/Settings/Intelligence)
12. **最终 IA?** 3 一级入口 (Conversation/Work/Tower), 旧页面 HIDE/MERGE/DEPRECATE

## K8 Architecture Verdict
```
WebUI Status:         HUMAN CONSOLE 收敛中 (新三页 REAL, 旧页并存)
Conversation:         REAL (默认入口, K6/K7 验证)
Work:                 REAL (Project/Sprint/Task/Approval)
Control Tower:        REAL (Overview/WhoWorking/Drill)
API Integration:      新 API SSOT 投影; 旧 API 并存 (收敛建议)
Unified Contract:     新页面消费; 旧页面未迁移
Realtime:             polling (SSE Contract 定义, 推送未实现)
Data Consistency:     Core=API=UI 一致 (新链); Agent/Approval 双来源 (GAP)
UX:                   三入口清晰; 旧页认知负担 (收敛建议)
Architecture:         WebUI ≠ 第二业务层 (K6 证明)

Current WebUI Readiness: 78/100

P0: 无
P1: Agent 状态双来源 (workforces vs ops); Approval 双 API — 收敛到新链
P2: 旧页面并存 (HIDE/MERGE); /api/board deprecate; 前端 39 测试失败
P3: SSE 推送; Incident 视图; Task Detail 独立页

Recommended IA: Conversation / Work / Control Tower (3 一级入口)
Recommended Next Sprint: K9 — WebUI 收敛执行 (HIDE 旧页 + Agent/Approval 收敛 + 测试修复)
```

## 验证
- 真实服务: 5180 (200) + 8011 (318 API) + /api/board (HTML 确认)
- 零代码修改 (纯审计)
- git clean

等待架构决策。不自动进入 K9。
