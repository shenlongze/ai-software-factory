# S10-046 Task 006 — Completion Engine Design

> 日期:2026-08-14 | Sprint: S10-046 CLI Design v2 | 设计, 未修改代码
> 目标: TAB 自动补全 — 命令/参数/项目/Agent/Skill/Provider/路径

---

## 1. 补全目标

| 补全类型 | 示例 | 数据来源 |
|---|---|---|
| 命令补全 | `fact<TAB>` → factory | Static Command Registry |
| 子命令补全 | `factory d<TAB>` → demo/doctor | Static Command Registry |
| 参数补全 | `factory run --pro<TAB>` → --project | Static Command Registry |
| 项目补全 | `/project <TAB>` → P-xxx / my-app | Factory Registry (projects.json) |
| Agent 补全 | `--agent <TAB>` → backend-1/flutter-dev | Factory Registry (agents.json) |
| Skill 补全 | `/skill <TAB>` → development/python | Factory Registry (skills.json) |
| Provider 补全 | `--provider <TAB>` → deepseek/openai | ControlPlane (providers.json) |
| 文件路径补全 | `--repo-path <TAB>` → ~/my-app/ | File System |

## 2. 数据源分层

```
Completion Engine
    ├── Static Command Registry (命令/参数表 — 代码内定义)
    ├── Factory Registry (projects/agents/skills — JSON 读取)
    ├── Workspace (current project 内文件/目录)
    └── File System (路径补全, 通用)

优先级: 显式参数类型 > 上下文 (current_project) > 全量 Registry
```

## 3. 实现架构

```
TAB 按下
  ↓
[1] tokenize: 当前输入行 → cursor 位置
[2] 定位: 是顶层命令? 子命令? 参数值? (基于 parser 结构)
[3] 查源: Static → Registry → Workspace → FS
[4] 过滤: 前缀匹配 + 去重 + 排序
[5] 渲染: 单值补全 / 多值候选列表
```

**关键: Completion 必须基于 argparse parser 结构(命令/参数表单一来源), 不硬编码。**

## 4. 补全上下文注入

```
/run --agent <TAB>       → 列出 agents (Factory Registry)
/run --project <TAB>     → 列出 projects (Registry) + 当前项目标记
factory project <TAB>    → create/list (子命令)
--repo-path <TAB>        → 文件系统路径补全 (支持 ~ 展开)
--provider <TAB>         → providers.json 启用列表
```

## 5. 交互模式 vs Command Mode

| 模式 | 补全方式 |
|---|---|
| Interactive Session | 内建 TAB 补全(prompt_toolkit 类) |
| Command Mode (bash) | shell 补全脚本(可选): `eval "$(factory completion bash)"` |

## 6. 候选排序

```
1. 精确前缀匹配优先
2. 上下文相关优先 (current_project 的 agent/项目)
3. 字母序兜底
```

## 7. 边界

- 补全只做"候选生成", 不执行任何操作
- 未知位置 → 无候选(不报错)
- Registry 缺失 → 静默跳过该类补全
- 禁止: 补全触发副作用(只读)

---

> Task 006 完毕 | 补全源: Static+Registry+Workspace+FS | 基于 parser 结构 | 只读无副作用
