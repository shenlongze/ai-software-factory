# AI Software Factory — 架构文档(Python 技术栈落地)

> 版本: v1.0 | 状态: 工程化落地版 | 关联文档: [design/architecture.md](./design/architecture.md)(设计稿)· [design/runtime-design.md](./design/runtime-design.md)(运行设计)
>
> 本文档是**实现依据**:设计稿定义"是什么",本文档定义"用 Python 怎么落地"。原则不变:KISS、事件驱动、可断点续传、验证独立。技术栈固定为 Python 3.12+ / Pydantic / SQLite / Typer / Rich / FastAPI,不做微服务、不做 Kubernetes、不做复杂前端。

---

## 1. 总体架构

```
┌──────────────────┬────────────────────┬────────────────────┐
│  CLI (Typer)     │  Dashboard         │  API (FastAPI)     │  入口层
│  工程师主入口      │  Rich 表格 / MD 导出 │  P2,未来自动化触发  │  (三种形态,
│  factory task/   │  (只读投影)         │  GitHub Issue →    │   同一 core)
│  workflow/logs   │                    │  API → 任务        │
└────────┬─────────┴─────────┬──────────┴─────────┬──────────┘
         │ 命令(写)           │ 查询(只读)          │ HTTP(读写)
         ▼                   ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    Factory Core (factory_core 包)            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Orchestrator(决策) —— 第一版 = CLI 人工决策循环;         │  │
│  │ P1 可选 LLM 驱动(决策模块,不写代码)                      │  │
│  └──────┬────────────────────────────────────────────────┘  │
│  ┌──────▼───────┐ ┌──────────────┐ ┌────────────────────┐  │
│  │ Task Manager │ │Workflow Engine│ │  Validation Engine │  │
│  │ 状态机/拆解/   │ │ 流程/闸口/锁   │ │ 范围校验/测试/diff  │  │
│  │ checkpoint   │ │ (声明式 JSON)  │ │ (独立于 Agent)      │  │
│  └──────┬───────┘ └──────┬───────┘ └────────┬───────────┘  │
│  ┌──────▼───────┐ ┌──────▼───────┐ ┌────────▼───────────┐  │
│  │Agent Registry│ │Skill Registry│ │   MCP Manager      │  │
│  │ 角色/实例/统计 │ │ 版本/角色装配  │ │ 工具清单/连接(懒)    │  │
│  └──────┬───────┘ └──────────────┘ └────────────────────┘  │
│  ┌──────▼───────────────────────────────────────────────┐  │
│  │ Event Logger(SQLite, append-only)                    │  │
│  │ 唯一事实源 ← 所有模块发布事件;提供投影/回放/聚合          │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Knowledge System(订阅事件 → 自动沉淀 ADR/Bug/会话)      │  │
│  └───────────────────────────────────────────────────────┘  │
└────────┬────────────────────────────────────────────────────┘
         │ Runtime Adapter 接口(协议,唯一执行出口)
         ▼
┌─────────────────────────────────────────────────────────────┐
│              runtimes/(Adapter 实现,可插拔)                  │
│    Hermes Adapter │ Claude Code │ LangGraph │ OpenHands ... │
│    (启动外部 Agent 进程,注入委派指令 + 文件范围 + 工具上限)      │
└────────┬────────────────────────────────────────────────────┘
         │ 执行
         ▼
┌─────────────────────────────────────────────────────────────┐
│   Agents(角色实例,装配 Skills) ──▶ Tools                     │  执行层
│   执行任务 → 自报告;Tools = MCP 工具 / 文件操作 / git / 命令   │
└─────────────────────────────────────────────────────────────┘
```

**分层纪律(落地版)**:

1. **入口层只有 3 个进程形态**:CLI(P0)、Dashboard(P1,CLI 内嵌 + Markdown 导出)、API(P2)。三者全部通过 `factory_core` 的公开 API 工作,**不直接碰 SQLite 以外的任何东西**。
2. **Factory Core 是唯一进程内主体**:单进程运行,8 个逻辑模块 + 1 个决策入口。模块之间**只通过两条通道交互**——控制流(直接调用,上游→下游)与事件流(Event Logger)。任何模块不得直接修改其他模块的内部状态。
3. **执行统一走 Runtime Adapter**:core 不直接调用任何 LLM/Agent 框架;Agent 执行、验证命令执行、MCP 工具调用都经过各自的 Adapter/引擎封装。换 Runtime = 换 Adapter,core 零改动。
4. **数据只有一份**:所有持久化收敛到单个 SQLite 文件(事件 + 定义性数据),项目文件(源码工作区)属于 Agent 执行器的 git 仓库,Factory 不直接改它。

