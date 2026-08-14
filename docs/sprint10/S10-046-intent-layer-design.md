# S10-046 Task 004 — Intent Layer Design

> 日期:2026-08-14 | Sprint: S10-046 CLI Design v2 | 设计, 未修改代码
> 核心: 自然语言入口 — 不生成 shell 命令, 解析为结构化 Intent

---

## 1. 架构

```
Natural Language ("帮我创建一个电商 APP")
    ↓
Intent Parser (LLM 结构化输出 — 不生成命令!)
    ↓
Intent Object (结构化: intent_type + params + constraints)
    ↓
Policy Check (权限/上下文验证 — 防错误执行)
    ↓
Workflow Planner (映射到 Factory Service 工作流)
    ↓
Factory Service (exec/org/ControlPlane — 现有)
    ↓
Execution (真实执行链)
```

## 2. Intent Object 定义

```python
@dataclass
class IntentObject:
    intent_type: str          # "create_project" | "run_task" | "show_status" | ...
    params: dict              # {"project_name": "ecommerce", "goal": "..."}
    constraints: dict         # {"provider": "deepseek", "agent": "backend-1", "budget_usd": 0.1}
    confidence: float         # 0-1 (LLM 解析置信度)
    raw: str                  # 原始输入 (审计)
```

### 示例

| 用户输入 | IntentObject |
|---|---|
| "帮我创建一个电商 APP" | `create_project {project_name: "ecommerce", goal: "电商 APP"}` |
| "给 main.py 加测试" | `run_task {project: <current>, objective: "加测试", agent: <current>}` |
| "用了多少钱" | `show_cost {period: "session"}` |
| "用便宜点的模型" | `set_provider {preference: "cheapest"}` |

## 3. 关键问题回答

### Q1: LLM 在哪里调用?

```
只在 Intent Parser 阶段调用 LLM — 且输出是"结构化 Intent", 不是 shell 命令。

设计:
  Intent Parser = LLM + 严格 schema (JSON mode / function calling)
  LLM 输出: {"intent_type": ..., "params": ..., "constraints": ...}
  解析失败 → 不执行, 请求澄清

禁止: LLM 生成 bash 命令字符串后执行 (无结构、无法验证、危险)
```

### Q2: 如何防止错误执行?

```
三重防护:
[1] Schema 校验: LLM 输出必须是合法 IntentObject (类型/必填/枚举)
[2] Policy Check: 执行前验证 —
    - provider 存在且可用
    - project 存在 (或允许创建)
    - agent 存在
    - 预算约束 (constraints.budget_usd)
    - 上下文: current_project 缺失时请求明确
[3] 确认门: 高风险/不确定 (confidence < 0.7) → 打印 Intent 让用户确认
    "将执行: 创建项目 ecommerce (goal=电商 APP) [y/N]"
```

### Q3: 如何和 Agent Workflow 集成?

```
Intent → Workflow Planner 映射到现有 Agent 执行链:

  run_task Intent
    ↓
  Workflow: ensure_project → build_task → select_agent → ServiceLayer.run()
    ↓
  等价于: factory run --project <current> --objective <goal> --agent <current>

  create_project Intent
    ↓
  Workflow: project.create() → (可选) demo run → 展示
    ↓
  等价于: factory project create --repo-path <dir>

任何 Intent 最终落到 Service Layer — 与 Command/Slash 同源。
```

## 4. Intent 类型注册表(初始)

| intent_type | 参数 | 映射服务 |
|---|---|---|
| create_project | name, goal, path | Project Service |
| run_task | project, objective, agent, provider | Execution Service |
| list_projects | — | Project Service |
| list_agents | — | Agent Registry |
| show_status | — | Runtime Status |
| show_cost | period | Usage/Audit |
| show_audit | filter | Events DB |
| set_provider | provider_id | ControlPlane |
| explain | topic | (Help/Docs) |
| help | — | Help |

## 5. 失败安全

| 场景 | 行为 |
|---|---|
| LLM 解析失败/超时 | 提示重试; 不执行 |
| Intent 无效 (schema) | 显示原因; 不执行 |
| Policy 拒绝 | 显示原因 + 修复建议; 不执行 |
| confidence < 0.7 | 确认门: 打印 Intent 请求确认 |
| 上下文缺失 (无 current_project) | 请求指定; 不猜测 |

## 6. 边界

- Intent Layer 只在 Interactive Session 可用(v0.3)
- 不生成/执行任意命令 — 只映射到注册 Intent 类型
- 全部执行走 Service Layer(不 bypass)
- LLM 调用计入成本显示(透明)

---

> Task 004 完毕 | Intent = 结构化对象 (非 shell 命令) | 三重防护: schema+policy+确认门 | 落 Service Layer
