# S10-097 M3e — 调度器接管真实执行 + 动态分配 (M3 收尾) Sprint 规格

> 日期: 2026-08-24 | Hermes CTO → Codex | 目标 v1.1.15 | M3 收尾
> 最大尾巴: M3a-d 产物只"算得出来", 没接入 execute_project 真实执行(仍走旧 TaskTree 顺序路径)

---

## 0. 现状核验(已确认)

- M3a-d 完成(v1.1.14): DecomposeEngine(原子) + CriticalPathEngine(关键路径) + TaskScheduler(轮次) + DecompositionEvaluator(质量门控)
- `orchestrator.execute_project`: mode 参数(solo 默认)+ M3c parallel 配置(max_concurrency)已存在
- AgentMatcher(agents.py:356)已存在, 未接入实时分配
- **缺口**: M3a-d 产物未驱动真实执行——仍走旧 TaskTree 顺序路径

## 1. 执行链接口

```
orchestrator.execute_project 增加 M3 模式 (mode="m3"):
  输入: project + plan.json (M3b) + execution_state
  流程: DecomposeEngine(复合→原子) → CriticalPathEngine(关键路径)
        → TaskScheduler(轮次) → 每轮: AgentMatcher 动态分配 → ExecutionLoop 执行
        → 证据落盘 → 审计 → 下一轮 (依赖就绪检查)
  输出: 同 execute_project 既有结果结构 + state.m3 = {rounds, assignments, evidence}
```

## 2. 模式切换语义

```
mode 取值: solo(默认, 旧路径零变化) | parallel(M3c) | m3(本 Sprint 全链)
默认: solo — 旧行为完全不变
开关: mode="m3" 显式启用; 失败回退: M3 链任何异常 → 降级 solo 顺序执行(诚实标注 degraded)
```

## 3. 动态分配接入点(M3-4)

```
每轮就绪叶子 → AgentMatcher.match(task, agents) 实时匹配
  (skill 匹配 × 历史成功率; 复用 agents.py AgentMatcher, 不修改)
分配落盘: state.m3.assignments[{round, task, agent_id}]
无匹配 agent → 任务标记分配失败 → 诚实报告(不伪造分配)
```

## 4. 并行与冲突

```
轮内并行: 按 rounds 执行(每轮内任务依序执行 — 线程化后置)
冲突: 轮内同文件冲突 → ConflictResolver.resolve 复用(串行化, 已在 M3c 验证)
```

## 5. 状态/证据/审计

```
- execution_state: 每任务完成回填 status/evidence(依赖就绪检查用)
- 证据: 每任务 EvidenceBundle(diff+test+决策) → evidence/ 落盘 (M1a 复用)
- 审计事件: EXECUTION_ROUND_STARTED / EXECUTION_TASK_ASSIGNED /
  EXECUTION_TASK_COMPLETED / EXECUTION_ROUND_COMPLETED / EXECUTION_M3_DEGRADED
```

## 6. 契约测试

```
tests/console/test_m3e_full_chain.py:
1. 全链: 复合任务 → decompose → critical → scheduler → 执行 → 证据落盘 (一个产品真实执行)
2. 动态分配: AgentMatcher 返回的 agent_id 落盘 assignments
3. 旧路径零变化: mode=solo → 原 TaskTree 流程 (行为不变)
4. 单任务失败不中断: 轮内一个任务失败 → 下一轮继续 (诚实标注失败)
5. 冲突串行: 同文件任务不同轮 (ConflictResolver 生效)
6. 失败回退: M3 链异常 → 降级 solo + degraded 标注
```

## 7. Codex Scope

| 文件 | 动作 |
|---|---|
| `factory-console/session/orchestrator.py` | ★改造: execute_project 增加 mode="m3" 全链分支 (默认 solo 零变化) |
| `factory-console/session/agents.py` | 只读复用 AgentMatcher(不修改) |
| `factory-console/audit/audit_event.py` | 新增 5 事件 |
| `tests/console/test_m3e_full_chain.py` | ★新建 |
| 版本文件 | → v1.1.15 |

## 8. 边界(不做)

- ❌ 并行执行线程化(轮内仍依序, 线程后置)
- ❌ 原子沙箱改造
- ❌ M3f / M3g(后续)
- ✅ 向后兼容: solo 路径零变化; M3 链异常降级

## 验收标准(Hermes 独立验证, 全链实测)

```
1. 一个产品真实执行: 复合任务 → M3 链 → 真实执行(非只算轮次) → 项目目录有产物
2. 动态分配断言: assignments 每任务有 agent_id (AgentMatcher 实时匹配)
3. 单任务失败不中断整链 (后续轮次继续)
4. 旧路径零变化 (mode=solo 行为不变)
5. 全量回归 0 新增 + git clean + v1.1.15
```

---

# Codex 指令摘要(一条可直接执行)

```
你是 AI Factory Senior Engineer。实现 M3e 调度器接管真实执行 + 动态分配 (M3 收尾):
1) orchestrator.execute_project 增加 mode="m3" 全链分支: DecomposeEngine(复合→原子) → CriticalPathEngine(关键路径) → TaskScheduler(轮次) → 每轮就绪叶子 AgentMatcher.match 动态分配 → ExecutionLoop 执行 → 证据落盘 → 审计 → 下一轮; 默认 mode="solo" 旧路径零变化。
2) 动态分配 M3-4: 复用 agents.AgentMatcher (不修改); 分配落盘 state.m3.assignments[{round, task, agent_id}]; 无匹配 → 诚实报告不伪造。
3) 状态/证据: 每任务回填 execution_state; EvidenceBundle 落盘 (M1a 复用); 冲突轮内 ConflictResolver 串行 (M3c 复用)。
4) 审计 5 事件: EXECUTION_ROUND_STARTED/TASK_ASSIGNED/TASK_COMPLETED/ROUND_COMPLETED/M3_DEGRADED。
5) 失败安全: M3 链异常 → 降级 solo 顺序执行 (degraded 诚实标注); 单任务失败不中断整链。
6) 测试 tests/console/test_m3e_full_chain.py: 全链真实执行/动态分配断言/旧路径零变化/单任务失败不中断/冲突串行/失败回退。
7) 版本 1.1.14→1.1.15 同步 pyproject/install.sh/docs/CHANGELOG/版本断言。
8) 全量回归 0 failed (runtime flaky 除外)。Completion Report: 修改文件/测试/全链实测(产品真实执行证据)/风险/下一步。
禁止: stub/fake, 超前范围 (并行线程化/原子沙箱/M3f/M3g 不做), 修改 agents 核心, solo 路径任何变化。
```

规格: docs/sprint10/S10-097-m3e-full-chain-plan.md
