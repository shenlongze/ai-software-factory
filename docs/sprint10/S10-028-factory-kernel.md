# S10-028 Task 002 — Factory Kernel

> 日期:2026-08-14 | Sprint: S10-028 Platform Architecture Freeze | 只设计,不实现代码
> 目标:定义什么必须属于 AI Factory Core,什么应成为可插拔能力

---

## 1. 核心问题

**未来 3 年,哪些能力永远属于核心,哪些应该可插拔?**

答案决定:
- 平台稳定性(核心不变量)
- 独立产品化边界(哪些能拆)
- 插件化时机(S10-027 已评估)

## 2. Factory Kernel 定义

```
┌────────────────────────────────────────────────────┐
│                 Factory Kernel (不可变核心)          │
│                                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Identity │  │  Config  │  │     Event        │  │
│  │ 身份     │  │ 配置     │  │ 事件 (唯一事实源) │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Runtime  │  │ Extension│  │  Kernel Contract │  │
│  │ 执行壳   │  │ 扩展接口 │  │ 契约 (稳定 API)  │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└────────────────────────────────────────────────────┘
```

## 3. 五个 Kernel 组件

### 3.1 Identity(身份)

| 项 | 定义 |
|---|---|
| 职责 | 所有实体的唯一身份:User/Project/Agent/Skill/Task/Runtime 的 id 语义 |
| 规则 | id 唯一、稳定、可审计(id 即存储键,禁止路径分隔符) |
| 现状 | 已存在:Agent.id / Skill.id / Task.id / RuntimeSession.id(各域自己的 id 规范) |
| 未来 | **统一 id 规范**(如 af://agent/backend-1)供跨模块引用 |
| 可插拔? | **绝不** — 身份是内核 |

### 3.2 Config(配置)

| 项 | 定义 |
|---|---|
| 职责 | 分层配置:env > .env > config.json > 默认;各配置文件 schema 校验 |
| 规则 | Kernel 只负责"读配置 + 分发",不解释业务配置 |
| 现状 | ConfigProvider 已实现(分层)+ pydantic schema(各文件) |
| 未来 | 统一配置访问接口(不是新文件,是稳定 API) |
| 可插拔? | **内核** — 配置分发机制固定;具体配置段可扩展 |

### 3.3 Event(事件)

| 项 | 定义 |
|---|---|
| 职责 | 事件溯源:append-only SQLite,唯一事实源(Who/What/When/Model/Tool/Result) |
| 规则 | 一切状态变化经事件;事件不可变 |
| 现状 | events.db 已实现 + org.execution.* / provider.* / router.decided 事件 |
| 未来 | **事件 schema 统一**(当前 session 事件/org 事件/usage 双轨,Task 001 已识别) |
| 可插拔? | **绝不** — 事件是内核(审计/回放/治理的根基) |

### 3.4 Runtime(执行壳)

| 项 | 定义 |
|---|---|
| 职责 | 执行生命周期:Task→Session→Loop→Result(不关心具体执行者是谁) |
| 规则 | Kernel 只编排生命周期,执行能力(Agent/Provider)经 Extension 注入 |
| 现状 | AgentRuntime/ExecutionLoop 已实现(但 provider 装配在 console 层 — 待下沉) |
| 未来 | **装配下沉**:Runtime 自己从 Kernel 契约取 provider,不依赖 console |
| 可插拔? | **内核壳** — 生命周期编排固定;执行能力可插拔 |

### 3.5 Extension Interface(扩展接口)

| 项 | 定义 |
|---|---|
| 职责 | 一切外部能力(Agent/Skill/Router/RAG/Governance/Evaluation)的注册边界 |
| 规则 | Extension 经统一接口注册,不直接改内核 |
| 现状 | 注册表模式已存在(DoctorCheck/ServiceDef/SkillRegistry) |
| 未来 | 正式 Extension Contract(Task 003 设计) |
| 可插拔? | **接口本身是内核** — 实现可插拔,接口固定 |

## 4. 什么必须永远属于 Core

| 组件 | 理由 |
|---|---|
| Identity | 跨模块引用基础;一旦拆散无法统一 |
| Config 分发 | 配置一致性;拆分后多源冲突 |
| Event 溯源 | 审计/回放/治理根基;拆分后无法保证完整审计链 |
| Runtime 生命周期壳 | 执行编排统一;执行者可变但生命周期不可变 |
| Extension Interface | 扩展边界;接口漂移 = 生态破裂 |
| **Kernel Contract(稳定 API)** | 所有模块的对外契约;契约冻结 = 平台稳定 |

## 5. 什么应该成为可插拔能力

| 能力 | 可插拔理由 | 前置条件 |
|---|---|---|
| Agent(执行者) | 不同 Agent 实现可换 | 装配下沉 exec |
| Skill(能力包) | Skill = 最小扩展单元 | 策略引擎(安全加载) |
| Router(决策策略) | 决策源可换(Router 核心五层链冻结,rule source 可插拔) | ModelChoice 共享类型 |
| RAG(知识引擎) | 索引/检索/embedding 可换 | 先实现基础 |
| Governance(治理策略) | 审批策略可插拔 | 策略引擎 |
| Evaluation(评估器) | 不同评估维度可换 | 整合 evaluator |
| Provider(模型源) | 已可插拔(OpenAI/Anthropic/DeepSeek/Ollama) | ✅ 已实现 |
| UI(控制面) | 不同前端形态(CLI/Web/API) | ✅ 已实现(CLI first) |

## 6. 内核稳定性原则(冻结声明)

```
1. Kernel 五组件 (Identity/Config/Event/Runtime/Extension) 永不重构
2. Kernel Contract 是稳定 API — 外部模块只依赖契约,不依赖实现
3. 一切新能力走 Extension,不直接改 Kernel
4. 内核变更 = 版本号主版本升级 (v1.x → v2.x 才允许)
5. 现有 Core 冻结铁律 (S10 系列) 升级为 Kernel 概念
```

## 7. 与现状的映射

| Kernel 组件 | 现状 | 差距 |
|---|---|---|
| Identity | 各域 id 规范 | 统一 id 规范(af://) |
| Config | ConfigProvider ✅ | 配置访问 API 化 |
| Event | events.db ✅ | 事件 schema 统一 |
| Runtime | AgentRuntime/ExecutionLoop | 装配下沉 |
| Extension | 注册表模式(3 个) | 正式 Contract(Task 003) |

## 8. 结论

**Factory Kernel = 5 组件 + 1 契约,是平台不可变核心。**

- 可插拔 = Agent/Skill/Router 策略/RAG/Governance 策略/Evaluation/Provider/UI
- 不可插拔 = Identity/Config/Event/Runtime 壳/Extension 接口/Kernel Contract
- 独立产品化(Router/Governance/Agent)本质是"Kernel 之上提取可插拔能力",Kernel 本身永远属于 AI Factory
- 插件化时机 = Kernel Contract 冻结后(S10-027 结论一致)

---

> Task 002 完毕 | Factory Kernel 定义完成 | 只设计,未实现
