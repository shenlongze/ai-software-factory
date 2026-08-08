# AI Enterprise Operating System — Reference Architecture

> 状态: DESIGN ONLY (蓝图, 未实现或部分实现 — 见 ../audit/architecture-reality-audit.md)

> 日期: 2026-08-07 | 状态: 统一参考架构 (Phase 17B Consolidation)
> 定位: AI Factory 的最高统一设计文档 (整合 16A-17A 五个设计)
> 复用: factory-org-design.md / ai-employee-runtime-model.md / ai-enterprise-nervous-system-model.md / ai-enterprise-planning-operation-model.md / ai-enterprise-governance-model.md
> 原则: 不创建新模型; 只统一表述; Core/Runtime 零修改

---

## 1. 产品定位

**AI Factory = AI Enterprise Operating System**

为什么不是：
```
❌ Chatbot          (只对话, 不组织)
❌ Code Generator   (只产代码, 不管理)
❌ Single Agent Tool (只执行, 不协作)
```

而是：**管理 AI 专业员工、组织 AI 生产、积累组织经验、治理企业运行的操作系统。**

```
Human Leadership
  ↓
AI Executive Layer
  ↓
AI Organization (Company/Department/Role/Employee)
  ↓
Workflow Execution (Planning → Task → Agent → Review → Approval)
  ↓
Experience Learning Loop (Observe → Learn → Improve)
```

一句话：**Human 负责决策，AI 员工负责专业工作，神经系统负责透明与记忆，治理层负责信任。**

---

## 2. 三大运行模式

```
Solo Mode     一人公司: Human=CEO + AI 员工团队 (小不能没有角色)
Team Mode     多人企业: Human + AI Employees 混合
Enterprise Mode 集团: 总部→区域→公司→部门→岗位→员工 (递归嵌套)
同一组织模型, 不允许两个系统 (Solo 扁平 ↔ Enterprise 嵌套)
```

---

## 3. 统一模型（10 大模型）

### Product Model
```
User(Founder/CEO/Manager/Operator) → Organization → Workspace → Project
→ Task → Agent → Role → Workflow → Knowledge → Experience → Decision → Artifact
```

### Architecture Model
```
Human Console (多中心入口) → Intelligence → Organization → Extension → Runtime → Core(冻结)
边界: Core 冻结 | Extension 独立 | Runtime 唯一协调 | Desktop 无业务逻辑
```

### Organization Model（16A）
```
Company → Department → Role → Employee; Employee != Role (Role 定权, Employee 供能)
Knowledge 公司隔离; Authority 默认 deny
```

### Employee Model（16A/16B）
```
Employee = 组织身份 (长期资产: 经验/绩效/岗位)
```

### Agent Runtime Model（16B）
```
Agent Instance = 执行身份 (可替换: Provider 绑定/能力矩阵/状态)
Employee → 多 Agent Instance (GPT/Claude/Local); Experience 属 Employee
```

### Communication Model（16C）
```
CommunicationRecord: Who/To/Purpose/Context/Input/Output/Decision/Result
组织通信全记录, 无私聊/无黑盒
```

### Planning Model（17）
```
Goal → Analysis → Plan → Milestone → Task Graph → Role Matching → Execution → Review
多行业模板 (Software/Research/Marketing/Business); 不绑 Scrum
```

### Governance Model（17A）
```
四层权限 + Approval 分级 + Policy 约束 + Risk 管理 + Cost 治理 + Audit
Human 最终决定权
```

### Learning Model（16A/16C/17A）
```
三层: Knowledge (人工确认) / Experience (自动+Review) / System Improvement (Proposal→Approval)
```

### Provider Model（8A-10A）
```
Provider Layer 不绑定模型 (OpenAI/Anthropic/Google/Local)
四因素推荐: Capability/Cost/Performance/Experience — 模型变化零重构
```

---

## 4. AI 企业神经系统（组织智能）

```
Communication + Event + Artifact + Decision + Audit + Memory

Communication: 组织意图 (谁因什么目的传递什么)
Event:         事实变化 (时间线)
Artifact:      事实产物 (世界状态)
Decision:      决策 + Evidence (企业最重要资产)
Audit:         四重引用审计 (谁/为什么/依据/结果)
Memory:        组织记忆 (长期: 决策/经验/知识; TTL: 日常消息)

形成组织智能: 每步执行 → 记忆沉淀 → 未来计划更准
(16C 全链: 跨部门协作可追踪/可回溯/可学习)
```

---

## 5. Self Improvement Loop

```
系统自身进化 (受控):
Observe (发现问题) → Analyze (分析) → Proposal (改进建议)
→ Human Approval → Implementation → Testing → Release

AI 可自动: 观察/分析/推荐 (只读)
必须人工: 实施/合并/发布 (任何系统自身变更)
禁止: 无限自修改
```

---

## 6. Employee != Agent != LLM Provider

```
Employee (组织身份)  ≠  Agent Instance (执行身份)  ≠  Provider (模型来源)
  长期资产                可替换执行器                模型供应商
  经验/绩效/岗位           Provider 绑定               能力/成本/性能

替换关系: 换 Provider = 换 Agent, 不换 Employee, 组织零中断
```

---

## 7. ERP/SAP 演进方向（只记录, 不实现）

```
AI Enterprise OS 未来可能融合: ERP/CRM/HRM/PM/KM/R&D 管理

差异: 传统 ERP 记录"发生了什么"; AI OS 治理"为什么发生"
  (实时风险审批 / 全链审计 / 政策驱动执行 / 受控自改进)
→ 治理层 = AI OS 的信任基础

Phase 21+ 评估; 当前不实现商业系统
```

---

## 8. 设计文档索引

```
总纲:          本文 (Reference Architecture)
产品:          ai-enterprise-operating-model.md
组织:          factory-org-design.md
员工/执行身份:  ai-employee-runtime-model.md
通信/记忆:      ai-enterprise-nervous-system-model.md
规划/运行:      ai-enterprise-planning-operation-model.md
治理:          ai-enterprise-governance-model.md
底层:          vision.md / architecture/roadmap.md / ADR (35)
```

## 9. 边界

```
✅ 不创建新模型 (10 模型全部已有设计)
✅ Core/Runtime/Desktop 零修改
✅ 面向普通用户/管理者/架构师统一可读
```

## 10. 结论

```
AI Factory = AI Enterprise Operating System:
  组织层 (谁工作) + 执行身份 (如何工作) + 神经系统 (沟通记忆)
  + 规划运行 (做什么) + 治理 (信任基础)
5 个设计 → 1 个统一参考架构
```