---

## 2. 模块划分与职责

### 2.1 factory_core 包内 8 个核心模块

| 模块 | 文件 | 职责 | 关键输出 |
|---|---|---|---|
| **Task Manager** | `task_manager.py` | 任务生命周期:拆解、分配、状态迁移、checkpoint、依赖排序 | 任务状态机 `pending→assigned→running→verifying→done\|blocked\|failed`;每个 checkpoint 一条 `system.checkpoint` 事件 |
| **Workflow Engine** | `workflow_engine.py` | 执行声明式流程:决策门、三挡板监听、关键资源串行锁 | 闸口决定(继续/暂停/返回)、锁的获取/释放;挡板命中 → `task.blocked` + 上报 |
| **Agent Registry** | `agent_registry.py` | 按角色实例化/复用 Agent;记录身份、Skill 绑定、运行统计 | 全局唯一 agent_id;指标 first_attempt_success / path_errors / human_intervention |
| **Skill Registry** | `skill_registry.py` | 扫描/校验 Skill 元数据;按角色装配;版本快照归档 | 角色→Skill 清单;任务归档时记录所用 Skill 版本 |
| **MCP Manager** | `mcp_manager.py` | 管理 MCP 工具:注册、校验、懒连接、调用转发 | 工具清单(名称/参数 schema);Agent 运行时注入可用工具 |
| **Knowledge System** | `knowledge_system.py` | 订阅事件流,按规则自动生成 ADR / Bug / 会话沉淀 | `knowledge/` Markdown + `knowledge` 表;人工只补充判断 |
| **Validation Engine** | `validation_engine.py` | 独立验证:验收标准检查、文件范围核对、测试执行、diff 审计 | pass/fail/偏差 + 证据链(命令输出、diff、测试报告);越权 → `validation.blocked` |
| **Event Logger** | `event_logger.py` | append-only 事件存储 + 进程内订阅分发 + 投影/回放/聚合 | `events` 表(唯一强制持久化);replay()/project()/metrics() |

### 2.2 决策入口:Orchestrator(第一版由 CLI 承载)

- **第一版(P0)**:Orchestrator 逻辑 = CLI 的人工决策循环。用户即决策者:拆解任务、审批、验收、挡板裁决,通过 `factory task create / approve / reject / resume` 等命令操作。core 提供决策所需的全部只读视图(任务状态、验证结论、事件证据链),不写代码、不碰文件。
- **P1(可选)**:`orchestrator.py` 用 LLM 驱动同样一组决策接口(输入:目标+事件流;输出:任务定义+批准/驳回),与 CLI 可互换。**决策接口先定好,Orchestrator 是人还是 LLM 只是同一个接口的两个实现。**

---

## 3. 技术选型落地(每模块用什么)

