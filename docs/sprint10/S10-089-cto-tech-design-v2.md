# CTO 技术架构 v2 — 基于 Claude 产品战略 (E1-E5)

> 日期: 2026-08-20 | 输入: Claude 产品战略 (s10-089) | 输出给 Codex
> 原则: 不堆功能; 信任优先 (证据+审批) → 交付 (积压清道夫) → 记忆护城河

---

## 0. 战略 → 技术映射

| Claude 战略 | 技术落点 | 复用现状 |
|---|---|---|
| E1 证据包系统 | EvidenceBundle 聚合 (diff+test+logs+依据) | S10-083 Observability + AuditEvent + artifacts |
| E2 人工审批 | 分级审批工作流 (角色/爆炸半径) | ApprovalGate + ConfirmationGate |
| E3 积压清道夫 | Workload Pack: repo_mode + issue 队列 + PR | 执行管线 + Delivery (S10-083) |
| E4 最小集成 | GitHub/Jira 适配器 (read/write) | MCP 真连 (Mock→真实) |
| E5 记忆闭环 | 审批决策 → Org Memory 回流 | LearningEngine + ExperienceStore |

## 1. 技术架构 (M1 目标: 证据包 + 审批 + 积压清道夫闭环)

```
GitHub/Jira (E4, MCP 真实连接)
  ↓
Workload Pack: Backlog Sweeper (E3)
  ├─ 拉取 issue 队列 → 分诊 (bug/依赖/补丁)
  ├─ 任务 → Execution Kernel (现有) → patch
  ├─ EvidenceBundle 组装 (E1):
  │    {diff, tests, logs, decisions, artifacts}
  ├─ ApprovalGate 分级审批 (E2):
  │    低风险 → 自动推荐; 高风险 → 人工必批
  └─ 批准 → 走客户 CI / PR
  ↓
Decision → Org Memory (E5, 回流)
```

## 2. Module 变化

| 模块 | 动作 | 内容 |
|---|---|---|
| `factory-console/session/evidence.py` | ★新增 | EvidenceBundle 组装 (diff+test+log+依据) |
| `factory-console/session/workloads/backlog_sweeper.py` | ★新增 | 积压清道夫负载包 (分诊/修复/证据/PR) |
| `factory-exec/exec/mcp.py` | 改造 | Mock → 真实 GitHub/Jira 连接 (E4) |
| `factory-exec/exec/approval.py` | 扩展 | 分级审批 (风险等级/角色) |
| `factory-console/memory/learning_engine.py` | 接线 | 审批决策 → 经验回流 (E5) |
| `factory-console/session/observability.py` | 扩展 | EvidenceBundle 视图 (CLI/API) |

## 3. 数据模型

```python
class EvidenceBundle:          # E1: 证据包 (产品面核心)
    bundle_id: str
    project_id: str
    task_id: str
    agent_id: str
    diff: str                  # patch 内容
    test_results: list[dict]   # 真实测试输出
    logs: list[dict]           # 执行日志 (时间/事件)
    decisions: list[dict]      # 为什么这么做 (决策链)
    artifacts: list[str]       # 产物引用
    created_at: str
    status: str                # pending/approved/rejected/applied

class ApprovalRequest:         # E2: 审批请求 (分级)
    request_id: str
    bundle_id: str
    risk_level: str            # low/medium/high (爆炸半径)
    required_roles: list[str]  # developer/tech_lead/compliance
    status: str
    decided_by: str
    decided_at: str
    decision: str              # approve/reject/modify
```

## 4. Event 设计 (复用 AuditEvent)

新增:
```
EVIDENCE_BUNDLE_CREATED   — 证据包组装完成
APPROVAL_REQUESTED        — 审批请求 (含 risk_level)
APPROVAL_DECIDED          — 审批决策 (approve/reject)
DECISION_LEARNED          — 决策回流记忆 (E5)
WORKLOAD_ITEM_CLAIMED     — 积压任务接单
WORKLOAD_ITEM_DELIVERED   — 积压任务交付 (含证据包)
```

## 5. API 设计

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/projects/{id}/evidence` | GET | 证据包列表 |
| `/api/evidence/{bundle_id}` | GET | 证据包详情 (diff/test/logs/decisions) |
| `/api/projects/{id}/approvals` | GET | 审批请求列表 |
| `/api/approvals/{id}/decide` | POST | 审批决策 (approve/reject/modify) |
| `/api/projects/{id}/workload` | POST | 触发积压清道夫 |
| `/api/workload/{run_id}` | GET | 负载运行状态 |

## 6. CLI 设计

```
factory evidence list [--project X]       — 证据包列表
factory evidence show <bundle_id>         — 证据包详情 (diff/test/logs)
factory approval list [--project X]       — 待审批
factory approval decide <id> approve|reject — 审批
factory workload backlog [--project X]    — 触发积压清道夫
factory workload status <run_id>          — 负载运行状态
```

## 7. Agent 设计

```
BacklogSweeper 工作流角色 (复用 Exec 内核):
  Triage → Implementer(现有 DeveloperAgent) → Reviewer(Evaluator) → QA

证据包组装: 执行链每步 emit 事件 → evidence.py 聚合 → bundle
审批: 风险分级 (文件影响数/敏感路径/新增依赖 → low/med/high)
```

## 8. Workflow 设计

```
Backlog Sweeper 闭环:
  issue 拉取 → 分诊 → 任务 → 执行 → 证据包 → 审批
  → 批准 → apply/PR → 决策回流记忆 → 下一个 issue
```

## 9. 风险分析

| 风险 | 等级 | 缓解 |
|---|---|---|
| GitHub/Jira 真实连接 (token 安全) | 高 | env token + 只读默认 + 审批后才写 |
| 证据包变"日志堆积" | 中 | 结构化的 decisions 链 + 测试摘要 (非全量日志) |
| 审批流复杂化 | 中 | 先做 binary approve/reject, 分级后置 |
| 又堆功能 | 高 | 冻结: 仅 E1+E2+E3 (证据/审批/积压) |

## 10. Sprint 拆解 (Codex)

| Sprint | 内容 | 验收 |
|---|---|---|
| **M1a** | EvidenceBundle + 分级审批 (E1+E2) | `factory evidence show` 显示 diff+测试+决策 |
| **M1b** | 积压清道夫 v1 (E3, 本地 repo 模式) | `factory workload backlog` 修一个真实 issue + 证据包 |
| **M1c** | 决策回流记忆 (E5) | 审批 reject → 经验沉淀 → 下次任务引用 |
| **M2** | GitHub/Jira 真实连接 (E4) | 从真实仓库拉 issue + 出 PR |

---

**交付 Codex 顺序**: M1a (证据包+审批) → M1b (积压清道夫) → M1c (记忆回流) → M2 (集成)。
