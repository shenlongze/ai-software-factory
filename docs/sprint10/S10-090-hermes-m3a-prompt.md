# Hermes 提示词 — M3a Sprint 规格（递归原子拆解引擎）

> 用途: 三部门循环第 ② 步 — Hermes(CTO) 产出 M3a Sprint 规格，供 Codex(工程) 实现
> 日期: 2026-08-23 | 前置: v1.1.10 · M2 完成 · 全量基线 0 回归 · 架构符合性审计通过

---

【AI Factory M3a Sprint 规格 — 递归原子拆解引擎】

## 角色
Hermes = CTO + 架构委员会。你的职责：产出可执行的 Sprint 规格（架构方案 + 拆解引擎设计 + 验收标准 + 边界），不写实现代码。

## 当前状态（已确认事实，非自报告）
- 版本: v1.1.10 · M2 员工内核完成（AgentEntity/AgentRegistry/ExpertFactory/HandoffBus + T1-T5 专家真干活）
- 测试基线: 11988 collected · 0 回归（全量 3 分 11 秒）
- 架构符合性审计通过（设计↔代码一致，§2.8.2 模块地图 22/22 存在）
- 已有地基（Codex 已交付，可复用不可重造）:
  - `factory-console/session/pipeline.py` — TaskTree / FeatureTaskGenerator（确定性拆解，功能级 Epic/Task）
  - `factory-console/session/dependencies.py` — TaskDependencyGraph（动态 DAG：add/remove/modify + cycle_detect 环检测 + 拓扑排序）
  - `factory-exec/exec/execution_loop.py` — LLMPlanner Decision（FINAL / ACTION_REQUIRED + MAX_ROUNDS 收敛 + 诚实 FAILED）
  - `factory-console/session/execution_state` 状态机（pending/ready/running/success/failed/blocked）

## 背景痛点（M3a 要解决的）
用户实测痛点"一步一个坑"根因 = **任务粒度太粗（复合任务），Agent 一次做不完 → 失败**。
拆到原子 = 直接提高执行成功率（方案书 §3.7.4 已定性）。

## M3a 目标（只做 M3-1，禁止越界）
**递归原子拆解引擎**：复合任务 → 递归拆解 → 原子叶子任务（进执行队列）

- 原子判定四条件（§3.7.3，落成可执行规则）:
  1. 单 Agent 可执行（当前能力边界内一次执行）
  2. 单工具 / 单文件（一次工具调用或单文件修改）
  3. 可验证（明确输入/输出/验收，测试可断言）
  4. 时间盒 ≤ 10 分钟（一个执行周期）
- 拆解深度 = Agent 能力边界（能力越强拆得越浅，动态收敛）
- 非叶子节点 = 编排 Loop（委派子节点 → 观察子节点证据 → 汇总验证 → 自身证据 → 恢复，§4.12.9）
- 输出: 带层级 DAG（树 + depends_on 边），**只有叶子进执行队列**

## 规格必须包含（8 项）
1. **拆解引擎接口**: 输入（复合任务 + 上下文）/ 输出（层级 DAG）/ 状态落盘（execution_state 衔接）
2. **原子判定流程**: 把四条件落成确定性判定步骤（哪些可硬编码判定、哪些需要 LLM 判断）
3. **递归循环控制**: 递归深度上限 + 每层判定 + 防死循环（复用 dependencies.py 环检测）
4. **失败安全（铁律）**: LLM 拆解失败 / 无 LLM → 确定性模板兜底（FeatureTaskGenerator），**诚实降级不伪造**；降级事件落审计
5. **与现有模块衔接**: execution_state.json / dependencies.py / execution_loop.py / handoff_bus.py 的接线点
6. **契约测试要点**（新模块第一天，§2.11.4）: schema / 接口 / 返回值 / 错误码 / 血缘（agt- 前缀）
7. **Codex 写 scope**: 明确实现文件清单（新增哪些、修改哪些，最小改动）
8. **边界声明**: 明确不做 M3-2 关键路径 / M3-3 并行调度 / M3-4 动态分配 / 拆解质量评估（后续 Sprint）

## 验收标准（Codex 完成后，你独立验证，不轻信自报告）
- 复合任务 → 原子叶子（四条件可断言，测试覆盖）
- 拆解深度随能力配置收敛
- 成环拒绝 + 失败安全（无 LLM 降级不伪造，事件可审计）
- 定向测试全绿 + 全量回归 0 新增失败 + git clean
- 版本: M3a 完成后 bump v1.1.11

## 输出物
- 本规格文档: `docs/sprint10/S10-090-m3a-atomic-decomposition-plan.md`（架构方案 + Sprint 规格 + Codex 写 scope）
- 供 Codex 的指令: 一条可直接执行的 `codex exec --approve-for-me "..."` 摘要

## 关键纪律（从坑里学到的，写进规格）
1. 代码存在 ≠ 能力；自报告 ≠ 事实 — 你独立验证
2. 禁止 stub/fake；无 LLM 诚实 skipped
3. 复用已有地基，不重造轮子（dependencies.py / pipeline.py / execution_loop.py）
4. 向后兼容：现有确定性拆解行为不被破坏（旧 TaskTree 流程仍可用）
