# AI Factory OS — 项目全身 CT 审计(平行/重复体系盘点)

> Date: 2026-09-08 | 性质: 只读审计, 零代码改动 | 执行: Hermes
> 触发: "task tree 前后逻辑/作用是否一致? 项目中类似情况还有多少? 做全身 CT"
> 方法: 模块地图 + 状态机签名提取 + import 消费图谱 + 入口接触面统计
> ⚠️ 审计时工作区有并发未提交改动(golden_path.py M、task_decomposition.py untracked) — 未触碰

---

## 0. 总判定

**项目存在 10 个平行/重复体系家族, 合计 40+ 个同职能模块, 其中约一半有生产消费(活), 一半仅测试/历史(滞留)。**
不是"设计多态", 而是**多轮迭代各自落盘、未收敛**的产物。task_tree 问题只是冰山一角。

规模: factory-console 平铺 ~120 模块 + session/ ~130 模块 + 子包(audit/memory/external_executor/retrieval)。
模块总数 250+, 远超一个收敛平台的合理规模。

---

## 1. 家族盘点(按"逻辑是否一致 × 作用是否一致"分级)

### 🔴 家族 A: Task Tree / 任务拆解 — 4 套(用户问的)

| 成员 | 逻辑(状态机/结构) | 作用 | 落盘 | 生产消费 | 一致性 |
|------|------------------|------|------|---------|--------|
| session/decomposer.py | 递归原子拆解(depth≤5/tasks≤64/cycle_detect/LLM注入) | 拆到原子叶 | projects/<slug>/decomposition.json | change_control/actions/orchestrator(session旧链) | 逻辑独立完整 |
| task_tree.py(K2) | parent/children 两级 + depends_on + progress | conv_* 系任务树 | S43 task_ 实体(ops/) | golden_suite/cli_factory/project_os/API | 依赖 conversation_os |
| golden_path._derive_plan_tasks | **单层**(PRD 一句=一 task, 无树) | 新链 Plan.tasks | product_truth PLAN-*.tasks[] | golden_path | **作用重叠但逻辑降级(2/7根源)** |
| task_decomposition.py(新,未提交) | Project→Domain→Leaf 多级 + change_type + expected_files + depends_on | 新链计划层组织 | task_trees/{plan_id}.json | golden_path/canonical(接入中) | 声称 canonical |

**结论**: 逻辑上 4 套各不同(原子/两级/单层/多级), 作用上 session→旧链、golden_path→新链 各归其主; 但 task_tree(K2) 与 task_decomposition(新) **作用重叠**, decomposer 的原子拆解智慧未被新域复用 → **部分一致, 收敛未完成**。

### 🔴 家族 B: Conversation Runtime — 4+ 套

| 成员 | 状态机 | 生产消费 |
|------|--------|---------|
| conversation_os.py(conv_*) | INTENTS + 自有实体 | API legacy 端点 + CLI chat + project_os + task_tree |
| conversation_app.py(conv-*) | Fact/Understanding 语义 | canonical_golden_path + API PU 端点(仅) |
| session/conversation.py(ConversationManager) | ConversationState(DISCOVERY等) | session/session.py(CLI REPL) |
| console_sessions.py + session/agent_loop.py | ExecState/agent_loop | WebUI /api/sessions |
| golden_path.py(新链编排) | Plan/NodeRun | canonical_golden_path |

**结论**: 逻辑全不同(Intent/Fact/Discovery/ExecState/Plan), 作用=4 个入口各接一套 → **不一致(表现层分叉)**, 与 R0 审计一致。新域 conv- 无 API 创建入口 → 半断链。

### 🔴 家族 C: 执行 Runtime — 4 套

| 成员 | 状态机 | 消费 |
|------|--------|------|
| node_runtime.execute_node_run | PENDING→RUNNING→VERIFYING→REPAIRING→COMPLETED/FAILED + WAITING | 12 处(核心,已收敛为单节点内核) |
| production_runtime.execute_task | 同上(薄封装) | golden_path + conversation_os |
| production_run(register_workflow/execute_production_run) | PENDING/RUNNING/COMPLETED/FAILED/BLOCKED + depends_on/input_binding/resume | 24 处(图编排,最强但未裁决) |
| workflow_runner.start_project_workflow | 旧 workflow 链 | service/professional_workflow |
| session/agent_loop | 自有 ExecState | WebUI |

**结论**: node_runtime 单节点已收敛✅, 但计划级(production_run vs golden_path 循环 vs workflow_runner)**三入口并行**, 状态机签名几乎相同(PENDING/RUNNING/COMPLETED/FAILED) → **逻辑近似重复, 作用未归并**。

### 🔴 家族 D: 产品事实/理解 — 4 套

| 成员 | 状态 | 消费 |
|------|------|------|
| product_truth.py | idea/discovery/requirement/prd/plan 六层正式域 | golden_path/requirement_node/cli_factory/agent_loop/API |
| product_understanding.py(conv-*) | Fact(PROPOSED/CONFIRMED/DEFERRED…) | semantic_proposal/golden_path/canonical/conversation_app |
| session/product.py + session/discovery.py | ProductIntent/DiscoveryState(旧) | session 旧链(13 处) |
| session/product_intelligence.py | Industry/Competitor/Persona 分析 | session 系 |

**结论**: product_truth(正式资产) 与 product_understanding(会话认知)**语义分层**(S49 裁决), 逻辑一致✅; 但 session/product+discovery(旧链) 与新域**作用重叠未退休** → 部分不一致。

### 🔴 家族 E: Workforce/Agent — 6 套(最碎片)

