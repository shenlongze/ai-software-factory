# AI Software Factory — CLI 设计

> 版本: v1.0 | 状态: 设计稿
> 关联文档: [runtime-design](./design/runtime-design.md)、[validation-model](./design/validation-model.md)、[event-model](./event-model.md)、[dashboard-design](./dashboard-design.md)
> 技术栈: Typer + Rich | 存储: SQLite(见 event-model.md)
> 设计原则: KISS、命令即事件、一切可脚本化。

---

## 1. 总览

### 1.1 命令格式

```
factory <verb> <object> [options]
```

- `verb`:动作 —— `create / list / status / assign / run / validate / logs / dashboard / …`
- `object`:对象 —— `project / task / agent / workflow / logs / dashboard / …`
- 参数与选项:对象级参数在前,过滤/修饰选项在后(如 `factory task list --status running`)

### 1.2 全局选项

| 选项 | 默认 | 说明 |
|---|---|---|
| `--db PATH` | `~/.factory/factory.db` | 事件库路径(见 event-model.md) |
| `--json` | 关 | 输出 JSON,供脚本消费(绕过 Rich 表格) |
| `--verbose` | 关 | 打印底层事件写入日志 |
| `--help` | — | 命令帮助(Typer 内置) |

### 1.3 铁律:命令 = 事件

**每个写操作命令的唯一副作用是发布事件到 events 表;命令本身不直接改业务状态。**

```
factory task assign T-042
        │
        ▼
   发布 task.assigned 事件 ──▶ events 表(append-only)
                              │
                              ▼
                    投影(projection)更新 tasks/agents 派生状态
```

读操作命令(`list / status / logs / dashboard`)只查 events 表及其投影,不写任何状态。
这条铁律保证 CLI、Dashboard、恢复链路共用同一个事实源。

---

## 2. 命令总表

### 2.1 工厂级(factory)

| 命令 | 用途 |
|---|---|
| `factory init [--project NAME]` | 初始化:建 DB 与 events 表、目录骨架(`projects/ roles/ skills/ workflows/`),发 `system.metric` 事件 |
| `factory status` | 工厂总览:项目数 / 任务数 / 事件总数 / 运行中 Agent / 指标一行 |
| `factory config get KEY` | 读配置(如 `tool_call_limit`) |
| `factory config set KEY VALUE` | 写配置(发 `system.metric` 事件记录变更) |

### 2.2 项目级(project)

| 命令 | 用途 |
|---|---|
| `factory project create NAME [--workflow W] [--repo PATH]` | 建项目,绑定工作流与仓库,发 `system.metric` 事件 |
| `factory project list` | 项目列表(名称 / 任务数 / 活跃 Agent 数) |
| `factory project status NAME` | 项目总览(= Dashboard 视图 1 的单次输出) |

### 2.3 任务级(task)

| 命令 | 用途 |
|---|---|
| `factory task create PROJ --title T [--role dev] [--depends T-01] [--acceptance "…"] [--allowed "lib/**"] [--forbidden "…"]` | 定义任务,发 `task.created` |
| `factory task list [PROJ] [--status running] [--role dev]` | 任务列表(每任务一行,可过滤) |
| `factory task status T-042` | 任务详情:定义 + 状态 + 事件时间线 |
| `factory task assign T-042 [--agent A-012]` | 委派给 Agent(缺省按角色挑选),发 `task.assigned` |
| `factory task report T-042 --summary "…" --files "…"` | Agent 提交自报,发 `task.reported` |
| `factory task complete T-042` | 验证通过后置为完成,发 `task.completed` |
| `factory task fail T-042 --class code_error --reason "…"` | 置失败(必须带失败分类),发 `task.failed` |
| `factory task block T-042 --gate G1 --reason "…"` | 命中挡板暂停,发 `task.blocked` |
| `factory task resume T-042` | 恢复,发 `task.resumed` |
| `factory task cancel T-042 --reason "…"` | 取消,发 `task.cancelled` |

### 2.4 Agent 级(agent)

| 命令 | 用途 |
|---|---|
| `factory agent list [--role dev] [--status running]` | Agent 列表(角色 / 状态 / 当前任务 / 工具调用数) |
| `factory agent status A-012` | Agent 详情:当前任务、当前动作、工具调用数/上限、历史指标 |
| `factory agent start --role dev --task T-042` | 实例化 Agent 并绑定任务,发 `agent.started` |
| `factory agent stop A-012 --reason "…"` | 停止,发 `agent.stopped` |

### 2.5 Workflow 级(workflow)