| 模块 | 选型 | 说明(为什么) |
|---|---|---|
| 全包模型层 | **Pydantic v2** | 所有领域对象(Event/Task/Agent/Role/Skill/WorkflowDef)都是 Pydantic 模型;校验即注册校验,进 SQLite 前先过模型 |
| Event Logger | **标准库 `sqlite3` + 内存订阅者列表** | 事件就是单表 insert;不引 SQLAlchemy/ORM(对 append-only 事件流是过度设计)。`seq` 用 `INTEGER PRIMARY KEY AUTOINCREMENT` 天然单调递增 |
| Task Manager | Pydantic + `tasks` 表(定义性数据) | 状态**不落表**,由事件投影得出;表里只存 role/scope/acceptance/dependencies |
| Workflow Engine | **声明式 JSON + 自写轻量状态机(~100 行)** | 不引 BPM 引擎(如 Spiff/Zeebe);transitions 表驱动 + guard 用简单表达式字符串(`role == 'architect'`),P1 再考虑解析器 |
| Agent Registry | Pydantic + SQLite `agents` 表 | 统计字段不落表,由事件聚合;表里只存身份与定义 |
| Skill Registry | **目录扫描 + meta.json 校验** | Skill 即 `skills/<name>/SKILL.md + meta.json`,注册 = 扫描目录;版本在 meta 里 |
| MCP Manager | **subprocess/httpx + JSON-RPC**(stdio / SSE) | 懒连接:首次调用工具才拉起进程;工具清单 JSON 声明参数 schema |
| Knowledge System | 事件订阅 + **Jinja2 模板** | 事件 → 模板 → `knowledge/` Markdown;结构化字段同时写 `knowledge` 表 |
| Validation Engine | subprocess + 规则 JSON | 规则(范围/必测项)是数据不是代码;证据落 `validation/artifacts/` |
| CLI | **Typer + Rich** | Typer 生成参数解析与帮助;Rich 渲染表格/进度/时间线 |
| Dashboard | **Rich Table + Markdown 导出** | 无状态只读:读 Event Logger 投影;`factory dashboard` 终端渲染,`factory dashboard --md` 导出文件 |
| API | **FastAPI + Pydantic**(P2) | 同一 `factory_core` 库,单进程内提供 HTTP 入口;不做独立服务 |
| 依赖管理 | `pyproject.toml` + pip | 第三方依赖最小集:typer, rich, pydantic, fastapi, uvicorn, jinja2 |

**依赖原则**:能用标准库就不用第三方;能用数据(JSON/Markdown)就不用代码;能单进程就不起服务。

---

## 4. 目录结构说明

```
ai-software-factory/
├── pyproject.toml           # 包定义 + 依赖(typer/rich/pydantic/fastapi/jinja2)
├── README.md
├── docs/                    # 文档
│   ├── design/              #   设计稿(抽象层,只读参考)
│   └── architecture.md      #   本文档(工程化落地依据)
│
├── factory-core/            # ★ 唯一 Python 包 factory_core,全部核心逻辑
│   ├── __init__.py          #   公开 API 出口(入口层只 import 这里)
│   ├── event_logger.py      #   Event Logger + 订阅分发 + replay/project/metrics
│   ├── task_manager.py      #   Task 状态机 / checkpoint
│   ├── workflow_engine.py   #   流程状态机 / 闸口 / 锁
│   ├── agent_registry.py    #   Agent 实例注册 / 角色装配
│   ├── skill_registry.py    #   Skill 扫描 / 版本 / 角色绑定
│   ├── mcp_manager.py       #   MCP 工具管理 / 懒连接
│   ├── knowledge_system.py  #   事件 → 知识沉淀(订阅者)
│   ├── validation_engine.py #   独立验证 / 范围校验 / 证据链
│   ├── runtime.py           #   RuntimeAdapter 协议(执行出口)
│   └── projection.py        #   纯函数:事件流 → 状态快照
│
├── cli/                     # CLI 入口(Typer 薄壳:只做参数解析 + 调 core)
│   ├── main.py              #   factory 根命令
│   ├── task_cmds.py         #   factory task create/approve/reject/status
│   ├── workflow_cmds.py     #   factory workflow run/pause/resume
│   ├── log_cmds.py          #   factory logs/events/replay
│   └── dashboard_cmd.py     #   factory dashboard [--md]
│
├── dashboard/               # Dashboard 渲染(MVP 由 cli 调用;API 版复用)
│   ├── views.py             #   Project 总览 / Task 列表 / Agent 面板 / 时间线
│   └── templates/           #   Markdown 导出模板
│
├── api/                     # API 入口(FastAPI,P2,骨架预留)
│   └── app.py
│
├── agents/                  # ★ 注册物(数据,非代码)
│   └── roles/               #   角色定义:security-auditor.json ...
│       └── _schema.json     #   角色 JSON 的 Pydantic 校验 schema
│
├── skills/                  # ★ Skill 库(独立于 Agent)
│   └── <skill-name>/        #   每个 Skill 一个目录
│       ├── SKILL.md         #   方法集(检查清单/命令序列/质量标准)
│       └── meta.json        #   name/version/roles/trigger/requires
│
├── workflows/               # ★ 流程定义(声明式状态机)
│   ├── feature-delivery.json
│   ├── bug-fix.json
│   └── release.json
│
├── mcp/                     # ★ MCP 工具注册物
│   └── tools/               #   <tool>.json:name/command|url/params schema
│
├── knowledge/               # 知识沉淀(Knowledge System 自动生成,git 提交)
│   ├── adr/                 #   决策记录 <id>-<title>.md
│   ├── bugs/                #   缺陷记录 <id>-<title>.md
│   └── sessions/            #   会话轨迹 <project>-<date>.md
│
├── validation/              # 验证规则 + 证据
│   ├── rules/               #   <rule>.json:范围/必测项/危险操作清单
│   └── artifacts/           #   证据:测试日志/diff/校验报告(gitignore)
│
├── runtimes/                # ★ Runtime Adapter 实现(可插拔)
│   ├── hermes/              #   Hermes 适配器(第一版默认)
│   ├── claude_code/         #   Claude Code 适配器
│   └── registry.py          #   Adapter 注册表 + config 选择
│
└── data/                    # 运行时数据(gitignore,全在单库里)
    ├── factory.db           #   ★ SQLite 唯一数据库(events/tasks/agents/knowledge 表)
    └── projects/            #   项目工作区引用(project_id → git 仓库路径)
```

