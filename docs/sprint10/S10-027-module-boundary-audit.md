# S10-027 Task A — Module Boundary Audit

> 日期:2026-08-14 | Sprint: S10-027 Hardening | 只读审计,未修改代码
> 目标:检查当前模块边界,判断哪些模块未来可独立成为产品

---

## 1. 模块全景

```
AI Software Factory
├── factory-console/     Console 层 (CLI + FastAPI + 前端)
│   ├── cli_factory.py   ./bin/factory 统一入口 (578+ 行, 15+ 命令)
│   ├── cli_doctor.py    DoctorCheck 框架 (S10-026-A)
│   ├── cli_services.py  ServiceDef 服务注册表 (S10-026-B)
│   ├── llm_control.py   LLMControlPlane — providers.json (S10-021)
│   ├── model_catalog.py ModelCatalog — models.json (S10-022)
│   ├── llm_router.py    LLMRouter 五层决策链 (S10-024)
│   ├── agent_policy.py  Agent/Skill 策略 (S10-024)
│   ├── config.py        ConfigProvider 分层配置
│   ├── workflow_runner.py 真实执行链装配 (S10-023)
│   └── web/             FastAPI + React 前端
├── factory-core/        Core (冻结) — events/tasks/agents/workflows/providers/
├── factory-exec/        Execution — agent_runtime/execution_loop/tool/skill/mcp
├── factory-org/         Organization — company/employee/artifact/approval
└── factory-runtime/     沙箱执行环境
```

## 2. 各模块边界分析

### 2.1 factory-console/llm_router.py (LLM Router)

| 维度 | 分析 |
|---|---|
| 职责 | 五层决策链:User > Agent/Skill > Project > System > Fallback → ModelChoice |
| 输入 | task_type/agent_id/skill_ids/project_dir/explicit_provider/model + ControlPlane + ModelCatalog |
| 输出 | ModelChoice {model_id, provider_id, score, reasons, source} |
| 依赖方向 | → llm_control.py (读 providers.json) → model_catalog.py (读 models.json) → agent_policy.py (读 yaml) |
| 独立产品可能性 | **高** — AI Decision Router:输入任务特征 → 输出最优模型选择 |
| 耦合点 | ModelChoice 定义在 model_catalog.py(应独立);依赖 ControlPlane 的 resolve_runtime_config |

### 2.2 factory-console/llm_control.py (Control Plane)

| 维度 | 分析 |
|---|---|
| 职责 | Provider 生命周期:providers.json 持久化/enabled/api_key_ref 解析 |
| 输入 | providers.json + 环境变量引用 |
| 输出 | ProviderConfig / resolve_runtime_config (装配契约) |
| 依赖方向 | 几乎零依赖(只 import config.PROVIDER_DEFAULTS) |
| 独立产品可能性 | **高** — Provider 配置管理可独立为轻量工具/库 |
| 耦合点 | 无强耦合,边界清晰 |

### 2.3 factory-console/model_catalog.py (Model Catalog)

| 维度 | 分析 |
|---|---|
| 职责 | 模型元数据:models.json 持久化/capabilities/context/cost |
| 输出 | ModelInfo / ModelChoice / suggest() 候选 |
| 独立产品可能性 | **中高** — 模型目录/成本查询工具 |
| 耦合点 | **ModelChoice 被 Router 复用**(类型归属应独立成共享模型) |

### 2.4 factory-core/providers/ (Usage/Feedback/Selector)

| 维度 | 分析 |
|---|---|
| 职责 | Provider 目录/usage 统计/feedback/capability 画像/selector 四层链 |
| 现状 | 与 exec 执行链**未接线**(S10-021~024 全部走 console 层新模块) |
| 独立产品可能性 | **中** — usage/feedback 数据基础;但当前与执行链断裂是技术债 |
| 耦合点 | 与 exec 的双轨(两套 Provider 抽象并存) |

### 2.5 factory-exec/ (Execution Layer)

| 维度 | 分析 |
|---|---|
| 职责 | AgentRuntime / ExecutionLoop / Tool / Skill / MCP / 沙箱 |
| 输入 | ExecutionRequest + provider |
| 输出 | ExecutionResult + Artifact |
| 独立产品可能性 | **中** — Agent 执行引擎可独立;但依赖 console 层装配 ControlPlane |
| 耦合点 | 真实 Provider 由 console 层 workflow_runner 装配(职责倒挂风险) |

### 2.6 factory-org/ (Organization/Governance)

| 维度 | 分析 |
|---|---|
| 职责 | company/employee/artifact/approval/workflow 组织域 |
| 独立产品可能性 | **中高** — AI Governance OS 基础(审批门/审计) |
| 耦合点 | 与 console service 的 workflow_lifecycle 装配耦合 |

### 2.7 Governance / RAG / Agent / Skill(命令骨架)

| 模块 | 现状 | 独立产品可能性 |
|---|---|---|
| governance | 无独立模块,审批/审计散在 org + events | **中高** — AI Governance OS |
| rag | 仅 CLI 占位 (factory rag → "RAG 未实现") | **中** — Enterprise Knowledge Engine |
| agent | 骨架 (factory agent 只读列表) | **中高** — Agent Management Platform |
| skill | 骨架 + exec skill.py (权限链) | **中高** — Skill 市场/Registry |

## 3. 依赖方向总览

```
                    ┌─────────────────────────┐
                    │  factory-console (CLI)  │
                    │  cli_factory/doctor/     │
                    │  services                │
                    └────────┬────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ llm_router   │───▶│ llm_control  │    │ workflow_    │
│ (决策)       │    │ (providers)  │    │ runner(执行) │
└──────────────┘    └──────────────┘    └──────┬───────┘
        │                    │                  ▼
        ▼                    ▼            ┌──────────────┐
┌──────────────┐    ┌──────────────┐     │ factory-exec │
│ model_catalog│    │ agent_policy │     │ (runtime)    │
└──────────────┘    └──────────────┘     └──────────────┘
```

## 4. 未来独立可能性排序

| 排序 | 模块 | 独立产品 | 市场价值 | 当前技术债 |
|---|---|---|---|---|
| 1 | LLM Router | AI Decision Router | 高(LLM 选型是刚需) | ModelChoice 归属待独立 |
| 2 | Control Plane | Provider 管理 | 中高 | 低,边界最清晰 |
| 3 | Governance(org) | AI Governance OS | 中高 | 与 console 装配耦合 |
| 4 | Agent Lifecycle | Agent Management | 中高 | 依赖 console 装配 provider |
| 5 | Model Catalog | 模型目录/成本 | 中 | ModelChoice 耦合 |
| 6 | RAG | Enterprise Knowledge | 中 | 未实现(占位) |
| 7 | Execution | Agent 执行引擎 | 中 | provider 装配职责倒挂 |

## 5. 结论

- **边界最清晰、最易独立**:llm_control(ModelChoice 归属除外)、llm_router
- **最大技术债**:① ModelChoice 定义在 model_catalog 被 router 复用(应提升为共享类型)② factory-core/providers 与 exec 双轨未合并 ③ exec 的 provider 装配依赖 console 层(职责倒挂)
- **S10-027 建议动作**:不重构(用户约束),但记录这些耦合点为未来产品化做准备

---

> 审计完毕 | 只读 | 输出:S10-027-product-module-roadmap.md 见 Task D
