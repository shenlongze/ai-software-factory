# AI Factory OS — 目标架构（SSoT v0.1 骨架）

> 状态: 骨架（索引，非内容） | 冻结: 是（改动需显式裁决）

## 一、五层结构

**1. Kernel（内核）** — OS 不可替换的最小闭环
- 类别：会话入口 · 意图 · 能力解析 · 调度契约 · 执行 · 验证 · 事实 · 治理 Gate
- 只放：契约 + 数据模型 + 注册表 + 事实源

**2. Services（OS 服务）** — OS 本体能力，可替换实现
- 类别：组织 · 项目/工作 · 记忆 · 知识 · 员工装配 · 审批流程 · 审计服务 · 可观测

**3. Extensions（扩展）** — 一切插件
- 类别：Factories（Software/其他）· Agents · Skills · Tools · MCP · Models/Providers · Workloads
- 规则：只实现"怎么做"，不含 OS 语义

**4. Projections（投影）** — 人类控制台
- 类别：CLI · Web · Workbench · Desktop · Mobile
- 规则：只呈现与触发，零事实源

**5. Infrastructure（基础设施）** — 存储与运行时底座
- 类别：持久化 · 缓存 · 向量库 · 消息/队列 · 进程管理 · RAG 底座
- 规则：可插拔，不承载业务语义

## 二、依赖铁律

1. **上层可 import 下层 contracts**（单向）
2. **Extensions 只 import Kernel contracts** — 不知 OS 内部实现
3. **Projections 只 import API Gateway** — 不得直连 Domain/Store
4. **禁止循环依赖**

## 三、Kernel 六段

| 段 | 职责（一句话） | 形态（一句话） |
|----|--------------|--------------|
| **Conversation** | 用户表达目标的唯一入口 | 会话状态机 → 产出"目标"事实 |
| **Capability** | 能力注册与解析 | Registry + Resolver（SPI） |
| **Scheduler** | 从"要做什么"到"现在执行谁" | 只读事实 → 返回下一个执行单元 |
| **Node** | 执行节点（自治原语） | 输入 node 定义 → 输出结果 + 证据 |
| **Events** | 唯一事实源 | append-only + query |
| **Governance** | 审批/预算/审计挂点 | check(action) → allow/deny |

## 四、Constitution（不可违背）

1. **无固定流程** — OS 本体没有流程；流程是插件内部的事
2. **一切插件** — 核心基座 + 一切插件（Factory/Agent/Skill/Tool/MCP/Model/Provider 皆插件）
3. **会话唯一入口** — 所有业务经会话驱动
4. **学习自治是核心** — 记忆 / 学习 / 自修复 / 自提升 / 懂用户，非附属
5. **Golden Path 绝不进 Core** — 它只是第一个 Factory 的插件流程

## 五、术语

| 术语 | 含义 |
|------|------|
| **Node** | 执行节点（自治原语，非普通任务） |
| **Capability** | 能力（抽象"谁能做"），经解析绑定到扩展 |
| **Extension** | 插件（提供具体能力实现） |
| **Conversation** | 会话（唯一业务入口） |
| **Projection** | 投影（只读呈现层，零事实源） |
| **Contract / SPI** | 契约（层间唯一允许的依赖形式） |
