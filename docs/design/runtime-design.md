# AI Software Factory — Runtime 设计

> 版本: v1.0 | 状态: 设计稿 | 关联文档: [architecture.md](./architecture.md)
>
> 本文档定义 Factory Runtime 的运行细节:数据流、事件驱动、Dashboard、数据模型、扩展点。设计原则:KISS、数据驱动、可落地。

---

## 1. 模块间数据流

### 1.1 总览

```
                控制流(直接调用,同步)                   信息流(事件,异步)
   ┌────────────┐  定义/审批  ┌──────────────┐         ┌─────────────────┐
   │    PO      │───────────▶│ Orchestrator │         │                 │
   └────────────┘            └──────┬───────┘         │                 │
        ▲           验收/挡板上报    │                 │                 │
        └────────────────────────────┼─────────────────┤                 │
                                     ▼                 ▼                 ▼
   ┌──────────────┐  分配  ┌──────────────┐  事件  ┌───────────────────────────┐
   │Task Manager  │───────▶│Agent Registry│──────▶│                           │
   └──────┬───────┘        └──────┬───────┘        │       Event Logger       │
          │                       │ 实例化          │   (append-only 事件总线)  │
          │                       ▼                 │                           │
          │              ┌──────────────┐  调用     │   ◀── 所有模块发布事件 ──  │
          │              │    Agent     │──────────▶│   ──▶ 查询/回放/投影 ──▶  │
          │              └──────┬───────┘           │         │        │       │
          │                     │ 产物/自报告        └─────────┼────────┼───────┘
          ▼                     ▼                             ▼        ▼
   ┌──────────────┐     ┌──────────────┐              ┌────────┐  ┌──────────┐
   │Workflow Engine│◀───▶│  Validation  │              │Knowledge│ │Dashboard │
   │ (流程/闸门/锁) │     │    Engine    │              │  Base   │ │ (只读)   │
   └──────────────┘     └──────────────┘              └────────┘  └──────────┘
```

**两条通道的纪律:**
1. **控制流(同步调用)**:Orchestrator → Task Manager → Agent Registry → Agent;Workflow Engine → Validation Engine。方向固定,用于"下达指令"。
2. **信息流(事件,异步)**:任何模块的**状态变化**只做一件事——向 Event Logger 发布事件。**模块之间不互相读状态,状态一律从事件流投影(projection)得到。** 这条纪律保证可回放、可恢复、可观测。

### 1.2 关键路径一:一次任务委派(主链路)

```
1.  Orchestrator    定义 Task(task_id, 角色, 验收标准, Allowed/Forbidden 文件)
2.  Task Manager    task_id: pending ──▶ assigned(发事件 task.assigned)
3.  Task Manager    向 Agent Registry 请求可用 Agent(按角色)
4.  Agent Registry  实例化/复用 Agent,绑定角色 Skill(发事件 agent.started)
5.  Agent           执行(每一步动作发事件 agent.action)
6.  Agent           自报告完成(发事件 task.reported)
7.  Workflow Engine 触发验证门(双验证):
    Validation Engine 执行独立校验(范围核对/测试/diff),产出证据
    (发事件 validation.started / validation.passed | failed)
8.  Task Manager    根据验证结论: verifying ──▶ done | failed(发事件)
9.  Orchestrator    收到完成事件 + 验证结论 → 批准 | 返工 | 上报 PO(挡板时)
10. Event Logger    全程落库;Dashboard 实时投影显示
```

### 1.3 关键路径二:截断续跑(恢复链路)

```
1.  事件流按 task_id 回放 → 重建任务状态(不依赖对话记忆)
2.  Task Manager   取最近 checkpoint(任务 + 上下文引用 + 已完成步骤)
3.  决策:未完成步骤 → 重新委派(复用 Agent 或新 Agent)
4.  前置检查:git 状态与 checkpoint 一致?(不盲目 checkout)
5.  从 checkpoint 续跑,继续发事件;中断点之前的动作不重放
```

### 1.4 关键路径三:挡板暂停

```
1.  事件流中出现挡板信号(产品冲突/架构变更/Scope 扩展)
    —— 由 Workflow Engine 的挡板监听器识别,或 PO 主动触发
2.  Orchestrator  冻结相关任务(发事件 task.blocked)
3.  上报 PO:附事件证据链(谁、何时、改了什么、为什么触发)
4.  PO 决策 → resume(继续/调整) | abort(终止) | rework(返工)
5.  Task Manager 按决策迁移状态(发事件 task.resumed / task.cancelled)
```

---

## 2. 事件驱动设计(Event Logger 核心)

### 2.1 设计原则