| 命令 | 用途 |
|---|---|
| `factory workflow list` | 已注册流程(读 `workflows/` 注册表) |
| `factory workflow run PROJ [--from 开发]` | 启动/续跑流程:按依赖委派、验证后自动推进、命中挡板即停 |
| `factory workflow gate list PROJ` | 各闸门状态(open / passed / blocked) |
| `factory workflow lock list` | 当前文件锁(`workflow.lock_*` 事件投影) |

### 2.6 验证级(validate)

| 命令 | 用途 |
|---|---|
| `factory validate run T-042 [--level L2]` | 协调器独立验证(双验证的环节 B),发 `validation.started / passed / failed / blocked` |
| `factory validate approve T-042` | 人工验收通过(L3 用户实测结论),发 `validation.passed` + `human.decision` |
| `factory validate reject T-042 --class path_error` | 人工验收驳回,发 `validation.failed`(带失败分类) |

### 2.7 日志 / 事件级(logs, events)

| 命令 | 用途 |
|---|---|
| `factory logs [PROJ] [--task T-042] [--agent A-012] [--type validation.failed] [--tail 50]` | 事件日志查询(倒序) |
| `factory events replay PROJ [--since 100] [--to 200]` | 按 seq 回放事件流(审计 / 恢复定位) |
| `factory checkpoint list T-042` | 任务断点列表(最近者优先) |
| `factory checkpoint restore T-042` | 断点恢复:回放 → 校验 → 续跑(见 event-model §7) |

### 2.8 指标级(metrics)

| 命令 | 用途 |
|---|---|
| `factory metrics [PROJ] [--period 7d]` | 输出 first_attempt_success / path_errors / human_intervention / 截断率 |

### 2.9 Dashboard(dashboard)

| 命令 | 用途 |
|---|---|
| `factory dashboard [--watch 2] [--view overview\|tasks\|agents\|timeline]` | CLI 实时仪表盘(Rich,见 dashboard-design.md) |
| `factory dashboard --format markdown --out docs/STATUS.md` | 生成 Markdown 状态文件 |

---

## 3. 命令 → 事件映射

每个写命令发布的事件(读命令不发事件):

| 命令 | 发布事件 |
|---|---|
| `task create` | `task.created` |
| `task assign` | `task.assigned` |
| `task report` | `task.reported` |
| `task complete` | `task.completed` |
| `task fail` | `task.failed`(payload.failure_class = `--class`) |
| `task block` | `task.blocked`(payload.gate = `--gate`) |
| `task resume` | `task.resumed` |
| `task cancel` | `task.cancelled` |
| `agent start` | `agent.started` |
| `agent stop` | `agent.stopped` |
| `validate run / approve / reject` | `validation.started` / `validation.passed` / `validation.failed`(或 `validation.blocked`) |
| `workflow run` | 过程中的 `workflow.gate_*`、`workflow.lock_*`、`system.checkpoint` |
| `init / config set / project create` | `system.metric`(初始化与配置类系统事件) |

事件结构见 [event-model.md](./event-model.md) §2。

---

## 4. 关键命令详解与输出示例

> 所有输出用 Rich 组件:表格 `Table`、状态徽章(绿/黄/红)、进度条 `Progress`、代码块 `Syntax`。
> `--json` 时输出等价的 JSON 结构(字段同名)。

### 4.1 `factory init`

```bash
factory init --project markpad
```

用途:初始化工厂(建 DB、目录骨架),幂等,重复执行不报错。
输出:

```
✔ 初始化完成
  DB        ~/.factory/factory.db (events 表就绪, WAL 模式)
  projects/ roles/ skills/ workflows/ 目录骨架已建
  project   P-markpad 已创建 (workflow: feature-delivery)
  事件      E-00001 system.metric 已写入
```

### 4.2 `factory project create`

```bash
factory project create markpad --workflow feature-delivery --repo /Users/agentdev/markpad
```

用途:建项目,绑定工作流与仓库。参数:`NAME` 必填;`--workflow` 缺省 `feature-delivery`;`--repo` 可选。

```
✔ 项目 P-markpad 已创建
┌──────────────┬───────────────────────────┐
│ workflow     │ feature-delivery          │
│ repo         │ /Users/agentdev/markpad   │
│ 里程碑       │ M1 未开始                  │
└──────────────┴───────────────────────────┘
```

### 4.3 `factory task create`

```bash
factory task create markpad \
  --title "实现 Block Editor 撤销/重做" \
  --role dev --depends T-038 \
  --acceptance "撤销后光标位置正确;新写测试通过" \
  --allowed "lib/editor/block_editor/**" \
  --forbidden "lib/editor/editor_page.dart"
```

