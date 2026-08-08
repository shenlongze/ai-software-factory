# AI Employee Execution Runtime Model

> 状态: DESIGN ONLY (蓝图, 未实现或部分实现: exec 工程已实现, Employee 执行运行时未实现 — 见 ../audit/architecture-reality-audit.md)

> 日期: 2026-08-07 | 状态: 架构评审, 待确认 (Phase 18)
> 定位: AI Enterprise OS Execution Layer 最高设计文档
> 引用: ai-employee-runtime-model.md / ai-enterprise-nervous-system-model.md / ai-enterprise-planning-operation-model.md / ai-enterprise-governance-model.md
> 原则: Core/Runtime 零修改; 不创建重复模型; Agent 不直接修改用户环境

## 0. 缺口

```
已有: Organization/Employee/Capability/Planning/Governance/Communication
缺: 真正执行层 — AI 员工如何从 Task 到 Execution

Execution Runtime = 把"计划的任务"变成"真实的世界变化" (受控/可审计)
```

---

## 1. Agent Runtime 定义

```
Agent Runtime = 执行身份的运行环境 (16B AgentInstance 的落地执行器)

职责:
  接收 ExecutionRequest → 组装上下文 → 校验 → 调 Provider → 沙箱执行
  → 产 Artifact → 记录 Event/Communication/Audit → 反馈 Experience

形态 (与 Phase 15 裁决 B 同哲学):
  Managed Service (常驻 worker) + Command Execution (任务执行)
```

---

## 2. Task → Execution Request 流程

```
Task (17 模型: objective/input/output/owner/reviewer)
  → ExecutionRequest (执行请求: 任务契约 + 上下文引用)
  → 门禁检查 (Capability/Authority/Policy/Risk — §7/§8/治理)
  → Agent Runtime 执行
  → Artifact + Result
  → Review (独立审核) → Approval (按风险) → Apply (合并/落地)

流程事件: execution.requested → started → completed|failed (Core 已有 + org.execution.* 包装)
```

---

## 3. Employee / Agent / Provider / Runtime 关系

```
Employee (组织身份: 做什么) → Agent Instance (执行身份: 怎么做)
  → Provider (模型来源: 能力/成本) → Runtime (运行环境: 沙箱/工具)

映射: Task → Employee (Role 匹配) → Agent Instance (Provider 选择)
     → Runtime (执行) — 每层可替换, 互不耦合
```

---

## 4. Multi Agent Execution

```
单任务可能需多员工协作 (16C §5):
  Developer 实现 → QA 验证 → Reviewer 审核 → Business 发布

并行: 依赖无关任务 → Parallel Group (17 §4) → 多 Runtime 并行执行
协调: 全部经 Communication + Artifact + Event (禁私聊/黑盒)
```

---

## 5. Context Assembly

```
执行前组装上下文:
  任务契约 (objective/input/output/requirement)
  相关 Artifact (前置产物引用)
  企业知识 (16A: 规范/文档 — Layer 2)
  项目知识 (当前架构/决策链 — Layer 3)
  历史决策 (16C Decision Memory: 避免重复/踩坑)

Context = 最小必要集 (不传全库, 防泄露/防噪音)
```

---

## 6. Memory Loading

```
执行时加载组织记忆:
  Experience Memory (同类任务历史: 成功率/坑/最佳实践)
  Decision Memory (相关决策 + Evidence)
  Knowledge Memory (领域知识, 按公司/项目授权)

加载规则: 只读 + 授权过滤 (公司隔离铁律) + 可审计 (加载了什么)
```

---

## 7. Capability Verification

```
执行前验证:
  Employee.capabilities (声明 Level 1-3, 16B)
  Agent.capability_matrix (实例实际, Provider 表)
  匹配 = min(声明, 实际) ≥ 任务要求

不满足 → 拒绝 + 建议 (培训/换 Agent/换 Employee — HR 建议制)
```

