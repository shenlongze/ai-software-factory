# S30-002 — Conversation / Session / Execution Architecture Convergence (审计)

> 日期: 2026-08-31 | 阶段: 审计 + 架构决策 (零代码修改)

---

## 一、已确认架构事实 (S30-001 + S30-ARCH)

- Backend: 唯一 8011
- UI: frontend (Web) + desktop (Tauri), 无散落/无强耦合
- Runtime: 8011 API + 5180 static + 5173 dev (非 duplication)
- **sessions = 真实 LLM Conversation Runtime** (S30-001 六项全 PASS)

---

## 二、P0-1: Conversation / Session 职责分离

### 目标模型

```
Conversation (长期语义上下文)
  │ 1:N
  ▼
Session (一次 interaction, messages/streaming/active run)
  │
  ▼
Run (一次真实执行)
  │
  ▼
Task / NodeRun → Artifact → Verification / Evidence
```

### 职责定义

| 对象 | 职责 | 现状 |
|------|------|------|
| **Conversation** | 用户长期上下文/Project context/决策历史/Session 分组 | ⚠️ conversation_os 规则链路 (弱) |
| **Session** | 一次 interaction/messages/streaming/active run | ✅ console_sessions (真实 LLM) |
| **Run** | 一次真实执行生命周期 | ✅ production_run |

### P0-1.1: conversations 消费者审计

| 消费者 | 类型 | 判定 |
|--------|------|------|
| golden_suite.py | 测试套件 | KEEP (语义对象) |
| conversation_quality.py | 质量报告 | KEEP (语义对象) |
| project_os.py (extract_requirement) | 需求提取 | MIGRATE (接 session) |
| task_tree.py | 任务树 | MIGRATE |
| cli_factory.py (conv 命令) | CLI | DEPRECATE (指向 session) |
| fastapi_adapter /api/conversations | API | DEPRECATE (WebUI 已用 sessions) |
| ConversationPage.tsx (旧页面) | 前端 | REMOVE (已被 V2 取代) |
| tests (operational_state/k7/project_os/control_tower) | 测试 | KEEP (测试语义层) |

### P0-1.2: 禁止双事实

**现状**: sessions → 真实 LLM; conversations → 规则模板。
**目标**: WebUI 只走 sessions (S30-001 已验证)。conversations 保留为**上层语义对象**, 不承担第二套 LLM Runtime。

### P0-1.3: conversation_os 迁移

```
不删除。重新定位:
  conversation_os = Conversation Application/Context Layer
  (长期语义/决策历史/需求提取)
  但 WebUI Runtime = sessions (唯一 LLM 链路)
```

---

## 三、P0-2: Execution 收敛

### 现状 (三件套)

| 模块 | 职责 | 判定 |
|------|------|------|
| workforce.py | 角色定义 + create_task (唯一 Orchestrator) | **KEEP 唯一 Orchestrator** |
| workflow_runner | 项目级工作流 (start_project_workflow, 后台线程) | KEEP (工作流定义) |
| professional_workflow | 专业 Agent executor factory (LLM 执行器) | KEEP (执行器) |

### 真实调用链

```
Entry: POST /projects/{id}/start → workflow_runner.start_project_workflow
  ↓ (后台线程)
Orchestrator: workforce.py (角色/权限/任务)
  ↓
Workflow: workflow_runner (pm→dev→tester→release 阶段)
  ↓
Task: workforce.create_task
  ↓
Node: 阶段节点
  ↓
Executor: professional_workflow.build_llm_executor_factory (LLM + codex)
  ↓
Artifact: artifact_lifecycle.create_artifact
  ↓
Verification: verification.py
```

### P0-2.1: 职责重叠?

- **workflow_runner vs professional_workflow 不重复**: 前者是"工作流编排", 后者是"执行器工厂" — 互补, 非双引擎
- **真问题**: 7 处直接调 create_production_run (conversation_os/adaptive_workforce/agent_kernel/effectiveness/self_healing/production_service) — Run 创建入口分散

### 结论

**唯一 Execution Semantics 基本成立** (workflow_runner 编排 + professional_workflow 执行)。
**改进**: 统一 Run 创建入口 (收敛到 production_run.create_production_run 单一门面)。

---

## 四、P0-3: 一级关联现状

```
conversation_id → session_id → run_id → task_id → node_run_id → artifact_id → verification_id
```

| 关联 | 现状 | 缺口 |
|------|------|------|
| session → messages | ✅ sessions_store | — |
| session → run | ⚠️ session 有 project_id, 无 run 直接关联 | 🔴 缺 |
| run → task | ✅ production_run | — |
| task → node_run | ✅ node_runtime | — |
| node → artifact | ✅ artifact_lifecycle | — |
| artifact → verification | ✅ verification.py | — |

**P0-3 缺口**: session ↔ run 无直接关联 — 需在 session 持久化 run_id (下阶段)。

---

## 五、最终回答 (14 问)

1. **Conversation 职责**: 长期语义/决策/项目上下文 (应用层)
2. **sessions 唯一 Runtime**: ✅ 是 (S30-001 六项验证)
3. **conversations 处置**: KEEP (语义层), 不承担 LLM Runtime
4. **conversation_os 处置**: 重定位为 Application/Context Layer
5. **workflow_runner 处置**: KEEP (工作流编排)
6. **professional_workflow 处置**: KEEP (执行器工厂)
7. **workforce.py 唯一 Orchestrator**: ✅ 是
8. **唯一 Execution Semantics**: ✅ 基本成立 (workflow_runner + professional_workflow 互补)
9. **一级关联完整**: ⚠️ 差 session↔run (P0-3)
10. **进入 UI Integration**: ⚠️ 需先补 session↔run 关联

## 六、本阶段不执行

- 不删 conversations/conversation_os/workflow_runner/professional_workflow
- 不迁移目录 / 不新增 Backend/Port/Orchestrator
- 不改 Production Core Contract
