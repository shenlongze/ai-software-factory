# S10-046 Task 007 — Renderer Design

> 日期:2026-08-14 | Sprint: S10-046 CLI Design v2 | 设计, 未修改代码
> 目标: CLI 输出层 — 简单、清晰, 禁止复杂 GUI/过度动画

---

## 1. 渲染类型

| 类型 | 用途 | 示例 |
|---|---|---|
| Markdown | 文档/报告/帮助 | `factory run-status --id X` 的 report |
| Table | 列表 (项目/agent/成本) | `factory project list` |
| Progress | 执行过程 (阶段提示) | `[2/4] LLM 调用中...` |
| Diff | 代码改动展示 | demo run 后 patch 摘要 |
| Error | 失败提示 | `❌ Failed + Reason + Solution` |
| Cost | 成本/用量 | `usage: 1234 tokens · $0.0009` |

## 2. 渲染原则

```
1. 简单: 纯文本 + 少量符号 (✔/❌/→), 无 ANSI 动画
2. 一致: 同一类型同一格式 (Table 永远对齐)
3. 可解析: 不依赖颜色表达信息 (CI/日志友好)
4. 分级: 普通模式简洁, --verbose 详细
5. 机器可读: 全局 --json 覆盖为 JSON
```

## 3. 各渲染器设计

### Table

```
项目清单 (2 个)
  ID          名称
  P-xxxx      my-app
  P-yyyy      demo-app
```

### Progress

```
[1/4] Router 决策中...
[2/4] LLM 调用中... (12s)
[3/4] 验证中...
[4/4] 生成报告...
✔ 完成! 用时 41.8 秒
```

### Diff(核心价值展示)

```
--- main.py (before)
+++ main.py (after)
+ def hello():
+     print("Hello, world!")
```

### Error(已实现 S10-044)

```
❌ Failed

Reason:
  provider error: deepseek api key missing

Solution:
  export DEEPSEEK_API_KEY=... 后重试
```

### Cost

```
本次执行: 5,549 tokens · $0.0022 · 41.8 秒
会话累计: $0.0123 (5 次执行)
```

## 4. 渲染层架构

```
Service Layer (exec/org/...) → dict result
    ↓
Renderer (根据类型选择模板)
    ├── table_render(result)      → Table
    ├── progress_render(stage)    → Progress
    ├── diff_render(patch_text)   → Diff
    ├── error_render(failure)     → Error (S10-044 已实现)
    └── cost_render(usage)        → Cost
    ↓
Output (stdout / --json 覆盖)
```

**关键: Service Layer 返回结构化 dict, Renderer 负责展示 — 输出与逻辑解耦。**

## 5. --json 支持

```
所有命令支持 --json:
  factory run-status --id X --json  → 完整结构化结果
  factory project list --json       → {"projects": [...]}
  factory demo run "X" --json       → 执行结果

JSON = 机器可读 (CI/脚本); 人类默认 = Renderer
```

## 6. 边界

- 禁止: 复杂 GUI/动画/进度条(spinner 类)— 用阶段提示替代
- 禁止: 颜色作为唯一信息通道
- 允许: 简单 emoji/符号增强可读性(✔/❌/⚠/→)
- Renderer 是纯函数(输入 dict → 输出文本), 无副作用

---

> Task 007 完毕 | 6 渲染类型 | 简单清晰可解析 | --json 覆盖 | 逻辑与展示解耦
