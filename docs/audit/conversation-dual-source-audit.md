# S30-002 — Conversation Dual-Source Audit

> 日期: 2026-08-31 | 纯审计

## 一、双事实来源确认

| 链路 | 模块 | 行为 | WebUI 使用 |
|------|------|------|-----------|
| **sessions** | console_sessions.py + run_agent_native | 真实 LLM + 工具 + SSE | ✅ V2 WebUI (S30-001 六项 PASS) |
| **conversations** | conversation_os.py | 规则/关键词 + 模板 | ⚠️ 旧 ConversationPage (已被 V2 取代) |

## 二、问题

一个 WebUI Conversation 如果走不同 API 会得到不同 AI 行为:
- `/api/sessions/{id}/messages` → 真实 LLM
- `/api/conversations/{id}/messages` → 规则模板

**违反"一个 Conversation 一种行为"。**

## 三、消费者清单与判定

| 消费者 | 类型 | 判定 |
|--------|------|------|
| V2 WebUI (AfConversationCenter) | 前端 | ✅ sessions (正确) |
| 旧 ConversationPage | 前端 | 🔴 仍用 conversations — REMOVE (V2 已取代) |
| api/client conversations 方法 | API client | DEPRECATE (保留兼容, 前端不再用) |
| golden_suite | 测试 | KEEP (语义层测试) |
| conversation_quality | 质量 | KEEP (语义层) |
| project_os extract_requirement | 需求提取 | MIGRATE (接 session) |
| task_tree | 任务树 | MIGRATE |
| cli_factory conv 命令 | CLI | DEPRECATE (指向 session) |
| /api/conversations 端点 | API | DEPRECATE (保留, 不删) |

## 四、结论

**sessions = 唯一 WebUI Conversation Runtime (已定)。**
**conversations 保留为语义层 (长期上下文/决策), 不承担 LLM Runtime。**
**唯一动作: 移除旧 ConversationPage 对 conversations 的使用 (前端收敛到 V2)。**
