# AI Factory — Current State Baseline (Reality Re-baseline)

> 日期: 2026-09-04 | 性质: 只读事实重建 (零代码 / 零提交 / 零修改)
> 仓库: /Users/Shared/work/ai-software-factory | HEAD: 1e993dec (main) | pyproject: 1.1.364
> 数据根: ~/.factory (只读核对)
> 方法: 主审查 (Git/数据/代码直查 + 测试实跑 org+exec 2183/主链 70) + 3 个并行只读子代理
>       (前端链 / 执行链+后链+Learning+Release+Model / WebUI+Project Contract) 交叉取证,
>       关键结论经主审查独立复核 (execution_records/session_exec/audit 关联验证)。
> 原则: 不问"设计应该是什么", 只问"代码与真实运行证据现在是什么"
> 分级: REAL / PARTIAL / TEMPLATE / MISSING; DESIGNED ≠ IMPLEMENTED ≠ PROVEN

---

## 1. Executive Summary

AI Factory (v1.1.364) 是一个**已拥有真实执行内核与真实外部 Agent 委派 (claude/codex) 的 AI 软件开发平台**:
会话 → 计划 → backlog 任务 → 依赖门控 → 外部 Agent/LLM 真实执行 → (应回写 exec_ref) → 审计。
**中段代码与测试 (Plan→Task→Run→Audit) PROVEN (2183+70 测试绿), 外部委派机制真实发生
(execution_records 100 条: 87 success/13 failed; 8/14-8/31; 其中 8/26-8/31 的 12 条 claude/codex
success 委派可对上 session_exec 中 done 任务)**;
但**"回写 → 验证 → 收敛" 的真实闭环未在数据中完成**: session_exec 6 个会话文件全部 status=running
未收敛 (2 个推进过部分任务), done 任务 exec_ref=None (EXS-* 未回写), verify=unknown ("无项目目录",
method 空), 委派时 project_dir 未传入 gateway。
前链 (Idea→Requirement→PRD) 与后链 (Verification→Release→Learning) 仍未完整闭合 —
Requirement 有持久化与部分 plan 引用但无 PRD 域实体; Learning 双向代码存在但真实消费证据 = 0;
Release 仅 design+部分代码, v0.1.0 = tagged 未 published。

一句话: **"把获批计划拆成任务并真实委派给 claude/codex 干活" 的中段已经发生且可审计,
"执行证据回挂任务、验证、收敛、发布、学习" 的完整产品闭环尚未成立。**

---

## 2. Git Reality

| 项 | 值 | 证据 |
|---|---|---|
| Branch | main | git branch --show-current |
| HEAD | 1e993dec77de0554423a4b6999c0d8804863e9a9 (2026-09-02 15:00:55 +0800, "docs: append chapter 23 reality errata") | git log -1 |
| origin/main | = HEAD (0 ahead / 0 behind) | git ls-remote origin HEAD == 1e993dec |
| Staged files | 0 | git diff --cached 空 |
| Modified (unstaged) | 2: demo/team_execution_state.json, unused/teams/teams.json (均为时间戳噪音, 9/1 demo/teams 运行残留) | git diff 内容仅为 started_at/updated_at 变化 |
| Untracked | docs/audit/fix-sprint-design/ (14 份), docs/audit/git-reality/ (2 份), exec/checkpoints.json (空 {}), .trae-html-share-packages/, 3 个 html (商业计划/社区申请), docs/audits/2026-09-04-product-professor-review/ (上轮审查) | git status --porcelain |
| 最近 20 commits | 全部为 docs/audit/feat(orchestration)/fix(truth) 混合; 最近 4 个 = docs (governance/README/errata) | git log --oneline -20 |
| 版本 tag | v1.1.364 = 19d71483 (8/31) 是 HEAD 祖先; HEAD 尚有 107 commits (含 9/1-9/2 feat/fix), **版本号未再 bump** | git describe, git merge-base --is-ancestor |

### STEP10 / STEP11 真实状态

