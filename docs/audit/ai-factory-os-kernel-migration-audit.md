# AI Factory OS — Kernel Migration Audit

**Date**: 2026-09-08
**Auditor**: Hermes Agent (Code Inspection)
**Status**: READ-ONLY Audit — No Code Modification

---

## 1. Executive Summary

| Question | Answer |
|----------|--------|
| Current System's Real Kernel | **agent_loop.py** (4017 lines, 38 dispatch branches, hardcoded tool schemas) |
| Target Kernel | **Production Runtime / Orchestrator** using node_runtime + capability_router + artifact_lifecycle |
| Biggest Structural Barrier | **agent_loop.py 直接控制 Execution + State + Tool Dispatch，绕过 Production Core** |

**Verdict**: 当前系统是一个**带有 Node Runtime 原型的 AI Coding Assistant**，不是 AI Factory OS。Kernel 迁移尚未开始。

---

## 2. Current Kernel — Who Controls The System

### 2.1 Real Call Graph (当前真实执行路径)

```
User Message
    ↓
WebUI /api/agent (FastAPI endpoint)
    ↓
agent_loop.run_agent() [line 3838]
    ↓
agent_loop.run_agent_native() [line 2497]
    ├─→ _resolve_active_work() [line 3711] — LLM 猜测当前工作
    │   └→ _ACTIVE_WORK_PROMPT (line 3683) — 让 LLM 猜 active_work/next_action
    │       └→ 结果写入 conv_state.json (line 2652-2656)
    │
    ├─→ tool_schemas() [line 191] — 硬编码 30+ 工具定义
    │
    ├─→ call_with_tools() [line 139] — LLM Loop
    │   ├─→ messages.append(system_prompt) [多个 system prompt 注入]
    │   ├─→ LLM decides tool_call
    │   └─→ dispatch(tool_id, args) [line 1012, 38 个 if 分支]
    │       └→ Tool Handler (硬编码, 无 Registry)
    │
    └─→ return {"answer", "calls", "evidence"}
```

### 2.2 Special Node Path (only requirement_analysis)

```
requirement_analysis_round tool (line 1924)
    ↓
agent_loop.py:dispatch (1924)
    ↓
node_runtime.get_active_run() [line 1721]
    ↓
requirement_analysis_node.run_round()
    ↓
NodeRun checkpoint/update
```

**但是**: 这个路径仍然是"tool handler 内部调用 node_runtime"，不是"Production Runtime 统一调度"。

---

## 3. Target Kernel — What Should Control The System

### 3.1 Target Call Graph (目标执行路径)

```
User: "我要做一个飞机大战"
    ↓
Conversation OS (入口)
    ↓
Intent Detection (DISCUSS/DECIDE/APPROVE/EXECUTE/...)
    ↓
Project Scope Resolution
    ↓
OS Router → Capability Discovery
    ↓
Workforce Assembly (动态组装)
    ↓
Task Tree Creation
    ↓
Node Selection/Creation
    ↓
NodeRun Creation
    ↓
Production Runtime [TARGET KERNEL]
    ├─→ Execution Loop
    │   ├─→ LLM decides next action
    │   ├─→ Capability Router → Tool Registry
    │   ├─→ Tool Executor
    │   └─→ Result → Evidence
    │
    ├─→ Checkpoint/Decision
    ├─→ WAIT (if needs human) → RESUME
    ├─→ Verification
    ├─→ Recovery (if failed)
    └─→ Completion
        ↓
    Artifact Creation
        ↓
    Artifact Lifecycle (GENERATED → STAGED → REVIEWED → APPROVED → COMMITTED → RELEASED)
        ↓
    Evidence Record
        ↓
    Event/Fact
        ↓
    Projection
        ↓
    WebUI Update
```

---

## 4. Kernel Authority Matrix