用途:定义任务(定义性数据,状态由事件投影)。参数:`--role` 缺省 `dev`;`--acceptance` 支持重复传入多条;`--allowed/--forbidden` 支持 glob。

```
✔ 任务 T-042 已创建 (project: P-markpad)
┌─────────────┬──────────────────────────────────┐
│ role        │ dev                              │
│ depends_on  │ T-038                            │
│ acceptance  │ 1. 撤销后光标位置正确             │
│             │ 2. 新写测试通过                   │
│ allowed     │ lib/editor/block_editor/**       │
│ forbidden   │ lib/editor/editor_page.dart      │
└─────────────┴──────────────────────────────────┘
```

### 4.4 `factory task list`

```bash
factory task list markpad --status assigned
```

用途:任务列表(每任务一行,来自 tasks 投影表 + 事件聚合)。输出(Rich Table):

```
┌────────┬──────────┬──────────┬───────────────────────────┬─────────────────────┬────────┐
│ Task   │ 状态      │ 角色     │ 标题                       │ 当前动作             │ 风险   │
├────────┼──────────┼──────────┼───────────────────────────┼─────────────────────┼────────┤
│ T-042  │ assigned │ dev      │ 实现 Block Editor 撤销/重做 │ 等待委派执行         │        │
│ T-041  │ running  │ debugger │ 撤销后光标偏移根因调查      │ run_repro            │ 截断×1 │
│ T-038  │ done     │ dev      │ 渲染引擎事件分发            │ —                    │        │
└────────┴──────────┴──────────┴───────────────────────────┴─────────────────────┴────────┘
3 tasks (1 running, 1 assigned, 1 done)
```

### 4.5 `factory task status`

```bash
factory task status T-042
```

用途:任务详情 = 定义 + 投影状态 + 事件时间线。

```
T-042  实现 Block Editor 撤销/重做        [dev]  状态: assigned
├─ acceptance  1. 撤销后光标位置正确  2. 新写测试通过
├─ scope       allowed: lib/editor/block_editor/**   forbidden: editor_page.dart
├─ attempts    0    checkpoints: 0    tool_calls: 0
└─ 时间线 (最近 5 条)
   seq 1023  task.assigned   10:02:01  → A-012
   seq 1022  task.created    10:00:00  创建, depends_on [T-038]
```

### 4.6 `factory task assign` / `agent start`

```bash
factory agent start --role dev --task T-042
# 或合并为: factory task assign T-042 --agent A-012
```

用途:委派任务给 Agent。`task assign` 缺省按角色从 Agent Registry 挑选空闲实例。

```
✔ T-042 → A-012 (dev)
┌──────────────┬──────────────────────────────┐
│ agent_id     │ A-012                        │
│ role         │ dev                          │
│ skill        │ development@1.2              │
│ tool_call    │ 0 / 60                       │
│ scope        │ allowed: block_editor/**     │
│              │ forbidden: editor_page.dart  │
└──────────────┴──────────────────────────────┘
```

### 4.7 `factory agent list` / `agent status`

```bash
factory agent list --status running
```

```
┌──────────┬─────────────┬──────────┬──────────────┬───────────────────┐
│ Agent    │ 角色        │ 状态     │ 当前任务      │ 工具调用 0/上限    │
├──────────┼─────────────┼──────────┼──────────────┼───────────────────┤
│ A-012    │ dev         │ running  │ T-042        │ 12 / 60           │
│ A-013    │ debugger    │ running  │ T-041        │ 47 / 60  ⚠ 接近上限│
└──────────┴─────────────┴──────────┴──────────────┴───────────────────┘
```

```bash
factory agent status A-012
```

```
A-012  [dev]  running  当前任务 T-042
├─ 当前动作     patch block_editor/history.dart  (agent.action @10:15:02)
├─ tool_calls   12 / 60
└─ 历史指标     tasks_done 5   first_attempt_success 0.80   path_errors 1
```

### 4.8 `factory workflow run`

```bash
factory workflow run markpad
```

用途:启动/续跑流程——按依赖委派、自动推进、命中挡板即停(退出码 4)。`--from 开发` 指定续跑阶段。

```
▶ 流程 feature-delivery 已启动 (P-markpad)
  [需求]  T-040  → A-011  ✓ 完成
  [架构]  T-041  → A-013  ✓ 完成 (决策记录已落盘)
  [开发]  T-042  → A-012  … 运行中
  [测试]  等待 T-042 完成
⚠ 命中挡板 G2(架构变更):等待人类决策 → 退出码 4
```

### 4.9 `factory validate run`

```bash
factory validate run T-042 --level L2
```

用途:协调器独立验证(不引用 Agent 自报)。`--level` 取值 L1(静态)/ L2(构建+测试)/ L3(用户实测)。结果发 `validation.*` 事件。