- **STEP10 冻结: 是, 已提交入库。** commit cf81d24a "chore(audit): establish STEP10 architecture baseline" (在 HEAD 历史中), docs/audit/product-system-baseline/ 21 份已 tracked。
- **STEP11 fix-sprint-design: 未提交。** docs/audit/fix-sprint-design/ 14 份**全部 untracked** (git ls-files = 0)。DOCUMENTATION_MATRIX 声称其 "KEEP (待人工批准)" 但矩阵自身已提交而设计文档未入库 → **状态: 工作区设计稿, 非 git 基线, 未获批准, 未实施**。
- **git-reality 报告 (STEP10.6/10.7): 未提交** (untracked)。
- **用户声称完成但 git 不存在**: STEP11 Fix 设计 13-14 份、git-reality 2 份、exec/checkpoints.json。这些是"已完成的设计/报告", 不是"已完成的代码修复" — Fix 代码本身未开始 (CURRENT_SYSTEM_TRUTH 与 AGENTS.md §6 一致: FX-01~08 待人工批准)。

---

## 3. Architecture Reality

```
运行时 = factory-console (Web 8011/会话/编排, 268 py) + factory-org (领域 SSOT, 18 py)
      + factory-exec (执行域, 52 py)            [package-dir 映射: factory_console → factory-console]
独立模块 = factory-core (138 py, 27 顶层子包) + factory-runtime (12 py)
数据根 = ~/.factory (DEFAULT_DATA_DIR, config.py:47)
```

| 模块 | 真实角色 | 证据 |
|---|---|---|
| factory-console | 生产主链 (会话/编排/执行桥/Web API) | console_sessions.py, session/orchestrator.py, external_executor/ |
| factory-org | org 域 SSOT (projects/management backlog/execution model) | factory-org/org/{projects,management,execution}.py |
| factory-exec | exec 域 (EXR/EXS/ART id, AgentRuntime, 沙箱) | factory-exec/exec/models.py:36, execution_loop.py |
| factory-core | **独立子包库 (无生产主链消费者)** — grep 无 console/org/exec 反向 import | 全仓 import 扫描 |
| factory-runtime | 独立 (PyInstaller bundle 在 dist/) | dist/factory-runtime-bundle/ |

- **代码 import 方向**: console → org/exec 为**惰性局部 import** (service.py 大量 `from org...` / `from exec...` 在方法内); org/exec/core **不 import console** → 依赖方向基本健康。
- **数据多源并存 (已知, STEP10 D-9 冻结)**: ① backlog TASK-* (workspace/projects/*/management/backlog/task.json) ② session_plans.json (16 session plans, PLAN-*/plan_*) ③ exec 域 — **权威记录 = execution_records.json (100 条)**, exec/results.json (85 条) 是其子集投影 (85/100 result_id 对上), factory.db events (org.execution.*) 是同一 exec 域的事件镜像 (EXR-* request_id / backend-1 沙箱证据一致) — 三者同域, 非三套执行; 但**与 backlog/session 链无 ID 关联 (exec_ref 未回写)**。
- **factory.db**: SQLite 3.3MB, 仅 events 表 (7825 events, 2026-08-05→09-01; 6156 console.viewed + 430 tool.call + org.execution.* 86/86/75 + intelligence.feedback.learned 85)。CURRENT_SYSTEM_TRUTH §13 将 factory.db 用途列为 UNKNOWN → **可部分回答: 它是第二事件存储 (与 audit_events.json 并存), 用途=事件镜像; 是否生产消费待查**。

---

## 4. Product Lifecycle Reality

