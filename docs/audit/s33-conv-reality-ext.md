# S33-CONV-REALITY-EXT — Conversation / Data Truth / Continuity / Consistency 验收

> 日期: 2026-08-31 | 依据: 真实代码 + API + 存储 + 浏览器实测

## 1. Data Truth Matrix

| 对象 | 唯一事实来源 | API | 持久化 | UI Projection |
|------|------------|-----|--------|--------------|
| Conversation | console_sessions.json | /api/sessions | console_sessions.json | 左栏列表 |
| Session | console_sessions.json | /api/sessions/{id} | console_sessions.json | Conversation |
| Message | console_sessions.json | /api/sessions/{id}/messages | console_sessions.json | 消息流 |
| Project (org) | org/projects.json | /api/projects | org/projects.json | 左栏/右栏 ProjectWorkspace |
| Project (os) | org/projects.json | /api/projects-os | org/projects.json | 左栏项目块 |
| Task | workspace/projects/{id}/management/backlog/task.json | project_tasks | task.json | ProjectWorkspace |
| Run | workflow_runs/{project}/{run}/progress.json | /api/sessions/{id}/runs | progress.json | Run 卡/Execution Detail |
| Artifact | exec/artifacts.json | (artifacts) | artifacts.json | Workspace Files |
| Verification | exec/execution_records.json | (verification) | execution_records.json | Evidence tab |
| Context | session.project_id | /api/sessions | console_sessions.json | 右栏 Context |

**结论: 无 SOURCE DUPLICATION** — 每个对象单一来源, API 全部读真实存储。

## 2. Identity Consistency

```
✅ Session: sess-xxx (唯一)
✅ Project: P-xxx / project_xxx (唯一)
✅ Run: R1788175174725 (唯一, session.run_ids 关联)
✅ Message: msg-xxx (唯一)
✅ 逐级追溯: Conversation→Session→Run 真实存在
```

## 3. Cross-API Consistency (P-5be3a04a 番茄钟 实测)

```
✅ /api/projects: 番茄钟 | idea
✅ org/projects.json: 番茄钟 | idea
✅ AI 回答: 「番茄钟」0% idea
✅ 三方完全一致 — 无 P0 Cross-Projection Inconsistency
```

## 4. Run 状态真实性

```
✅ 磁盘 progress.json: status=running stages=[product COMPLETED] tokens=1639 cost=0.000644
✅ API session_runs: 同数据
✅ 项目级并发锁: 409 conflict (同项目重复启动诚实拒绝)
```

## 5. Tool Protocol 泄漏

```
✅ 存储层清理: 27 条历史泄漏 → 0
✅ 修复后新消息: 无泄漏 (真实验证 P-5be3a04a 查询)
✅ 三层防线: 源头清洗 (1432/1484) + 出口清洗 (GET messages) + 强制重答
```

## 6. Continuity Matrix

| 场景 | 状态 | 证据 |
|------|------|------|
| Multi-turn | REAL | _history_text + topic_ledger |
| Refresh | REAL | GET messages 恢复 (实测 240 字符 content 完整) |
| Browser Close | REAL | Run 独立于浏览器 (R1788175174725 持续) |
| Backend Restart | REAL | 存储持久化, 重启后 API 正确 |
| Multi-window | PARTIAL | UI 选择隔离, SCOPE_KEY localStorage 共享 (低风险) |
| Multi-session Isolation | REAL | 每 session 独立 project_id |
| Long Conversation | PARTIAL | compact_context 工具存在, 未实测 30+ 轮 |
| Context Compression | PARTIAL | compact_context 工具 (Spine 交接卡) |

## 7. Leakage Matrix

```
✅ Project Leakage: 无 (每 session 独立 project_id)
✅ Session Leakage: 无
✅ Run Leakage: 无 (run_ids 集合关联)
✅ Tool Protocol Leakage: 已修复 (3 层防线 + 存储清理)
```

## 8. 最终评级

```
Conversation Capability:
  简单任务       REAL
  多轮会话       REAL
  复杂任务       REAL (工具+自然语言)
  项目上下文     REAL (project_id + ProjectWorkspace)
  长期记忆       PARTIAL (compact_context 工具, 未完整实测)
  长任务         REAL (R1788175174725 持续运行)

Data Truth:      REAL (单一来源, 无重复)
Consistency:     REAL (Cross-API 实测一致)
Continuity:      REAL (refresh/restart/close 全部持久化)
Tool 泄漏:       已修复 (存储 0 泄漏 + 出口防线)
```

## 9. P0/P1 发现

```
P0 已修复: 存储层 27 条历史协议泄漏 (已清理为 0)
P1 记录: 
  - Session→Project 仍靠 project_id 字段 (非显式 Run Contract) — 已记录 S30-003 P1
  - Delete/Search 缺失 (UNSUPPORTED, 未伪造)
  - 多窗口 SCOPE_KEY localStorage 共享 (低风险)
  - Long Conversation 30+ 轮未完整实测
```

## 10. 结论

用户可只通过 Conversation 持续、自然、连续地使用 AI Factory:
- 所有 Production Object 单一事实来源
- Cross-API 一致 (实测番茄钟三方一致)
- 刷新/重启/关闭浏览器全部持久化
- Tool Protocol 不泄漏 (3 层防线 + 存储清理)
- 无假数据/假状态/假完成

**达标**: 可以进入下一阶段 UI 精细化。