| Capability | Current Owner | Evidence | Target Owner | Status |
|------------|--------------|----------|--------------|--------|
| Intent Detection | conversation_os.py:99 | deterministic patterns | Conversation OS | ✓ OK |
| Project Scope | conv_state.json + URL hash | active_work/next_action in conv_state.json | Domain/Backend | ✗ DUPLICATE |
| Task | conv_state.json | work_items in state | Task Domain | ✗ DUPLICATE |
| Task Tree | NOT IMPLEMENTED | 无真实树结构 | Task Graph | ✗ MISSING |
| Node | agent_loop.py | 只有 requirement_analysis 走 node_runtime | Node Runtime | ✗ PARTIAL |
| NodeRun | node_runtime.py (部分) | 只有 RA Node 有 Run | Production Runtime | ✗ PARTIAL |
| Execution | agent_loop.py | 直接 LLM → tool → response | Production Runtime | ✗ WRONG OWNER |
| Agent | agent_loop.py | 作为执行主体 | Capability | ✗ WRONG OWNER |
| Workforce | NOT IMPLEMENTED | 无动态组装 | Orchestrator | ✗ MISSING |
| Tool Definition | agent_loop.py:191 | 30+ hardcoded schemas | Tool Registry | ✗ WRONG OWNER |
| Tool Dispatch | agent_loop.py:1012 | 38 if branches | Capability Router | ✗ WRONG OWNER |
| Capability Routing | capability_router.py | EXISTS but NOT USED | Capability Router | ✗ DEAD CODE |
| Artifact | artifact_lifecycle.py | EXISTS but NOT MANDATORY | Artifact Lifecycle | ✗ PARTIAL |
| Evidence | agent_loop.py (浅) | only "tool_ok" flag | Evidence Layer | ✗ PARTIAL |
| Verification | NOT IMPLEMENTED | Agent says "done" = done | Verification Runtime | ✗ MISSING |
| Recovery | recovery.py | EXISTS but NOT IN MAIN PATH | Recovery Runtime | ✗ DEAD CODE |
| State | conv_state.json (重复) | active_work/next_action 存在两处 | NodeRun only | ✗ DUPLICATE |
| Event | audit_event.py | EXISTS but NOT COMPLETE | Event/Fact Layer | ✗ PARTIAL |
| Memory | conversation history | 混用 context/evidence/memory | Experience → Memory | ✗ MIXED |
| WebUI State | Frontend useState | 真实业务状态在前端 | Backend only | ✗ P0 VIOLATION |

---

## 5. Production Primitive Audit

### 5.1 Node

| Item | Status | Evidence |
|------|--------|----------|
| Node Definition | PARTIAL | 只有 requirement_analysis 是真正 Node |
| Node Registry | PARTIAL | node_runtime.py 有 register_node() 但很少用 |
| All Work as Node | NO | 大部分 tool 调用直接走 agent_loop dispatch |

**Code Evidence**:
- `agent_loop.py:1924` — requirement_analysis_round tool handler 内注册/调用 Node
- `node_runtime.py:74` — register_node() 定义但使用有限

### 5.2 NodeRun

| Item | Status | Evidence |
|------|--------|----------|
| NodeRun Creation | PARTIAL | 只在 requirement_analysis 路径 |
| Checkpoint | PARTIAL | node_runtime 有接口但只有部分使用 |
| Resume | PARTIAL | 只有 requirement_analysis 有 WAIT/RESUME |
| Decision | PARTIAL | node_runtime.py:238 transition_node_run 有 Decision |

**Code Evidence**:
- `node_runtime.py:128` — create_node_run()
- `node_runtime.py:238` — transition_node_run()
- `node_runtime.py:405` — finalize_node_run()

### 5.3 Execution

| Item | Status | Evidence |
|------|--------|----------|
| Execution as Loop | NO | LLM → tool → response 不是真正的 Production Loop |
| Run Tracking | PARTIAL | 只有 Node Run 有跟踪 |
| Who/What/Why/Result | NO | 无法追踪完整 Execution context |

