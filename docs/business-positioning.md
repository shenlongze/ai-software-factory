# AI Software Production Platform — 商业定位 (Business Positioning)

> 日期: 2026-08-06 | 归属: Phase 12A-5 | 状态: **只分析不实现** (商业策略文档, 非路线图承诺)
> 关联: [vision.md](./vision.md) · [lifecycle-model.md](./lifecycle-model.md) · [capability-architecture.md](./capability-architecture.md)
> · [human-console-model.md](./human-console-model.md) · [approval-model.md](./approval-model.md) · [demo-scenario.md](./demo-scenario.md)

---

## 1. 一句话定位

> **AI Software Factory 不是 AI Code Generator (AI 代码生成器), 而是 AI Software
> Production Platform (AI 软件生产平台) —— 管理 AI 员工完成"从想法到上线再到优化"
> 完整软件生产过程的平台: 生命周期编排 + 执行资源调度 + 决策审计 + 人工闸门 + 经验闭环。**

| 不是 | 是 |
|:-----|:---|
| 不是编辑器里的补全/对话助手 | 是组织 AI 生产的平台 (Idea → Operation, 12 阶段) |
| 不是"给一句话就出代码"的生成器 | 是"代码只是中间产物"的生命周期管理者 |
| 不是单个自主编码 Agent | 是多 Agent / 多 Provider / 多 Runtime 的调度与治理层 |
| 不是开发者搭 Agent 的框架 | 是内置完整生产流程的成品平台, 框架只是其中一块积木 |

---

## 2. 竞争格局: 四类玩家, 一个空白

按两个维度切分 —— **抽象层级** (工具 → 平台) × **生命周期覆盖** (单点 → 全生命周期):

```
                生命周期覆盖
   全生命周期   │            AI Software Factory ★ (空白区)
               │
   多阶段       │    Devin (任务级自主编码)
               │
   单点/局部    │    Cursor / Copilot (编码环节增强)
               │
               └──────────────────────────────────────────► 抽象层级
                        工具助手      框架        平台
                                   AutoGen / LangGraph
                                   (开发框架: 给开发者搭 Agent 的积木)
```

| 玩家 | 本质 | 覆盖的软件生命周期 | 决策与审计 | 人工闸门 | 经验沉淀 |
|:-----|:-----|:------------------|:----------|:---------|:---------|
| **Cursor / Copilot** | 代码助手 (编辑器内) | Development 单点 (写代码) | 无 (黑箱补全) | 无 (人工在编辑器里改) | 无 (每次会话孤立) |
| **Devin** | 自主编码 Agent | Task 级: 一个任务端到端 (计划→编码→测试) | 弱 (内部规划, 不可审计) | 弱 (任务级委托, 中间无闸门) | 弱 (单 Agent 记忆, 无组织级资产) |
| **AutoGen / LangGraph** | Agent 开发框架 | 无 (开发者自己搭流程) | 无 (框架不裁决) | 无 (由应用层自建) | 无 (框架不沉淀业务经验) |
| **AI Software Factory** | 软件生产平台 | **Idea→Research→PRD→UI→Architecture→Task→Development→Testing→Release→Deployment→Monitoring→Optimization** (12 阶段) | **有** (Decision+Approval: 候选/评分/推荐/原因/证据链/风险) | **有** (PRD/UI mandatory, Deploy mandatory, 节点表) | **有** (Experience Loop: 30 天半衰期, 正负经验聚合) |

> **空白区结论**: 代码助手和自主 Agent 都站在"代码"这一层; 框架把搭 Agent 的活儿
> 交给开发者。**没有任何一类产品管理"软件生产的全过程 + 决策审计 + 组织级经验资产"** ——
> 这正是 Factory 的定位空间。

---

## 3. 与四类竞品的逐项差异

### 3.1 vs Cursor / Copilot — 代码助手: 我们不做补全, 我们做生产组织

| 维度 | Cursor / Copilot | AI Software Factory |
|:-----|:-----------------|:---------------------|
| 对象 | 代码片段 / 文件 | 软件产品全生命周期 (代码是中间产物) |
| 上下文 | 当前文件 + 对话窗口 | 项目唯一事实源 (Event/Artifact/决策链), 跨会话、跨项目不丢失 |
| 多 AI 调度 | 单一模型 | Agent/Skill/Runtime/Provider 四类执行资源统一抽象, per-role 偏好路由 (架构师用 Claude, 开发者用 Codex, 测试用 Hermes — 换工具=改配置) |
| 质量保障 | 无 (补全靠人看) | 四层验证 (L1-L4) + 证据链, 独立于执行者 |
| 审计 | 无 | 全链事件 + 决策理由 + 审批留痕 (企业可回放) |
| 经验 | 每次会话从零开始 | 经验闭环: 一次执行 → 落库 → 下一次推荐自动读到更好依据 |

**一句话**: Cursor 让"写代码"更快; Factory 让"软件被生产出来"这件事可组织、可审计、可积累。

### 3.2 vs Devin — 自主编码 Agent: 我们不是把活儿全包给一个 Agent

