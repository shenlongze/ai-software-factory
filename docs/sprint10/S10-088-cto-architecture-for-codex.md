# AI Factory 下一阶段技术架构设计 (CTO → Codex)

> 日期: 2026-08-20 | 输入: MASTER-PLAN v3 (M1-M2) + 体检报告 + S10-087
> 原则: 不堆功能; 真实执行 / 可观察 / 可恢复 / 可审计

---

## 1. 技术架构设计

### 目标状态 (M1+M2 后)

```
User (CLI/Web/REPL)
  ↓
Human Console (CLI/API/Web) — 现有, 复用
  ↓
Intelligence Layer (Planning/Routing/Learning/Repair)
  ↓
Organization Layer ★新增: AgentEntity + Registry + 装配器 + HandoffBus
  ├── PM Agent ──→ 资产 (market/competitive/prd)
  ├── Architect ──→ architecture.md
  ├── Backend/Frontend/QA ──→ 执行链
  ↓
Execution Kernel (现有: AgentRuntime/DeveloperAgent/ExecutionLoop/Evaluator)
  ↓
Tools ★扩展: MCP 真实连接 + repo_mode
  ↓
Workspace/Repo (真实代码落地)
```

### 分层原则

- **Organization Layer 薄**: 不复制执行逻辑; 只做角色实体/装配/交接/共识
- **Execution Kernel 不动**: 单 Agent 执行链已验证真实, 保留
- **新增最小**: AgentEntity + Registry + 装配器 + HandoffBus + 真实工具适配器

## 2. Module 变化

| 模块 | 动作 | 内容 |
|---|---|---|
| `factory-org/org/agent_entity.py` | ★新增 | AgentEntity(角色实体: role/skill/memory/state) |
| `factory-org/org/agent_registry.py` | ★新增 | 注册表(创建/查询/实例化) |
| `factory-org/org/assembler.py` | ★新增 | 专家装配器(按角色装配 LLM+Skill+Tools+Memory) |
| `factory-org/org/handoff_bus.py` | ★新增 | 角色间交接总线(事件驱动) |
| `factory-exec/exec/mcp.py` | 改造 | Mock → 真实连接(stdio/http, 1-2 个真实工具) |
| `factory-console/session/actions.py` | 扩展 | team_execute 接入 HandoffBus |
| 其余 | 不动 | Core/Console/Extension 保留 |

## 3. 数据模型变化

```python
class AgentEntity:            # 角色实体 (工厂层)
    agent_id: str             # pm-1 / backend-1
    role: str                 # pm/market/competitive/ux/architect/backend/frontend/qa
    llm_provider: str         # 装配的 provider
    skills: list[str]
    memory_scope: str         # 该角色记忆命名空间
    state: str                # idle/busy/done/failed
    created_at / updated_at

class HandoffRecord:          # 交接记录 (事件源)
    handoff_id: str
    from_agent: str
    to_agent: str
    artifact_ref: str         # 交接资产 (prd.md → architect)
    decision: str             # 共识/决策摘要
    timestamp: str

# 资产链 (复用现有 project_dir 文件系统, 不新库):
# projects/{id}/discovery.md / market_analysis.md / competitive_analysis.md
#               /prd.md / architecture.md / tasks.json (现有)
```

## 4. Event 设计

新增事件类型(复用 AuditEvent 20+ 字段):

```
AGENT_CREATED        — 角色实体装配完成
AGENT_ACTIVATED      — 角色开始工作 (含 llm_provider/model)
HANDOFF_PASSED       — 角色 A → B 交接 (artifact_ref)
ARTIFACT_CREATED     — 已有 (资产落盘)
ARTIFACT_CONSUMED    — 角色 B 消费资产 A 产出 (血缘)
DECISION_RECORDED    — 角色决策 (为什么这么做)
AGENT_FAILED         — 角色失败 (含原因)
```

血缘链: PRD → (ARTIFACT_CREATED) → Architect 消费 (ARTIFACT_CONSUMED) → architecture.md → ...

## 5. API 设计

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/agents` | GET | 角色实体列表 |
| `/api/agents/{id}` | GET | 角色详情 (role/skills/state) |
| `/api/projects/{id}/handoffs` | GET | 交接记录 (时间线) |
| `/api/projects/{id}/assets` | GET | 资产链 (discovery→market→prd→arch→tasks) |
| `/api/projects/{id}/team/analyze` | POST | 触发多角色分析 (PM→Market→Competitive→PRD) |

## 6. CLI 设计

```
factory team status                  — 角色/状态/当前任务
factory team analyze [--project X]   — 触发多角色分析链 (CLI 版 /api/team/analyze)
factory asset tree [--project X]     — 资产链树状展示
factory asset show <name> [--project X]  — 查看单个资产 (prd/market/...)
factory handoff list [--project X]   — 交接历史
```

## 7. Agent 设计

```
AgentEntity (工厂层, 薄) 
  ├─ 装配: llm_provider (Router 选择) + skills (能力匹配) + memory_scope
  ├─ 执行: 委托 Execution Kernel (现有 DeveloperAgent 链) — 不复制
  ├─ 产出: 资产文件 (md/json) + ARTIFACT_CREATED 事件
  └─ 交接: HandoffBus.publish(next_agent, artifact_ref, decision)

角色最小集 (M2): PM → Market → Competitive → Architect → Backend/Frontend → QA
每角色独立资产 + 互引 (prd.md 引 market/competitive 结论)
```

## 8. Workflow 设计

```
分析链 (M2):
  PM.analyze(discovery) → market_analysis.md + competitive_analysis.md + prd.md
  → [用户审批门] → Project Creation
  → Architect.consume(prd) → architecture.md
  → EngineeringPlan (tasks.json 现有) → Backend/Frontend 执行

执行链 (M1, 现有增强):
  Task → AgentRuntime → LLM → patch → Delivery 管线 (S10-083) → repo 落地
```

## 9. 风险分析

| 风险 | 等级 | 缓解 |
|---|---|---|
| 多 Agent 变"多段单模型" (名义协作) | 高 | HandoffBus 强制资产交接 + ARTIFACT_CONSUMED 血缘 |
| LLM patch 编码问题 (中文乱码) | 高 | M1 repo_mode 先验证真实落地; 失败即暴露 |
| MCP 真实连接的安全面 | 中 | 白名单工具 + 审批门 |
| 项目骨架缺失 (LLM 无代码可写) | 高 | repo_mode: 空项目先生成骨架 (main/requirements/tests) |
| 范围蔓延 (又堆功能) | 中 | 冻结: 仅 M1+M2 允许 |

## 10. Sprint 拆解 (Codex 实现单元)

| Sprint | 内容 | 验收 (Codex 完成标准) |
|---|---|---|
| **M1** (v1.1.5) | repo_mode + 真实工具发现 + 执行循环接线 | `factory repo <dir>` 对现有仓库改一个文件 + 测试绿 |
| **M2** (v1.1.6) | AgentEntity/Registry/装配器/HandoffBus/7角色 | "让PM分析" 走真 Agent 链; prd.md 引 market 结论 |
| **M3** (v1.1.7) | PRD 深度 + 需求变更 + 审批 | 执行中"加导出"→ PRD v2 + 新任务 |

---

**交付 Codex 的实现顺序**: M1 (repo_mode → MCP 真连 → 执行接线) → M2 (AgentEntity → HandoffBus → 7 角色)。