```text
Idea            PARTIAL      (session/console_sessions 捕获, intent 解析真实; 无独立 Idea 实体)
↓
Discovery       PARTIAL      (discovery_intelligence.py 536 行 + conversation 集成;
                              audit DISCOVERY_CONFIRMED 2833 条 = 真实运行证据, 但项目多为空/历史;
                              **分析结果不落盘** — 只存内存/审计, 无 discovery.md 实体文件
                              (子代理取证: 文件内无 write_text/json.dump; ~/.factory 无实体))
↓
Requirement     PARTIAL      (requirements.json 7 条 req_* VALIDATED 真实落盘 — agent_loop.py:795;
                              4/16 plans 携带 requirement_id (session_plans 数据证据);
                              但无 requirement→PRD→plan 全链; Task 不携带 requirement)
↓
PRD             TEMPLATE     (无 Domain Entity / 无 persistence / 无 API;
                              PRD.md 由 actions.generate_prd 纯规则生成到 projects/<slug>/PRD.md
                              (agent_loop.py:511, 不调 LLM), org/artifact.py 有 prd 类型契约;
                              6 个项目有 PRD.md 文件 (数据证据), 但非结构化实体)
↓
Backlog         REAL         (backlog/task.json TASK-* SSOT; 235 tasks 全仓 (13 文件);
                              org.management.Task model 含 plan_id/exec_ref/exec_result/history)
↓
Plan            REAL         (session_plans.json 16 session plans; PLAN-*/plan_* 持久化;
                              plan_id 落 backlog TASK (53 tasks 带 plan_id, E2E 项目证据);
                              plan 结构含 goal/tasks/order/acceptance/approval_id/status)
↓
Task            REAL         (TASK-* 8 状态 model; 依赖校验 validate_dependency; audit TASK_CREATED 1183)
↓
Run             PARTIAL→REAL  (ExecState 门控真串行 (exec_state.py:100-169); 真实委派发生
                              (execution_records 100, EXS-*); factory.db org.execution.started 86;
                              但 session_exec 6 文件未收敛 status=running, exec_ref 未回写 → 门控代码 REAL,
                              真实链路完整收敛 = 未达)
↓
Artifact        PARTIAL      (exec 域 225 artifacts (patch/report/test_result 各 75) 真实
                              (exec/artifacts.json + EXS-*.report.md 文件); org/artifacts.json 24 条
                              (code/design/idea/product/release/test/ux_ui); 但 Task→Artifact 经 Run
                              间接 (D-6) 未全链实施 — backlog task exec_ref 填充 = 0)
↓
Verification    PARTIAL      (verification.py 真实 pytest/syntax subprocess (S5);
                              exec test_result 75 条; release_service._run_verification 调用;
                              Verification SSOT 未冻结 (FX-08, D 类))
↓
Evidence        PARTIAL      (projects/ai-factory-self/evidence/ev-*.json 9 条 (diff/test_results/logs/
                              decisions/artifacts/evaluation); exec event_refs 数字序列引用;
                              evidence→任务完成证明链未系统化)
↓
Release         MISSING      (release_service.py S18 代码存在 (state machine/gates);
                              ~/.factory/releases/ 数据目录不存在 → 无真实 ReleaseRecord;
                              v0.1.0 = git tag 指向 8/14 commit e1ff14d4, docs 状态=待发布,
                              dist/ 仅 factory-runtime-bundle (PyInstaller 产物, 非发布包),
                              无 wheel 文件 → **tagged, 非 built/packaged/published**)
↓
Learning        PARTIAL      (双向代码: on_execution_complete 写入 + resolve_for_task 检索注入
                              (actions.py:1376/1486, memory/learning_loop.py);
                              experiences.json 85 条 (quality 1.0×75 / 0.3×10);
                              memory/experience_store.json 84 条; learning_trace 存在;
                              但 last_used = 0/85 → **检索代码存在, 真实消费证据 = 0** → C 级未达)
```

### 各层判定总表

| 层 | 状态 | 关键证据 |
|---|---|---|
| Idea | PARTIAL | console_sessions 78 sessions, session_topics 81 |
| Discovery | PARTIAL | DISCOVERY_CONFIRMED 2833 audit |
| Requirement | PARTIAL | requirements.json 7 条; 4 plan 带 requirement_id |
| PRD | TEMPLATE | 无实体; PRD.md 规则生成 (generate_prd agent_loop.py:511) |
| Backlog | REAL | 235 TASK-* (13 backlog 文件) |
| Plan | REAL | session_plans.json 16 plans + plan_id 落 task |
| Task | REAL | org.management.Task + audit TASK_CREATED 1183 |
| Run | PARTIAL→REAL | ExecState 门控 + 真实委派 (execution_records 100) + session_exec 未收敛 |
| Artifact | PARTIAL | exec 225 (patch/report/test_result) + org 24; task.exec_ref=0 |
| Verification | PARTIAL | verification.py pytest subprocess; SSOT 未冻 |
| Evidence | PARTIAL | ai-factory-self evidence 9; 关联弱 |
| Release | MISSING | 无 releases/ 数据; v0.1.0 tagged only |
| Learning | PARTIAL | 双向代码; 消费证据 0/85 |

