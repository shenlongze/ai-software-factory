# AI Enterprise Operating Model

> 日期: 2026-08-07 | 状态: 最高层产品与架构说明书 (官方)
> 定位: AI Software Factory → AI Organization Factory → AI Enterprise Operating System
> 权威文档索引: 本文是总纲; 细节见各引用文档 (不重复概念)

---

## 1. 产品定位

**AI Factory 是什么？**

AI Factory 不是：
- ❌ AI 聊天工具
- ❌ AI Prompt 工具
- ❌ AI Code Generator
- ❌ 单 Agent 自动化工具

而是：**AI 企业操作系统** — 管理 AI 专业员工、组织 AI 生产、积累组织经验的操作系统。

```
Human Leadership
  ↓
AI Executive Layer
  ↓
AI Organization
  ↓
AI Professional Employees
  ↓
Workflow Execution
  ↓
Experience Learning Loop
```

一句话：**Human 负责决策，AI 员工负责专业工作，系统负责透明与记忆。**

（详见 vision.md / ai-company-operating-model.md）

---

## 2. 产品形态（三种使用模式）

### Solo Mode — 一人公司
```
一个人拥有: CEO/产品经理/项目经理/架构师/开发/测试/财务/市场/运营 = AI 员工团队
原则: 公司小不能没有角色 — Human = CEO, 其余岗位 AI
(solo 扁平模板, 已实现 factory-org)
```

### Team Mode — 多人企业
```
Human + AI Employees 混合团队 (Human 各司其职 + AI 员工补齐岗位)
```

### Enterprise Mode — 大型集团
```
总部 → 区域 → 公司 → 部门 → 岗位 → 员工 (递归嵌套)
同一组织模型, 不允许两个系统 (Solo 扁平 ↔ Enterprise 嵌套)
```

---

## 3. 核心理念 — 专业的人做专业的事

**Agent ≠ 万能 AI。**

```
Agent = Identity + Role + Responsibility + Capability + Knowledge
      + Authority + Experience + Performance
```

一个 Agent 可以拥有多个 Capability：
```
AI Engineer: Capability [Java, Python, Architecture, Cloud]
             当前 Role: Backend Developer (职责决定权限)
```

- Capability ≠ Role: 技能可多, 职位定权
- Authority 绑定 Role, 不绑定 Agent
- 执行权 != 审核权 (Developer 不能 Review 自己)

（详见 agent-role-model.md / agent-employee-model.md）

---

## 4. 多 Agent 协作模型

```
Goal → Analysis → Planning → Task Graph → Role Matching
→ Parallel Execution → Review → Human Approval → Delivery
```

支持：
- 多任务并行 (Parallel Group)
- 依赖管理 (Dependency Graph)
- Critical Path (瓶颈识别)
- Dynamic Replanning (风险触发重规划, 建议制)

Analysis Agent (顾问: 事实/数据/风险) ≠ PM Agent (组织者: 目标/计划/调度)

（详见 planning-intelligence.md / ai-company-operating-model.md §4）

---

## 5. AI 企业神经系统

**定义: Communication + Event + Knowledge + Memory + Decision Evidence**

现实企业问题: 部门信息孤岛 / 沟通成本高 / 信息丢失

AI Enterprise Operating System 通过:
```
Event System       (137+ 事件, 唯一事实源)
Artifact System    (所有产物版本化可追溯)
Communication Record (谁发给谁/何时/为什么)
Decision Evidence (每个决策的依据链)
Audit Trail       (只追加审计)
```

例: A 部门 → B 部门 的消息: 谁发送/什么时候/为什么/依据什么/产生什么决定/影响什么任务 — 全部留痕。

（详见 system-architecture-review.md / decision-intelligence-model.md）

---

## 6. 自我学习系统

### Learning Loop
```
Observe → Collect → Analyze → Evaluate → Approve → Learn → Improve
```

### 三个层级

**① Knowledge Learning — 企业知识学习**
```
产品/客户/市场/技术/流程/文化 (公司知识库)
来源: 企业知识库; 入库 = 人工确认
```

**② Experience Learning — 经验学习**
```
成功案例/失败案例/最佳实践 (ExperienceRecord 五域)
自动记录 + Review 校验
```

**③ System Improvement Learning — 自身进化**
```
新技术适配/新 LLM 适配/自动发现缺陷/Bug 修复建议/功能改进建议/架构优化建议
必须: Proposal → Review → Approval → Implementation → Validation
不能无限自修改 (每步人工闸门)
```

（详见 knowledge-learning-model.md / experience-learning-model.md）

---

## 7. LLM Provider Architecture

**AI Factory 不绑定模型。**

```
支持: OpenAI / Anthropic / Google / Local LLM / 未来模型
通过: Provider Layer (8A-10A 抽象: capability/cost/performance/experience 四因素推荐)
```

模型变化 → AI Factory 不需要重构 (Provider 可替换, 推荐可解释)。

（详见 provider-selection-model.md / provider-intelligence-model.md / recommendation-engine-model.md）

---

## 8. 行业扩展模型

软件公司只是第一个模板。

