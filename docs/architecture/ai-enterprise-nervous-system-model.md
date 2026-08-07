# AI Enterprise Nervous System Model

> 日期: 2026-08-07 | 状态: 架构评审, 待确认 (Phase 16C)
> 定位: AI 企业操作系统的信息流最高设计文档
> 引用: ai-enterprise-operating-model.md / ai-employee-runtime-model.md / knowledge-learning-model.md / factory-org-design.md
> 原则: Core 冻结; 不创建重复模型; 全部 Extension

## 0. 核心缺口

```
现实企业问题: 部门信息孤岛 / CEO 不知执行细节 / 决策不透明 / 经验不沉淀 / 沟通不可审计

AI 企业神经系统 = Communication + Event + Artifact + Decision + Memory
→ 解决: 组织信息流的可追踪 / 可审计 / 可学习
```

---

## 1. Communication Model

### 通信对象

```
Human / Employee / Agent / Department / Company (全对象可通信)
```

### 通信类型

```
Message (消息) / Request (请求) / Report (报告) / Decision (决策) / Notification (通知) / Approval (审批)
```

### CommunicationRecord（每次通信必须记录）

```python
class CommunicationRecord(Pydantic):
    id/company_id
    comm_type: str          # message|request|report|decision|notification|approval
    from_entity: str        # human:<id>|employee:<id>|agent:<id>|dept:<id>|company:<id>
    to_entity: str
    purpose: str            # 目的
    context: str            # 上下文 (引用 Artifact/Event)
    input: str              # 输入摘要
    output: str             # 输出摘要
    decision: str | None    # 产生的决定
    result: str | None      # 结果/影响
    artifact_refs: list[str]
    event_refs: list[str]
    timestamp: str
```

---

## 2. Communication 与 Event 与 Artifact 的关系

```
三者分工 (不混淆):

Artifact  = 事实产物 (代码提交/文档/PRD) — 世界的状态
Event     = 事实变化 (task.completed) — 时间线上的状态变迁
Communication = 组织意图 (通知 PM) — 谁因什么目的传递什么

例: Developer 完成任务
  Artifact:  代码提交 (git commit / patch)
  Event:     task.completed (Core 事实)
  Communication: "Developer → PM: 任务完成, 请 Review" (组织意图)
```

### 关联规则

```
CommunicationRecord.event_refs → 对应 Event
CommunicationRecord.artifact_refs → 对应 Artifact
Communication 可触发新 Event (comm.* ) 但 Event 不自动变成 Communication
```

---

## 3. Organization Memory

### 四类记忆

```
Decision Memory       (决策记录 §4) — 长期
Experience Memory     (经验记录 10A-4) — 长期 (随衰减)
Knowledge Memory      (企业知识库 16A) — 长期 (人工确认)
Communication History (通信历史 §1) — 短期+长期分层
```

### 什么进入长期记忆 / 什么自动过期

```
长期 (永久, 可检索):
  决策 + Evidence (企业最重要资产)
  经验 (成功/失败案例 — ExperienceRecord, 半衰期衰减但保留)
  知识 (人工确认入库)

短期 (TTL 自动过期/归档):
  日常 Message/Notification (如 "进度更新") — 30-90 天归档
  临时 Request 上下文 — 任务完成后压缩为摘要
```

```
归档规则: Communication → 摘要 (Decision/Result 提炼) → 进 Decision/Experience Memory
```

---

## 4. Decision System

### DecisionRecord

```python
class DecisionRecord(Pydantic):
    id/company_id
    proposal: str           # 提案
    evidence: list[str]     # 依据 (Event/Artifact/Experience 引用)
    options: list[dict]     # 候选方案 + 评分
    decision_maker: str     # human:<id>|agent:<id> (CEO/PM Agent)
    approval: str           # 审批链 (9c)
    result: str | None      # 执行结果回填
    timestamp
```

### 决策来源

```
Human CEO 决策 (最终) + AI 建议 (10A-2 Decision Intelligence)
未来: AI CEO/Manager 可产生决策提案, 但最终批准 Human
```

---

## 5. Cross Department Collaboration

```
Product (需求) → Architecture (方案) → Development (实现) → QA (验证) → Business (发布)
```

### 全链可追踪

