# S10-061 — Autonomous Task Proposal & Gap Resolution 设计

> 日期:2026-08-15 | Sprint: S10-061 | 设计 (基于 GAP 分析 G1-G9)
> 目标: Replanning 从"AI 决定如何重规划"→"AI 自己发现缺口并生成可执行新任务"

---

## 1. 架构

```
旧: QA/Agent → 发现问题 → 调用方提供 new_tasks → INSERT_TASK
新: QA/Agent → 观察 → 发现 GAP → GapAnalyzer → TaskProposalEngine
     → Validator → DAG Insert → AgentMatcher → 执行 → Validation → 继续
```

## 2. GapAnalyzer (新增 gap_analyzer.py)

```
输入: project context / workspace / current task / execution result /
      validation result / artifacts / agent output / failures /
      existing tasks / DAG / previous replanning decisions
输出: GapAnalysis {detected, gap_type, description, evidence, severity,
      source_task_id, confidence, duplicate_of, recommended_action, reason}

gap_type: missing_requirement / missing_implementation / missing_test /
          validation_failure / dependency_gap / integration_gap /
          architecture_gap / ui_gap / unknown
recommended_action: NO_ACTION / REPAIR / MODIFY_TASK / INSERT_TASK /
                    BLOCK / REQUEST_REVIEW
severity: low / medium / high / critical
confidence: 0.0-1.0
```

## 3. TaskProposalEngine (新增 task_proposal.py)

```
TaskProposal {task_id, title, description, objective, required_role,
              dependencies, acceptance_criteria, validation_command,
              source_gap, rationale, confidence, priority}

规则模板驱动 (deterministic):
  missing_test → {required_role: qa, objective: "为 X 增加测试",
                  acceptance_criteria: ["pytest 通过"], validation_command: "pytest"}
  missing_persistence → {required_role: backend, objective: "实现持久化",
                         acceptance_criteria: ["数据可保存", "重启可恢复", "pytest 通过"]}
  missing_requirement → {required_role: pm, ...}
  ...
```

## 4. TaskProposalValidator (12 项 deterministic gate)

```
1. task_id 唯一    2. title 非空    3. description 非空
4. required_role 合法  5. dependencies 存在  6. 无 DAG cycle
7. acceptance_criteria 非空  8. validation_command 合法
9. 不与已有 Task 重复  10. source_gap 存在  11. confidence ≥ 阈值
12. 不超 replanning limit
失败 → REJECT_TASK_PROPOSAL + reason
```

## 5. Duplicate Detection

```
deterministic: task_id / normalized title / source_gap / existing objective
输出: duplicate_of (任务 id) 或 false
```

## 6. Replanning 集成 (backward compatible)

```
ReplanningEngine INSERT_TASK 路径:
  调用方有 new_tasks → 现有行为 (兼容)
  调用方无 new_tasks → GapAnalyzer → TaskProposalEngine → Validator
    → DAG insert → AgentMatcher → 执行
```

## 7. 安全边界

```
高 confidence + 低风险 → AUTO_EXECUTE
中等 confidence → AUTO_PROPOSE_REVIEW
低 confidence / architecture destructive / high risk → REQUEST_REVIEW
所有决策: reason + evidence + confidence
资产: gap_analysis.json / task_proposals.json / replanning_decisions.json
```

## 8. 无限 Replanning 防护

```
max_replan_rounds (5) / max_auto_insert_tasks / max_tasks_per_round /
max_total_generated_tasks
同一 source_gap: 第一次 INSERT_TASK → 再失败 RETRY/REPAIR → 第三次 REQUEST_REVIEW
```

## 9. Orchestrator 接入

```
execute → observe → validation → detect gap → decision
  if INSERT_TASK: analyze gap → propose task → validate → mutate DAG
                 → increment plan_version → assign Agent → execute → validate → continue
```

## 10. 真实性要求

```
新任务必须由 TaskProposalEngine 生成 (非测试注入)
测试只能提供初始项目 + 真实 GAP 信号
真实 DeepSeek 参与任务生成/执行
```

## 11. 模块计划

```
新增: session/gap_analyzer.py + session/task_proposal.py
修改: session/replanning.py (INSERT 自动提案) + session/orchestrator.py (循环接入)
新增测试: test_session_gap_analyzer.py / test_session_task_proposal.py /
          test_session_autonomous_replanning.py (合计 >=100)
```

## 12. 边界

- 不做: LLM semantic similarity (先 deterministic) / PyPI / marketing / UI / SaaS / 并行 DAG
- S10-060 API 保持兼容

---

> 设计完毕 | GapAnalyzer + TaskProposal + Validator + Duplicate + 安全边界 + 真实接入
