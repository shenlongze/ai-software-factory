# AI Factory OS User Journey (K7)

> 日期: 2026-08-29

## 普通用户旅程
```
打开 OS → Conversation (默认首页)
→ "我想做一个类似 XX 的产品" (自然讨论)
→ AI 澄清 → 用户补充 → 需求形成
→ "确认, 就这么办" (Decision)
→ "帮我做" (Work 创建)
→ Project → Sprint → Task Tree (自动)
→ Agent 执行 (真实 codex/pytest)
→ Evidence → 结果回 Conversation
→ 用户: "现在什么进展?" → 真实投影
→ 用户: "为什么失败?" → evidence-backed 解释
→ 用户: "修复它" → S39 Recovery → 结果回 Conversation
→ 用户修改需求 → Replan → 继续
→ 用户关闭浏览器 → 重开 → 状态恢复 (SSOT 持久化)
```

## 原则
- Conversation = 唯一主要入口 (用户不需理解 Agent/Plugin/Runtime)
- 所有状态来自 SSOT (UI 零业务状态)
- 失败诚实呈现 (不伪造)
- 可追溯 (谁决定/为什么/谁执行/结果)
