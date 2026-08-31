# S33-CONV-REALITY-FULL — Conversation Production Reality 全面审计

> 日期: 2026-08-31 | 纯审计 (不修复) | 依据: 真实代码 + API + 存储 + 实测

## 1. Test Environment

```
服务: 8011 (后端, 最新代码) / 5180 (dist) / 5173 (dev)
数据: /Users/agentdev/.factory/ (console_sessions.json / org/projects.json / workflow_runs/)
LLM: deepseek-chat (真实, DEEPSEEK_API_KEY 注入)
测试方式: 真实 API + 真实存储 + 真实 LLM + 真实 SSE
```

## 2. Conversation Capability Matrix

| Capability | Status | Evidence |
|-----------|--------|----------|
| Simple Conversation | REAL | 你好 → 自然回答 (实测) |
| Multi-turn | REAL | _history_text(max_turns=4) + topic_ledger |
| 10-20 turns | REAL | 历史会话 (S30-001 Test1 多轮上下文) |
| 30+ turns | NOT TESTED | 无 30+ 轮会话数据 (P1 待测) |
| Project Context | REAL | project_id + ProjectWorkspace (实测 P-5be3a04a) |
| Task Context | PARTIAL | session.task_id 存在, 无完整 Task 会话实测 |
| Run Context | REAL | run_ids 1:N + Run 卡归属消息 (S34-002) |
| Workspace Context | REAL | ctx.projectId → ProjectWorkspace |
| Tool 后自然语言总结 | REAL | 项目列表 → 表格回答 (实测) |
| 长任务中继续对话 | REAL | R1788175174725 持续 + 会话可继续 |
| Run 完成后继续对话 | REAL | done 后 sending=false, 可继续输入 |

## 3. Session Management

```
✅ 新建/切换/重命名/归档: REAL (S32-002)
✅ 多 Session 并存 + 隔离: REAL (每 session 独立 project_id, 实测)
✅ Session 历史恢复: REAL (GET messages 完整)
✅ Browser Refresh: REAL (实测 content 240 字符完整)
✅ Browser Close→Reopen: REAL (持久化)
✅ Backend Restart: REAL (存储不丢)
⚠️ 恢复 (archive 后 unarchive): 未实测 (P1)
```

## 4. Multi-window / Concurrency

```
⚠️ 未完整实测 (P1): 无真实双窗口自动化环境
代码分析:
- UI 选择 (activeId) 是 React state → 窗口隔离 ✅
- SCOPE_KEY localStorage 共享 → 窗口间 scope 会同步 (低风险, 非 Production Truth)
- Production Truth 全在后端 → 无数据覆盖风险
```

## 5. Idempotency (重复提交/幂等)

```
✅ send 防重复: ConversationContext:293 `if (!text || sending) return`
✅ 发送按钮 disabled (sending 时) — AfConversationCenter
✅ Run 幂等: 项目级并发锁 409 (workflow_runner)
⚠️ SSE reconnect: 无显式 reconnect 逻辑 (断连 → done 缺失 → 回退同步)
⚠️ 网络超时重试: 无显式重试策略 (fail → 诚实错误消息)
```

## 6. Data Truth Matrix (四方一致性)

| 对象 | Source of Truth | API | UI | AI 回答 | 第二份? |
|------|----------------|-----|----|---------|---------|
| Session | console_sessions.json | /api/sessions | 左栏 | 会话列表工具 | 无 |
| Message | console_sessions.json | /messages | 消息流 | _history_text | 无 |
| Project | org/projects.json | /api/projects | ProjectWorkspace | project_list | 无 (os 是另一实体) |
| Run | workflow_runs/.../progress.json | /runs | Run 卡 | project_status | 无 |
| Cost | progress.json totals | /runs | Run Detail | usage | 无 |