> ★ = 扩展点所在(见 §7)。**代码目录只有 `factory-core/`、`cli/`、`api/`、`runtimes/` 四处;其余目录全是数据(JSON/Markdown),加内容不需要改代码。**

---

## 5. 数据流:事件驱动设计落地

### 5.1 Event Logger = 唯一事实源(SQLite 落库)

```sql
-- 唯一强制持久化的表;错误以"新事件"纠正,永不 UPDATE/DELETE
CREATE TABLE events (
  seq        INTEGER PRIMARY KEY AUTOINCREMENT,   -- 全局单调递增,回放锚点
  event_id   TEXT UNIQUE,                         -- E-10086
  ts         TEXT NOT NULL,                       -- ISO8601 UTC
  type       TEXT NOT NULL,                       -- task.created / validation.failed ...
  source     TEXT NOT NULL,                       -- 发布模块名
  agent_id   TEXT,                                -- 可选
  task_id    TEXT,                                -- 可选
  project_id TEXT,                                -- 可选,多项目隔离键
  payload    TEXT NOT NULL                        -- JSON 载荷
);
CREATE INDEX idx_events_project ON events(project_id, seq);
CREATE INDEX idx_events_task    ON events(task_id, seq);
```

辅助表(只存**定义性数据**,状态一律投影):

- `tasks(task_id, project_id, parent_id, title, role, scope, acceptance, dependencies, created_at)` — scope/acceptance/dependencies 为 JSON 列。
- `agents(agent_id, role, status, current_task_id, created_at)` — 统计字段不落表。
- `knowledge(knowledge_id, type, title, payload, event_refs, created_at)` — 沉淀层结构化副本。

### 5.2 事件生命周期(落地实现)

```
emit(type, source, **payload)
  → 1. Pydantic Event 模型校验(必填字段/类型)
  → 2. INSERT INTO events(seq 自增) + commit
  → 3. 进程内分发:通知订阅者(workflow 挡板监听 / knowledge 沉淀 / 会话内存投影)
  → 4. 查询侧按需:project() 投影 / replay() 回放 / metrics() 聚合(SQL GROUP BY)
```

- **单进程纪律**:第一版无消息队列、无跨进程订阅。订阅者 = 注册在 `event_logger` 上的内存回调。CLI/API 共用一个进程(库),天然同步。
- **投影**:`projection.py` 是纯函数 `project(events) -> ProjectState`,Dashboard/CLI 每次渲染前从事件重建(或订阅者维护一份增量内存副本,二选一,第一版选后者避免重复扫描)。
- **恢复**:`restore(task_id)` = `SELECT ... WHERE task_id ORDER BY seq` 回放 → 找最近 `system.checkpoint` → 校验 git 状态一致 → 从断点续跑。**不依赖任何对话记忆。**
- **指标**:全部由事件聚合:`first_attempt_success`(无 failed 验证即 completed 的任务占比)、`path_errors`(`validation.blocked` 计数)、`human_intervention`(`human.*` 计数)、截断率(`system.interrupted` / 任务数)。**不另建统计表。**

### 5.3 主链路:一次任务委派(落地版)