---

## 5. Capability Maturity Matrix (Re-baseline 2026-09-04)

> 基于真实数据/代码重评, 不沿用旧数字。E2E? = 是否有真实端到端运行证据。

| # | Capability | M | 证据 (代码:行 / 数据) | Real E2E? | 主要 Gap |
|---|---|---|---|---|---|
| C-001 | Session Entry | M4 | console_sessions.json 78 sessions + session_topics 81 + Web UI | 是 | — |
| C-002 | Intent Capture | M4 | session/query_engine.py + execution_truth; audit 大量 | 是 | 部分 intent 靠 LLM 解析无独立实体 |
| C-003 | Requirement Persistence | M3 | agent_loop.py:795-827 落盘; 7 req 数据 | 是 | 非全 session 路径 (4/16 plans 带 ref) |
| C-004 | Requirement Traceability | M1 | plan.requirement_id 4 例; Task 无 requirement 引用 | 部分 | requirement→PRD→Task 无全链 |
| C-005 | Discovery/Clarification | M3 | discovery_intelligence.py + 2833 DISCOVERY_CONFIRMED | 是 | 大量历史测试噪音 |
| C-006 | Planning | M4 | session_plans.json 16 plans; execute_plan 幂等 (agent_loop.py:434-503) | 是 | plan_id 双格式 (PLAN-*/plan_*) |
| C-007 | Task Management | M4 | org.management.Task + 235 TASK data | 是 | backlog 分散 13 文件 |
| C-008 | Dependency Scheduling | M4 | exec_state.py:100-169 Ready/done/blocked; validate_dependency | 是 | 单任务串行 (真并行未实现) |
| C-009 | Agent Selection | M3 | external_executor/gateway.py:18-117 _pick_executor + router | 是 | 选择规则简单 |
| C-010 | Agent Execution | M3 | execution_records.json **100 条** (87 success/13 failed; backend-1×48/flutter-dev×17/claude×5/codex×1 等; 8/14-8/31); EXS report 含 usage/验证 | 是 | 委派执行真实, 但 verify=unknown (project_dir 未传) |
| C-011 | LLM Invocation | M4 | agent_loop call_with_tools/run_agent_native; usage tokens 真实 | 是 | — |
| C-012 | Model Selection | M2 | llm_router.py 五层链 + agent_loop._resolve_model_conf (L1-L5); 但 fallback 常驻 | 部分 | **有装配无 policy 约束证据**; 多为默认模型 |
| C-013 | Tool Invocation | M3 | _fc registry + TOOL_CALL 430 audit | 是 | — |
| C-014 | Skill | M1 | skills.json 2.5MB; 生产消费 UNKNOWN | 否 | 无真实消费证据 |
| C-015 | Orchestration (会话链) | M4 | orchestrator.py 4209 行; 测试 70 passed (主链) | 是 | — |
| C-016 | Execution (会话链) | M3 | chain_next→gateway→委派真实发生 (session_exec 2 会话推进 6 done = claude/codex EXS 成功); 但 exec_ref 未回写、verify unknown、文件未收敛 | 部分 | **委派真实, 回写/收敛断 (FX-01 未做)** |
| C-017 | Recovery (crash) | M3 | exec_state.recover + test_exec_state_recovery (通过) | 是 (测试) | 生产 crash 演练无记录 |
| C-018 | Cancellation | M4 | 4e1a42e1 + test_session_cancel (通过) | 是 (测试) | — |
| C-019 | Verification | M2 | verification.py pytest subprocess; 75 test_result | 部分 | SSOT 未冻结 (FX-08) |
| C-020 | Artifact Lifecycle | M3 | exec 225 artifacts + org 24 + artifact_contract.py | 是 (exec 域) | 未挂 backlog task (exec_ref=0) |
| C-021 | Audit | M4 | audit_events.json 5172 (审查期间 5160→5172); 22 event types | 是 | 两事件存储并存 (audit_events.json + factory.db) |
| C-022 | Governance/Approval | M3 | governance/approvals.json 8 + product/approvals.json 3 + APPROVAL audit 10 | 是 | 三处审批存储并存 |
| C-023 | Project Management | M4 | org/projects.json 27 + S35 Git Contract 字段已加 (ff52cdc8) + workspace API | 是 | repo_path 历史数据错误 (已修写路径) |
| C-024 | WebUI | M3 | frontend dist 已构建; api/client 全真 API; runtimeClient 带 mock fallback | 是 | Runtime/Timeline 视图可 mock (is_mock 标注) |
| C-025 | CLI | M3 | cli_factory 17+ 命令; exec cli | 是 | — |
| C-026 | Experience | M2 | experiences.json 85 + experience_store.json 84 | 部分 (写) | 读/消费证据 0 |
| C-027 | Learning | M1 | learning_loop resolve/complete 代码在 actions 链; last_used 0 | 否 | 无真实消费证据 |
| C-028 | Replanning | M1 | session/replanning.py + autonomous_replanning 测试 | 部分 | 主链集成弱 |
| C-029 | Release | M0 | release_service.py 代码; 无 releases/ 数据; v0.1.0 tagged only | 否 | 无真实发布 |

