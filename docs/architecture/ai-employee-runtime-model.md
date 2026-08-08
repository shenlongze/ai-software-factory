# AI Employee Runtime Identity Model

> 状态: DESIGN ONLY (蓝图, 未实现或部分实现 — 见 ../audit/architecture-reality-audit.md)

> 日期: 2026-08-07 | 状态: 架构评审, 待确认 (Phase 16B)
> 定位: Organization Foundation → Execution Layer 的最高设计文档
> 引用: agent-role-model.md / knowledge-learning-model.md / factory-org-design.md / ai-enterprise-operating-model.md
> 原则: Core/Runtime/Desktop 零修改; 不创建重复模型; Extension 架构

## 0. 架构缺口与补齐

```
Phase 16A 解决: "AI 员工是谁" (Organization: Company/Role/Employee/Authority/Knowledge)
Phase 16B 解决: "AI 员工如何工作" (Runtime Identity: Agent/Provider/Tool/Sandbox/Capability)

Organization Layer:  Employee (组织身份)
      ↓
Runtime Layer:       Agent Identity (执行身份)
      ↓
Execution Layer:     Provider / Tool / Sandbox / Capability
```

---

## 1. Employee 与 Agent Runtime Identity 的关系

### Employee != Agent

```
Employee (组织身份):   Java Backend Developer — 长期组织资产 (经验/绩效/岗位)
Agent Runtime Identity (执行身份): 可替换的执行实例

一个 Employee 可拥有多个 Agent Instance:
  Agent Instance A: GPT Provider
  Agent Instance B: Claude Provider
  Agent Instance C: Local Model
```

### 为什么不能直接把 Agent 当 Employee？

```
1. 模型/供应商会变: Agent (执行实例) 随 Provider 演进, Employee (组织身份) 稳定
2. 替换成本: 换 Provider = 换 Agent, 不换 Employee (组织零中断)
3. 职责分离: Employee 定义做什么 (组织), Agent 定义怎么做 (执行)
4. 审计归属: 行为记在 Employee 名下 (组织可追责), 执行细节记在 Agent 名下
```

### Agent 替换是否影响组织经验？

**不影响。** Experience 属于 Employee/组织，不属于 Agent：

```
Experience 归属链: Employee (组织) → 组织级经验库 (company_id 隔离)
Agent 只是执行通道: 换 Agent = 换执行器, 历史经验/绩效/知识不丢失
```

### Experience 属于 Employee 还是 Agent？

```
ExperienceRecord: subject = Employee (公司级, 长期)
ExecutionRecord:  subject = Agent Instance (执行级, 短期, 含 provider/token/成本)
两层分离: 组织考核看 Employee 经验; 执行诊断看 Agent 记录
```

---

## 2. Capability Model

### 五类 Capability（非简单标签）

```
Technical   Java/Spring/Database/Cloud/Flutter
Domain      Payment/Finance/Healthcare/E-commerce
Tool        Git/IDE/Browser/CAD/Docker
Reasoning   Analysis/Planning/Optimization
Language    中文/English/TypeScript/Java
```

### Capability 等级

```
Level 1 Knowledge          (知道, 可查资料)
Level 2 Independent Execution (可独立完成常规任务)
Level 3 Expert             (可解决疑难/培训他人/架构决策)
```

### Capability 属于 Employee / Agent / 两者结合？

**两者结合（分离声明）：**

```
Employee.capabilities   声明能力 (Level 1-3, 组织认定, 随培训/经验升级)
Agent.capability_matrix 实例能力 (执行时实际可交付, Provider 能力表 8A)
运行匹配: min(Employee 声明, Agent 实例) — 组织不高于实际
```

---

## 3. Task Matching Model

```
Task (开发支付系统)
  → Requirement Profile (Required Role + Required Capability + Experience + Performance + Cost + Availability)
  → Employee Matching (org Registry: find_by_capability/role → 候选)
  → Agent Selection (Agent Registry: 候选 Employee 的 Agent 实例 + Provider 四因素 10A-3)
  → Execution Recommendation (推荐 + 解释)
```

**原则: Recommendation != Automatic Execution**（自动分配 Phase 17 需确认）。

---

## 4. Multi Agent Collaboration

```
Product Employee → PM Employee → Architect Employee → Developer Employee → QA Employee
```

### 协作规则（禁止私聊/黑盒）

```
Communication: 全部经组织通信系统 (见 §5), 无 Agent 私聊
Artifact:      每步产出 Artifact (版本化/可追溯)
Event:         每步状态变化 = Event (谁/何时/什么)
Review:        独立 Review (执行权 != 审核权)
Approval:      关键节点 Human Approval
```

---

## 5. AI Enterprise Nervous System（重点）

### 企业通信系统