**Code Evidence**:
- `agent_loop.py:139` — call_with_tools() 是简单 LLM Loop
- 无 Run 概念（只有 NodeRun）

### 5.4 Artifact

| Item | Status | Evidence |
|------|--------|----------|
| Artifact Lifecycle | PARTIAL | artifact_lifecycle.py 存在但未强制使用 |
| Mandatory Lifecycle | NO | 很多执行绕过 Artifact |
| Artifact First | NO | Agent 输出只是 "answer" |

**Code Evidence**:
- `artifact_lifecycle.py` 存在完整 lifecycle (GENERATED → ... → RELEASED)
- `agent_loop.py:2958` 只有简单 evidence 标记

### 5.5 Evidence

| Item | Status | Evidence |
|------|--------|----------|
| Structured Evidence | NO | 只有 {"tool": x, "ok": y, "output": z} |
| Source/Verifier/Result | NO | 无完整 Evidence 模型 |
| Evidence-based Verification | NO | 无 Verification 链 |

**Code Evidence**:
- `agent_loop.py:2958` — evidence = [{"tool": c["tool"], "ok": c["ok"], "output": ...}]

### 5.6 Verification

| Item | Status | Evidence |
|------|--------|----------|
| Automated Verification | NO | Agent 自己说 "done" |
| Evidence-based Verify | NO | 无 pytest/pass/fail 验证 |
| Agent vs System Verdict | NO | Agent 拥有最终裁决权 |

**Status**: NOT IMPLEMENTED (P0)

### 5.7 Recovery

| Item | Status | Evidence |
|------|--------|----------|
| Recovery Runtime | PARTIAL | recovery.py 存在但不在主流程 |
| Auto Recovery | NO | 需要手动触发 |
| Replan/Rethink | NO | 只有简单 retry |

**Code Evidence**:
- `recovery.py` 完整实现 (analyze, recover, resume)
- `agent_loop.py:2644` 有 _recovery 但不是自动触发

---

## 6. State Ownership Audit

### 6.1 Backend vs Frontend State

| State | Current Owner | Target Owner | Migration Required |
|-------|--------------|--------------|-------------------|
| currentProject | Frontend useState (AfWorkspace.tsx:86) | Backend Domain | YES (P0) |
| tasks | Frontend useState (AfWorkspace.tsx:250,568) | Task Domain | YES (P0) |
| artifacts | Frontend useState (AfWorkspace.tsx:86,427) | Artifact Domain | YES (P0) |
| status | Frontend useState (AfWorkspace.tsx:366) | Run/Execution | YES (P0) |
| diffs | Frontend useState (AfWorkspace.tsx:531) | Artifact/Git | YES (P0) |
| approvals | Frontend useState (AfWorkspace.tsx:675) | Governance | YES (P1) |

### 6.2 Backend Duplicate State

| State | Location 1 | Location 2 | Should Be |
|-------|-----------|-----------|-----------|
| active_work | conv_state.json | NodeRun.checkpoint | NodeRun ONLY |
| next_action | conv_state.json | NodeRun.checkpoint | NodeRun ONLY |
| current_stage | conv_state.json | NodeRun.checkpoint | NodeRun ONLY |
| need_user_input | conv_state.json | NodeRun.state | NodeRun ONLY |

**Code Evidence**:
- `agent_loop.py:2652-2656` — 写入 conv_state.json
- `node_runtime.py` — checkpoint 在 NodeRun 内

---

## 7. agent_loop.py Demotion Plan

### 7.1 Current Responsibilities (4017 lines)