workforce.py + workforce_os.py + workforce_composition.py + adaptive_workforce.py + session/agents.py + session/expert_factory.py + agent_kernel.py + session/pipeline_runner.py + session/agent_entity.py + agent_policy.py
→ 仅 workforce* 系就 4 个平铺模块, 状态机 workforce_os(DRAFT/ACTIVE/…) 与 agent_kernel(PENDING…BLOCKED) 不同;
expert_factory.PIPELINE_ROLES(7 角色) 是 Codex 审计点名"存在未接"。

### 🔴 家族 F: 验证 — 3 份 pytest runner

verification.py(verify_pytest) + verification_domain.py(落盘) + 生产消费 5+4 处; session/quality.py(Validator/Reviewer/RepairManager) + professional_workflow/external_executor 各藏 runner → **同一职能 3+ 实现**(Codex §5.4 指出)。

### 🟡 家族 G: 恢复 — 3 套

recovery.py(analyze/recover) + recovery_service.py(recover_production_run,落 ops) + self_healing.py(incident→repair,落 ops) + rollback_service.py → 消费分散(recovery_service 被 CLI/API 用, recovery 被 production_service 用)。

### 🟡 家族 H: 治理 — 2 套

governance_service.py(request_approval/decide,落 approvals.json, 13 消费) vs session/approval_store.py(仅 agent_loop) → **governance_service 已事实收敛, approval_store 滞留**。

### 🟡 家族 I: Memory/Learning — 6 套

memory/experience_store + session/memory_core + session/project_memory + session/context_ledger + experience_bridge + learning_truth + learning_engine_v2 + production_experience + context_intelligence → 9 个模块横跨, 落盘 memory/learning/experiences 三处。

### 🟡 家族 J: Project — 2 套

project_os.py(P-*/sprint/replan/approval, 完整) vs golden path "conv-即项目"(无真实项目注册) + session/workspace + repo_mode → Codex §5.2 "项目双轨"。

---

## 2. 量化结论(回答"类似情况还有多少")

| 指标 | 数值 |
|------|------|
| 平行/重复体系家族 | **10 个** |
| 同职能模块总数(保守) | **40+** |
| 其中≥3 套实现的家族 | conversation(4) · 执行(4) · 拆解(4) · 产品事实(3) · workforce(4+) · memory(6+) · 恢复(3) · 验证(3) = **8 个家族** |
| 两入口(API/CLI) 都 import 的域模块 | 26(但分属不同子链, 无共享 Application 层) |
| 状态机签名重复(PENDING/RUNNING/COMPLETED/FAILED…) | node_runtime · production_run · agent_kernel · workforce_os · self_healing · production_session ≥6 处 |
| 已收敛的单点 | node_runtime(12 消费) · governance_service(13 消费) · product_truth(正式资产) |
| 真正"活"的平行(各有生产消费方) | ~一半; 另一半滞留(测试/历史) |

---

## 3. 断层表(位置/现状/后果)

| # | 断层位置 | 现状 | 后果 |
|---|---------|------|------|
| F1 | 计划级执行入口 | execute_approved(顺序) ∥ production_run(图) ∥ workflow_runner | 3 套 PENDING/RUNNING 状态机; 依赖/并行能力在 production_run 但无人裁决主入口 |
| F2 | Task 组织层 | task_tree(K2) ∥ task_decomposition(新) ∥ decomposer(原子) | 2/7 dogfood 失败根源; 新链单层平铺 |
| F3 | 项目锚点 | project_os(P-*) ∥ conv-即项目 | 认知链无真实代码库上下文; "给现有 X 加 Y"不可达 |
| F4 | 入口分叉 | CLI=session / WebUI=sessions / API legacy=conv_* / 新域=canonical | 用户经任何入口都到不了同一业务链(除 canonical) |
| F5 | 验证契约 | 3 份 pytest runner + 文件级验证 | "文件存在≠测试通过" |
| F6 | 认知段审计 | conversation_app/PU/formulation 零 audit 事件 | 审计链从源头断 |
| F7 | workforce 注册 vs 生产 | expert_factory 7 角色/agents 注册真实, 新链单 codex 全包 | 无专业分工 |
| F8 | 恢复链 | recovery_service/self_healing/node_runtime WAITING 存在 | golden_path 无 RCA/replan 循环 |
| F9 | 旧链滞留 | conversation_os conv_*(已标 LEGACY) + session 产品链 + approval_store 等 | 并行事实源; 新链与旧链互不可见 |

---

## 4. 与 R0/Codex 审计的关系

- R0 审计(我): 4 套 Conversation/执行逻辑, 新域零真实入口 — **被 CT 证实(家族 B/C/F4)**。
- Codex 审计(985ad5c4/67595f76 后): "P1-P6 是收敛+接线, 资产碎片化是最大敌人" — **被 CT 证实且量化**(10 家族/40+ 模块)。
- Codex §5.1(计划执行三入口)、§5.2(项目双轨)、§5.4(验证碎片) — **全部在 CT 家族 C/F3/F5 复现**。

---

## 5. 建议(零代码, 仅供裁决)

1. **先裁决 F1**(计划级执行入口 canonical = production_run 图编排) — 它是 P1/P2 的地基。
2. **再收敛 F2**(task_decomposition 吸收 decomposer 原子逻辑, task_tree(K2) 标 legacy)。
3. **F3 接 project_os**, 认知链锚真实项目。
4. 旧链(F9)明确退休闸: conversation_os/session 产品链仅保留到 canonical 覆盖其能力。
5. 验证/恢复/审计缺口(F5/F6/F8)作为 P4 内嵌。

> 本 CT 不改代码。按纪律 STOP, 等下一步指令。