```
▶ 独立验证 T-042 (level L2)
  L1 文件存在     ✓ lib/editor/block_editor/history.dart
  L1 静态检查     ✓ flutter analyze 0 错误
  L2 构建+测试    ✓ 759 tests passed (基线对比:无新回归)
✔ 验证通过 → task.completed 待 Orchestrator 确认 (退出码 0)

# 失败示例:
✘ 验证失败:越权写入 editor_page.dart (forbidden)
  → validation.blocked,退出码 3
✘ 验证失败:新写测试 2/2 未通过 (failure_class: code_error)
  → 打回返工(第 1 次),退出码 3
```

### 4.10 `factory logs`

```bash
factory logs markpad --task T-042 --tail 20
```

用途:事件日志查询(倒序),等效 SQL: `SELECT * FROM events WHERE project_id=? AND task_id=? ORDER BY seq DESC LIMIT 20`。

```
┌──────┬───────────────────┬───────────┬──────────────────────────┬────────────────────────┐
│ seq  │ 时间              │ type      │ agent                    │ action / evidence       │
├──────┼───────────────────┼───────────┼──────────────────────────┼────────────────────────┤
│ 1023 │ 10:02:01          │ assigned  │ A-012                    │ delegate T-042          │
│ 1045 │ 10:15:02          │ agent.act │ A-012                    │ patch history.dart      │
│ 1088 │ 10:31:44          │ reported  │ A-012                    │ 自报: 完成, 测试通过     │
│ 1090 │ 10:32:10          │ valid.fail│ —                        │ ref://artifacts/val.log │
└──────┴───────────────────┴───────────┴──────────────────────────┴────────────────────────┘
```

### 4.11 `factory checkpoint restore`

```bash
factory checkpoint restore T-042
```

用途:断点恢复(见 event-model.md §7):回放事件 → 找最近 `system.checkpoint` → 校验 git/文件状态 → 续跑。执行前做一致性校验,不一致以实际为准,不盲目 checkout。

```
▶ 恢复 T-042
  回放事件        1022..1088 (67 条)
  最近断点        chk-042-3 @10:20:00 (tool_calls 23)
  一致性校验      git HEAD 与断点记录一致 ✓  文件哈希 3/3 ✓
✔ 已恢复,从断点续跑 → 发布 task.assigned(续跑) → 退出码 0
```

### 4.12 `factory dashboard`

```bash
factory dashboard --watch 2
factory dashboard --format markdown --out docs/STATUS.md
```

CLI 实时仪表盘与 Markdown 状态文件,详见 [dashboard-design.md](./dashboard-design.md)。

---

## 5. 退出码约定

| 退出码 | 含义 | 触发场景 |
|:---:|---|---|
| `0` | 成功 | 命令正常完成;`validate run` 验证通过 |
| `1` | 一般错误 | DB 不可用、事件写入失败、内部异常 |
| `2` | 用法错误 | 参数缺失 / 非法值 / 未知命令(Typer 默认) |
| `3` | 验证失败 | `validation.failed` / `validation.blocked`(越权拦截) |
| `4` | 需要人工 | 命中三挡板(G1/G2/G3)、发布授权未批、第 3 次失败上报 |
| `5` | 中断 / 截断 | `system.interrupted`(会话中断 / 工具调用超限) |
| `6` | 资源冲突 | 文件锁被占用、依赖任务未完成(`workflow.lock_*` 冲突) |
| `7` | 未找到 | 任务 / 项目 / Agent / 断点不存在 |
| `130` | 用户中断 | SIGINT(Ctrl-C) |

**约定**:
- 可重试类失败(退出码 1/5/6)允许脚本自动重试;`3`(验证失败)与 `4`(需要人工)必须人工/流程处置,禁止无脑重试。
- 所有命令执行后返回一个退出码;组合脚本按退出码分流(如 CI:`factory workflow run || [ $? -eq 4 ] && 上报挡板`)。

---

## 6. 落地要点(KISS)

1. **一个入口**:`factory` 一个 Typer 应用,子命令即上表;不做第二个 CLI。
2. **写命令 = 发事件**:所有写操作封装为"构造事件 → 校验必填字段 → append 到 events 表 → 触发投影更新",禁止旁路改状态。
3. **读命令只查**:列表/详情/dashboard 全部是 events 表 + 投影的只读查询。
4. **`--json` 先行**:所有命令先支持 `--json`,Rich 渲染只是 JSON 的美化层;测试与脚本优先用 JSON 断言。
5. **退出码即状态**:脚本依赖退出码分流,命令文档必须写清退出码。