---

## 8. Authority / Permission Check

```
三层校验 (17A §1):
  Organization Authority (Role: code.modify?)
  Agent Runtime Permission (执行身份: 只执行授权任务)
  Tool Permission (具体工具: Git 只读?)

任一层 deny → 拒绝 + 审计 (Default Deny)
高危 (生产/机密/成本) → Human Approval 前置
```

---

## 9. Tool Execution

```
工具抽象 (16B §9):
  Tool Registry (Git/IDE/Browser/Database/... 声明式)
  Tool Permission (Role→Tool→操作 矩阵)

执行: Runtime 经 Tool 接口调用, 全记录 (tool.executed 事件)
```

---

## 10. Sandbox Isolation

```
铁律: Agent 不直接修改用户环境

Sandbox:
  工作副本 (项目快照) / 文件系统隔离 / 网络策略 (配置化)
  产出 = Patch/diff (6C git 语义)

Apply 条件: Validation 通过 + Approval (按风险) → 合并
```

---

## 11. Artifact Generation

```
执行产出 = Artifact (版本化):
  代码 Patch / 文档 / 测试报告 / 分析报告

Artifact 关联: artifact_refs → 任务/决策/通信 (16C 四重引用)
```

---

## 12. Event / Communication / Audit 记录

```
每步执行记录:
  Event:    execution.started/completed/failed (Core) + org.execution.* (组织语义)
  Communication: 完成通知/请求 Review (16C)
  Audit:    AuditRecord 四重引用 (谁/为什么/依据/结果 — 17A §7)

无静默执行 (一切可见)
```

---

## 13. Failure Recovery

```
失败分级:
  Transient (网络/超时) → 重试 (指数退避, ≤N)
  Task-level (测试失败) → 修复循环 (dev→debug, 记录)
  Runtime-level (沙箱崩溃) → 重启 Runtime (Managed Service watchdog)
  Approval-level (被拒) → 终止 + 反馈 (不自动绕过)

恢复原则: 可暂停/可恢复/可审计 (Checkpoint 4C-3 语义)
```

---

## 14. Experience Feedback

```
执行结果 → Experience Feedback (10A-4):
  ExecutionRecord (Agent 级: provider/token/成本/耗时)
  ExperienceRecord (Employee 级: 成功/失败/评分)

→ 未来任务匹配加权 (Performance Learning)
→ 组织记忆沉淀 (16C Memory)
```

---

## 15. Phase 19 Self Improvement 接口

```
执行层 → 自改进提案接口 (17A §6):
  ExecutionData (失败模式/成本异常/性能瓶颈) → Observe
  → Analysis Agent 分析 → Proposal (改进建议)
  → Human Approval → Implementation → Test → Release

执行层只提供数据与执行, 不自改 (禁止无限自修改)
```

---

## 16. 数据模型提案（新增, 不重复）

```python
class ExecutionRequest(Pydantic):   # §2 (task_id/context_refs/requirement)
class ExecutionContext(Pydantic):   # §5 (§6 加载结果)
class ToolCall(Pydantic):           # §9 (tool/action/args/result)
class SandboxSession(Pydantic):     # §10 (workspace_snapshot/patch)
```

## 17. 边界

```
✅ Core/Runtime 零修改 (Execution 是组织层语义, Core 已有 execution 原语)
✅ 无重复模型 (Task/Employee/Agent/Provider/Communication/Governance 复用)
✅ 沙箱铁律 | ✅ 全链审计 | ✅ 失败可恢复 | ✅ 自改进受控
```

## 18. 结论

```
18 定义 AI 员工执行: Task→ExecutionRequest→门禁→Sandbox→Artifact→Review→Approval→Apply
15 环节全链受控可审计, 为 AI OS 提供真正的"生产"能力
等待确认后进入实现 (18-1: ExecutionRequest + Sandbox 最小 + org.execution.* 事件)
```