```
1.  CLI/Orchestrator  → Task Manager.create_task(...)          # 定义性数据落 tasks 表
2.  Task Manager      → emit(task.created)                     # pending
3.  Workflow Engine   → 校验闸口(决策门) → 放行
4.  Task Manager      → emit(task.assigned)                    # assigned
5.  Agent Registry    → 按角色实例化/复用 Agent + 装配 Skill    # emit(agent.started)
6.  Runtime Adapter   → 启动外部 Agent 进程(注入:任务、范围、验收标准、工具上限、checkpoint 引用)
7.  Agent 执行期间    → 每次工具调用由 core 包装 emit(agent.action)
8.  Agent 自报告      → emit(task.reported)
9.  Workflow Engine   → 触发验证门:Validation Engine 独立校验(范围核对→测试→diff)
                       emit(validation.started / passed | failed),证据落 validation/artifacts/
10. Task Manager      → verifying → done|failed(emit)
11. Orchestrator/CLI  → 查看证据链 → approve(emit human.decision) | reject(返工回路) | 挡板上报
12. Knowledge System  → 订阅事件,自动生成 ADR/Bug 沉淀
```

---

## 6. 依赖关系(最小依赖)

```
                    ┌──────────────┐
                    │ cli/dashboard│  入口层:只依赖 factory_core 公开 API
                    │     /api     │
                    └──────┬───────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│  factory_core 内部(箭头 = 直接调用,事件流方向相反)        │
│                                                         │
│  orchestrator ──▶ task_manager ──▶ agent_registry ──▶ skill_registry │
│       │               │  │                │            │
│       │               │  └──────────────▶ runtime_adapter(协议)       │
│       │               ▼  ▼                │            │
│       └─────────▶ workflow_engine ◀───────┘            │
│                        │                                │
│  validation_engine ◀───┘  (Workflow 触发验证)           │
│       │                                                │
│  knowledge_system ◀── 订阅                              │
│       │                                                │
│  mcp_manager(独立,被 agent 执行时经 runtime 调用)        │
│       │                                                │
│  event_logger ◀── 所有模块发布事件(最底层,零依赖)         │
└────────────────────────────────────────────────────────┘
```

**三条硬规则**:

1. **event_logger 零依赖**,只被依赖;它是模块间唯一共享的"读状态"通道(查询函数),杜绝模块间直接读对方内部状态。
2. **依赖方向单向**:入口层 → core;core 内 决策→任务→Agent→Skill→Runtime 单向;Workflow→Validation 单向。禁止反向依赖与循环 import。
3. **执行出口唯一**:任何要"启动 Agent / 跑命令 / 调工具"的地方,只能走 RuntimeAdapter 或 Validation Engine / MCP Manager 的封装,不裸调 subprocess 散落各处。

---

## 7. 扩展点

> 全部扩展点都是**声明式(数据)+ 注册校验**,零代码改动。新增内容 = 加一份 JSON/Markdown + 通过校验(校验失败拒绝注册并发 `validation.blocked` 事件)。

### 7.1 新增 Runtime(唯一需要写代码的扩展)

```python
# factory-core/runtime.py —— 协议
class RuntimeAdapter(Protocol):
    name: str
    def run(self, request: AgentRunRequest, emit) -> AgentRunResult: ...
# AgentRunRequest: task_id, role, skills, prompt, scope, tool_limit, checkpoint_ref
# AgentRunResult:  ok, summary, artifacts, tool_calls
```

- 实现放 `runtimes/<name>/`(如 `runtimes/hermes/`),在 `runtimes/registry.py` 注册;
- `config.toml` 选默认 runtime,`factory run --runtime <name>` 可覆盖;
- 建议先实现 `hermes`(第一版默认)与 `mock`(测试用,返回固定结果,用于单测 core 逻辑)。

### 7.2 新增 Agent 角色(零代码)

```jsonc
// agents/roles/security-auditor.json
{
  "role": "security-auditor",
  "display_name": "安全审计工程师",
  "default_skills": ["codebase-inspection", "systematic-debugging"],
  "allowed_tasks": ["audit", "review"],
  "scope_policy": "readonly",          // readonly | restricted | full
  "report_format": "summary",
  "exit_criteria": ["must pass validation gate"]
}
```

接入:放入 `agents/roles/` → 校验(role 唯一、skill 引用存在)→ `factory task create --role security-auditor` 即生效。

### 7.3 新增 Skill(零代码)

