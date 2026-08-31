# K3 Conversation → Project Loop

> 日期: 2026-08-29

## 完整闭环
```
User "我要做一个简单的记账应用"
 ↓
Conversation (Intent DISCUSS/EXECUTE)
 ↓
Requirement (req_ 实体, parent=conv)
 ↓
Project (project_ 实体, source_conversation_id)
 ↓
Sprint (sprint_ 实体)
 ↓
Task Tree (task_ 层级, 串行依赖)
 ↓
Agent 执行 (真实 codex/LLM)
 ↓
Verification (真实 pytest)
 ↓
Evidence (evidence_ 实体)
 ↓
Project State (实时投影)
 ↓
Conversation "项目做到哪里了" → 从真实投影回答
```

## 持续运营
- 用户离开后回来: 新 conversation 查询真实 Project State (不需重解释)
- Requirement v2: 新版本 (supersedes) → 识别受影响 task → Replan (新 task)
- Approval gate: 高风险 task PENDING → 用户批准 → APPROVED / 拒绝 → REJECTED
