# S10-028 Task 001 — Module Architecture(最终确认)

> 日期:2026-08-14 | Sprint: S10-028 Platform Architecture Freeze | 只读,未修改代码
> 目标:最终确认 11 模块边界,为未来 3 年演进定基线

---

## 0. 当前系统基线

- pytest 8116 passed / 0 failed
- 版本 v1.0.0-rc1
- CLI 17 命令 | API 75 端点 | service.py 4046 行 | exec 37 文件

## 1. Core Runtime

| 维度 | 定义 |
|---|---|
| 当前职责 | 领域模型 + 事件溯源(SQLite ~/.factory/factory.db)+ 冻结基线(Core 零修改铁律) |
| 输入 | 领域操作命令(经 service) |
| 输出 | 事件(append-only)/ 模型对象 |
| 数据边界 | factory-core/(代码)+ ~/.factory/factory.db(事件) |
| API 边界 | 无直接 HTTP;经 console service 层 |
| 独立产品化 | ❌ 不独立(基础设施层) |
| 当前依赖 | 零领域依赖(最底层) |

## 2. Agent Runtime

| 维度 | 定义 |
|---|---|
| 当前职责 | 执行编排:AgentRuntime / ExecutionLoop / DeveloperAgent / 沙箱 / Artifact |
| 输入 | ExecutionRequest + provider |
| 输出 | ExecutionResult / Artifact / usage |
| 数据边界 | factory-exec/exec/(代码)+ ~/.factory/runtime-sessions/ + ~/.factory/workspace/ |
| API 边界 | 经 console 装配(AgentExecutor);无独立 HTTP |
| 独立产品化 | 中(Agent Execution Engine;需先解装配倒挂) |
| 当前依赖 | **console 层装配 provider(workflow_runner._build_provider)— 职责倒挂,最大耦合点** |

## 3. Skill System

