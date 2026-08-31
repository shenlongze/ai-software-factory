# S33-CONV-P0-AUDIT — P0 Production Correctness 真实审计

> 日期: 2026-08-31 | 纯审计 (不修复) | 真实 API/存储/LLM/SSE 证据

## P0-01 Run State Truth — FAIL (P0)

```
现状: 5 个 Run 全部 running, 最老 476h (19天) / 91h / 4.3h
  检测: grep heartbeat/stale → 无机制
证据:
  ai-factory-sel | R1787861863011 | running | 91.3h前
  P-806fe6e8   | R1786473507972 | running | 476.8h前
  P-69c4f155   | R1788175174725 | running | 4.3h前
结论: 线程死亡后 progress.json 永远 RUNNING — 无 stale/心跳检测
问题: 用户看到"永远执行中" (僵尸 Run)
建议: heartbeat 超时 → stale; executor 消失 → FAILED
```

## P0-02 Duplicate Execution Protection — PARTIAL

```
✅ 前端: ConversationContext:293 `if (!text || sending) return` (发送防重)
✅ 后端: WorkflowConflictError → HTTP 409 (同项目并发 Run 拒绝)
⚠️ SSE 断连回退: 404-412 回退同步会重发 (若流中途断 → 可能重复工具调用)
⚠️ 无 correlation id / idempotency key
结论: 点击防重 ✅ / 断连重试幂等 ⚠️
```

## P0-03 Session/Project/Run Isolation — REAL

```
✅ 22 会话 → ai-factory-self; 1 会话 → project_043d829351f3
✅ 每会话独立 project_id + 独立 messages (抽查 3 个无串)
✅ Run: session.run_ids 集合关联 (1:N)
结论: 无串项目/串会话证据
```

## P0-04 Conversation Persistence — REAL

```
✅ 服务重启后 sessions 49 个全恢复 (含历史)
✅ GET messages 完整 (content + meta)
✅ Browser Refresh 实测 (番茄钟 240 字符完整)
✅ Run 持久化 (workflow_runs 独立于浏览器/重启)
```

## P0-05 Tool/Protocol Leakage — PARTIAL (P0 残留)

```
✅ 修复后新消息: 15:00+ 零泄漏 (3 层防线生效)
✅ API 出口: 0 泄漏 (GET messages 清洗)
⚠️ 存储层 27 条旧数据仍在:
   原因: 清理磁盘被服务内存写回覆盖 (SessionStore 内存 _data + _save)
   → 需重启后清理才持久 (Fix 阶段)
⚠️ 根因: 修复前各版本清洗不完整 (全角竖线 U+FF5C 变体绕过)
结论: 新数据安全, 历史污染需重启后清理
```

## P0-06 Natural Conversation — REAL

```
实测 (真实 LLM):
 轮1 "我想做一个番茄钟 App" → AI 理解并追问 (技术栈/平台)
 轮2 "它应该支持什么核心功能?" → AI 正确理解"它"=番茄钟
      → "25 分钟专注倒计时 + 5 分钟短休息 + 15 分钟长休息…"
指代理解真实有效 (多轮上下文保持)
```

## P0-07 Real Context Assembly — REAL

```
✅ context_view (topic_ledger build_view) 优先
✅ _history_text(max_turns=4) 兜底
✅ history 来自 GET messages (真实存储)
✅ 指代测试证明组装有效
```

## P0-08 Failure Honesty — REAL

```
实测: "P-NONEXIST-999 是什么项目"
→ "未查询到 P-NONEXIST-999 这个项目。当前系统里共有 13 个项目,
   但没有一个 ID 是 P-NONEXIST-999" — 诚实不编造 ✅
```

## P0-09 Cancellation — MISSING (P0)

```
现状: 只有 /api/runtime-sessions/{id}/cancel (另一套 runtime session)
      workflow Run 无 cancel API
      前端无停止按钮
结论: 用户说"停止"无法真实停止 Run (P0 — 但 Run 本身是后台线程)
建议: workflow Run cancel (状态 → cancelled + 线程中断)
```

## P0-10 P0 Acceptance — PARTIAL

```
✅ 全链路真实: Conversation→Context→Project→Run→Tool→Answer (番茄钟实测)
✅ 无 fake progress/completion/token (全真实存储)
⚠️ 僵尸 Run (P0-01) + 无取消 (P0-09) 使链路"可启动不可停止"
```

## Failure Matrix

```
P0:
  F1: Run 状态 stale (僵尸 running) — P0-01
  F2: Run 无取消能力 — P0-09
  F3: 存储层 27 条历史泄漏 (清理被内存写回覆盖) — P0-05
P1:
  F4: SSE 断连无 correlation id (回退可能重复)
  F5: 30+ 轮长会话未实测
  F6: budget 文件未配置
P2:
  F7: 累计 tokens/cost 面板
  F8: Search/Delete 缺失
```

## P0/P1/P2 分类 + 建议修复

```
P0 Fix 顺序:
  1. Run stale 检测: heartbeat + executor 存活 → stale/failed
  2. Run cancel API: POST /runs/{id}/cancel → cancelled + 中断
  3. 历史泄漏清理: 重启后清理 (或后端启动时自动清洗)
P1:
  4. SSE correlation id (幂等重试)
  5. 30+ 轮实测 (compact_context 验证)
  6. budget 配置
P2:
  7. 累计面板 / Search / Delete
```

## 当前 Conversation 作为唯一入口?

```
REAL: 自然对话/指代/上下文/持久化/隔离/诚实失败
P0 阻碍: 僵尸 Run 显示 / 无法停止 / 历史泄漏残留
评级: PARTIAL (P0 修复后 REAL)
```
