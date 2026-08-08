# AI Enterprise Governance & Control Model

> 状态: DESIGN ONLY (蓝图, 未实现或部分实现 — 见 ../audit/architecture-reality-audit.md)

> 日期: 2026-08-07 | 状态: 架构评审, 待确认 (Phase 17A)
> 定位: AI 企业操作系统治理最高设计文档
> 引用: ai-enterprise-operating-model.md / ai-employee-runtime-model.md / ai-enterprise-nervous-system-model.md / ai-enterprise-planning-operation-model.md
> 原则: Core 冻结; 不重复已有模型; Human 最终负责

## 0. 治理缺口

```
已解决: Who works (16A) / How works (16B) / How communicate (16C) / What to do (17)
缺: 治理体系 — 权限/审批/政策/风险/成本/自改进/审计/领导

Governance Layer = 企业运行的规则层 (Default Deny 全面化)
```

---

## 1. Authority Model（四层权限体系）

```
Organization Authority (组织层):  Role → Permission (16A, 默认 deny)
Role Authority (角色层):         岗位职责边界 (Developer code.modify)
Agent Runtime Permission (执行层): 执行身份只能执行授权任务 (16B)
Tool Permission (工具层):        具体工具 (Git 只读/禁生产库)

任一层 deny = 拒绝 + 审计
```

**谁拥有最终决定权？Human（唯一）。**

```
Human (CEO/Manager) = 最终批准权
AI (Executive/Manager Agent) = 提案/建议/执行 — 无最终权
```

---

## 2. Approval Model

### 必须人工批准

```
战略方向 / 预算决策 / 组织变化 (招聘/转岗/权限提升) / 高风险执行 / 生产发布 / 外部依赖 / 成本增加
```

### 可自动执行

```
低风险任务 (内部实现/测试/分析) / 计划内调度 / 常规运维 / 经验记录
```

```
规则: 风险分级 (Risk Management §4) 决定审批层级:
  low → 自动 | medium → Manager | high → CEO/Human
```

---

## 3. Policy System

### 企业规则（声明式 policy.yaml）

```
安全规则   (禁生产访问/密码/外网)
代码规范   (命名/格式/禁反模式)
成本规则   (单任务预算上限)
合规规则   (金融/医疗/隐私/数据驻留)
```

### Policy 如何影响 Planning / Task / Execution

```
Planning:  约束计划 (成本上限→范围裁剪; 合规→阶段门)
Task:      校验任务 (task.policy 检查: 是否违反规则 → 拒绝/标记)
Execution: 执行时强制 (工具权限/禁危险操作/沙箱)
```

```
Policy 执行: 声明式 + 检查点 (planning gate / task validate / execution sandbox)
Policy 变更: 人工 Approval (规则是治理资产)
```

---

## 4. Risk Management

### AI 企业风险模型

```
Technical Risk  (技术: 架构/依赖/性能)
Business Risk   (业务: 市场/竞争/需求)
Security Risk   (安全: 数据/权限/漏洞)
Financial Risk  (财务: 成本/预算/收入)
```

### Risk 如何进入 Analysis / Decision / Approval

```
Analysis: 风险识别 + 分级 (low/medium/high) + 缓解建议 (10A-2 R1-R5 扩展)
Decision: 风险作为决策 Evidence (16C §4)
Approval: 高风险 → 必须人工 (Risk 决定审批层级 §2)
```

---

## 5. Cost Governance

### AI 成本构成

```
LLM Token (调用/推理) / Compute (执行资源) / Tool Usage (工具)
```

### 设计

```
Budget:   目标级预算 (每 Goal/Project 上限)
Quota:    配额 (每 Employee/Agent 周期额度)
Optimization: 推荐优化 (10A-3 Cost 因素: 便宜 Provider 优先/缓存/降级)

超预算 → 告警 + 暂停建议 + Manager Approval
```

```
数据来源: UsageRecord (8B-3: token/estimated_cost) + ExecutionRecord (16B)
```

---

## 6. AI Self Improvement Governance（重点）

### AI 可以自动

```
Observe (观察) / Analyze (分析) / Recommend (建议) — 只读
```

### 必须 Approval（修改类）

```
Self Modification: Proposal → Review → Test → Approval → Release

可自动提案: 新技术适配/新 LLM 适配/缺陷发现/Bug 修复建议/功能建议/架构优化建议
必须人工: 实施/合并/发布 (任何系统自身变更)
```

```
禁止无限自修改: 系统改进全部走 Proposal 闸门 (16C Learning Loop 铁律)
```

---

## 7. Audit Model

### Enterprise Audit Trail（统一）

```
Communication (16C) + Event (Core) + Artifact + Decision + Approval

AuditRecord 回答: 谁做了什么/为什么/依据什么/结果如何
  actor / action / reason / basis (四重引用) / result / timestamp

只追加 (append-only), 不可篡改, 支持金融/医疗/大型企业合规
```

---

## 8. Human Leadership Model

```
Human                       AI
─────────────────────────────────────────────
CEO     (战略/最终批准)     Executive Agent (分析/提案/汇报)
Manager (计划/资源/审批)    Manager Agent (计划/调度/监控)
Expert  (专业判断)          Professional Agent (专业执行)
Operator(日常运营)          Operation Agent (监控/报告)

关系: Human 决策 → AI 执行 → AI 汇报 → Human 复核 (闭环)
AI 越权 = 拒绝 + 审计; AI 提案 = 建议制
```

---

## 9. Governance ↔ Learning

### 治理数据反哺

```
Experience:  审批通过/拒绝案例 → 经验 (什么该批/什么该拒)
Knowledge:   政策/规则变更 → 知识库 (企业规范)
Performance: 风险命中率/成本控制 → 员工绩效 (治理合规度)

闭环: 治理约束执行 → 执行结果进经验 → 经验优化未来治理建议
```

---

## 10. 与未来 ERP/SAP

```
为什么 Governance 是 AI OS 区别传统 ERP 的核心:

传统 ERP: 记录"发生了什么" (数据录入/流程固化)
AI Enterprise OS: 治理"为什么发生" (决策+依据+审批+审计实时)

Governance 提供:
  实时风险分级审批 (非事后补录)
  全链审计 (非表级日志)
  政策驱动的执行约束 (非流程模板)
  自改进受控 (非静态系统)

→ 治理层 = AI OS 的信任基础 (企业敢把生产交给 AI 的前提)
```

---

## 11. 数据模型提案（新增, 不重复）

```python
class Policy(Pydantic):          # §3 (声明式规则: domain/rules/enforcement)
class BudgetAllocation(Pydantic): # §5 (goal_id/limit/used/quota)
class RiskAssessment(Pydantic):   # §4 (task_id/type/level/mitigation)
class AuditRecord(Pydantic):      # §7 (四重引用, 只追加)
```

## 12. 边界

```
✅ Core 冻结 (Governance 走 org.governance.* 事件)
✅ 无重复模型 (Authority/Approval/Experience/Knowledge 复用 16A-17)
✅ Human 最终权 | ✅ Default Deny 全面化 | ✅ 自改进受控
```

## 13. 结论

```
17A 定义 AI 企业治理体系: 权限四层/审批分级/政策约束/风险/成本/自改进闸门/统一审计
为 AI OS 提供信任基础 (企业敢把生产交给 AI 的前提)
等待确认后进入实现 (17A-1: Policy + RiskAssessment + org.governance.* 事件)
```