| 维度 | 定义 |
|---|---|
| 当前职责 | Skill 注册/权限链(Agent→Skill→Tool 3 环)/MCP 适配 |
| 输入 | Skill 定义(skill.yaml / registry)/ 权限检查 |
| 输出 | Skill 对象 / 权限决策 / Tool 执行 |
| 数据边界 | exec/skill.py + ~/.factory/skills/ |
| API 边界 | /api/skills /api/tools /api/mcp/* |
| 独立产品化 | 中高(Skill 市场/Registry) |
| 当前依赖 | 权限链硬编码(SYSTEM_AGENT_SKILLS)→ 策略引擎前置 |

## 4. LLM Control Plane

| 维度 | 定义 |
|---|---|
| 当前职责 | Provider 生命周期:providers.json 持久化/enabled/api_key_ref 解析/配置校验 |
| 输入 | providers.json + 环境变量引用 |
| 输出 | ProviderConfig / resolve_runtime_config(装配契约) |
| 数据边界 | ~/.factory/providers.json |
| API 边界 | /api/providers(只读)/ CLI config check |
| 独立产品化 | **高**(Provider 配置管理) |
| 当前依赖 | 几乎零(只 import config.PROVIDER_DEFAULTS)— 边界最清晰 |

## 5. AI Router

| 维度 | 定义 |
|---|---|
| 当前职责 | 五层决策链:User > Agent/Skill > Project > System > Fallback → ModelChoice |
| 输入 | task_type/agent/skill/project/explicit + ControlPlane + ModelCatalog |
| 输出 | ModelChoice {model_id, provider_id, score, reasons, source} |
| 数据边界 | ~/.factory/models.json + agent.yaml/skill.yaml/project.yaml |
| API 边界 | 无独立 API(经 workflow_runner 装配);CLI factory router 骨架 |
| 独立产品化 | **最高**(AI Decision Router) |
| 当前依赖 | ModelChoice 定义在 model_catalog(应提升共享);依赖 ControlPlane/ModelCatalog |

## 6. Governance Engine

| 维度 | 定义 |
|---|---|
| 当前职责 | 审批门 / 权限链(3 环)/ 事件溯源审计 / org 组织域(company/employee/artifact) |
| 输入 | 审批请求 / 权限检查 |
| 输出 | 审批决定 / 审计事件 |
| 数据边界 | factory-org/ + ~/.factory/org/ + events.db |
| API 边界 | /api/approvals /api/approval-gates /api/decisions |
| 独立产品化 | **中高**(AI Governance OS) |
| 当前依赖 | 与 console service workflow_lifecycle 装配耦合;策略引擎缺失;审计浏览器缺失 |

## 7. RAG Engine

| 维度 | 定义 |
|---|---|
| 当前职责 | **未实现**(CLI 占位 "RAG 未实现 — 规划中") |
| 数据边界 | 无 |
| 独立产品化 | 中(Enterprise Knowledge;Task 005 有完整设计) |
| 当前依赖 | 无 |

## 8. Memory/Experience Engine

| 维度 | 定义 |
|---|---|
| 当前职责 | 经验提取雏形(exec experience.py/experience_ctx.py)+ ExperienceStore(intelligence) |
| 输入 | ExecutionResult(成功/失败)→ 提取 ContextExperienceRecord |
| 输出 | Experience 记录 |
| 数据边界 | ~/.factory/intelligence/(experience)|
| 独立产品化 | 低(未成熟;跨会话 Memory 未实现) |
| 当前依赖 | exec agent_runtime 调用提取器 |

## 9. Evaluation System

| 维度 | 定义 |
|---|---|
| 当前职责 | 候选评估(evaluator.py/candidate.py)+ validation 循环 + Quality Gate |
| 输入 | Candidate / ExecutionResult |
| 输出 | 评估结果 / 质量分 |
| 数据边界 | exec/evaluator.py + ~/.factory/intelligence/ |
| 独立产品化 | 中(Evaluation Platform;散落待整合) |
| 当前依赖 | exec 内部;无独立 API |

## 10. Marketplace

| 维度 | 定义 |
|---|---|
| 当前职责 | **未实现**(远期;Skill 市场/Plugin 市场) |
| 独立产品化 | 中高(生态位) |
| 当前依赖 | 依赖插件架构(Task 002/003)+ 策略引擎 |

## 11. CLI/UI/API Gateway

| 维度 | 定义 |
|---|---|
| 当前职责 | CLI(17 命令,唯一入口)+ FastAPI(75 端点)+ React(17 页面) |
| 输入 | 用户命令 / HTTP |
| 输出 | 命令结果 / API 响应 |
| 数据边界 | ~/.factory/(全部数据根) |
| API 边界 | 75 端点(projects/runtime/tools/skills/mcp/providers/approvals/...) |
| 独立产品化 | ❌ 不独立(是平台外壳,承载其他模块) |
| 当前依赖 | 全部模块(装配中枢)|

## 12. 数据边界总览

```
~/.factory/
├── factory.db          事件溯源 (Core)
├── providers.json      Provider 生命周期 (ControlPlane)
├── models.json         Model 元数据 (ModelCatalog)
├── config.json         Runtime 配置
├── org/                组织域 (Governance)
├── agents/             Agent 注册
├── skills/             Skill 定义
├── tasks/              Task 数据
├── projects/           Project 数据
├── runtime-sessions/   执行会话 (Agent Runtime)
├── workspace/          沙箱工作区
├── intelligence/       经验/决策 (Memory)
└── providers/          usage 统计
```

## 13. 独立产品化最终判定

| 模块 | 独立产品 | 判定 | 前置条件 |
|---|---|---|---|
| AI Router | AI Decision Router | **可独立** | ModelChoice 提升共享类型 |
| Control Plane | Provider 管理 | **可独立** | 无(边界最清晰) |
| Governance | AI Governance OS | 可独立(后置) | 策略引擎 + 审计浏览器 |
| Agent Runtime | Agent 执行引擎 | 可独立(后置) | 装配下沉 exec |
| Skill | Skill 市场 | 可独立(生态期) | 策略引擎 + 插件化 |
| Evaluation | 评估平台 | 可独立(后置) | 整合 evaluator |
| RAG | 知识引擎 | 可独立(远期) | 先实现 |
| Memory | 记忆服务 | 暂不 | 跨会话 Memory 未实现 |
| Core/CLI/UI | — | 不独立 | 平台底座 |

---

> Task 001 完毕 | 11 模块边界最终确认 | 5 个模块具备独立产品化潜力