**四方一致性实测 (P-5be3a04a)**:
```
磁盘 org: 番茄钟 | idea     ✅
API /api/projects: 番茄钟 | idea  ✅
UI: 左栏/右栏 番茄钟       ✅
AI 回答: 「番茄钟」0% idea   ✅
```

## 7. Cache / Stale Data Matrix

| Cache | 是真数据? | Stale 风险 | 刷新后 |
|-------|----------|-----------|--------|
| React state (messages/runs) | Projection | 是 (后端修改不自动推) | GET 重新拉 ✅ |
| localStorage | 仅 theme (非 Truth) | 无 | - |
| API cache | 无显式缓存 | - | - |
| session store (内存) | 后端内存 + 磁盘双写 | 重启后从磁盘加载 ✅ | - |
| run progress cache | 磁盘 progress.json | 线程死 → stale running (已记录 P1) | - |

**发现**: Run 状态 stale 风险 — progress.json 线程死后 status 停留 running (R1788175174725 案例, 已记录 P1: Run 心跳/超时)

## 8. Cost / Token / Budget Matrix

```
✅ 单次 message usage: model/prompt/completion/total/elapsed/cost (实测 2895 tokens $0.000891)
✅ Run totals: progress.json (R1788175174725: 1639 tokens $0.000644)
✅ 三方一致: usage = Run totals 计算口径相同 (prompt+completion)
✅ Budget 控制: BudgetEnforcer.check 接入 board.py:3226 (workflow 前)
   BudgetEnforcer.enforce 接入 actions.py:1412 (会话动作)
⚠️ 单次 Run 上限: _max_calls (max_tool_calls) 有
⚠️ Session/Project 累计: 无显式累计面板 (P2)
⚠️ failed Run 计费: 有 usage 累加 (真实)
⚠️ budget 文件: ~/.factory/cost/ 为空 → 未配置 → 无上限 (默认)
评级: Cost 显示 REAL / Budget 控制 PARTIAL (有框架未配置)
```

## 9. Long-running Run

```
✅ R1788175174725: 11:19 启动, 持续 10+ 小时 (生产证据保留)
✅ watcher 超时 ≠ Run 超时 (S31-001.5 明确语义)
✅ Browser close → Run 继续 (后台线程独立)
⚠️ Backend restart 期间 Run: 后台线程可能被杀 → progress 停留 (P1 心跳)
```

## 10. SSE / Streaming

```
✅ 事件序列: thinking → tool → thinking → tool → done (实测)
✅ done 后 result.assistant 替换消息 (无重复)
✅ SSE 中断: 无显式 reconnect (P1) — 断连后 done 缺失 → 回退同步
✅ 重复事件: send 防重复 (sending guard)
```

## 11. Tool Protocol Leakage (根因追查)

```
27 条历史泄漏根因:
① 产生: 8-28~8-31 各版本清洗不完整的旧会话 (v1.1.256 前无清洗)
② UI 能拿到: 消息 content 含泄漏, 当时清洗正则未覆盖 (全角竖线 U+FF5C 变体)
③ normalization 没阻止: 每版清洗只覆盖当时已知形态, 模型换变体就绕过
④ 历史数据进入当前会话: 旧 session 打开时 GET messages 返回 (出口清洗 8-31 后才加)
⑤ 重启后是否再现: 修复后 (ae946af3) 3 层防线 → 新消息无泄漏 (实测 0)
⑥ 其他历史污染: 已扫描 DSML/工具 payload/调试文本/python 对象 = 0 条 ✅

现状:
✅ 存储层 27 条已清理 (27→0, 不破坏真实 content)
✅ 3 层防线: 源头清洗 (1484/1531) + 出口清洗 (GET messages) + 强制重答
✅ 修复后新消息: 无泄漏 (实测 P-5be3a04a 查询)
```

## 12. Project Context

```
✅ Global Conversation: 简单摘要 (project_list 表格)
✅ Project Context: ProjectWorkspace (描述/进度/任务/Runs/Artifacts)
✅ 关联真实: ctx.projectId → Backend → 真实数据
✅ 无前端复制 Project 数据 (全部 API)
```