```
✓ Message entry point (run_agent/run_agent_native)
✓ Intent detection (indirect via _GOVERN_PROMPT)
✓ Tool definition (30+ hardcoded schemas)
✓ Tool dispatch (38 if branches)
✓ State management (conv_state.json read/write)
✓ Active work inference (_ACTIVE_WORK_PROMPT)
✓ Product truth read/write (via tool)
✓ Task management (via tool)
✓ Project management (via tool)
✗ Node Runtime (partial: only requirement_analysis)
✗ Capability Router (exists but unused)
✗ Unified Tool Registry
✗ Production Run
✗ Artifact Lifecycle (not mandatory)
✗ Verification
✗ Recovery (not in main path)
```

### 7.2 Target Responsibilities (After Demotion)

```
agent_loop.py 应该只负责:
✓ 作为 Agent/Capability 被 Production Runtime 调用
✓ 提供 tool_schemas() 作为 Capability Registry 的数据源
✓ 提供 LLM execution capability
✓ 不保存任何业务状态 (删除 conv_state.json)
✓ 不做 active_work 推断 (删除 _ACTIVE_WORK_PROMPT)
✓ 不做 tool routing (由 Capability Router 接管)
✓ 不做 workflow orchestration (由 Orchestrator 接管)
```

### 7.3 Demotion Boundary

| Current | Target | Migration |
|---------|--------|-----------|
| tool_schemas() 硬编码 | 迁移到 Tool Registry (YAML/JSON) | Phase 2 |
| dispatch() 38 if 分支 | 迁移到 Handler Registry | Phase 2 |
| _ACTIVE_WORK_PROMPT | 删除，依赖 NodeRun checkpoint | Phase 1 |
| conv_state.json | 删除，业务状态移至 NodeRun | Phase 1 |
| run_agent() 主入口 | Production Runtime 主入口 | Phase 1 |
| LLM Loop | 变成 Production Runtime 的执行引擎 | Phase 3 |

---

## 8. Tool Dispatch Migration

### 8.1 Current (Hardcoded)

```python
# agent_loop.py:1012-2445
def dispatch(tool_id, args, ...):
    if tool_id == "plan_development":
        return handle_plan_development(...)
    elif tool_id == "scan_todos":
        return handle_scan_todos(...)
    # ... 38 个 if 分支
```

### 8.2 Target (Registry + Router + Handler)

```
Capability Router
    ↓
Tool Registry (YAML/JSON)
    ↓
Handler Registry (Plugin Kernel)
    ↓
Executor
    ↓
NodeRun
```

### 8.3 Migration Path

1. **Extract** tool_schemas() → Tool Registry (JSON)
2. **Extract** dispatch handlers → Handler Registry (separate files)
3. **Activate** capability_router.py usage in agent_loop
4. **Redirect** dispatch() → lookup from Registry
5. **Delete** hardcoded branches

---

## 9. Project Scope Migration

### 9.1 Current Problem

- URL hash 变化
- Dropdown 变化
- Workspace 变化
- Session scope 不变
- Execution scope 不变
- Backend Project 关联可选

### 9.2 Target Architecture

```
Project (Domain Entity)
    ↓ 1:1
Conversation
    ↓ 1:N
Session
    ↓ 1:N
Task Tree
    ↓ 1:N
NodeRun
    ↓ 1:N
Execution
    ↓ 1:1
Artifact
    ↓ 1:1
Evidence
```

### 9.3 Migration

1. Conversation 必须关联 Project (mandatory)
2. Task/NodeRun 必须继承 Project Scope
3. 选择 Project 时所有 scope 一致变化
4. 删除前端 project state，改为 URL parameter + Backend lookup

---

## 10. Migration Classification

| Module | Classification | Action |
|--------|---------------|--------|
| conversation_os.py | KEEP | 入口正确，需加强与 Production Core 集成 |
| node_runtime.py | ACTIVATE | 架构正确，提升为主 Runtime |
| capability_router.py | ACTIVATE | 存在但未使用，激活并集成 |
| artifact_lifecycle.py | ACTIVATE | 存在但非强制，改为强制执行 |
| recovery.py | ACTIVATE | 存在但非主流程，集成到 Runtime |
| product_truth.py | KEEP | 正确，保持 |
| audit_event.py | REFACTOR | 需完善作为 Event/Fact Source |
| agent_loop.py | DEMOTE | 从 Kernel 降级为 Capability |
| conv_state.json | DELETE | 与 NodeRun 重复 |
| _ACTIVE_WORK_PROMPT | DELETE | LLM 猜测，应依赖真实状态 |
| frontend useState (Business State) | DELETE/MIGRATE | 改为 Backend 驱动 |

