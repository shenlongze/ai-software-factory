# S10-061 — GAP ANALYSIS

> 日期:2026-08-15 | Sprint: S10-061 | P0 现状审查
> 审查方式: 读取真实代码 (replanning/orchestrator/dependencies/team_state/quality/workspace/agents/roles)

---

## 核心问题回答

### A. 当前 Gap Signal 从哪里产生?
```
replanning.py GAP_MARKERS: ("missing", "需要", "缺少", "缺口", "not found")
→ 匹配 agent_output 字符串 (outcome.error/output/agent_output)
→ 无结构化 Gap 分析, 无 gap_type/evidence/severity/confidence
```

### B. Validation failure 如何进入 Replanning?
```
orchestrator._replan_on_failure:
  failures = [{task_id, name, error: outcome.error 或 validation.errors}]
  → ReplanningEngine.decide(failures=..., validation={success, errors})
  → validation 失败本身不直接触发 INSERT (依赖 agent_output 缺口词)
```

### C. QA Agent 的输出如何进入 Replanning?
```
agent_output = outcome.get("agent_output") or outcome.get("output") or outcome.get("error") or ""
→ 纯文本关键词匹配; QA 的"发现缺口"只有含 GAP_MARKERS 才触发
```

### D. Artifact 如何提供给 Gap Analyzer?
```
_replan_on_failure: ctx = WorkspaceContext.load(project_dir)
→ 有 artifacts/completed_tasks, 但无独立 Gap Analyzer 消费
```

### E. Task 当前最完整的数据结构?
```
_task_record: id/name/agent_type/agent/feature/epic/reason/required_role/
              matched_role/files/status/artifact/retry_count/error
```

### F. TaskDependencyGraph 插入任务需要哪些字段?
```
add_task(task, depends_on) — 只需 id + 依赖; 完整任务字段 (name/role/验收) 不在 DAG
```

### G. AgentMatcher 如何根据 required_role 分配 Agent?
```
_team_prepare: required_role → RoleSystem.role_matches 过滤成员 → AgentMatcher 选最佳
→ 已具备, 新任务带 required_role 即可自动分配
```

### H. 当前 Task context 能否携带 gap/evidence/decisions/source/acceptance?
```
❌ 无 gap/evidence/source_task/acceptance_criteria 字段
(有 context.previous_decisions — S10-058, 但无 gap 元数据)
```

### I. 当前 Repair Loop 与 Replanning 的边界?
```
Repair: 任务失败 → RepairManager.create_repair (quality.py, 任务级 retry)
Replanning: 计划偏差 → ReplanningEngine (计划级改 DAG)
→ 边界已清晰 (S10-060), 但 Replanning 的 INSERT 依赖调用方提供 new_tasks
```

### J. 如何避免无限循环?
```
max_replan=5 → 超限 REQUEST_REVIEW ✅ (已有)
❌ 无 max_auto_insert_tasks / max_tasks_per_round / max_total_generated_tasks
❌ 无"同一 gap 不无限重复生成"机制
```

### K. 如何避免重复任务?
```
❌ 无 duplicate detection (S10-060 无)
```

### L. 如何避免生成无法执行的任务?
```
❌ 无 TaskProposalValidator (任务由调用方直接提供, 无 deterministic gate)
```

---

## GAP 汇总

| # | 缺失 | 说明 |
|---|---|---|
| G1 | **GapAnalyzer** | 无结构化 Gap 分析 (gap_type/evidence/severity/confidence/source_task) |
| G2 | **TaskProposalEngine** | 无自动任务生成 (INSERT 需调用方提供) |
| G3 | **TaskProposalValidator** | 无 deterministic 验证门 (12 项检查) |
| G4 | **Duplicate Detection** | 无重复任务检测 |
| G5 | **Replan 上限细化** | 有 max_replan, 缺 max_auto_insert/max_tasks_per_round/max_total_generated |
| G6 | **同一 gap 防重** | 无 (第一次 INSERT, 再失败应 RETRY/REPAIR/REVIEW) |
| G7 | **安全边界分级** | 无 AUTO_EXECUTE/AUTO_PROPOSE_REVIEW/REQUEST_REVIEW (confidence 分级) |
| G8 | **Task context 扩展** | 无 gap/evidence/source_task/acceptance_criteria 字段 |
| G9 | **资产化** | 无 gap_analysis.json / task_proposals.json |

## 可复用 ✅

| 能力 | 复用方式 |
|---|---|
| ReplanningEngine (8 决策) | INSERT_TASK 路径增强 (backward compatible) |
| ReplanDecision | 输出结构复用 |
| ReplanningEngine._insert_tasks | DAG 插入基础 (需补 proposal 元数据) |
| TaskDependencyGraph mutation | add_task/add_dependency/cycle 保护 |
| AgentMatcher + role_matches | required_role → 自动分配 Agent |
| WorkspaceContext | artifact/completed 提供 GapAnalyzer 输入 |
| max_replan | 已有防无限基础 |
| RepairManager | 边界保持 (任务级) |

## 设计方向 (S10-061)

```
新增 gap_analyzer.py:
  GapAnalyzer: 输入 (project/workspace/task/result/validation/artifacts/agent_output/
               failures/existing_tasks/DAG/prev_decisions) →
               GapAnalysis {detected, gap_type, description, evidence, severity,
               source_task_id, confidence, duplicate_of, recommended_action}
  gap_type: missing_requirement/missing_implementation/missing_test/
            validation_failure/dependency_gap/integration_gap/architecture_gap/ui_gap/unknown
  recommended_action: NO_ACTION/REPAIR/MODIFY_TASK/INSERT_TASK/BLOCK/REQUEST_REVIEW

新增 task_proposal.py:
  TaskProposal {task_id, title, description, objective, required_role, dependencies,
                acceptance_criteria, validation_command, source_gap, rationale,
                confidence, priority}
  TaskProposalEngine: GapAnalysis → TaskProposal (规则模板驱动, LLM 可选增强)
  TaskProposalValidator: 12 项 deterministic 检查 → PASS/REJECT + reason
  DuplicateDetector: task_id/标题归一化/source_gap/objective → duplicate_of

修改 replanning.py: INSERT_TASK 路径 — 调用方无 new_tasks → GapAnalyzer →
  TaskProposalEngine → Validator → DAG → 返回 (backward compatible)
修改 orchestrator.py: 执行循环 — validation 失败 → gap 分析 → 决策 →
  INSERT → 自动提案 → 分配 → 执行 → 继续
```

## 不该现在做 🚫

- LLM semantic similarity (先 deterministic)
- PyPI/marketing/UI/SaaS/账号/Billing/云/多租户/Git merge/并行 DAG/Reviewer 大系统

---

> GAP 完毕 | G1-G9 缺失 | 可复用充分 | 设计方向明确 | 真实性要求: 新任务必须由引擎生成非测试注入
