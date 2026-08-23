# Hermes 提示词 — M3c Sprint 规格（并行调度执行 M3-3）

> 用途: 三部门循环第 ② 步 — Hermes(CTO) 产出 M3c Sprint 规格，供 Codex(工程) 实现
> 日期: 2026-08-24 | 前置: v1.1.12 · M3a 原子拆解 ✅ · M3b 关键路径 ✅（用户实测通过）· 全量基线 0 回归

---

【AI Factory M3c Sprint 规格 — 并行调度执行 (M3-3)】

## 角色
Hermes = CTO + 架构委员会。产出可执行 Sprint 规格（架构方案 + 并行调度器设计 + 验收标准 + 边界），不写实现代码。

## 当前状态（已确认事实，非自报告）
- 版本: v1.1.12 · M3a DecomposeEngine（原子叶子）+ M3b CriticalPathEngine（plan.json）均已交付并通过独立验证 + 用户实测
- M3b 产出: `plan.json`（tasks[].critical / critical_path / merges / edges / estimated_duration）
- 已有地基（复用不重造）:
  - `session/dependencies.py` — topological_order（Kahn）+ cycle_detect + add_dependency
  - `session/conflicts.py` — ConflictResolver（同文件冲突 → 串行化 serial_groups + 落盘 conflict_resolution.json）
  - `session/agents.py` — AgentMatcher（role/skill/成功率匹配）✅ 已实现
  - `session/orchestrator.py` — execute_project/resume（当前**顺序执行**模式）
  - `execution_state.json` — 每原子任务状态（pending/ready/running/success/failed）

## 背景
§3.9.5 缺口: "✅ 拓扑 / ReplanningEngine / AgentMatcher / resume / ConflictResolver；📐 并行调度器 · 冲突自动串行化 · 资源配额"。
M3b 已补关键路径；M3c 补**并行调度执行** — 原子任务不再简单顺序跑，而是按依赖就绪队列 + 并发上限并行。

## M3c 目标（只做 M3-3，禁止越界）
**并行调度器**: 消费 plan.json + execution_state，做依赖驱动调度。

§3.9.2 流程:
```
原子任务 DAG → 拓扑排序 → 就绪队列（依赖全部完成的任务）
→ 并行度: 无依赖冲突的任务按 资源/预算/LLM 并发上限 并行
→ 冲突: 同文件/同资源 → ConflictResolver 串行化（复用已有）
```

必须包含:
1. **就绪队列**: 入度 0 + 依赖全部完成的任务进入待调度
2. **并发上限**: max_concurrency（可配置; 资源/预算/LLM 三重约束取最小）— 默认 1 = 顺序模式（向后兼容）
3. **冲突串行化**: 复用 ConflictResolver（同文件 → 串行分组），不重造
4. **调度批次落盘**: schedule_rounds[]（每轮哪些任务并行 + 结果）→ 可审计可回放
5. **与现有执行器衔接**: orchestrator 提供并行模式（parallel）vs 旧顺序模式（solo 不变）

## 规格必须包含（8 项）
1. **调度器接口**: 输入（plan.json + execution_state + 配置）→ 输出（schedule_rounds + 每任务状态）
2. **就绪判定**: 依赖边满足（topological 序 + 已完成集合）→ 就绪集合
3. **并发约束**: max_concurrency 语义（全局上限 + budget + LLM 并发），默认顺序兼容
4. **冲突处理**: ConflictResolver 复用点（同文件串行分组如何并入调度轮次）
5. **调度轮次模型**: 每轮 = 并行执行集合 → 全部完成 → 下一轮（可审计落盘）
6. **契约测试要点**: 无依赖 3 任务并行 / 单链串行 / 汇聚（merges 前并行后串行）/ 同文件冲突串行 / 并发上限生效 / 向后兼容（max_concurrency=1 = 旧顺序）
7. **Codex 写 scope**: 明确文件清单（新建 scheduler.py？扩展 orchestrator？最小改动 + 复用）
8. **边界声明**: 不做 M3-4 动态分配（AgentMatcher 已有，画像优先 M4）· 不做质量评估 · 不做快照点（M4）

## 验收标准（Codex 完成后，你独立验证）
- 无依赖 3 任务 → 同轮并行（手算轮次对照）
- 单链 4 任务（db→api→frontend→test）→ 4 轮串行（关键路径语义）
- 汇聚 merge 点 → 并行支路先并行、merge 后串行
- 同文件冲突 → ConflictResolver 串行化生效
- max_concurrency=1 → 与旧顺序行为一致（向后兼容）
- schedule_rounds 落盘可审计
- 定向测试全绿 + 全量回归 0 新增失败 + git clean
- 版本: M3c 完成后 bump v1.1.13

## 输出物
- 规格文档: `docs/sprint10/S10-093-m3c-parallel-scheduler-plan.md`
- 供 Codex 的指令摘要（一条可直接执行）

## 关键纪律（写进规格）
1. 代码存在 ≠ 能力；自报告 ≠ 事实 — 你独立验证（轮次手算对照）
2. 禁止 stub/fake；无 LLM 诚实降级
3. 复用 conflicts.py / dependencies.py / agents.py — 不重造、不修改核心
4. 向后兼容: max_concurrency=1 = 旧顺序模式零变化；M3a/M3b 输出不破坏
5. 版本: v1.1.12 → v1.1.13（每次修复 patch+1）
