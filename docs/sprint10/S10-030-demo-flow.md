# S10-030 Task 003 — Demo Scenario Design

> 日期:2026-08-14 | Sprint: S10-030 MVP Release | 设计,未实现
> 目标:设计"一句话创建 Todo Web 应用"完整演示流程

---

## 1. 演示开场(30 秒)

**"AI Factory 让 AI 员工为你开发软件——只需一句话。"**

```
用户输入: "创建一个Todo Web应用"
```

## 2. 完整流程(Idea → Artifact)

### Stage 1: Idea 理解(30 秒)

| 步骤 | 展示 | AI Factory 能力 |
|---|---|---|
| 1.1 输入想法 | `factory project suggest "创建一个Todo Web应用"` | projects/suggest(想法理解) |
| 1.2 AI 提议名称/理解 | "财迹 Todo — 一个待办事项 Web 应用(添加/完成/删除)" | 提议名称(非机器 slug) |
| 1.3 用户确认 | 确认名称 + 需求澄清(技术栈/功能范围) | discovery/answer/confirm |

**演示点:不是机器式创建,AI 先理解用户。**

### Stage 2: 项目创建(30 秒)

| 步骤 | 展示 | AI Factory 能力 |
|---|---|---|
| 2.1 创建项目 | 项目实体创建,进入 backlog | project create + lifecycle |
| 2.2 Backlog 生成 | Epic/Feature/Story/Task 树自动生成 | backlog API |
| 2.3 工作流启动 | workflow: product → ux_ui → design → development → testing → release | start_project_workflow |

**演示点:一个想法展开成完整项目结构。**

### Stage 3: Agent 开发(2-3 分钟)

| 步骤 | 展示 | AI Factory 能力 |
|---|---|---|
| 3.1 Agent 分配 | 指派 backend-1 Agent 执行 Task | agent registry |
| 3.2 Router 决策 | Router 五层链选择模型(deepseek-chat) | llm_router(L1-L5) |
| 3.3 真实执行 | Task→Session→LLM→代码生成 | execute_runtime_task |
| 3.4 审批门 | AI 产出 patch → 等待人工审批 | execution.approved gate |

**演示点:真实 LLM 执行 + 可审计 + 人工审批(治理)。**

### Stage 4: 产物与验证(1 分钟)

| 步骤 | 展示 | AI Factory 能力 |
|---|---|---|
| 4.1 Artifact | 代码产物 + 执行报告(usage/成本) | ExecutionResult + report |
| 4.2 审批通过 | 人工批准 → patch 应用 | approval approve |
| 4.3 质量门 | validation PASS(语法检查) | validation |
| 4.4 审计可见 | 全事件时间线(Who/What/When/Model/Cost) | events.db + audit |

**演示点:全过程可审计,成本透明。**

## 3. 演示脚本(技术实现,基于现有 CLI/API)

```bash
# 前置: factory init + providers.json 配 deepseek + key 环境
export DEEPSEEK_API_KEY=...

# 1. 想法理解 (API)
curl -X POST localhost:8011/api/projects/suggest \
  -d '{"idea": "创建一个Todo Web应用"}'
# → AI 提议名称 + 理解

# 2. 确认创建
curl -X POST localhost:8011/api/projects/confirm \
  -d '{"name": "todo-app", ...}'

# 3. 启动工作流 (真实执行链)
curl -X POST localhost:8011/api/projects/{id}/start

# 4. 执行任务 (Router 决策 + 真实 LLM)
curl -X POST localhost:8011/api/runtime/execute \
  -d '{"task_id": "T-001", "agent_id": "backend-1", 
       "context": {"project_dir": "/path/to/project"}}'

# 5. 审计
factory audit  # 或 /api/events
```

## 4. 演示脚本(自动化版本)

```bash
# scripts/demo-todo.sh — 一句话 Todo 演示 (基于现有 demo.sh 模式)
# 1. 隔离 demo workspace (S10-026-F)
factory demo init
# 2. 启动
factory demo start
# 3. 走完整流程 (API 调用如上)
```

## 5. 演示要点(讲故事)

| 环节 | 讲什么 |
|---|---|
| 开场 | "这不是聊天机器人,是 AI 软件公司操作系统" |
| Idea 理解 | "AI 先理解你的需求,不是机器式创建" |
| 真实执行 | "注意:这是真实 DeepSeek API 调用,不是 demo 数据" |
| 审批门 | "AI 产出必须人工批准——这是治理" |
| 审计 | "每一步都记录:谁/什么/何时/哪个模型/多少钱" |
| 成本 | "整个流程成本不到 0.01 美元" |

## 6. 演示验收标准

```
[ ] 一句话输入 → 项目创建成功
[ ] Router 决策可见 (source/reason)
[ ] 真实 LLM 执行 (usage tokens > 0)
[ ] 审批门拦截 → 人工批准 → patch 应用
[ ] 审计事件完整 (audit 可查)
[ ] 全程成本 < $0.01
[ ] 时长 ≤ 5 分钟
```

## 7. 前置条件(演示前)

- providers.json 配 deepseek(enabled + api_key_ref)
- DEEPSEEK_API_KEY 环境就绪
- 8011 后端运行(完整 PYTHONPATH + key 注入 — S10-023 验证过的启动方式)
- 演示项目目录(空目录,LLM 可自由创建文件)

## 8. 结论

**Demo 流程完整可用**:Idea → Requirement → Project → Agent → Task → Code → Artifact 全链已实现(S10-023 真实执行验证过),只需按本脚本组织成演示。

- 差异化叙事:真实执行 + 治理审批 + 成本透明(竞争对手做不到的三点)
- 落地:基于现有 CLI/API,零新开发;自动化版本可复用 demo.sh 模式

---

> Task 003 完毕 | Demo 场景设计完成 | 一句话 Todo 全流程 ≤5 分钟,基于现有能力