```
未来: Software / Finance / Manufacturing / Research / Healthcare / Education / Media
行业差异 = 模板差异 (不是重新开发系统):
  Organization Template
  Workflow Template
  Knowledge Template
  Role Template
```

（详见 ai-company-operating-model.md §5 / capability-architecture.md）

---

## 9. 产品模型

```
User          (Human: Founder/CEO/Manager/Operator)
Organization  (Company/Department)
Workspace     (数据空间, 公司隔离)
Project       (业务单元)
Task          (工作单元)
Agent         (AI 员工)
Role          (职位: 权限来源)
Workflow      (流程)
Knowledge     (企业知识)
Experience    (组织经验)
Decision      (智能决策 + 证据)
Artifact      (一切产物)
```

---

## 10. 架构模型

```
Human Console   用户入口 (Developer/CEO/Manager/Operation/Approval/Audit 多中心)
Intelligence    认知层 (Decision/Recommendation/Experience/Planning)
Organization    组织层 (Company/Role/Employee/Authority/Knowledge)
Extension       行业能力 (模板/Registry)
Runtime         运行层 (Managed Services + Command Execution)
Core            冻结原语 (Task/Workflow/Event/Artifact/State)
```

边界铁律:
```
Core 冻结 | Extension 独立 (Removal Isolation)
Intelligence 只读 Core | Runtime 唯一协调
Desktop 无业务逻辑 | Organization 是 Extension
```

（详见 architecture/roadmap.md / organization-runtime-boundary.md）

---

## 11. 数据模型（核心实体关系）

```
Company ─┬─ Department ─┬─ Role ─── Authority (Role→Permission, Default Deny)
         │              └─ Employee(Agent) ─ Capability
         ├─ KnowledgeSpace (公司隔离)
         └─ Experience (组织级)

Task ── Agent (分配) ── Execution ── Artifact
  │        │
  ├─ Event (唯一事实源)
  └─ Approval (人工闸门) ── Decision (证据链)
```

关系要点:
```
Employee != Role (Role 定权, Employee 供能)
Task → Agent 分配 (Registry 只推荐, 自动分配 Phase 17)
Decision 必须 Evidence (无证据不推荐)
Approval 是唯一最终闸门 (Human)
```

---

## 12. 权限模型

```
Default Deny (未声明 = 拒绝)
Authority 绑定 Role (不是绑定 Agent)
原则: 执行权 != 审核权 | 修改权 != 发布权 | 建议权 != 决策权
高风险 (生产/机密/成本) → Human Approval
越权 = 拒绝 + 审计
```

---

## 13. 项目管理能力

```
方法: Waterfall / Scrum / Kanban / Hybrid / MVP (不绑定单一)
智能规划: Task Graph / Dependency / Parallel Group / Critical Path / Dynamic Adjustment
Planning Agent (组织者) 输出: Project Plan / Task Graph / Schedule / Status
```

---

## 14. 当前实现状态（诚实）

```
✅ 已完成:
  Phase 1-14B  Core/Extension/Intelligence/Human Console/Web UI/Demo/开源发布 (v1.0.0-rc1)
  Phase 15     Runtime (Managed Services + Command Model) / Desktop (Tauri+dmg) / Distribution
  Phase 16A    Organization Foundation (factory-org: 六实体/Default Deny/Registry/模板/192 测试)
  4433 pytest + 116 cargo + 92 Vitest | 35 ADR | 151 EventType

📐 设计完成 (待实现):
  Organization 深层 (HR 招聘/培训) / Agent Model / Learning Model / Planning

❌ 未完成 (Phase 17+):
  真实 Agent Execution | LLM Provider 真实接入 | Sandbox | Self Improvement Loop
  (当前执行 = 管理闭环, 非生产闭环)
```

---

## 15. 长期愿景

**AI Global Enterprise Operating System**

```
类似 ERP/SAP/OS — 但是面向 AI + Human Organization
支持: 全球总部 → 区域 → 国家 → 公司 → 部门 (多级组织)
融合方向 (长期, 不现在实现): ERP/CRM/HRM/PM/KM/R&D 管理

未来十年:
  1 人 + Factory = 1 家公司 (2026-2027 验证)
  AI 员工团队管理平台 (2027-2028 组织化)
  AI 集团操作系统 (2028+ 全球化)
```

---

## 附录: 权威文档索引

```
总纲:            本文 (ai-enterprise-operating-model.md)
定位/愿景:       vision.md / architecture/roadmap.md / business-positioning.md
组织:            architecture/ai-company-operating-model.md / factory-org-design.md
员工:            architecture/agent-role-model.md / agent-employee-model.md
知识/学习:       architecture/knowledge-learning-model.md / experience-learning-model.md
规划:            architecture/planning-intelligence.md
运行:            architecture/runtime-service-model.md / runtime-distribution.md
桌面:            architecture/desktop-product-entry.md / phase15-runtime-design.md
架构详情:        system-architecture-review.md / project-structure.md / configuration-model.md
决策/推荐:       decision-intelligence-model.md / recommendation-engine-model.md
质量:            quality-report.md / real-world-validation.md
治理:            docs/adr/ (35 份)
```
