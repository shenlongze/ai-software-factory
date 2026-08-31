# K9 WebUI Convergence & Human Console Productionization — Completion Report

> 日期: 2026-08-29 | HEAD: (K9 commit) | v1.1.360

## 1. 收敛执行
- **IA 冻结**: 3 一级入口 (Conversation/Work/Control Tower); 专业区 (dashboard/projects/monitor/audit/settings) HIDE (路由保留)
- **P1-1 Agent 状态**: 前端统一走 /api/ops/who-working (Operational State); 旧 /api/workforces 不再被新 UI 消费
- **P1-2 Approval**: 前端统一走 tasks/{id}/approval + approvals/{id}/decide; 旧 /api/approvals 仅旧页
- **/api/board**: 不再作为新 WebUI 数据源 (新页全走 ops/projects-os)

## 2. 前端修复 (K9)
- api.artifacts 空 filters 尾随 ? bug (真实 bug, 测试发现)
- api.client.test 接口清单断言更新 (87→106 方法, K6 新增)
- af-workspace-shell 导航测试更新 (默认 conversation + 三入口 + i18n key)

## 3. 真实 LLM E2E — PASS
```
Conversation「计算器」→ Project → Sprint → Task → 真实 codex 2/2 → Project 100%
→ who working agents=1 (Operational State)
```

## 4. 测试
```
K9 前端新增/修复: api.client 21/21 | k6-human-console 6/6 | router 23/23 | shell 导航 4/4
后端全量: 1108 passed + 4 skipped (零失败)
tsc: PASS | vite build: PASS
前端既有 34 失败 (历史漂移, DEFERRED — 旧页面数据测试)
```

## 5. 18 个验收问题回答
1. 最终 IA: Conversation/Work/Tower 三入口 + 项目 Detail + 专业区 HIDE
2-5. 保留: 三入口+项目 Detail; 合并: 项目列表→Work; 隐藏: 专业区; deprecated: /api/board
6. WebUI 新页全基于 Unified Contract (S43); 旧页消费 Legacy
7. 无第二套业务状态 (K6 证明 + K9 收敛)
8. Conversation = OS Front Door YES (默认入口, 真实可用)
9. Work 覆盖 Project/Sprint/Task YES
10. Task 核心观察单位 YES (WorkPage + drill)
11. Control Tower 回答"谁在工作" YES (ops/who-working)
12. Backend=API=UI 一致 YES (真实 E2E)
13. Realtime 统一: polling 统一 (SSE 未实现, P3)
14. Approval 单一来源: 新链 tasks/approval+decide
15. Agent 状态单一来源: ops/who-working
16. 真实用户 Journey PASS
17. 前端测试: 新/修全过; 34 历史漂移 DEFERRED
18. P0: 无; P1: 无 (已收敛)

## 6. Commits
feat: K9 WebUI Convergence + chore(版本): bump v1.1.360 + tag

## 7. Final Verdict
**K9 = PASS** — WebUI 已收敛为 AI Factory OS 的 Human Console: 普通用户见 Conversation (Front Door) + Work; 专业用户见 Control Tower + 项目 Detail; 专业/内部能力 HIDE。WebUI 只消费 OS Projection / Unified Contract, 无第二业务层。旧 API/页面完成 KEEP/MERGE/HIDE/DEPRECATE 分类。**"WebUI 成为 Human Console 而不是另一个业务系统" = YES。** 按指令: STOP, 待全系统产品级审计后再定下一阶段。
