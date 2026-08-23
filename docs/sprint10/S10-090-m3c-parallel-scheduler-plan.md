# S10-090 M3c — 并行调度执行 (M3-3) Sprint 规格

> 日期: 2026-08-23 | Hermes CTO → Codex | 目标 v1.1.13 | 只做 M3-3
> 前提: M3a 原子拆解 ✅ + M3b 关键路径 ✅ (v1.1.12) — plan.json 产出 critical_path/edges/merges/order/tasks

---

## 0. 现状核验(已确认)

- M3b plan.json: `{tasks[], edges[], critical_path[], merges[], order[], estimated_duration}` — **已落盘**
- 复用地基: `dependencies.py` topological_order(229) · `conflicts.py` ConflictResolver.resolve(431) · `agents.py` AgentMatcher · `orchestrator.py` execute_project(mode: solo 默认, team 模式基础存在)
- **缺口**: 无并行调度器 —— 拓扑/Replanning/AgentMatcher/resume/ConflictResolver 已实现, 缺"就绪队列 + 并发上限 + 冲突串行化 + rounds 落盘"

## 1. 调度器接口

```
模块: session/scheduler.py (新建)

class TaskScheduler:
    def schedule(self, plan: dict, state: dict, *, max_concurrency: int = 1,
                 agent_matcher=None, conflict_resolver=None, persist=True) -> ScheduleResult
        # 输入: plan.json(tasks/edges) + execution_state(已完成任务)
        # 输出: ScheduleResult {
        #   rounds: [[task_id, ...], ...]        # 每轮可并行执行的任务组
        #   order:  [task_id, ...]                # 扁平执行序 (向后兼容)
        #   conflicts: [{task, reason}]           # 被串行化的冲突
        #   state:  落盘 projects/<slug>/schedule.json (可审计)
        # }

    def ready_tasks(self, completed: set[str]) -> list[str]  # 就绪判定
    def _concurrency_bucket(self, ready, max_c) -> list[list[str]]  # 并发分桶
```

## 2. 就绪判定

```
任务就绪 = 依赖(depends_on/edges 指向它)全部 ∈ completed
即: 入边 from_task 全部完成 → 任务进就绪队列
首轮: 无依赖任务 (入度=0)
```

## 3. 并发约束语义

```
max_concurrency (默认 1):
  - 1 = 顺序执行 (零变化, 兼容旧 solo)
  - N = 每轮最多 N 个任务并行 (就绪队列按轮分桶)
  资源配额 (可选扩展, 本 Sprint 用 max_concurrency 表示 LLM/预算上限)
```

## 4. ConflictResolver 复用点

```
冲突检测: 同 target_file / 同资源 → 冲突
冲突处理: ConflictResolver.resolve (复用 S10-057, 不修改) → 冲突任务不并行 (串行化, 后续轮次)
落盘: conflicts[] 记录 {task, reason, resolution}
```

## 5. 调度轮次模型

```
rounds 生成:
  1. topological_order 排序 (复用 dependencies)
  2. 逐轮: ready = 未调度且依赖完成的任务
  3. 冲突检测: ready 内同文件冲突 → 串行 (后者推下一轮)
  4. 并发上限: ready 按 max_concurrency 分桶 (超限任务推下一轮)
  5. 直到全部调度
落盘: schedule.json {rounds, order, conflicts, max_concurrency, created_at}
```

## 6. 契约测试(6 种)

```
tests/console/test_m3c_scheduler.py:
1. 无依赖并行: A/B/C 无依赖, max_c=3 → 1 轮 [A,B,C] (同轮)
2. 单链串行: db→api→frontend→test → 4 轮, 每轮 1 任务
3. 汇聚: {A,B}→C → 轮1 [A,B], 轮2 [C] (先并行后串行)
4. 同文件冲突: A/B 同 target_file → 串行 (不同轮), conflicts 记录
5. 并发上限: 5 就绪任务 max_c=2 → 轮1 [2个], 轮2 [2个], 轮3 [1个]
6. 向后兼容: max_c=1 → 单任务轮 (零变化); 无 plan 输入 → 直接旧路径
```

## 7. Codex Scope(最小改动)

| 文件 | 动作 |
|---|---|
| `factory-console/session/scheduler.py` | ★新建(调度器主体) |
| `factory-console/session/orchestrator.py` | 最小: execute_project 增加 parallel 模式(默认 solo 不变; parallel 消费 plan.json → rounds 执行) |
| `factory-console/session/dependencies.py` | 只读复用(不修改) |
| `factory-console/session/conflicts.py` | 只读复用(不修改) |
| `factory-console/session/agents.py` | 只读复用(AgentMatcher) |
| `tests/console/test_m3c_scheduler.py` | ★新建 |
| 版本文件 | → v1.1.13 |

## 8. 边界(不做)

- ❌ M3-4 动态 Agent 分配
- ❌ 质量评估
- ❌ 快照点/恢复点
- ✅ 向后兼容: solo 模式零变化; max_concurrency=1 = 旧顺序

## 验收标准(Hermes 独立验证, 轮次手算对照)

```
1. 3 无依赖任务 max_c=3 → 1 轮并行
2. db→api→frontend→test → 4 轮串行
3. {A,B}→C → 轮1[A,B] 轮2[C] (先并行后串行)
4. 同文件冲突 → 串行 + conflicts 记录
5. max_c=1 → 旧顺序零变化
6. rounds 落盘 schedule.json
7. 全量回归 0 新增 + git clean + v1.1.13
```

---

# Codex 指令摘要(一条可直接执行)

```
你是 AI Factory Senior Engineer。实现 M3c 并行调度执行 (M3-3):
1) 新建 factory-console/session/scheduler.py — TaskScheduler.schedule(plan, state, max_concurrency=1, agent_matcher=None, conflict_resolver=None) → {rounds[[task...]], order[], conflicts[], state}; ready_tasks(completed) 入度=0 就绪; 冲突检测(同 target_file) → ConflictResolver.resolve 复用 → 串行化; 并发分桶(就绪按 max_c 分轮); 落盘 schedule.json {rounds, order, conflicts, max_concurrency, created_at}。
2) orchestrator.execute_project 增加 parallel 模式(默认 solo 不变; parallel 消费 plan.json → rounds 依序执行, 同轮内按现有执行链跑)。
3) 复用 dependencies.topological_order / conflicts.ConflictResolver / agents.AgentMatcher — 不修改这三者核心。
4) 失败安全: 环/无 plan → 降级顺序执行(诚实标注); 不伪造并行。
5) 测试 tests/console/test_m3c_scheduler.py: 6 种 (无依赖并行/单链串行/汇聚先并行后串行/同文件冲突串行/并发上限分桶/向后兼容 max_c=1)。
6) 版本 1.1.12→1.1.13 同步 pyproject/install.sh/docs/CHANGELOG/版本断言。
7) 全量回归 0 failed (runtime flaky 除外)。Completion Report: 修改文件/测试/轮次手算对照表/风险/下一步。
禁止: stub/fake, 超前范围 (M3-4 动态分配/质量评估/快照不做), 修改 dependencies/conflicts/agents 核心。
```

规格: docs/sprint10/S10-090-m3c-parallel-scheduler-plan.md
