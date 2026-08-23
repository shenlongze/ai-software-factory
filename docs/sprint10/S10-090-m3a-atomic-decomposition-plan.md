# S10-090 M3a — 递归原子拆解引擎 Sprint 规格

> 日期: 2026-08-22 | Hermes CTO → Codex | 目标 v1.1.11 | 只做 M3-1
> 背景痛点: 复合任务粒度太粗 → 执行成功率低; 原子任务 = 单 Agent/单工具/可验证/≤10min

---

## 0. 已核验地基(复用不重造)

| 地基 | 位置 | 复用点 |
|---|---|---|
| TaskTree / FeatureTaskGenerator | `session/pipeline.py:242/280` | 确定性任务树生成 |
| 动态 DAG + 环检测 + 拓扑 | `session/dependencies.py` | `add_dependency`(成环拒绝)/`cycle_detect`(DFS)/`topological_order`(失败安全) |
| LLMPlanner FINAL/ACTION_REQUIRED | `exec/execution_loop.py` | 执行循环收敛 |
| HandoffBus 血缘 | `session/handoff_bus.py` | 非叶子节点编排 Loop 的事件/资产 |
| 证据包 | `session/evidence.py` | 拆解结果证据落盘 |

## 1. 拆解引擎接口

```
模块: session/decomposer.py (新建)

class DecomposeEngine:
    def decompose(task: dict, *, product, agent_capabilities, depth=0) -> DecomposeResult
        # 输入: task {id,name,goal,requirement}
        # 输出: DecomposeResult {
        #   leaves: [原子任务 {id,name,goal,agent_type,verify_cmd,est_minutes}]
        #   tree:   [节点 {id,parent,type:compound|atomic,children[]}]
        #   state:  落盘 projects/<slug>/decomposition.json (可追溯)
        # }

    def is_atomic(task, capabilities) -> tuple[bool, list[str]]  # 四条件判定
    def _depth_limit / _max_depth
```

## 2. 原子判定流程(四条件 → 可执行步骤)

| 条件 | 判定方式 | 硬编码 vs LLM |
|---|---|---|
| ① 单 Agent 可执行 | 所需 agent_type ⊆ 单一 Agent 能力(候选 agent 数=1) | 确定性(能力表) |
| ② 单工具·单文件 | 目标明确指向 1 文件 + 1 工具(如改 main.py / 写 test_x.py) | 确定性(关键词/结构) + LLM 辅助 |
| ③ 可验证 | 存在验证命令(pytest <file> / flutter test / 语法检查) | 确定性(语言→验证映射) |
| ④ ≤10 分钟 | 估计工作量(行数/复杂度启发) | 启发式 + LLM 辅助 |

**流程**: 先确定性判定(能力表/语言映射/文件数) → 判定模糊时 LLM 辅助(注入点) → 四条件全过 = 原子; 任一不过 = 复合 → 递归拆解。

## 3. 递归深度上限 + 防死循环

- `_max_depth = 5`(常量, 配置可覆盖)
- 每层递归前 `dependencies.cycle_detect`(任务 id 链成环 → 拒绝 + 审计事件 `DECOMPOSE_CYCLE_REJECTED`)
- 深度到达 → 当前节点标记 `atomic(unverified)` 直接进执行队列(诚实标注, 不伪造原子性)
- 递归任务数上限 `_max_tasks = 64`(防爆炸)

## 4. 失败安全铁律

```
1. LLM 辅助失败/无 LLM → 确定性拆分 (按 features/deps 结构切, 非空)
2. 无 LLM → 所有判定走确定性路径, 不伪造 LLM 结论
3. 每步审计事件: DECOMPOSE_STARTED / DECOMPOSE_ATOMIC / DECOMPOSE_SPLIT /
   DECOMPOSE_CYCLE_REJECTED / DECOMPOSE_COMPLETED (复用 AuditEmitter)
4. 任何异常 → 返回当前 leaves(部分结果) + 明确 error 字段, 不静默
```

## 5. 接线点