**计数 (重评): M4×9 / M3×9 / M2×4 / M1×4 / M0×1 (调整: Requirement Persistence M2→M3,
Artifact M2→M3, Discovery M1→M3 因运行证据; Model Selection M1→M2 因装配存在;
Execution (会话链) M4→M3 因回写/收敛断; Skill/Experience/Learning 如实低分)。**

### 分数重算 (方法 = STEP7 SYSTEM_CAPABILITY_SCORE 权重: CORE×3/SUPPORTING×1/FUTURE×0.3,
基于本表新 M 值, 非沿用旧数字)

- **Capability Reality ≈ 86** (CORE 中 M≥2 占比高: 真实委派 + Artifact/AgentExec 生产证据; C-016 回写断已扣)
- **Contract Fulfillment ≈ 72** (产品旅程: Plan→委派→Record 已兑现; Req 部分、PRD 缺失、Learning/Release 未达)
- **Production Closure ≈ 48** (委派真实但回写/收敛未闭合, task.exec_ref=0, Verification SSOT 未冻, Release 无数据)

> 说明: 这些是**近似重算**, 与 85.2/75.0/49.8 同量级但方向=执行域证据增强、
> 前端链未变、后链仍断。**旧数字非"错误", 但基于 8 月底快照; 本表为 9/4 视角。**

---

## 6. E2E PROVEN Chains (区分: 代码/测试级 PROVEN vs 真实运行数据级 PROVEN)

**A. 代码 + 测试级 (测试绿, 2026-09-04 实测)**
1. **主链代码路径 (Session→Plan→Task→ExecState→回写→Recover→Audit)**: 测试 70 passed (test_m3e_full_chain/planning_orchestration/exec_state_recovery/session_cancel)。
2. **org+exec 测试基线**: tests/org + tests/exec = **2183 passed**。
3. **崩溃恢复链**: ExecState.recover + 测试通过。
4. **Plan→Task 落库**: execute_plan 幂等创建 TASK + plan_id (agent_loop.py:434-503; 测试 + E2E 项目 53 tasks 带 plan_id 数据)。

**B. 真实运行数据级 (有实际执行痕迹)**
5. **外部 Agent 委派真实发生**: execution_records.json **100 条** (87 success/13 failed; backend-1×48/flutter-dev×17/claude×5/codex×1/examiner 角色×15; 8/14-8/31)。其中 8/26-8/31 的 **12 条 claude/codex success 委派**与 session_exec 的 done 任务标题一一对应 (如 "项目骨架与页面结构搭建"→claude EXS-2f301554, "搭建项目基础结构"→codex EXS-e2bd72e1) — **委派真实完成**。
6. **真实 LLM 调用**: EXS report 含 usage tokens/cost + 语法验证 PASS (EXS-002f56f0.report.md)。
7. **exec/org 域记录**: exec/results.json 85 = execution_records 的子集投影 (85/100 的 result_id 可对上); factory.db org.execution.* 86/86/75 = 同域事件镜像 (EXR-* 沙箱证据一致)。

