# ADR-0002: Phase 2 Factory Control CLI — 事件类型扩展、工厂根目录布局与读命令发事件

> 状态: 已接受 | 日期: 2026-08-05 | 作者: 后端开发工程师
> 关联: `docs/design/phase2-status.md` · `docs/design/cli-design.md` · `docs/design/event-model.md` §3 · `docs/adr/0001-eventtype-and-events-schema.md`

## 背景

Phase 2 落地 Factory Control CLI 时, 任务指令与既有设计存在三处需要消解的张力:

1. **事件类型缺口**: 任务要求 CLI 发 `system.init / task.created / task.viewed / task.updated / validation.started / validation.completed`
   事件, 但 Phase 1 的 `EventType` 仅有六类最小事件 (task.start/end/fail, tool.call, checkpoint, session.close),
   这些名字在枚举中不存在; 而任务同时禁止"修改已有 Event API (events/models.py 等)"。
2. **目录骨架约定冲突**: 任务指令要求 init 建 `tasks/ agents/ workflows/ events/` 目录骨架;
   cli-design.md §2.1 约定 `projects/ roles/ skills/ workflows/`; cli-design §1.2 约定事件库在 `~/.factory/factory.db`。
3. **读命令是否发事件**: cli-design §1.3 铁律"读操作命令只查, 不发事件"; 任务指令要求"所有 CLI 行为必须产生 Event"
   (task list/status → task.viewed)。

## 决策

1. **EventType 纯增量扩展 8 成员** (system.init/system.logs_viewed/system.status_viewed/task.created/task.viewed/
   task.updated/validation.started/validation.completed)。
   - 依据 ADR-0001 决策 1 与后果"新增事件类型无需迁移: 加 EventType 成员 + logger 便捷方法即可", 这是设计预留的扩展路径;
   - 只改 `events/models.py` 的枚举定义, 不改表结构、不新增列、不改任何方法签名; 既有 6 类事件行为与 69 个测试零影响
     (未知类型拒绝测试用 `not.a.type`, 不受影响);
   - 命名遵循 event-model.md §3 六类字典 (task.* / system.* / validation.*)。

2. **工厂根目录布局**: 默认 `~/.factory` (cli-design §1.2 的 `~/.factory/factory.db` 约定), 可 `--root` 覆盖;
   目录骨架按任务指令清单 `tasks/ agents/ workflows/ events/` (任务指令优先于 cli-design 的 projects/roles/skills/workflows,
   Phase 3 需要时再补); 事件库为 `<root>/factory.db` (SQLite EventStore, WAL)。

3. **读命令也发事件**: 任务指令"所有 CLI 行为必须产生 Event"优先于 cli-design §1.3 "读命令不发事件"。
   读命令只发"查看类"事件 (task.viewed / system.logs_viewed / system.status_viewed), 不改业务状态,
   仍是只读语义; 这使 CLI 行为可审计、Dashboard 时间线更完整。

4. **包布局沿用 events 顶层包约定**: factory-core/ 下 `tasks`/`cli` 为独立顶层包 (setuptools
   `where=["factory-core"]`), 不引入 `factory_core` 命名空间; 入口为 console script `factory = cli.main:main`,
   亦可用 `.venv/bin/python -m cli.main`。CLI 为 argparse (标准库零依赖, 不用 Typer/Rich)。

5. **隐式 ensure_dirs**: 所有命令幂等自建目录与 DB, 不强制"先 init"; init 是显式引导 (发 system.init + 打印骨架)。

## 后果

- 事件库可检索到全部 CLI 行为 (含读操作), 审计/回放/Dashboard 有完整事实源。
- `events/models.py` 有且仅有一次增量修改 (枚举扩展); 后续 Phase 3 扩 `agent.*/workflow.*/human.*` 沿用同一路径。
- 已知取舍: JSON 文件任务库无并发锁 (单进程约定, KISS); TaskStore 由 CLI/测试独占。
- 风险: 若未来把读命令事件视为噪音, 可加 `--no-audit` 选项, 不改已写事件。