```
每步 = Communication + Artifact + Event + Decision:
  Product→Architecture: 需求 Communication + PRD Artifact
  Architecture→Dev:     方案 Communication + 技术设计 Artifact
  Dev→QA:               实现 Communication + 代码 Artifact + task.completed Event
  QA→Business:          验证 Communication + 报告 Artifact + release.approval Decision

回溯: Business 可查"谁/何时/为什么/依据/结果" 全链
学习: 全链 Communication → Decision → Result 可沉淀为经验
```

---

## 6. Audit System

```
企业审计回答: 谁做了什么? 为什么? 依据什么? 结果如何?

AuditRecord = Communication + Event + Artifact + Decision 的四重引用
  actor (human/employee/agent)
  action (发起/修改/批准/拒绝)
  reason (purpose + evidence)
  basis (event_refs + artifact_refs + decision_refs)
  result (outcome)

支持: 金融/医疗/大型企业 (合规审计, 只追加, 不可篡改)
```

---

## 7. Learning Loop Integration

```
失败项目闭环:
  Communication (谁传递了什么) → Decision (基于什么依据决定)
  → Execution (执行) → Result (结果) → Experience (经验记录)

形成 Organization Learning:
  失败项目 → 全链通信审计 → 定位决策失误 → 经验入库 → 未来项目规避
  (成功项目同理 → 最佳实践入库)
```

---

## 8. 与现有架构关系（Core vs Extension 归属）

| 系统 | 归属 | 理由 |
|:-----|:-----|:-----|
| Core Event (task.*/workflow.*/execution.*) | **Core** (冻结) | 通用执行事实 |
| Artifact | **Core** (已有) | 通用产物 |
| Approval (9c) | **Core** (已有) | 通用闸门 |
| Experience (10A) | **Core** (已有) | 通用经验 |
| Knowledge (16A) | **Extension** (org) | 公司隔离知识 |
| Communication (16C) | **Extension** (org.communication.*) | 组织通信专用 |
| Decision Record (16C) | **Extension** (org.decision.*) | 组织决策专用 |
| Audit (16C) | **Extension** (org.audit.*) | 组织审计专用 |

```
规则: Core 提供通用事实原语; 组织层 (org Extension) 提供组织语义包装
Communication/Decision/Audit 全部 org.* 事件, 经 EventLogger 落同一事件库 (审计统一)
```

---

## 9. 与 Phase 17/18 关系

```
Phase 17 Planning Intelligence:
  读取 Communication Memory → 理解上下文/约束/历史决策
  → 输出计划 (建议制) → 经 Communication 分发给 Employee

Phase 18 Execution Runtime:
  Execution 每步产生 Event (已有) → Runtime 包装为 Communication Event
  (org.communication.execution_started/completed) → 进 Organization Memory

循环: Planning 读记忆 → 计划 → Execution 产生新记忆 → 下一轮更聪明
```

---

## 10. 未来 ERP/SAP 方向（仅设计）

```
为什么 AI Enterprise Nervous System 可能成为 AI ERP/OS 基础:

1. 统一信息流: 传统 ERP 的孤岛 (CRM/HRM/PM/KM) 在这里是同一信息流的不同视图
2. 决策即资产: Decision + Evidence 天然支持治理/合规 (金融/医疗刚需)
3. 组织记忆: Communication History + Experience = 企业唯一知识源
4. 可演进: Communication Model 是语义层, 可叠加 CRM/财务/供应链 业务视图 (模板 16A/20)

传统 ERP = 数据录入系统; AI Nervous System = 组织意图+事实+记忆的统一流
(不现在实现; 记录方向, Phase 21+ 评估)
```

---

## 11. 数据模型提案（新增, 不重复）

```python
class CommunicationRecord(Pydantic):   # §1
class DecisionRecord(Pydantic):        # §4
class AuditRecord(Pydantic):           # §6 (四重引用)
class MemoryPolicy(Pydantic):          # §3 (TTL/归档规则, 声明式)
```

## 12. 边界

```
✅ Core 冻结 (Communication/Decision/Audit 全 org.* Extension)
✅ 无重复模型 (复用 Event/Artifact/Approval/Experience/Knowledge)
✅ 全链可审计 (Who/Why/Basis/Result)
```

## 13. 结论

```
16C 定义 AI 企业操作系统的信息流: Communication + Event + Artifact + Decision + Memory
解决信息孤岛/决策不透明/经验不沉淀/沟通不可审计
为 Phase 17 (Planning 读记忆) 与 Phase 18 (Execution 产记忆) 提供神经系统基础
等待确认后进入实现 (16C-1: CommunicationRecord + org.communication.* 事件 + Memory 基础)
```