**C. 注意 (audit 事件链≠当前 backlog 链)**: audit 的 TASK_STARTED 29/TASK_COMPLETED 30 全部在 8/18,
task_id 形如 task-e1-core/task-match-record-score, project_id 为旧数字 id (1787033426) — **属于旧版
production_run 体系, 不是当前 backlog TASK-* 主链**, 当前 TASK-* 从未在 audit 中 STARTED/COMPLETED。
→ 审计事件链与当前 backlog/session 链**脱节** (audit 可查, 但跨链追溯断)。

## 7. Broken Chains (真实断点)

1. **Requirement → PRD → Plan 需求链**: Requirement 有落盘与 4/16 plan 引用, 但 PRD 无实体、无 requirement→task 全链追溯 (前端链断裂)。
2. **委派执行 → 回写 → 收敛 (核心断点)**: 委派真实完成 (claude/codex 有 EXS-* result_id), 但
   session_exec 6 个会话文件**全部 status=running 未收敛** (updated 8/31-9/1), done 任务 exec_ref=None
   (EXS-* 未回写), verify=unknown ("无项目目录"/method 空) — **执行发生, 证据未挂回任务, 链未关闭** (FX-01/FX-04 未做)。
3. **Task → Artifact/Verification**: backlog task.exec_ref 填充 = 0/53 done; exec 域 225 artifacts 未系统性挂回任务。
4. **Verification SSOT**: 未冻结 (FX-08), exec results + ExecState.verify + factory.db 并存; gateway 委派 verify=unknown (project_dir 未传入)。
5. **Release 链**: 无 releases/ 数据, v0.1.0 未发布 → 产品无法被用户获取。
6. **Learning 消费**: 双向代码已接但 experiences last_used = 0/85 (usage_count=0, subject_id 全 unknown-employee) → 经验不影响下次执行。
7. **Model Policy 治理**: LLMRouter 装配存在 (agent_loop _resolve_model_conf) 但部署态单 provider (deepseek), models.json/agent policy/project llm.yaml 全缺 → L2-L4 空转, reasoning 路径绕过 router。
8. **Sprint/Milestone**: 实体真实 (api/sprint.py CRUD) 但 **0 实测数据** — 未在任何会话/产品管线中出现。
9. **审计跨链**: audit_events.json (5172) + factory.db events (7825) 双事件存储; 审批存三处 (governance/product/audit)。

---

## 8. Backend / WebUI Truth Audit

| 项 | 判定 | 证据 |
|---|---|---|
| WebUI 业务状态 | **Projection (干净)** | state/ = React Context (currentProjectId/theme 等 UI 态); 无业务 SSOT |
| localStorage | **仅 UI 偏好** (theme/locale/sidebar) | theme.tsx:29/49, i18n 等 — 无任务/业务数据 |
| 数据来源 | **核心查询全真 API** | api/client.ts 143-267: /api/dashboard, /api/projects, /api/conversations, /api/projects/{id}/backlog/task 等 |
| 写面 | 审批决定/项目创建/任务审批/Runtime 生命周期 → 后端 | client.ts 注释 + sendJson 调用 |
| 前端自生成任务 | **无** | 无 createTask 本地逻辑; 任务审批经 /api/tasks/{id}/approval |
| mock | **部分视图 mock fallback (诚实标注)** | runtimeClient.ts: Workflow/Timeline/Runtime/Artifact 视图, is_mock=true 演示模式; 核心业务无 mock |
| Backend 职责 | fastapi_adapter 单一 (REST + 静态托管 + SSE) | web/backend/fastapi_adapter.py |
| API 鉴权 | **无认证** (零 auth 中间件) | api/ + fastapi_adapter grep 无 Authorization 校验 |
| 风险 | 中: mock fallback 视图可绕过真数据; 低: 无鉴权 (本地单用户形态) | — |