| 接线 | 说明 |
|---|---|
| `execution_state.json` | 拆解结果写 `tasks[]`(leaves 替代原复合任务, 保留复合任务为 group) |
| `dependencies.py` | 叶子间依赖用 add_dependency(成环拒绝) + topological_order |
| `execution_loop.py` | 原子叶子 → 执行(LLMPlanner FINAL 路径); 非叶子 = 编排 Loop 占位(不实现) |
| `handoff_bus.py` | 非叶子节点的委派/证据事件(血缘 parent_artifact) |

## 6. 契约测试要点

```
tests/console/test_m3a_decomposer.py:
- 复合任务 → 原子叶子(四条件断言: agent_type 单数/文件数=1/verify_cmd 存在/est≤10)
- 深度收敛: 能力越强 → 深度越浅 (capabilities 注入不同配置断言深度差异)
- 成环拒绝: 构造环 → DECOMPOSE_CYCLE_REJECTED + 不产出
- 无 LLM 降级: llm_fn=None → 确定性拆分非空 + 审计事件
- 向后兼容: 旧 TaskTree 流程(pipeline.py from_product) 不受影响
```

## 7. Codex Scope(最小改动)

| 文件 | 动作 |
|---|---|
| `factory-console/session/decomposer.py` | ★新建(引擎主体) |
| `factory-console/session/dependencies.py` | 只读复用(不修改, 或仅暴露 cycle_detect 若已公开) |
| `factory-console/session/actions.py` | 最小: execute_project 前调用 decompose(可选开关, 默认开) |
| `factory-console/audit/audit_event.py` | 新增 5 事件类型 |
| `tests/console/test_m3a_decomposer.py` | ★新建契约测试 |
| 版本文件 | pyproject/install.sh/docs/CHANGELOG/断言 → v1.1.11 |

## 8. 边界声明(不做)

- ❌ M3-2 关键路径标注
- ❌ M3-3 并行调度
- ❌ M3-4 动态 Agent 分配
- ❌ 质量评估
- ❌ 非叶子节点编排 Loop 实现(仅接口/事件占位)
- ✅ 向后兼容: 旧 TaskTree 流程不破坏(分解器可开关)

## 验收标准(Hermes 独立验证)

1. 复合任务("实现登录功能")→ 原子叶子(四条件可断言)
2. 深度随能力配置收敛(capabilities 注入不同 → 深度不同)
3. 成环拒绝 + 审计事件
4. 无 LLM → 确定性降级非空, 不伪造
5. 定向全绿 + 全量回归 0 新增失败 + git clean
6. 版本 v1.1.11

---

# Codex 指令摘要(一条可直接执行)

```
你是 AI Factory Senior Engineer。实现 M3a 递归原子拆解引擎:
1) 新建 factory-console/session/decomposer.py — DecomposeEngine: decompose(task, capabilities, depth=0) → {leaves, tree, state}; is_atomic 四条件(单Agent/单文件单工具/可验证/≤10min; 确定性判定优先, LLM 注入点辅助); _max_depth=5 + _max_tasks=64; 递归前 dependencies.cycle_detect 成环拒绝。
2) 接线: actions.execute_project 前调用 decompose(默认开, 可开关); 叶子写 execution_state.tasks[]; 复合任务保留为 group。
3) 审计事件 5 个: DECOMPOSE_STARTED/ATOMIC/SPLIT/CYCLE_REJECTED/COMPLETED (audit_event.py)。
4) 失败安全: LLM 失败/无 LLM → 确定性拆分非空 + 诚实标注 atomic(unverified); 异常返回部分结果+error。
5) 测试 tests/console/test_m3a_decomposer.py: 四条件断言/深度收敛/成环拒绝/无LLM降级/旧流程兼容。
6) 版本 1.1.10→1.1.11 同步 pyproject/install.sh/docs/CHANGELOG/版本断言。
7) 全量回归 0 failed (runtime flaky 除外)。Completion Report: 修改文件/测试/验收断言实测/风险/下一步。
禁止: stub/fake, 超前范围 (M3-2/3/4, 编排Loop实现不做), 破坏旧 TaskTree 流程。
```

规格: docs/sprint10/S10-090-m3a-atomic-decomposition-plan.md