---

## 11. Smallest Viable Kernel Migration

### Phase 0: Audit & Freeze (Current)

- 完成本审计报告
- 冻结 agent_loop.py 新功能
- 不再往 agent_loop.py 添加代码

### Phase 1: Kernel Boundary (Week 1-2)

**目标**: 建立 Production Runtime 作为真正 Kernel

| Task | Deliverable |
|------|-------------|
| 1.1 删除 _ACTIVE_WORK_PROMPT | agent_loop 不再猜测 active_work |
| 1.2 删除 conv_state.json 业务状态 | 状态全部移至 NodeRun |
| 1.3 修改 conversation_os 触发执行 | 从模板回复变为调用 Production Runtime |
| 1.4 建立 Production Runtime 入口 | production_runtime.py 作为统一入口 |

**验收 Test A**: 用户说"我要做飞机大战" → 进入 Production Runtime

### Phase 2: First Vertical Slice (Week 2-3)

**目标**: 一个真实 Production Node 端到端

| Task | Deliverable |
|------|-------------|
| 2.1 选择最小 Node (如 Create Spec 或 Requirement Analysis) | 完整经过 NodeRun |
| 2.2 集成 capability_router | Tool 选择经过 Router |
| 2.3 集成 artifact_lifecycle | 输出强制经过 Artifact |
| 2.4 集成 evidence | 执行产生结构化 Evidence |

**验收 Test B**: 用户 Intent → Node → NodeRun → Execution → Artifact → Evidence (全部真实)

### Phase 3: Universal Node Runtime (Week 3-4)

**目标**: 所有 Node 使用相同 Runtime

| Task | Deliverable |
|------|-------------|
| 3.1 Node 定义为配置 | 不再 hardcode Node 类型 |
| 3.2 所有 Tool 调用经过 Node Runtime | 统一执行路径 |
| 3.3 统一 WAIT/RESUME | 所有 Node 支持 Human-in-loop |
| 3.4 统一 Checkpoint | 所有 Node 有状态累积 |

**验收 Test C**: 任意新 Node 都自动获得 Runtime 能力

### Phase 4: Artifact + Evidence + Verification (Week 4-5)

**目标**: 真正的生产验证链

| Task | Deliverable |
|------|-------------|
| 4.1 强制 Artifact Lifecycle | 所有输出必须经过 lifecycle |
| 4.2 结构化 Evidence | evidence = {source, execution, artifact, verifier, result, confidence} |
| 4.3 Verification Runtime | 独立验证，不依赖 Agent 声称 |
| 4.4 Recovery Integration | 验证失败自动触发 Recovery |

**验收 Test D**: Execution → Artifact → Evidence → Verification → Recovery (全链路)

### Phase 5: Event / Projection / WebUI (Week 5-6)

**目标**: 干净的数据流

| Task | Deliverable |
|------|-------------|
| 5.1 迁移 WebUI State | 前端只有 Projection，无业务状态 |
| 5.2 完善 Event Layer | 所有动作产生 Event |
| 5.3 Project Scope 统一 | 选择 Project → 全局 scope 一致 |
| 5.4 删除 conv_state.json | 完全移除重复状态 |

**验收 Test E**: WebUI 永远不成为 Source of Truth

### Phase 6-8: Workforce / Learning / Governance (Future)

| Phase | Target |
|-------|--------|
| Phase 6 | Dynamic Workforce Assembly |
| Phase 7 | Experience → Memory → Learning |
| Phase 8 | Enterprise Governance |

