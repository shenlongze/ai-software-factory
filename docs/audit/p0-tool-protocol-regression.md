# P0 — Conversation Tool Protocol 回归修复 (项目列表泄漏)

> 日期: 2026-08-31 | 状态: 修复完成

## 问题

用户输入 "项目列表",UI 显示 `<｜DSML｜tool_calls><｜DSML｜invoke name="bash_exec">...` 协议泄漏,且无自然语言回答。

## Root Cause Audit

### 1. 泄漏的精确形态

```
模型输出: <｜DSML｜tool_calls>  ← 全角竖线 U+FF5C 伪装!
实际字符: U+003C U+FF5C U+FF5C U+0044 U+0053 U+004D U+004C ...
→ 现有 ASCII 清洗正则 <tool_calls> 完全不匹配 (绕过! )
```

模型/provider 把 DSML 标签的 `|` 转义为全角 `｜`(U+FF5C),绕过所有 ASCII 清洗。

### 2. 双层问题

```
① 协议泄漏: 全角 DSML 变体未被 _strip_fake_toolcalls 覆盖
② 回答丢失: 模型该轮只输出协议 (无自然语言) → 清洗后为空 → 用户看到空回答
```

## Fix (3 处)

```
① _strip_fake_toolcalls: 全角竖线 U+FF5C → ASCII | 归一化
② DSML 前缀包装还原: <|DSML|tool_calls>/<||DSML||invoke> → 普通标签 → 常规清洗
③ 清洗后为空 + 工具已执行 → 注入强制总结提示让模型重答 (不能返回空)
```

## 验证

```
✅ 真实泄漏 384 字符 → 0 (全清除)
✅ 自然语言保留: "当前共有 8 个项目: | 项目名 | 状态 |..." (表格完整)
✅ 工具证据保留: project_status ✓ bash_exec ✓ (meta 结构化)
✅ 诚实: "3 个项目未设置名称,显示为项目ID本身"
✅ 测试 +4 (DSML 全角/双竖线/正常保留/表格渲染)
✅ 后端 1138 + 前端 517/518 + tsc 0
```

## 架构原则 (正式记录)

```
Internal Agent Protocol ≠ Assistant Content
Tool Execution ≠ Final Answer

User → Agent → Tool ──┬── Tool Call
                      └── Tool Result → Agent Context → Final LLM → Assistant Content
```

## Regression Matrix

| 能力 | 修复后 |
|------|--------|
| 普通聊天 | ✅ |
| 多轮会话 | ✅ |
| Tool Calling | ✅ |
| bash_exec | ✅ |
| project_status | ✅ |
| 自然语言 Final Answer | ✅ |
| Tool Protocol 不泄漏 | ✅ |
