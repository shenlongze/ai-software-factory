# S7-005 — Full Chain Demo（Completion Report）

> 日期: 2026-08-09 | 状态: 完成 (待人工审核) | pytest 6018 (5988 + 30)
> 目标: 组织级全链集成验证 — Product→Architecture→Development→Testing→Release
> 5 阶段链 + Artifact 链 (前输出→后输入 VALIDATED) + Runner 自动推进 +
> Tester Loop (失败→修复→成功 ≤2 轮)

## 实现概述

```
S7-005 是集成验证 (非新增能力): 复用 S7-003 编排壳 (WorkflowLifecycle/
WorkflowRunner/DevTestLoopRunner) + S7-004 TesterAgent + S7-002 Artifact
契约, 组合出可复现的 Demo 全链。零重写 (EmployeeExecutor/Workflow/
Artifact/Tester 只组合); 不实现 PM/Architect/Release Agent 自动化 (Sprint 8)。
```

## 新增文件

```
factory-org/org/demo.py                        (Demo 定义/构造: 5 阶段链 + loop 变体
                                                + mock executors + 组合适配)
tests/s7/test_s7_full_chain_demo.py            (30 测试)
docs/sprint7/implementation/S7-005-report.md   (本报告)
```

## 完整流程图

```
User (Demo 想法: "示例产品")
  ↓
Project P-1 (生命周期容器)
  ↓
Workflow (Full Chain Demo — 编排壳, DRAFT → ACTIVE → COMPLETED)
  ├─① Product      (product-manager, mock executor — 非 LLM 占位)  → PRD  A-DEMO-PRD
  │     ↓ input = A-DEMO-PRD (VALIDATED)
  ├─② Architecture (architect,      mock executor — 非 LLM 占位)  → Design A-DEMO-DESIGN
  │     ↓ input = A-DEMO-DESIGN (VALIDATED)
  ├─③ Development  (developer,      mock executor — 确定性版本轨迹) → Code  A-DEMO-CODE
  │     │           (真实写文件: calc.py + test_calc.py)
  │     ↓ input = A-DEMO-CODE (VALIDATED)
  ├─④ Testing      (tester,         真实 TesterAgent — 确定性 pytest
  │     │           + mock LLM 失败分析, 生产 = DeepSeek v4-pro)   → Test A-DEMO-TEST
  │     │          失败 → bug_report → repair task (≤2 轮, 禁无限)
  │     │          ← Dev↔Tester Loop: repair(developer) → retest(tester)
  │     ↓ input = A-DEMO-TEST (VALIDATED)
  ├─⑤ Release      (devops,         mock executor — 非 LLM 占位)  → Release A-DEMO-RELEASE
  │     ↓
  Artifact 链: PRD → Design → Code → Test → Release (每阶段产物 = 下一阶段输入)
```

## Artifact 链 (前输出 → 后输入, VALIDATED)

| Stage | role_id | 输入 (id 引用) | 输出 (id) | 契约 (CONTRACTS) | 状态 |
|---|---|---|---|---|---|
| Product | product-manager | — | A-DEMO-PRD | problem/user/features | VALIDATED |
| Architecture | architect | A-DEMO-PRD | A-DEMO-DESIGN | architecture/api/database | VALIDATED |
| Development | developer | A-DEMO-DESIGN | A-DEMO-CODE | files/changes + project_dir | VALIDATED |
| Testing | tester | A-DEMO-CODE | A-DEMO-TEST | results.passed/bugs | VALIDATED |
| Release | devops | A-DEMO-TEST | A-DEMO-RELEASE | version/notes/artifact_ref | VALIDATED |

```
断言 (test_artifact_chain_input_equals_prev_output):
  architect 输入 = [A-DEMO-PRD, validated]   (Product 输出)
  developer 输入 = [A-DEMO-DESIGN, validated] (Architecture 输出)
  tester    输入 = [A-DEMO-CODE, validated]   (Development 输出)
  devops    输入 = [A-DEMO-TEST, validated]   (Testing 输出)
每阶段 input_artifacts 预定义 = 前阶段输出 id; Runner 就绪判定要求全部
VALIDATED (未验证 → BLOCKED); 跨项目输入拒绝 (项目隔离铁律)。
```