---

## 12. P0 Migration Blockers

| Blocker | Description | Solution |
|---------|-------------|----------|
| P0-1 | agent_loop.py 作为 Kernel 控制 Execution | Phase 1 建立 Production Runtime 入口 |
| P0-2 | conv_state.json 保存业务状态与 NodeRun 重复 | Phase 1 删除，迁移到 NodeRun |
| P0-3 | _ACTIVE_WORK_PROMPT 让 LLM 猜测状态 | Phase 1 删除，依赖 NodeRun |
| P0-4 | Frontend useState 包含真实业务状态 | Phase 5 迁移到 Backend 驱动 |
| P0-5 | 无Verification链，Agent 自己说 done | Phase 4 实现 Verification Runtime |
| P0-6 | Tool 完全硬编码，无 Registry | Phase 2 建立 Tool Registry |

---

## 13. Acceptance Criteria

### Test A: User Intent → OS Runtime

```
User: "我要做一个飞机大战"
System: 不需要指定 Agent/Tool/Project
Result: 进入 Production Runtime (不是 agent_loop 直接执行)
```

### Test B: Task → Task Tree

```
User triggers work
Result: Task 进入 Task Tree，不是直接执行
```

### Test C: Node → NodeRun

```
Any Node execution
Result: 创建 NodeRun，有 checkpoint，状态可查询
```

### Test D: Execution → Artifact → Evidence

```
Tool execution
Result: 产生 Artifact (有 lifecycle) + Evidence (结构化)
```

### Test E: Verification Executed

```
Execution completes
Result: Verification 真正执行，不只是 Agent 说 "done"
```

### Test F: Verification Fail → Recovery

```
Verification fails
Result: 自动触发 Recovery 流程
```

### Test G: WebUI Not Source of Truth

```
Check frontend state
Result: 只有 Projection，无业务状态
```

### Test H: Project Scope Consistent

```
Select Project
Result: Conversation/Session/Task/Run/Artifact scope 一致变化
```

### Test I: agent_loop.py Not Kernel

```
Check execution path
Result: agent_loop 作为 Capability 被调用，不是 Orchestrator
```

---

## 14. Final Verdict

```
KERNEL MIGRATION STATUS

OLD KERNEL: agent_loop.py (完全控制 Execution + State + Tool)

TARGET KERNEL: Production Runtime (node_runtime + capability_router + artifact_lifecycle)

CURRENT STATUS: NOT STARTED

FIRST MIGRATION BOUNDARY:
删除 _ACTIVE_WORK_PROMPT + conv_state.json 业务状态
建立 Production Runtime 入口
修改 conversation_os 调用 Production Runtime

P0 BLOCKERS:
1. agent_loop.py 直接控制 Execution
2. 重复状态 (conv_state.json vs NodeRun)
3. LLM 猜测状态而非读取真实状态
4. 前端业务状态
5. 无 Verification 链
6. Tool 硬编码

RECOMMENDED NEXT ACTION:
开始 Phase 1: Kernel Boundary
- 删除 _ACTIVE_WORK_PROMPT (line 3683-3753)
- 删除 active_work/next_action 写入 conv_state.json (line 2652-2656)
- 验证 requirement_analysis 路径可用
```

---

## Conclusion

**System is NOT currently AI Factory OS. It's an AI Coding Assistant with a Node Runtime prototype.**

The kernel migration has NOT started. The first step should be:

1. **Delete** the duplicate state mechanism (_ACTIVE_WORK_PROMPT + conv_state.json)
2. **Build** Production Runtime as the true kernel entry point
3. **Integrate** conversation_os with Production Runtime (not agent_loop directly)
4. **Activate** existing Production Core (node_runtime, capability_router, artifact_lifecycle, recovery)

**Option: B** — Need to fix Production Core Contract before full migration, but Phase 1 (Kernel Boundary) can start immediately.