```
所有组织通信必须产生记录:
  Message / Event / Artifact / Decision Evidence / Audit

每次通信记录: Who / To / Purpose / Context / Input / Output / Decision / Result
形成: Organization Memory (组织记忆, 可检索/可复用)
```

### Communication 属于 Core Event 还是 Extension？

**Extension（不污染 Core）：**

```
Core Event:    保留通用事实 (task.*/workflow.*/execution.* — 冻结)
Extension 新增: org.communication.* (org 域, 组织通信专用)
  org.communication.sent / org.communication.artifact_linked / org.communication.decision_recorded
经 EventLogger 落同一事件库 (审计统一), 但类型属 org Extension
```

---

## 6. Learning Loop（三层）

```
Observe → Analyze → Proposal → Human Approval → Implementation → Testing → Release
```

### 哪些可以自动 / 哪些必须人工批准

| 层级 | 自动 | 必须人工批准 |
|:-----|:-----|:------------|
| Knowledge Learning | 收集/分析 (Analysis Agent 建议) | 知识入库/变更 (重大) |
| Experience Learning | 记录/聚合 (自动 + Review) | — (Review 校验) |
| System Improvement | 观察/分析/提案 | 实施/Release (Proposal→Approval 铁律) |

```
禁止无限自动修改: 系统自身改进 (新 LLM 适配/缺陷修复/功能建议) 全部走 Proposal → Approval
```

---

## 7. LLM Provider Abstraction

```
Agent 不绑定模型: OpenAI/Anthropic/Google/Local — Provider Layer (8A-10A)
模型变化 → 不影响 Organization (Employee 稳定, 只换 Agent Instance)
```

### Provider 属于 Agent Instance 还是 Runtime Infrastructure？

**两者分层：**

```
Runtime Infrastructure: Provider 注册表 (8A: 能力/成本/性能/经验 四因素数据)
Agent Instance:         Provider 绑定 (实例选哪个 Provider/模型)
Employee:              Provider 无关 (组织身份稳定)

模型变化: 改 Agent Instance 绑定 → 组织零影响
```

---

## 8. HR Agent

```
职责: Recruit / Training / Capability Assessment / Employee Evolution

流程: Business Need → HR Analysis → Capability Gap
  → Training / Hiring Recommendation → Human Approval
```

```
HR Agent 建议制: 招聘/培训/转岗 = 推荐 + Approval
HR Agent 无权: 直接赋高权限 / 直接雇人 (9c Approval)
```

---

## 9. Permission Boundary（三层权限）

```
Organization Authority (Role 权限, 16A)
   ↓ 例: Developer: code.modify ✅ / release.approve ✗
Agent Runtime Permission (执行限制)
   ↓ 例: Agent 只能执行已授权任务, 不能自选任务
Tool Permission (具体工具)
   ↓ 例: Git 只读 / IDE workspace / 禁生产库
```

```
任何一层 deny = 拒绝 + 审计
高危 (生产/机密/成本) = 顶层 Human Approval
```

---

## 10. Phase 17 / 18 依赖关系

```
Phase 17 Planning Intelligence 依赖:
  Employee (16A) + Capability (§2) + Matching (§3) + Communication (§5)
Phase 18 Execution 依赖:
  Agent Runtime (§1) + Provider (§7) + Tool (§9) + Sandbox (执行边界)

16B (Runtime Identity) = 17/18 的地基
```

---

## 11. 数据模型提案（新增, 不重复 16A）

```python
class AgentInstance(Pydantic):     # 执行身份
    id/employee_id
    provider_id: str                # Provider 绑定 (8A registry)
    model: str
    capability_matrix: dict         # 实例实际能力 (Provider 表)
    status: active|disabled

class CapabilityProfile(Pydantic): # 五类 + 等级
    employee_id/capability_type (technical|domain|tool|reasoning|language)
    name/level (1|2|3)/evidence

class RequirementProfile(Pydantic): # Task Matching
    task_id/required_role/required_capabilities
    min_experience/min_performance/max_cost/availability

class CommunicationRecord(Pydantic): # 神经系统
    id/company_id/from_employee/to_employee
    purpose/context/input/output/decision/result
    artifact_refs/event_refs/timestamp
```

## 12. 边界

```
✅ Core 冻结 (Communication 走 org.* Extension 事件, 不碰 Core Event 类型)
✅ Runtime 不修改 (Provider 注册表是 8A 已有抽象)
✅ 无重复模型 (Employee/Authority/Knowledge 复用 16A)
✅ 推荐 != 自动执行 (Matching/HR 全部建议制)
```

## 13. 结论

```
16B 定义 AI 员工"如何工作": Employee (组织) → Agent Instance (执行) → Provider/Tool/Sandbox
为 Phase 17 (Planning/Matching) 与 Phase 18 (Execution) 提供统一运行时身份模型
等待确认后进入实现 (Phase 16B-1: AgentInstance + CapabilityProfile + Communication 基础)
```
