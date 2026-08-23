# Hermes 提示词 — M3b Sprint 规格（关键路径标注 M3-2）

> 用途: 三部门循环第 ② 步 — Hermes(CTO) 产出 M3b Sprint 规格，供 Codex(工程) 实现
> 日期: 2026-08-23 | 前置: v1.1.11 · M3a 完成（DecomposeEngine 验收通过）· 全量基线 0 回归

---

【AI Factory M3b Sprint 规格 — 关键路径标注 (M3-2)】

## 角色
Hermes = CTO + 架构委员会。产出可执行 Sprint 规格（架构方案 + 关键路径引擎设计 + 验收标准 + 边界），不写实现代码。

## 当前状态（已确认事实，非自报告）
- 版本: v1.1.11 · M3a 递归原子拆解引擎已交付并通过你的独立验证（commit 7998f44）
- M3a 产出: `session/decomposer.py` DecomposeEngine → {leaves, tree, state}
  - leaves: 原子任务（id/agent_type/target_file/verify_cmd/est_minutes/verified/parent）
  - tree: 带层级节点（compound/atomic）
  - 落盘 `projects/<slug>/decomposition.json`
- 现有地基（复用不重造）:
  - `session/dependencies.py` — TaskDependencyGraph: add_dependency(成环拒绝) / cycle_detect(DFS) / topological_order(Kahn)
  - `session/decomposer.py` — 原子叶子生成（M3a）
  - `execution_state.json` — 任务状态（pending/ready/running/...）
  - `audit/audit_event.py` — 审计事件（已有 DECOMPOSE_* 5 事件）

## 关键设计缺口（M3b 必须解决）
M3a 的 leaves 只有**父子关系（树）**，没有**横向依赖边（DAG）**——关键路径需要依赖边。
M3b 规格必须设计**依赖边来源**:
1. 技术层确定性依赖（同 feature 内: db → api → frontend → test）
2. 跨 feature 依赖（共享模块/资源，如公共 schema）
3. LLM 注入点（复杂依赖关系辅助，失败 → 确定性兜底）
4. 依赖边落盘（扩展 dependencies.py 或独立依赖文件）

## M3b 目标（只做 M3-2 关键路径标注，禁止越界）
**关键路径引擎**: 从原子任务 DAG 计算**最长依赖链** → 决定总工期 → 关键路径任务标记 `CRITICAL`。

- §3.9.1: 关键路径任务标记 CRITICAL → 优先调度、优先分配资源、失败立即影响交付 → 提前告警
- §3.8.2: 依赖汇聚节点（merge point）判定 — 多路依赖在此汇合 → 校验全部输入就绪 + 冲突检查
- 输出: critical_path 列表 + 每任务 critical 标记 + estimated_duration + merge points
- 落盘: projects/<slug>/plan.json（或扩展 decomposition.json → plan 字段）

## 规格必须包含（8 项）
1. **依赖边模型**: 边的来源/结构/落盘（技术层确定性 + LLM 注入 + 失败安全）
2. **关键路径算法**: 最长依赖链计算（复用 topological_order 做拓扑序，再按 est_minutes 累加找最长链）
3. **CRITICAL 标记**: 关键路径上的任务标记 + 落盘字段（critical: true）
4. **依赖汇聚节点**: merge point 判定（入度 ≥2 的节点）+ 标记
5. **estimated_duration**: 整链预估总工期（关键路径长度）+ 每任务 critical 状态
6. **契约测试要点**: 单链/分叉/汇聚/环拒绝/无依赖 5 种 DAG 形态 + 落盘 + 向后兼容（M3a 输出无依赖边时行为）
7. **Codex 写 scope**: 明确文件清单（新增 critical_path.py？还是扩展 decomposer？最小改动 + 复用）
8. **边界声明**: 不做 M3-3 并行调度执行 / M3-4 动态分配（本 Sprint 只做"计划层标注"，调度消费在 M3c）

## 验收标准（Codex 完成后，你独立验证）
- 构造 5 种 DAG（单链/分叉/汇聚/环/无依赖）→ 关键路径正确（手算对照）
- 技术层链 "db→api→frontend→test" 关键路径可断言（8 叶子 = 2 features → 关键路径含 4 节点 × est）
- CRITICAL 标记落盘 + merge point 标记
- 环 → 失败安全（不崩，明确 error 或跳过）
- 向后兼容: M3a 输出（无依赖边）→ 默认按技术层推断依赖，不破坏旧流程
- 定向测试全绿 + 全量回归 0 新增失败 + git clean
- 版本: M3b 完成后 bump v1.1.12

## 输出物
- 规格文档: `docs/sprint10/S10-091-m3b-critical-path-plan.md`
- 供 Codex 的指令摘要（一条可直接执行）

## 关键纪律（写进规格）
1. 代码存在 ≠ 能力；自报告 ≠ 事实 — 你独立验证
2. 禁止 stub/fake；无 LLM 诚实降级（依赖推断失败 → 确定性技术层链，不伪造 LLM 结论）
3. 复用 dependencies.py（拓扑/环检测）与 decomposer.py（叶子）— 不重造
4. 向后兼容: M3a 输出 / 旧 TaskTree 流程不破坏
5. 版本每次修复 patch+1（当前 v1.1.11 → M3b 完成 v1.1.12）