| 原则 | 说明 |
|---|---|
| **append-only** | 事件只追加、不修改、不删除;错误以"新事件"纠正,如 `task.corrected` |
| **事件即事实** | 系统状态 = 事件流投影;任何时刻可从头回放重建 |
| **事件有来源** | 每个事件带 `source`(模块)与 `agent_id`(若非系统事件),支撑审计与指标 |
| **指标从事件算** | 不另建统计表;first_attempt_success / path_errors / human_intervention 全部由事件聚合得出 |

### 2.2 事件分类(最小集)

| 类别 | 事件 | 触发方 | 载荷要点 |
|---|---|---|---|
| 任务 | `task.created` / `task.assigned` / `task.reported` / `task.completed` / `task.failed` / `task.blocked` / `task.resumed` / `task.cancelled` | Task Manager / Agent | task_id, 状态, 原因 |
| Agent | `agent.started` / `agent.action` / `agent.summary` / `agent.stopped` | Agent Registry / Agent | agent_id, 角色, 动作, 文件 |
| 验证 | `validation.started` / `validation.passed` / `validation.failed` / `validation.blocked`(越权拦截) | Validation Engine | task_id, 结论, 证据引用 |
| 工作流 | `workflow.gate_opened` / `workflow.gate_passed` / `workflow.gate_blocked` / `workflow.lock_acquired` / `workflow.lock_released` | Workflow Engine | 流程名, 闸口, 锁资源 |
| 系统 | `system.checkpoint` / `system.interrupted` / `system.resumed` / `system.metric` | 任意模块 | checkpoint 引用, 指标键值 |
| 人工 | `human.review_requested` / `human.decision` / `human.intervention` | Orchestrator | 挡板类型, PO 决策 |

> 事件 = `(event_id, timestamp, type, source, agent_id?, task_id?, payload)`,完整结构见 §4.3。

### 2.3 事件生命周期

```
产生(模块发布) → 校验(必填字段) → 持久化(append) → 分发(订阅者) → 投影(状态重建) → 聚合(指标) → 归档(沉淀进 Knowledge Base)
```

1. **持久化**:顺序写、带序号(seq);每事件一个 `seq`,支持按 `(project, task_id)` 索引。
2. **分发**:订阅者模式——Dashboard 投影、Knowledge Base 沉淀、Workflow Engine 挡板监听、Orchestrator 决策。
3. **投影**:`projection(event_stream) → 当前状态快照`,纯函数,可随时重放。
4. **聚合**:按时间窗/任务/角色聚合出指标:
   - `first_attempt_success` = 任务在无 failed 验证情况下首次 completed 的比例
   - `path_errors` = `validation.blocked`(越权文件操作)计数
   - `human_intervention` = `human.*` 事件计数(挡板频率)
   - `task_truncation_rate` = `system.interrupted` / 任务数(截断频率,治理截断续跑)

### 2.4 回放与恢复

- **回放**:`replay(project_id, since_seq)` 重建任意历史状态,用于审计与复盘。
- **恢复**:`restore(task_id)` = 回放该任务事件 → 找最近 `system.checkpoint` → 从断点续跑。
- **一致性校验**:恢复前比较"checkpoint 记录的文件哈希/git 状态"与当前实际,不一致则以校验结果为准(不盲目 checkout)。

---

## 3. 可观测性:Factory Dashboard 设计

### 3.1 设计约束

- **只读投影**:Dashboard 不写任何状态,全部数据来自 Event Logger 查询;崩溃/重启后重放事件即可重建。
- **一个页面回答六个问题**:项目在做什么 / 每个任务什么状态 / 谁在做 / 卡在哪 / 进展如何 / 下一步是什么。

### 3.2 视图规格

#### 视图 1:Project 总览

| 列 | 说明 | 数据来源(事件) |
|---|---|---|
| Project | 项目名/ID | — |
| Active Tasks | 进行中任务数 | `task.assigned` − `task.completed` − `task.cancelled` |
| Blocked Tasks | 阻塞任务数 | `task.blocked` 未 `task.resumed` |
| Agents Running | 运行中 Agent 数 | `agent.started` − `agent.stopped` |
| 里程碑进度 | 里程碑 X 完成度 | 关联任务 completed / 总数 |
| 质量指标 | first_attempt_success / path_errors / human_intervention / 截断率 | 事件聚合(§2.3) |
| 最近事件 | 最新 10 条 | `recent_events(project_id, 10)` |

#### 视图 2:Task 列表(每任务一行)

| 列 | 说明 |
|---|---|
| Task ID | 全局唯一 |
| 状态 | pending / assigned / running / verifying / done / blocked / failed |
| 角色 | 负责角色(dev / test / architect / debugger / pm / release) |
| 进度 | 已完成步骤/总步骤(checkpoint 序列推进) |
| 当前动作 | 最新 `agent.action` 简述(如 "run tests", "patch editor_page.dart") |
| 上次事件 | 最新事件类型 + 时间 |
| 下一步 | 由 Workflow Engine 状态机给出(如 "等待验证", "等待 PO 批准") |
| 风险标记 | 截断次数 ≥ 阈值、验证失败 ≥ 2 次、越权拦截 > 0 |