```jsonc
// skills/systematic-debugging/meta.json
{
  "name": "systematic-debugging",
  "version": "2.1",                    // 版本化;任务归档记录所用版本
  "roles": ["debugger", "dev", "test"],
  "trigger": "task.type == 'debug'",   // 可选自动装配
  "entry_points": ["run_repro", "bisect"],
  "requires": ["python3", "git"]
}
```

接入:放入 `skills/<name>/SKILL.md + meta.json` → 扫描注册 → 按角色装配或按 trigger 自动附加。

### 7.4 顺带声明式扩展(同一机制)

- **新增工作流**:`workflows/<name>.json`(states/transitions/gates/locks,见 design/runtime-design.md §5.3)→ `factory init --workflow <name>` 生效。
- **新增 MCP 工具**:`mcp/tools/<tool>.json`(name/command|url/params schema)→ MCP Manager 校验后注入 Agent 工具集。

---

## 8. 与设计稿的演进关系

| 设计稿(抽象) | 工程化落地(差异) | 理由 |
|---|---|---|
| 9 模块(含独立 Orchestrator/Dashboard/KB) | **8 个 core 模块 + 入口层**:Orchestrator 第一版由 CLI 承载(决策接口预留,LLM 驱动为 P1 同一接口的实现);Dashboard/知识库落到入口层与订阅者 | 不写代码的 Orchestrator 不需要独立模块;人/LLM 只是决策接口的两个实现 |
| Event Logger = "append-only 事件文件/表" | **SQLite `events` 单表**,`seq` 自增主键 + 索引 + Pydantic 校验 | 单文件可备份、可 SQL 聚合,免去自研文件格式与索引 |
| 状态全部"由事件流投影,不落库" | 保留:状态不落表;**但 tasks/agents 表存定义性数据**,投影只负责 status/checkpoints/metrics | 定义性数据反复投影是浪费;KISS 折中 |
| 进程模型未定 | **单进程、串行执行**;Agent/验证/工具都是 subprocess 调用,阻塞等待;无消息队列、无守护进程 | 第一版不需要并发;API(P2)同库同进程 |
| Dashboard = 独立视图层 | MVP 为 **CLI 内嵌 Rich 表格 + Markdown 导出**;FastAPI 版(P2)复用同一 views 渲染函数 | 不做复杂前端,终端即可回答六个问题 |
| Orchestrator 在会话中手工推进 | CLI 命令即决策:task create/approve/reject/resume,证据链全程可查 | 人工决策先固化,LLM 化只是换实现 |
| 知识库 = 文档归档 | Knowledge System 订阅事件,**模板自动生成** `knowledge/` Markdown + knowledge 表;人工只补判断 | 自动沉淀,防漏 |
| "文件即事实"(Allowed/Forbidden) | Validation Engine 前置范围校验 + 证据落 `validation/artifacts/` | 原样保留,这是自报告不可信的解药 |
| 单项目(隐含) | 所有表带 `project_id`,单库多项目隔离 | README 原则 6:支持未来多项目 |
| 扩展点(角色/Skill/流程) | 原样落地 + **补 Runtime Adapter 扩展点**与 MCP 工具扩展点 | Runtime 解耦是"不绑定单一 Agent 框架"的执行层实现 |

**保留不变的原则**(设计稿的魂):事件即事实 / 自报告不可信验证独立 / 可断点续传 / 三挡板人闸口 / KISS 最小模块集。

---

## 9. MVP 里程碑(MVP 只需 4 件事)

1. **Event Logger + SQLite**(events 表 + emit/replay/project/metrics)—— 一切的地基。
2. **Task Manager + 任务状态机**(tasks 表 + checkpoint + 恢复命令)—— 解决"截断/不可恢复"。
3. **Validation Engine 范围校验**(rules JSON + subprocess 执行 + 证据)—— 解决"自报告不可信/越权写"。
4. **CLI 薄壳 + Rich 视图**(Typer 命令 + Dashboard 表格)—— 解决"不可观测"。

先跑通 `factory init → task create → workflow run → logs` 一条主链路(mock runtime),再接入 Hermes runtime 实跑;Dashboard、API、Knowledge 自动沉淀在事件流成型后自然获得。

> 落地顺序与设计稿 runtime-design.md §6 一致:先"事件驱动 + 断点续传 + 越权拦截",再补其余。
