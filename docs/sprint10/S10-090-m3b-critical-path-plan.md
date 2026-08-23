# S10-090 M3b — 关键路径标注 (M3-2) Sprint 规格

> 日期: 2026-08-22 | Hermes CTO → Codex | 目标 v1.1.12 | 只做 M3-2(计划层标注)
> 前提: M3a DecomposeEngine 已交付(v1.1.11, 7998f44)——leaves 只有树关系, 无横向依赖边

---

## 0. 现状核验(已确认)

- M3a leaf 字段: `agent_type/depth/est_minutes/goal/id/name/parent/source/target_file/unverified/verified/verify_cmd` — **无 depends_on**
- 复用地基: `dependencies.py` add_dependency(成环拒绝)/cycle_detect(DFS)/topological_order(失败安全)
- **缺口**: 关键路径需要横向依赖边(DAG), M3a 只有树

## 1. 依赖边模型(来源/结构/落盘)

```
来源(优先级):
  ① 技术层确定性链 (同 feature): db → api → frontend → test (硬编码模板)
  ② 跨 feature 共享: 共享 target_file/模块 → 边 (确定性检测)
  ③ LLM 注入点: llm_fn(task_a, task_b) → 额外依赖 (失败 → 跳过, 用①②)
  ④ 落盘: dependencies.json (项目级) + plan.json 内含 edges

结构:
  edge: {from_task, to_task, kind: technical|shared|llm, source}
  落盘: projects/<slug>/dependencies.json
  plan.json: {tasks[], edges[], critical_path[], merges[], estimated_duration}
```

## 2. 关键路径算法

```
1. 依赖边 → 有向图 (add_dependency 逐条, 成环拒绝 + 审计)
2. topological_order → 拓扑序列 (失败安全: 环 → 剩余原顺序)
3. est_minutes 沿拓扑累加: dist[task] = max(dist[dep] + est[task])
4. 最长链 = 关键路径 (从 end 回溯 max dist)
5. estimated_duration = max dist (整链预估)
```

## 3. CRITICAL 标记落盘

```
plan.json tasks[] 每任务增加: critical: bool
critical=True (在关键路径上) → CRITICAL
审计事件: PLAN_KEYPATH_COMPUTED
```

## 4. merge point 判定

```
merge = 入度 ≥ 2 的节点 (多个依赖汇聚)
plan.json merges[]: {task, deps[>=2]}
(§3.8.2 — 汇聚节点; 不执行调度, 仅标注)
```

## 5. estimated_duration

```
整链预估 = 关键路径总 est_minutes
落盘 plan.json.estimated_duration + summary_text (CLI 展示)
```

## 6. 契约测试(5 种 DAG + 落盘 + 兼容)

```
tests/console/test_m3b_critical_path.py:
1. 单链: A→B→C (est 1/2/3) → 关键路径 A-B-C, duration=6
2. 分叉: A→{B,C} → 关键路径 A+max(B,C), merge 无
3. 汇聚: {A,B}→C → merge=C, duration=max(A,B)+C
4. 环: A→B→A → 拒绝 + 审计事件, 不产出关键路径(失败安全)
5. 无依赖: 全孤立 → 每任务独立, duration=max est
6. 落盘: plan.json + dependencies.json 可读
7. 向后兼容: M3a 无依赖边输入 → 默认技术层链(不崩溃, 兼容旧行为)
```

## 7. Codex Scope(最小改动)

| 文件 | 动作 |
|---|---|
| `factory-console/session/critical_path.py` | ★新建(依赖边推断 + 关键路径算法 + merge + plan 落盘) |
| `factory-console/session/dependencies.py` | 只读复用(不修改) |
| `factory-console/session/decomposer.py` | 最小: decompose 结果可传 critical_path 生成 plan(或由 actions 串联) |
| `factory-console/session/actions.py` | 最小: execute_project 前置步骤调用(可开关, 默认开) |
| `factory-console/audit/audit_event.py` | 新增 2 事件: PLAN_KEYPATH_COMPUTED / PLAN_MERGE_MARKED |
| `tests/console/test_m3b_critical_path.py` | ★新建 |
| 版本文件 | → v1.1.12 |

## 8. 边界(不做)

- ❌ M3-3 并行调度执行(只计划层标注)
- ❌ M3-4 动态 Agent 分配
- ❌ 质量评估
- ✅ 向后兼容: M3a decompose 无依赖边输入不崩溃(技术层链兜底)

## 验收标准(Hermes 独立验证, 手算对照)

```
1. 5 种 DAG 关键路径与手算一致 (单链/分叉/汇聚/环/无依赖)
2. 技术层链 4 节点 × est → duration 可断言 (db→api→frontend→test)
3. CRITICAL + merge 落盘 plan.json
4. 环 → 失败安全 (拒绝 + 审计, 不崩溃)
5. M3a 无依赖边输出向后兼容 (默认技术层链)
6. 全量回归 0 新增失败 + git clean + v1.1.12
```

---

# Codex 指令摘要(一条可直接执行)

```
你是 AI Factory Senior Engineer。实现 M3b 关键路径标注 (M3-2):
1) 新建 factory-console/session/critical_path.py — 依赖边推断(技术层链 db→api→frontend→test / 共享 target_file / llm_fn 注入失败跳过) + 关键路径算法(add_dependency 成环拒绝 → topological_order → est_minutes 累加 max → 最长链 CRITICAL) + merge point(入度≥2) + plan.json 落盘{tasks[], edges[], critical_path[], merges[], estimated_duration} + dependencies.json。
2) 接线: actions.execute_project 前置调用(可开关默认开); M3a 无依赖边输入 → 默认技术层链(向后兼容)。
3) 审计 2 事件: PLAN_KEYPATH_COMPUTED / PLAN_MERGE_MARKED (audit_event.py)。
4) 失败安全: 环 → 拒绝 + 审计不崩溃; LLM 推断失败 → 确定性技术层链(不伪造)。
5) 测试 tests/console/test_m3b_critical_path.py: 5 种 DAG (单链/分叉/汇聚/环/无依赖) 手算对照 + 落盘 + 向后兼容。
6) 版本 1.1.11→1.1.12 同步 pyproject/install.sh/docs/CHANGELOG/版本断言。
7) 全量回归 0 failed (runtime flaky 除外)。Completion Report: 修改文件/测试/验收断言实测(手算对照表)/风险/下一步。
禁止: stub/fake, 超前范围 (M3-3 并行执行/M3-4 动态分配不做), 修改 dependencies.py 核心。
```

规格: docs/sprint10/S10-090-m3b-critical-path-plan.md