## Workflow 执行记录 (状态转换 + 事件)

### 全链 happy path (WF-1, base WorkflowRunner 一次 run)

```
Workflow: DRAFT → ACTIVE (org.workflow.started) → ... → COMPLETED
Stage 状态转换 (每阶段, 幂等受控转换表):
  PENDING → READY (org.workflow.stage_ready)  依赖满足 + 输入 VALIDATED
  READY   → RUNNING (org.workflow.stage_started) executor 调用
  RUNNING → COMPLETED (org.workflow.stage_completed) 输出产物自动注册
           (create → generated → validated, org.artifact.validated ×5)
事件计数: stage_ready=5, stage_started=5, stage_completed=5,
         artifact.validated=5, workflow.started=1, workflow.completed=1
```

### Tester Loop 变体 (WF-L, DevTestLoopRunner — 失败→修复→成功)

```
Development (dev, buggy v0) → Testing (test: pytest 2 failed)
  → TesterAgent 确定性执行 → 失败 → LLM 失败分析 (mock v4-pro 契约, 1 次)
  → bug_report 产物 (location/repro/expected/actual/root_cause/severity)
  → repair task 回传 → 动态创建 repair 1 (developer, 输入 = bug_report)
  → 自动接线 → repair 1 (dev, fixed v1) → retest 1 (tester, pytest 全通过)
  → 质量门禁通过 (bugs=[]) → Release 推进 → COMPLETED
修复轮数 = 1 (≤2, DEFAULT_MAX_REPAIR_ROUNDS); 无第 4 轮测试 (计数保护)
动态阶段全部 org.stage.created 审计 (阶段可追踪)
```

## 测试结果

```
pytest 全量: 6018 passed, 0 failed (5988 基线 + 30 新增)
新增 30 测试分布:
  TestDemoWorkflowDefinition   8  (5 阶段链/depends_on/输入预定义/拓扑序/loop 变体/角色注册)
  TestMockExecutors            6  (mock 产物契约 + dev 写文件/轮次轨迹 + tester 组合适配)
  TestFullChainRunner          7  (全链完成/Artifact 链断言/状态事件/事件序列/产物归属/真实 pytest/幂等)
  TestTesterLoopDemo           6  (失败→修复→成功/bug_report/repair 记录/release 推进/≤2 轮/末轮通过)
  TestDemoLimits               3  (planning 角色 mock 标注/零 LLM 调用/未知角色响亮失败)
执行: 真实 pytest 子进程 (确定性, 不靠 LLM 猜测试结果); 失败分析 mock
provider (v4-pro 契约, 不调真实 LLM); Core/Runtime/Desktop diff = 0
```

## 当前限制 (诚实标注)

```
1. PM/Architect/Release Agent 未自动化 (Sprint 8): 对应阶段用 mock executor
   (非 LLM 占位语义) — 对应角色 execution_kind=planning; 本 Sprint 是集成
   验证链正确性, 角色能力由 Sprint 6.5 (v4-pro) / S7-004 (Tester) 证明
2. Developer mock: 注入确定性版本轨迹 (buggy→fixed), 非 LLM 生成 —
   Developer 真实能力由 Sprint 6.5 exec 引擎 (AgentRuntime/验证闭环) 证明
3. Tester LLM 失败分析: Demo 用 mock provider (契约等价), 生产 = DeepSeek
   v4-pro — 集成链验证不消耗真实 LLM 成本
4. Release 产物占位: version/notes/artifact_ref 为 mock 语义, 无真实构建
5. 仅线性链演示: Demo 5 阶段为顺序 depends_on; 并行分支/人工闸门路径由
   S7-003 既有测试覆盖 (blocked/重试/失败路径), 本 Demo 不重复
6. Artifact 链引用结构验证 (id + VALIDATED), 不验证产物内容质量
   (质量验证 = 确定性 pytest 执行, 内容语义超出本 Sprint 范围)
```

## 下一步 (Sprint 8)

```
PM/Architect/Release Agent 自动化 (planning → executable, v4-pro)
→ 全链真实 LLM 执行 (无 mock) → 真实小项目端到端 Demo
```
