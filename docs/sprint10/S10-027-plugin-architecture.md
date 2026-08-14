# S10-027 Task 2 — Plugin Architecture Feasibility

> 日期:2026-08-14 | Sprint: S10-027 Hardening | 只设计,不实现插件系统
> 目标:评估 AI Factory 是否应演进为插件平台

---

## 1. 现状:已有的"准插件"机制

AI Factory 已有 3 个注册表模式(插件架构的种子):

| 机制 | 位置 | 协议 | 用途 |
|---|---|---|---|
| DoctorCheck | cli_doctor.py | {id, label, run()} → CheckResult | 诊断检查器注册即发现 |
| ServiceDef | cli_services.py | {id, start, stop, status} | 服务注册即发现 |
| SkillRegistry | exec/skill.py | Skill {id, tools, permissions} | 技能注册 + 权限链 |
| MCP Adapter | exec/mcp.py | MCPConnection/Tool | 外部工具协议扩展 |

**结论:项目已在"注册表模式"上自然生长,插件架构是现有模式的泛化,不是跳跃。**

## 2. 未来统一 Plugin Runtime(设计)

```
Factory Runtime (v0.1 基线)
    │
    ▼
Plugin Manager (插件管理器)
    │
    ├── 发现 (scan plugin.yaml)
    ├── 加载 (entrypoint → 注册)
    ├── 权限 (permissions 校验)
    └── 生命周期 (enable/disable/reload)
    │
    ┌────────────┬────────────┬────────────┬────────────┬────────────┐
    ▼            ▼            ▼            ▼            ▼            ▼
Agent Plugin  Skill Plugin  Router Plugin RAG Plugin  Governance  Evaluation
(执行者)      (能力)       (决策)       (知识)      Plugin      Plugin
                                                        (治理)      (评估)
```

## 3. Plugin Manifest 设计(未来 plugin.yaml)

```yaml
name: factory-rag-engine        # 插件唯一名
version: 1.0.0
type: rag                      # agent | skill | router | rag | governance | evaluation
description: "Project RAG engine"

dependencies:                  # 依赖的其他插件/服务
  - name: factory-core
    version: ">=0.1"
  - name: vector-db             # 未来服务 (ServiceDef 注册)

permissions:                   # 权限声明 (最小权限)
  - read: ["~/.factory/projects"]
  - write: ["~/.factory/rag-index"]
  - network: ["vector-db:6333"]  # 明确网络边界

entrypoint:                    # 加载入口
  module: rag_engine.plugin
  class: RagEnginePlugin

config_schema:                 # 配置 schema (JSON Schema)
  type: object
  properties:
    index_dir: {type: string}
    embedding_model: {type: string}
```

## 4. 各能力插件化分析

### 4.1 Agent 插件化

| 维度 | 分析 |
|---|---|
| 应该? | **部分** — Agent 是"执行身份",不应完全插件化(有状态/生命周期);但 Agent 的**能力组合**(skills)可插件化 |
| 建议 | Agent 本体保留核心;Agent 能力经 Skill 插件扩展 |
| 参考 | VSCode 的 Task Provider(不插件化 Task 本身,插件化 Task 类型) |

### 4.2 Skill 插件化

| 维度 | 分析 |
|---|---|
| 应该? | **是** — Skill 已是注册表模式,天然适合插件化 |
| 建议 | Skill = 最小插件单元(能力/工具/权限/指令打包);未来 Skill 市场 = 插件市场 |
| 参考 | npm package / MCP Server(Skill 就是"能力包") |
| 现状差距 | 权限链硬编码(SYSTEM_AGENT_SKILLS)→ 需策略引擎才能安全加载第三方 Skill |

### 4.3 Router 插件化

| 维度 | 分析 |
|---|---|
| 应该? | **是(策略级)** — Router 决策算法不应插件化(核心稳定);但**决策源**(rule provider)可插件化 |
| 建议 | Router 核心(五层链)冻结;未来新决策层(如 evaluation 反馈)经 Plugin 注册为新的 rule source |
| 参考 | VSCode 的 Language Server(协议稳定,实现可插拔) |

### 4.4 RAG 插件化

| 维度 | 分析 |
|---|---|
| 应该? | **是** — RAG 是典型的可插拔能力(索引/检索/embedding 可换) |
| 建议 | RAG 作为第一个完整 Plugin 类型(类型=rag);内部 embedding/retriever 再插件化 |
| 参考 | LangChain retriever 生态 |

### 4.5 Governance / Evaluation 插件化

| 维度 | 分析 |
|---|---|
| Governance | **部分** — 审批策略可插件化(策略引擎);核心审计链保留 |
| Evaluation | **是** — 评估器(evaluator)可插件化(不同评估维度/基准) |

## 5. 参考模式对比

| 参考 | 关键机制 | 对 AI Factory 的启示 |
|---|---|---|
| VSCode Extension | manifest (package.json) + contribution points | Plugin Manifest + 贡献点(注册表) |
| npm package | 依赖树 + 版本管理 | 插件依赖解析 + 版本约束 |
| MCP Server | 标准化协议 + 工具暴露 | **已实现**(exec/mcp.py)— Skill/MCP 是插件化的先例 |

## 6. 是否演进为插件平台的结论

### 支持论据
1. 已有 3 个注册表模式(DoctorCheck/ServiceDef/Skill),插件化是自然泛化
2. 产品路线图(Router/Governance/RAG/Agent 独立产品)需要"能力边界",插件化提供统一边界
3. 洋葱式开源战略:插件 = 开源贡献的单元
4. MCP 已证明外部协议扩展可行

### 反对/风险论据
1. **时机过早**:当前核心能力尚未完全稳定(S10-021~026 刚完成);过早插件化 = 过度抽象
2. **安全门槛**:第三方插件需权限沙箱 + 策略引擎(当前权限链硬编码,未就绪)
3. 参考 VSCode:插件生态建立在**稳定核心**之上;AI Factory 核心还在演进

### 结论

**应该演进为插件平台,但不是现在。**
- **现状**:保留注册表模式(DoctorCheck/ServiceDef/Skill)继续作为"准插件"机制
- **前置条件**(满足后再正式插件化):
  1. P0: 策略引擎/RBAC(第三方代码安全加载的前提)
  2. P1: 装配下沉 exec(provider 装配不再依赖 console 层)
  3. P1: 核心 API 稳定(v1.0 冻结后)
- **建议路径**:
  ```
  Phase A (现在): 注册表模式继续 (已存在)
  Phase B (v1.1): Plugin Manifest 草案 (本设计, 冻结为规范)
  Phase C (v2.0): Plugin Manager 实现 + 策略引擎
  ```
- **不做的**:本 Sprint 不实现插件系统;不引入插件依赖框架

## 7. 设计要点记录(供未来实现)

1. Plugin Manifest 必须含 permissions(最小权限)— 与 Skill 权限链同哲学
2. 插件类型对应注册表:agent→SkillRegistry / skill→SkillRegistry / router→决策源 / rag→RAGRegistry / governance→策略 / evaluation→EvaluatorRegistry
3. entrypoint 延迟加载(失败安全:插件坏不影响核心)
4. config_schema 校验(插件配置不污染主配置)

---

> 可行性评估完毕 | 只设计 | 结论:演进为插件平台(时机=核心稳定+策略引擎后),现状保留注册表模式
