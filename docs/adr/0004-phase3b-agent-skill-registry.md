# ADR-0004: Phase 3B Agent + Skill Registry — 事件扩展、目录布局与集成边界

> 状态: 已接受 | 日期: 2026-08-05 | 作者: 后端开发工程师
> 关联: `docs/design/phase3b-status.md` · `docs/design/event-model.md` §3.2/§2.1 · `docs/adr/0002-phase2-cli-events-layout.md` · `docs/adr/0001-eventtype-and-events-schema.md`

## 背景

Phase 3B 引入 Agent 身份管理 + Skill 能力目录 (AgentRegistry/SkillRegistry + JSON 持久化 + CLI
`agent add/list`、`skill add/list`),并要求所有注册行为经 EventLogger 发 `agent.*` / `skill.*` 事件。
落地时有四处设计张力需明确:

1. **事件词汇**: event-model.md §3.2 的 agent 事件字典只有运行时事件 (started/action/summary/stopped),
   没有"身份注册/移除"类事件; skill.* 命名空间为空。任务指令要求 `agent.registered/updated/removed` 与
   `skill.registered/removed` — 需明确与运行时事件的关系。
2. **读命令事件**: ADR-0002 铁律"所有 CLI 行为必须产生 Event",但任务只列了写事件;
   `agent list` / `skill list` 需要事件类型。
3. **目录布局**: context.py 骨架有 `agents/` 占位但无 `skills/`;任务指定
   `.factory/agents/agents.json` + `.factory/skills/skills.json` 双文件。
4. **引用文档缺失**: 任务设计依据列了 `docs/design/agent-model.md` 与 `docs/design/skill-model.md`,
   但两者在仓库中不存在 — 模型字段以任务指令为准落地。

## 决策

1. **事件按任务指令增量扩展** (沿 ADR-0001 扩展路径: 加枚举成员即可, 不改表结构/API):
   `agent.registered / agent.updated / agent.removed / skill.registered / skill.removed`,
   外加 `agent.viewed / skill.viewed` (读命令事件, 满足 ADR-0002 铁律)。
   身份注册类事件与 event-model §3.2 运行时事件 (started/action/summary/stopped) 语义互补不冲突:
   前者描述"注册表身份", 后者描述"实例运行"。所有 agent.* 事件带 `agent_id` (event-model §2.3),
   stage 取 `status.value.lower()` (available/working/offline), result=OK, payload 含角色/技能等。
   skill.* 事件不带 agent_id (技能无 agent 维度), stage 取 category。
2. **写路径**: 存储先落地、事件后发 — 与 tasks CLI 模式 (cmd_task_create) 一致;
   events 是独立 SQLite, 事件失败不回滚已落盘状态 (由上层重试/补发), 保持单文件 JSON 无事务的 KISS。
   registry 写方法返回 `(对象, Event|None)` — Event 含存储层回填的 seq, 供 CLI 输出审计锚点。
3. **目录布局**: context.py `_SUBDIRS` 增加 `skills/`; `agents/agents.json` 与 `skills/skills.json`
   均为单文件整体原子写 (临时文件 + os.replace), `{id: 模型 dict}` 格式按 id 排序,
   损坏文件 (JSON/校验失败) 抛 CorruptStoreError, 不静默返回空。
4. **模型字段以任务指令为准**: Agent (id/name/role/description/skills/status/current_task/created_at/updated_at,
   AgentStatus=AVAILABLE/WORKING/OFFLINE), Skill (id/name/category/description/capabilities/version,
   能力描述非执行)。`Agent.skills` 为 Skill.id 引用列表, 注册表解耦, 不自动校验存在性。
5. **Task 集成边界**: Task.owner 可引用 Agent.id, 不自动分配 (phase3b-status.md 明确 Phase 4 再做),
   本阶段零代码改动, 仅确认语义。

## 后果

- EventType 纯增量扩展 7 成员; 事件库无 schema 变更, 既有测试断言不受影响。
- CLI 新增 `factory agent add|list` / `factory skill add|list`, 支持 `--json`;
   `agent list --skill X` 走 find_by_skill 语义。退出码沿用 cli-design §5 (重复注册=1, 用法=2)。
- 目录骨架新增 `skills/` (init 与 ensure_dirs 均幂等创建, 不影响既有目录断言 — 需同步检查
  tests/cli 中目录列表断言)。
- 风险: agents.json/skills.json 为整文件读写, 单进程假设下无并发问题; 若未来多进程写入
  需升级为单条文件或文件锁 (Phase 4 议题)。
- 后续 Phase: Agent 自动调度/运行时事件 (started/stopped) 复用 agent_id 维度, 与注册表投影互补。