| 维度 | Devin | AI Software Factory |
|:-----|:------|:---------------------|
| 工作单元 | 单个任务 (autonomous task) | 生命周期 (多阶段, 每阶段有产物与闸门) |
| 中间过程 | 内部规划, 黑箱执行 | 每个阶段显式: 产物 Artifact + 候选 + 评分 + 推荐 + 原因 + 证据链 |
| 人工介入 | 任务级委托, 中间无闸门 | PRD/UI/Deploy mandatory 人闸口, 未批准不前进 (无绕过路径) |
| 失败恢复 | Agent 自愈 (不可审计) | Checkpoint + Event Replay, 断点续跑, 恢复路径可审计 |
| 经验 | 单 Agent 上下文 | 组织级经验资产 (provider/agent/skill 聚合, 30 天半衰期, 负经验必记) |
| 决策权 | AI 自主 | **AI 只产出候选与证据, 执行权永远在人** (Decision≠Approval, 推荐≠执行) |

**一句话**: Devin 替人干活; Factory 替人**管理** AI 干活 —— 每步决策看得见、可复算、可驳回。

### 3.3 vs AutoGen / LangGraph — Agent 框架: 我们是用框架搭好的成品平台

| 维度 | AutoGen / LangGraph | AI Software Factory |
|:-----|:--------------------|:---------------------|
| 用户 | 开发者 (需要自己写编排代码) | 工程师 + 技术负责人 + 业务方 (Web/CLI 直接用) |
| 内置流程 | 无 (图/会话是原语, 流程自己搭) | 12 阶段生命周期 + 声明式阶段链 + 内置工作流 (feature-delivery/bug-fix/release) |
| 决策智能 | 无 (消息传递, 不裁决) | Decision Intelligence (规则评分四因素 + 证据链 + 风险 R1-R5) |
| 审批 | 无 | Approval Gate 状态机 (5 态终态可逆 + Artifact Version 绑定) |
| 可观测 | 开发者自己接 | Dashboard 20 视图 + 事件唯一事实源 + Metrics 六域 |
| 开放 | 框架本身就是开放的 | **Capability OS**: Skill/MCP/Runtime/Provider/Plugin 声明式注册, 零 Core 修改 (能力积木可组合可替换) |

**一句话**: AutoGen/LangGraph 是造 Agent 的积木盒; Factory 是**已经用积木搭好、带
决策与审批的生产线** —— 并保留同样的开放扩展能力 (capability-architecture.md)。

### 3.4 差异支柱总结 (四大壁垒)

1. **生命周期管理 (Lifecycle Management)**: 任意阶段接入 (Idea/已有代码/开发中/生产),
   单点进入统一推进; 产品链 (Idea→Task) 与执行链 (Task→Release) 无缝衔接
   (task 阶段自动生成 Core Task)。
2. **经验闭环 (Experience Loop)**: Task → Recommendation → Execution → Result →
   Experience → Better Recommendation; 只记录不修改 (经验≠自我修改), 30 天半衰期,
   正负经验对记, 人工反馈权重最高。
3. **决策系统 (Decision + Approval)**: AI 产出可复算的推荐 (四因素 × 权重 + 原因 +
   证据链 + 风险), 人通过 Approval Gate 裁决; **决策≠审批, 推荐≠执行**, 高风险/低置信度
   强制人工, 无自动执行指令字段。
4. **Human Console (普通 + 专家模式)**: 普通用户只回答四个问题 (在跑什么/在做什么/
   要我决定什么/为什么推荐); 专家展开 Provider/Cost/Evidence/Event; 只读投影零写路径,
   Web = CLI = 同一批可审计事件。

---

## 4. 商业化: Open Source Core + 商业服务 (只分析不实现)

### 4.1 分层模型

