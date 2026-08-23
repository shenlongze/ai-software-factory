# Hermes 提示词 — M3e Sprint 规格（调度器接管真实执行 + 动态分配）

> 用途: 三部门循环第 ② 步 — Hermes(CTO) 产出 M3e Sprint 规格，供 Codex(工程) 实现
> 日期: 2026-08-24 | 前置: v1.1.14 · M3a-d 四部曲完成（拆解/关键路径/调度/质量评估）· 全量基线 0 回归

---

【AI Factory M3e Sprint 规格 — 调度器接管真实执行 + 动态分配 (M3 收尾)】

## 角色
Hermes = CTO + 架构委员会。产出可执行 Sprint 规格，不写实现代码。

## 当前状态（已确认事实）
- 版本: v1.1.14 · M3a-d 完成: DecomposeEngine → CriticalPathEngine → TaskScheduler → DecompositionEvaluator
- **最大尾巴（架构真实性裂缝）**: M3a-d 产物（拆解树/关键路径/调度轮次）**只"算得出来"，没接入 execute_project 真实执行路径**——execute_project 仍走旧 TaskTree 顺序路径（§22.0 弱点 1）
- M3-4 动态分配未做（AgentMatcher 已有, 但调度时未实时匹配）
- 复用地基:
  - `session/decomposer.py`（原子叶子）· `session/critical_path.py`（关键路径）· `session/scheduler.py`（调度轮次）
  - `session/agents.py` AgentMatcher（role/skill/成功率匹配 ✅）
  - `session/orchestrator.py` execute_project（当前顺序旧路径）· `exec/execution_loop.py`（LLMPlanner）
  - `session/evidence.py`（证据包）· `audit/`（审计事件）

## M3e 目标（M3 收尾核心: 让 M3a-d 真正驱动执行）
**调度器接管真实执行**: execute_project 可选走"M3 执行链"——

```
复合任务 → DecomposeEngine(原子叶子) → CriticalPathEngine(关键路径)
  → TaskScheduler(调度轮次) → 每轮就绪叶子 → AgentMatcher 动态分配(M3-4)
  → ExecutionLoop 执行 → 证据落盘 → 审计 → 下一轮
```

必须包含:
1. **执行链入口**: execute_project 增加 M3 模式（decompose→keypath→schedule→execute rounds），
   旧路径保留（开关/默认策略, 向后兼容零破坏）
2. **叶子进执行队列**: 每轮就绪叶子按调度轮次执行（max_concurrency 控制并行度,
   默认 1 = 顺序兼容）
3. **动态分配 (M3-4)**: 每轮就绪任务用 AgentMatcher 按 角色/技能/成功率/成本 实时匹配
   Agent（非预分配）→ 分配结果落盘 + 审计
4. **执行结果回填**: 每任务执行 → evidence + execution_state 更新 → 依赖完成后下一轮就绪
5. **审计**: 执行链事件（DAG_SCHEDULED / ROUND_STARTED / TASK_ASSIGNED / ROUND_COMPLETED...）

## 规格必须包含（8 项）
1. **执行链接口**: 新执行器 vs orchestrator 扩展（最小改动, 复用 ExecutionLoop）
2. **模式切换语义**: M3 模式 vs 旧模式（默认哪个? 开关名? 失败回退旧路径?）
3. **动态分配接入点**: AgentMatcher 在每轮就绪时调用（数据源/匹配规则/兜底）
4. **并行与冲突**: 轮次内并行（max_concurrency）+ 同文件冲突串行（复用 ConflictResolver）
5. **状态/证据/审计**: 每任务与每轮的状态落盘 + 证据 + 审计事件
6. **契约测试要点**: 拆解→调度→执行全链 / 动态分配生效 / 旧路径零变化 / 单任务失败不中断整链 / 冲突串行
7. **Codex 写 scope**: 明确文件清单（最小改动）
8. **边界声明**: 不做并行线程化（真实多线程执行, 后续）· 不做原子沙箱（并行配套）· 不做 M3f/M3g

## 验收标准（Codex 完成后，你独立验证）
- 一个产品: 拆解→关键路径→调度→**真实执行**→结果落盘（非只算轮次）
- 动态分配: 就绪任务实时匹配 Agent（断言分配结果 + 审计）
- 单任务失败 → 不中断整链（失败记录 + 继续/重试）
- 旧 execute_project 路径零变化（开关关闭 = 原行为）
- 全量回归 0 新增失败 + git clean
- 版本: M3e 完成后 bump v1.1.15

## 输出物
- 规格文档: `docs/sprint10/S10-097-m3e-exec-loop-plan.md`
- 供 Codex 的指令摘要

## 关键纪律
1. 代码存在 ≠ 能力；自报告 ≠ 事实 — 独立验证（全链实测）
2. 禁止 stub/fake；无 LLM 诚实降级
3. 复用 decomposer/critical_path/scheduler/agents/orchestrator — 不重造
4. 向后兼容: 旧 execute_project 路径零变化（开关控制）
5. 版本: v1.1.14 → v1.1.15（patch+1）