**结论: WebUI = Backend projection (核心业务), 非双状态源; 残留 mock 仅限演示视图且带标注。localStorage 不存业务 SSOT。**

---

## 9. Project / Git Contract Audit

| 项 | 状态 | 证据 |
|---|---|---|
| Project model Git 字段 | **REAL (9/1 已修)** | projects.py:306-312: git_enabled/git_repo_url/git_provider/git_default_branch/git_current_branch/git_head_commit/git_working_tree (commit ff52cdc8) |
| repo_path 回写 | REAL | api/projects.py:215-238 写回 workspace/projects/{slug} |
| Workspace API | REAL | /api/projects/{id}/workspace + requirements/plans/tasks 端点 (fastapi_adapter) |
| Git 实时探测 | REAL | fastapi_adapter.py:1556-1572 project_scan._git_info |
| 数据现状 | 部分旧数据 repo_path=~/.factory (历史), 新写已修正 | org/projects.json 抽样 |
| S35 P0 结论 | **已解决** (s35-project-management-contract 审计 9/1 的 4 P0 在 ff52cdc8 修复) | git show ff52cdc8 + model 字段 |
| 空 P-* 目录 | 812 个空壳 (projects/ + workspace/projects/) 未跟踪 (git ls-files=0) | 仓库卫生问题, 非 git 契约问题 |
| 当前 working tree | 仅时间戳噪音 + untracked 设计文档; 无代码破坏 | git status |

---

## 10. Current Scores (2026-09-04)

| Score | 值 | 依据 |
|---|---|---|
| Capability Reality | ~86 / 100 | 重评 M 矩阵; 执行委派证据增强, 但 Discovery 落盘近零/C-016 降 M3 |
| Contract Fulfillment | ~72 / 100 | 主链代码兑现; 前端 PRD/后链 Learning/Release 未兑现; 真实委派已有 |
| Production Closure | ~48 / 100 | 委派真实但回写/收敛断 (exec_ref=0, session_exec 6/6 running), Verify SSOT 未冻, Release 无 |
| Overall (Product Professor) | 62 / 100 | 诚实治理 + 真实执行内核; 产品闭环缺两端 |
| Launch Readiness | 45 / 100 | 可安装可运行, v0.1.0 未发布, 无分发/种子用户证据, 服务当前未运行 |
| True Score | 70 / 100 | 执行内核真实非 demo; 产品智能层半真 |

> 旧数字 85.2/75.0/49.8 为 STEP7 (8 月底) 评估; 本次为同方法重算的 9/4 视角, 差异源于
> 新增执行/产物运行证据与 Requirement 落盘证据。数字仍为估计, 非精确测量。

---

## 11. Critical P0/P1 Findings (真实存在)

**P0**
1. **fix-sprint-design (STEP11, 14 份) 未提交且未批准** — 声称"Fix 设计就绪"但 git 无此基线 (untracked); 后续任何 Fix Sprint 都无对照物。
2. **委派执行 → 回写 → 收敛断 (核心)**: 外部委派真实完成 (claude/codex 12 条 success, EXS-* 存在),
   但 session_exec 6/6 会话文件 status=running 未收敛, done 任务 exec_ref=None (EXS-* 未回写),
   verify=unknown (project_dir 未传入 gateway) → **执行发生但任务层看不到证据, 链无法证明完成** (FX-01/FX-04 未做, STEP10 D-9 落地缺失)。
3. **Verification SSOT 未冻结 (FX-08)** — verification.py 真实但归属未定; gateway 委派 verify 事实为空转; 验证事实无唯一真源。