#### 视图 3:Agent 面板

| 列 | 说明 |
|---|---|
| Agent ID / 角色 | 实例身份 |
| 当前任务 | 正在执行的任务 |
| 当前动作 | 最新动作(实时) |
| 已用工具调用数 / 上限 | 防截断预警(接近上限 → 黄色) |
| 历史指标 | 该 Agent 的 first_attempt_success / path_errors |

#### 视图 4:时间线(回放视图)

- 按 `seq` 展示事件流,可跳转到任意 `system.checkpoint` 查看当时快照。
- 用于:截断续跑定位、挡板原因追溯、审计。

### 3.3 更新机制

- Dashboard = Event Logger 的**投影订阅者**:事件落库即增量更新对应视图(或 1–2s 批量刷新),不做轮询扫描。

---

## 4. 数据模型(最小结构)

> 全部为 JSON 友好的记录结构;仅 Event 表必需(append-only),其余为投影/派生,可惰性生成。

### 4.1 Task

```jsonc
{
  "task_id": "T-042",                // 全局唯一
  "project_id": "P-markpad",
  "parent_id": null,                 // 子任务归属(任务拆分)
  "title": "实现 Block Editor 的撤销/重做",
  "role": "dev",                     // 负责角色,见 §5.1 角色注册
  "status": "verifying",             // pending|assigned|running|verifying|done|blocked|failed
  "dependencies": ["T-038"],         // 依赖任务(排序/并行判断)
  "scope": {                         // 文件范围声明(实证:Allowed/Forbidden)
    "allowed": ["lib/editor/block_editor/**"],
    "forbidden": ["lib/editor/editor_page.dart", "pubspec.yaml"]
  },
  "acceptance": ["撤销后光标位置正确", "新写测试通过"],   // 验收标准
  "checkpoints": ["chk-041-3"],      // 断点引用列表,最近者优先续跑
  "attempts": 2,                     // 委派次数(含返工)
  "metrics": { "tool_calls": 47, "interrupted": true },
  "created_at": "…", "updated_at": "…"
}
```

**KISS 要点**:`status` 为**派生字段**(由事件流投影),`checkpoints` 与 `metrics` 亦为投影聚合;Task 记录本身只保存定义性数据(角色/范围/验收/依赖)。

### 4.2 Agent

```jsonc
{
  "agent_id": "A-012",
  "role": "debugger",                // 角色
  "skills": [{"name": "systematic-debugging", "version": "2.1"}],  // 版本化绑定
  "status": "running",               // idle|running|blocked|stopped
  "current_task_id": "T-042",
  "tool_call_count": 47,             // 本轮上限控制
  "tool_call_limit": 60,             // 防截断预警
  "stats": {                         // 跨任务统计(事件聚合)
    "tasks_done": 5,
    "first_attempt_success": 0.8,
    "path_errors": 1
  },
  "created_at": "…", "last_seen_at": "…"
}
```

### 4.3 Event(唯一强制持久化)

```jsonc
{
  "event_id": "E-10086",
  "seq": 10086,                      // 全局单调递增,回放锚点
  "timestamp": "2026-08-05T10:00:00Z",
  "type": "validation.failed",       // 见 §2.2 事件分类
  "source": "validation_engine",     // 发布模块
  "agent_id": "A-012",               // 可选:若与 Agent 相关
  "task_id": "T-042",                // 可选:若与任务相关
  "payload": {                       // 类型相关载荷
    "reason": "越权写入 editor_page.dart",
    "evidence": "ref://artifacts/T-042/val-3.log"
  }
}
```

### 4.4 Knowledge(沉淀层,由事件自动生成)

```jsonc
// 类型一:决策记录(ADR)—— 由 workflow.gate_* + human.decision 生成
{
  "knowledge_id": "K-ADR-017",
  "type": "adr",
  "title": "撤销/重做采用命令模式而非快照",
  "task_id": "T-042",
  "decision": "命令模式,栈上限 100",
  "rationale": "快照内存开销大,且需深拷贝",
  "events": ["E-10020", "E-10021"],   // 证据链,可回放
  "created_at": "…"
}

// 类型二:缺陷记录 —— 由 validation.failed + 修复事件生成
{
  "knowledge_id": "K-BUG-003",
  "type": "bug",
  "title": "撤销后光标位置偏移",
  "severity": "high",
  "task_id": "T-045",
  "events": ["E-10090", "E-10095"],
  "status": "open"                   // open|fixed|wontfix
}

// 类型三:会话轨迹 —— 由全量事件按 project 归档,提供检索
{
  "knowledge_id": "K-SES-007",
  "type": "session",
  "project_id": "P-markpad",
  "task_ids": ["T-041", "T-042"],
  "period": ["2026-08-04", "2026-08-05"],
  "events": "ref://events/P-markpad/2026-08-05.log"
}
```