```
┌─────────────────────────────────────────────────────────────┐
│  Marketplace (生态层): Skill / MCP / Runtime / Provider / Plugin   │
│  第三方能力积木交易 + 分成                                          │
├─────────────────────────────────────────────────────────────┤
│  Enterprise (企业层): 多租户 / SSO / 私有部署 / 合规审计 / 定制工作流   │
├─────────────────────────────────────────────────────────────┤
│  Team (团队层): 协作审批 / 审计导出 / 共享经验资产 / Console 专家模式   │
├─────────────────────────────────────────────────────────────┤
│  Personal (个人层): CLI + 单项目 + 内置 Provider (免费)              │
├─────────────────────────────────────────────────────────────┤
│  Open Source Core (开源底座): 事件/任务/工作流/执行/验证/决策/审批       │
│  —— 单机可跑, 能力完整, 永不闭源                                   │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 各层价值主张与收费锚点 (只分析)

| 层 | 目标用户 | 价值主张 | 收费锚点 | 依赖现状 (缺口) |
|:---|:--------|:---------|:---------|:----------------|
| **Open Source Core** | 工程师/独立开发者 | 完整单机生产闭环: 生命周期 + 决策 + 审批 + 经验, 零成本 | 免费 (获客 + 信任 + 生态) | ✅ 已具备 (4090 tests, 41 commits) |
| **Personal** | 个人开发者 | 开箱即用: 内置 Hermes Provider + 示例项目 + Console 只读入口 | 订阅 ($/月): 云 Provider 用量代付 / 优先支持 | 缺: 云 Provider Adapter (8A 预留)、账号系统 |
| **Team** | 小团队 (≤20 人) | 协作审批流 (多 approver 角色) + 审计导出 (合规) + 共享经验资产 | 按席订阅; 专家模式 / 审计导出付费 (human-console-ui-model §6) | 缺: 用户系统/角色权限 (Viewer/Approver/Admin)、审批通知 |
| **Enterprise** | 中大型组织 | 私有部署 + SSO/多租户 + 定制工作流/门禁 + 全量审计回放 | 年费 + 实施; 数据不出内网 | 缺: auth、多租户、部署形态 (factory-console 独立 extension, 架构已不挡路) |
| **Marketplace** | 生态开发者 + 全层用户 | 能力积木 (Skill/MCP/Runtime/Provider/Plugin) 交易; "我要完成什么" → 自动组合 | 交易分成 + 企业定制服务 | 缺: 能力注册表对外化、结算、自动组合编排 (capability-architecture §六 远期) |

### 4.3 商业化逻辑 (为什么这个顺序)

1. **开源底座 = 信任与分发**: 单机完整可用 (当前状态), 让"生产平台"成为可验证的事实,
   而不是 PPT。开源版本永不阉割核心能力 (决策/审批/经验是产品灵魂, 不是付费墙内容)。
2. **付费墙长在"协作与组织"上, 不长在"单机智能"上**:
   - 免费: 只读价值 (普通模式 Console) + 单机 CLI 全功能
   - 付费: 多人在哪里产生价值, 就在哪里收费 —— 审批协作 / 审计导出 / 共享经验 /
     多租户 / 私有部署。这与 human-console-ui-model §6 的付费墙策略一致。
3. **Marketplace 是终局, 不是起点**: 先有真实用户用 Core 跑真实项目 (Personal/Team),
   才有第三方愿意卖 Skill/MCP/Provider; 生态收入依赖前两层先成立。
4. **与云 Provider 是互补而非竞争**: Factory 调度多家 Provider (per-role 偏好),
   Personal 层的"云用量代付"把 API 成本透明化, 是增值服务不是模型生意。

### 4.4 商业化前提 (Phase 依赖, 不承诺时间)

| 前提 | 现状 | 需要 |
|:-----|:-----|:-----|
| 云 Provider 实跑 | 内置 hermes (free) | 8A 已建抽象, 需官方 Adapter (openai/anthropic/codex) + 计费代付 |
| Console 写通道 | 11B 只读投影 (安全默认) | 审批动作 Web 化 (等价事件, 无第二审批路径) |
| 多用户 | 无账号 | 角色权限 (Viewer/Approver/Admin) + SSO |
| 私有部署 | 单机 JSON store | 部署形态/迁移工具 (SQLite 投影已有雏形) |
| 生态 | 声明式注册就绪 | Marketplace 注册表对外化 + 结算 |

---

## 5. 风险与边界 (诚实分析)

| 风险 | 说明 | 缓解 |
|:-----|:-----|:-----|
| **与代码助手竞争错位** | 用户习惯在编辑器里干活, "平台"心智成本高 | 定位不抢编辑, 抢**生产组织与审计**; Console 普通模式把学习成本压到"四问" |
| **Devin 类产品也在演进** | 自主 Agent 可能加审计/闸门 | 我们的差异化在**组织级经验资产 + 多执行资源治理**, 单 Agent 补不上 |
| **框架免费化** | AutoGen/LangGraph 免费, 平台收费难 | 开源 Core 同策略: 价值在流程/审批/经验 (框架不提供), 不在编排原语 |
| **AI 生成质量波动** | 生成产物质量影响信任 | 人工闸门 + 经验负信号 (失败即降分) + L1-L4 验证独立于执行者 |
| **商业化过早** | 产品未到规模化就谈付费 | 本文档**只分析不实现**; Personal 层开源先行, 付费墙依赖协作场景成熟 |

---

## 6. 结论

- **类别判断**: AI Software Factory 属于 **AI Software Production Platform** ——
  与 Cursor/Copilot (工具助手)、Devin (自主 Agent)、AutoGen/LangGraph (开发框架)
  是四个不同物种; 最近的类比是传统软件体系的 **Jira + Jenkins + K8s Dashboard +
  Confluence + CI/CD 的 AI 时代合体** (vision.md 对应表)。
- **护城河**: 生命周期 (组织生产) + 决策系统 (可审计) + 经验闭环 (可积累) +
  Human Console (人人可用) —— 四者互为支撑, 单点复制都难成立。
- **商业化路径**: Open Source Core (信任与分发) → Personal/Team (协作付费) →
  Enterprise (组织付费) → Marketplace (生态分成); 付费墙长在"协作与组织"上,
  开源永不阉割核心能力。**本文档仅作定位分析, 不构成实现承诺。**

---

*本定位与已实现能力逐条对应 (lifecycle-model 12 阶段、decision-intelligence-model、
recommendation-engine-model、experience-learning-model、approval-model、human-console
11A/11B), 无虚构功能。*