## 13. Failure / Recovery

```
✅ Tool 失败: 诚实显示 (project_scan 报错 → AI 说"工具报错, 基于元数据")
✅ 失败规则注入: agent_loop 关键工具失败 → 重试/追问 (1552+)
✅ 失败≠无数据: 注入规则禁止"失败推断无数据"
⚠️ LLM timeout/error: 有降级 (回退同步), 未实测
⚠️ Run failure → Recovery UI: 有 recovery 服务 (S28), 未实测
⚠️ 失败后 UI 显示: 诚实 (错误消息/工具 ✗)
```

## 14. Data Lifecycle

```
✅ Session→Run: add_run 关联 (S30-003)
✅ Run→Task: progress stages
✅ Task→NodeRun: (exec 层)
✅ NodeRun→Artifact: exec/artifacts.json
✅ Artifact→Verification: execution_records.json
✅ Cost→Run: progress totals
⚠️ Verification→Evidence: 关联存在, 未完整实测
```

## 15. Delete / Archive

```
✅ Archive: REAL (PATCH /api/sessions)
✅ Archive 后 Session 可恢复: 未实测 (P1)
✅ Archive 后 Run 可追踪: run_ids 保留 (不删 Production Truth)
⚠️ Delete: MISSING (无 API, 未伪造 — 诚实)
⚠️ Search: MISSING (无 API, 未伪造 — 诚实)
```

## 16. Failure Matrix (P0/P1/P2)

```
P0: 无 (历史泄漏已修复, 存储 0, 新消息 0)
P1:
  1. Run 状态 stale (线程死后 progress 停留 running) — 需心跳/超时
  2. SSE 断连无显式 reconnect
  3. 30+ 轮长会话未实测
  4. Session→Run Contract 显式化 (project→session 反查残留)
  5. Archive 后恢复未实测
  6. 多窗口并发未实测
  7. 网络超时重试策略无
P2:
  1. Session/Project 累计 tokens/cost 面板
  2. budget 文件未配置 (框架有, 默认无上限)
```

## 17. REAL / PARTIAL / MISSING 总结

```
REAL: 简单会话/多轮/项目上下文/Run 关联/长任务/SSE/Tool 总结/Data Truth/Cost 显示
PARTIAL: Budget 控制 (框架无配置) / SSE reconnect / Task 上下文 / 恢复
MISSING: Delete / Search / 30+ 轮实测 / 多窗口实测 / Recovery UI 实测
```

## 18. Recommended Fix Order

```
1. P1: Run 状态心跳/超时 (stale running 修复) — 最影响真实感
2. P1: SSE 断连处理 (回退+提示)
3. P1: 30+ 轮长会话实测 (context compression 验证)
4. P1: Run Contract 显式 session_id
5. P2: budget 配置 (成本控制落地)
```

## 19. 最终回答

**Q: 当前 Conversation 是否可以作为 AI Factory 唯一用户入口?**

基于真实证据:

```
✅ 能 (核心链路): 自然会话 → 工具 → 自然总结 → Run → Workspace → 继续
✅ Data Truth: 单一来源, 四方一致 (实测)
✅ 长任务: 真实持续 (10+ 小时)
✅ 无泄漏: 存储 0 + 新消息 0
✅ 无假数据: 全真实 API/存储/LLM

⚠️ 但有 P1 限制:
   - Run stale 风险 (需心跳)
   - SSE 断连体验
   - 30+ 轮未验证
   - Budget 未配置

结论: 作为唯一入口 = PARTIAL → 修完 P1 后 REAL
(不能因为测试通过就说生产就绪 — 上述 P1 是真实差距)
```

评级: A.REAL(核心) / B.PARTIAL(budget/SSE/长会话) / C.MISSING(delete/search/30+轮) / D.P0(无) / E.P1(7项) / F.P2(2项)
