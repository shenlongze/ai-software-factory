# S34-003B — P0 Tool Protocol Leakage & Response Integrity

> 日期: 2026-08-31 | 状态: 修复完成

## 问题

用户输入 "P-2f622bdf 是什么项目",UI 显示 `<tool_calls><invoke name="bash_exec">...` 内部协议。

## 根因定位(完整链路审计)

```
User Message → ConversationContext.send → POST /api/sessions/{id}/messages?stream=1
  → stream=1 → v3 run_agent_native (已清洗) ✅
  → 非 stream → v1 run_agent (无清洗) ❌  ← 泄漏源
    → agent_result.answer 直接 append 账本/落库
    → 前端渲染 content 含 <tool_calls> 原文
```

**泄漏点**: v1 路径 (fastapi_adapter 6739) 未调用 _strip_fake_toolcalls。
历史遗留: 旧版本无清洗时写入的孤儿消息 (session 不存在, meta 为空)。

## 修复(3 层防线)

```
① v1 路径清洗: agent_result.answer → _strip_fake_toolcalls (与 v3 一致)
② GET messages 出口清洗: 任何历史/其他路径残留 → 出口统一清除
③ _strip_fake_toolcalls 强化: <tool_calls>/<invoke>/<parameter> 块+散标签全覆盖
```

## 数据边界(确立)

```
AssistantResponse
  ├── content         ← 自然语言 (绝无协议)
  └── execution       ← 结构化
       ├── toolCalls  ← meta.tool_calls (真实)
       ├── toolResults← meta.evidence
       └── run        ← meta.run_ids
```

## 验证

```
✅ 清洗真实泄漏样例: 全部干净, 自然语言保留
✅ 正常文本 (粗体/列表): 不受影响
✅ 测试 +3 (块/正常/散标签)
✅ 后端 1129 passed + 前端 515/516 + tsc 0
```

## 原则(写入架构)

```
Internal Agent Protocol must never be rendered as Assistant Content.
Tool execution is evidence of an Assistant Response, not the Assistant Response itself.
```
