# AI Software Factory — Agent Employee Model

> 状态: DESIGN ONLY (蓝图, 未实现或部分实现: org Employee 仅组织身份, 非执行实体 — 见 ../audit/architecture-reality-audit.md)

> 日期: 2026-08-07 | 状态: 设计 (Phase 16 Deep Review)
> 核心: Capability ≠ Role — Agent 是组织中的专业员工, 不是 LLM+Prompt

## 1. AI 员工是什么？

```
AI Employee = Identity + Role + Responsibility + Capability + Knowledge + Authority + Experience + Performance

Identity      员工身份 (id/姓名/所属公司)
Role          当前职位 (决定职责与权限)
Responsibility 该职位负责什么 (产出/目标/边界)
Capability    专业技能集 (多能力可并存)
Knowledge     企业知识 (公司上下文, 三层隔离 §4)
Authority     权限 (绑定 Role, 非绑定 Agent; 默认 deny)
Experience    做过什么 (历史任务/结果, 组织级)
Performance   做得怎么样 (成功率/成本/评分)
```

## 2. Capability ≠ Role（多能力员工）

**一个 Agent 可以拥有多个专业能力，但当前职位决定权限和责任。**

```
示例: 一个 AI 员工
  Capability: [Java 架构, Python 开发, 数据分析]
  当前 Role: Developer (职责: 技术实现)
  → 可用 Java/Python 技能开发; 无权做架构决策 (那是 Architect Role)
  → 数据分析能力暂未启用 (除非担任 Data Role)

现实类比: 员工懂财务+管理+技术, 但当前职位决定做什么和能做什么。
```

### Role 与 Capability 的关系

```
Role 引用 Capability 集 (Role.capabilities 白名单)
Capability 是技能 (可跨 Role 复用, 如 Python 技能 Dev/Data 都要)
Authority 绑定 Role (Developer 能改代码不能批准上线; QA 能测不能改生产)
Capability 变化 = 培训 (不自动提权)
Role 变化 = 转岗 (权限随之变, 需 Approval)
```

## 3. 多 Role 与冲突规则

```
Agent.roles 可多 (一人多岗), 但禁冲突组合:
  ✗ Developer + Reviewer (执行权 != 审核权)
  ✗ Developer + QA (自测自批)
  ✗ 任何 + CEO (最终批准权唯一)
多 Role 时 Authority = 各 Role 并集, 冲突组合注册表硬拒绝
```

## 4. AI Employee Lifecycle（招聘/培养/替换）

```
Business Goal (缺 Java 架构师)
  → CEO/Manager (确认需求)
  → HR Agent (AI HR: 人才搜索/能力评估/招聘建议/培训计划)
  → Search Existing (查 Agent Registry: 已有员工有 Java 架构能力?)
  → Training (无 → 培训计划: 补 Knowledge/Capability, 需 Approval)
  → Recruit External (无 → 从 Skill/Provider 生态装配新 Agent)
  → Create Employee (创建: Role+Capability+Authority, 初始经验 0)
  → Approval (HR 无权直接赋高权限 — 高权限需 Human/CEO 批准)
```

```
培养: Experience 回流 → Performance 提升 → 更复杂任务
替换: 同 Role 新员工接任 (经验是组织的, 不随员工流失)
解雇: Authority 撤销 + 任务 reassign + 审计
```

## 5. 透明与审计

```
每员工行为 = Event (org.*/task.*/execution.*) + Audit
招聘/转岗/培训/权限变更 = Approval 记录
绩效 = ExperienceRecord + Performance 可查
```