**KISS 要点**:Knowledge 不保存对话原文,只保存"事件引用 + 结构化字段",需要详情时回放事件。

---

## 5. 扩展点

> 三个扩展点对应三种最常见的定制需求:新角色、新 Skill、新工作流。全部采用**声明式注册 + 事件驱动**,不改核心代码。

### 5.1 新增角色

**接口:角色注册表(声明式)**

```jsonc
// roles/<role>.json
{
  "role": "security-auditor",
  "display_name": "安全审计工程师",
  "default_skills": ["codebase-inspection", "systematic-debugging"],  // 默认装配
  "allowed_tasks": ["audit", "review"],
  "scope_policy": "readonly",        // readonly | restricted | full —— 决定文件范围默认值
  "report_format": "summary",        // Agent 自报告的格式要求
  "exit_criteria": ["must pass validation gate"]   // 任务完成的强制条件
}
```

**接入流程**:放入 `roles/` 目录 → 注册表校验 → Agent Registry 可实例化该角色 → Orchestrator 的委派指令中引用 `role: "security-auditor"` 即生效。**零代码改动**。

### 5.2 新增 Skill

**接口:Skill 注册表(声明式)**

```jsonc
// skills/<skill-name>/SKILL.md  +  skills/<skill-name>/meta.json
{
  "name": "systematic-debugging",
  "version": "2.1",                  // 版本化,任务归档时记录所用版本
  "roles": ["debugger", "dev", "test"],      // 适用角色(与角色注册表双向校验)
  "trigger": "task.type == 'debug'",         // 可选:自动装配触发条件
  "entry_points": ["run_repro", "bisect"],
  "requires": ["python3", "git"]             // 运行环境依赖
}
```

**接入流程**:放入 `skills/` → 注册表校验(角色引用完整性)→ Skill Registry 按角色装配或按触发条件自动附加。**零代码改动**。

### 5.3 新增工作流

**接口:流程定义(声明式状态机)**

```jsonc
// workflows/<name>.json —— 例:标准交付流程
{
  "name": "feature-delivery",
  "states": ["spec", "design", "review", "approve", "implement", "verify", "done"],
  "start": "spec",
  "transitions": [
    { "from": "design", "to": "review", "on": "task.reported", "guard": "role == 'architect'" },
    { "from": "review", "to": "approve", "on": "validation.passed", "guard": "reviewer != implementer" },
    { "from": "approve", "to": "implement", "on": "human.decision", "guard": "decision == 'approve'" },
    { "from": "implement", "to": "verify", "on": "task.reported" },
    { "from": "verify", "to": "done", "on": "validation.passed" },
    { "from": "verify", "to": "implement", "on": "validation.failed" }   // 返工回路
  ],
  "gates": [
    { "name": "三挡板", "on_event": ["human.decision", "gate:conflict|architecture|scope"], "action": "pause" }
  ],
  "locks": [
    { "resource": "editor_page.dart", "serialize": true }   // 关键文件串行锁
  ]
}
```

**接入流程**:放入 `workflows/` → Workflow Engine 校验(状态可达性、守卫可解析)→ 项目创建时选择流程名即生效。**零代码改动**。

### 5.4 扩展纪律(三个扩展点的共同约定)

1. **声明式优先**:角色/Skill/流程都是数据,不是代码;新扩展 = 新增一份 JSON/Markdown。
2. **事件驱动**:扩展只"监听事件 + 发事件",不修改其他模块的内部状态。
3. **版本化**:Skill/流程有版本;任务归档记录所用版本,保证复现。
4. **校验先行**:注册时校验完整性(角色↔Skill 双向引用、流程状态可达、守卫表达式可解析),校验失败拒绝注册并出 `validation.blocked` 事件。

---

## 6. 落地建议(最小可运行版本)

按 KISS 原则,MVP 只需 4 件东西:

1. **Event Logger**:一个 append-only 事件文件(或表)+ 订阅分发。
2. **Task 记录**:`tasks/<task_id>.json`(定义性数据),状态由事件投影。
3. **三份注册表**:`roles/`、`skills/`、`workflows/` 三个目录 + 校验脚本。
4. **Dashboard**:一个读事件文件的只读页面。

先落地"事件驱动 + 断点续传 + 越权拦截",即可解决实证中最高频的三个问题(截断、自报告不可信、无观测);Dashboard 与指标在事件流成型后自然获得。