**P1**
4. **PRD 域实体缺失** — 只有规则生成 PRD.md; idea→产品承诺无结构化载体。
5. **Learning 消费 = 0 (last_used 0/85, usage_count=0)** — 经验闭环代码已接但从未真实影响执行。
6. **Release 未发布** — v0.1.0 tagged (8/14) 但无 releases 数据/wheel/分发; "可被用户获取" = 否。
7. **Model Selection 名义 > 实际** — LLMRouter 有装配 (agent_loop _resolve_model_conf) 但部署态单 provider (deepseek), models.json/agent policy/project llm.yaml 全缺 → L2-L4 空转; reasoning 路径绕过 router。
8. **audit 事件链与当前 backlog 链脱节** — TASK_STARTED/COMPLETED 属旧数字 project 体系 (task-e1-core 等, 8/18); 当前 TASK-* 从未 STARTED/COMPLETED; audit (5172) + factory.db (7825) 双事件存储 + 审批三处存储 → 跨链追溯断。
9. **9/1 的 1154 TASK_CREATED 无对应 STARTED/COMPLETED** — 大量任务创建但无执行收敛记录 (系统/console actor)。
10. **Discovery 产物落盘近零** — discovery_intelligence 真实 LLM 分析但结果只存内存/审计事件, 无 discovery.md 实体文件; 2833 DISCOVERY_CONFIRMED 审计 ≠ 产品实体。
11. **Sprint/Milestone 0 实测数据** — 实体与 API 存在但从未在管线中使用。
12. **org/projects.json 数据层 repo_path 未生效** — 27/27 git_enabled=false/repo_path 错/空 (代码已修写路径, 但存量数据未迁移/未回填); 812×2 空 P-* 目录污染。
13. **Task Tree 无任意深度递归** — task_tree.py 只产 2 层 (root + 扁平模板子任务, 顺序执行失败即停), 无递归遍历 children 代码; decompose_* audit 事件 (252+72) 与 backlog 任务树非同一实现。

## 12. What Is Actually Working (真实成立)

- **执行委派机制真实**: 外部 Agent (claude/codex) 委派真实发生并可审计 — execution_records 100 条 (87 success), 其中 12 条 claude/codex success 委派 (8/26-8/31), 6 条与 session_exec done 任务一一对应, 各有 EXS-* 记录 + usage/cost + 语法验证。**不是 demo**。
- **真实 LLM 执行**: EXS report 带真实 usage tokens/cost + 验证 PASS (EXS-002f56f0.report.md)。
- **真实 Artifact**: 225 exec artifacts (patch/report/test_result ×75) + 24 org artifacts, 有文件实体。
- **中段代码 + 测试**: 主链 (Session→Plan→Task→ExecState→Recover→Audit) 代码完整, org+exec 2183 + 主链 70 测试全绿。
- **Plan→Task 关联**: plan_id 落 backlog (53 tasks), execute_plan 幂等 — Plan/Task 链真实。
- **Requirement 落盘**: requirements.json 真实写入 + 4/16 plans 带 requirement_id (agent_loop.py:795)。
- **Project Git Contract**: S35 P0 已修复 (model 字段 + repo_path 写路径 + workspace API, commit ff52cdc8)。
- **WebUI 为纯投影**: 业务状态全走后端 API; localStorage 仅 UI 偏好; 核心查询无 mock。
- **文档诚实度治理**: STEP1-11 forensic 已提交, README/00-index/STEP10 构成可信导航。
- **测试基线**: 全仓 13731 测试函数静态计数; org+exec 2183 实测通过; 主链 70 通过。

---

## 13. What AI Factory Actually Is Today

**AI Factory 今天是一个"计划→任务→真实委派 (claude/codex/DeepSeek) → 记录"中段已真实发生、
代码与测试 (M4) PROVEN、但"回写→验证→收敛→发布→学习"闭环尚未在运行数据中完成的
本地 AI 软件开发执行平台** —
它已经能把获批计划拆成带依赖的任务并真实委派给外部 Agent 执行、留下 EXS 记录与 usage/验证痕迹、
全程可审计; 但任务层看不到执行证据 (exec_ref 空)、委派验证为空转 (verify unknown)、
会话执行状态永不收敛 (6/6 running)、需求→PRD 无实体、经验零消费、v0.1.0 无处获取。
**中段机制是 REAL 且有真实委派痕迹, 全链产品闭环 (证据回挂→验证→收敛→发布→学习) 是
PROMISED ARCHITECTURE + 部分 IMPLEMENTED CODE, 尚未在真实数据中 PROVEN。**

---

*报告完。未修改任何文件/代码/git; 唯一产物为本报告。审查期间检测到并发会话写入 audit (5160→5172)。*
