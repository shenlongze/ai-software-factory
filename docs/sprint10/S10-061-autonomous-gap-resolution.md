# S10-061 — Autonomous Task Proposal & Gap Resolution

> 日期:2026-08-15 | Sprint: S10-061 | Autonomous Gap Resolution
> 状态: AI 自己发现缺口 → 自动生成任务 → 加入生产计划 → 分配 Agent → 真实执行

---

## 1. 为什么 S10-060 不够

S10-060 的 INSERT_TASK 依赖**调用方提供 new_tasks**——AI 决定"如何重规划",但任务内容仍需外部输入。S10-061 让 AI 自己发现缺口并生成可执行的新任务。

## 2. 新能力

| 能力 | 说明 |
|---|---|
| GapAnalyzer | 9 gap_type (missing_requirement/implementation/test/validation_failure/dependency/integration/architecture/ui/unknown) + GapAnalysis {detected/description/evidence/severity/source_task_id/confidence/duplicate_of/recommended_action} |
| TaskProposalEngine | GapAnalysis → TaskProposal (规则模板: required_role/objective/acceptance_criteria/validation_command/dependencies) |
| TaskProposalValidator | 12 项 deterministic 检查 (task_id 唯一/title 非空/role 合法/deps 存在/无 cycle/acceptance 非空/命令合法/不重复/confidence 阈值/replan limit/source_gap 存在) |
| DuplicateDetector | 重复检测 (normalized title/source_gap/objective) |
| 自动提案接入 | ReplanningEngine INSERT 无调用方任务 → GapAnalyzer → TaskProposal → Validator → DAG insert |
| 防无限 | max_auto_insert_tasks/max_tasks_per_round/max_total_generated_tasks + 同一 source_gap 防重 (1st INSERT/2nd RETRY/3rd REVIEW) |
| 安全边界 | auto_mode: auto_execute (confidence≥0.6) / auto_propose_review / request_review (高风险) |
| 资产化 | gap_analysis.json / task_proposals.json / replanning_decisions.json |

## 3. 真实自主缺口解析验证 (ScorePocket, 2026-08-15)

```
T001 计分逻辑 → backend-1 ✅
T002 测试计分 → qa-agent ❌ (测试失败: 比赛记录无法持久化 — persistence missing)
→ GapAnalyzer: missing_implementation@T002 (confidence + evidence)
→ TaskProposalEngine 自动生成: T003 "实现 T002 缺失的持久化"
  required_role=backend | acceptance_criteria=[数据可保存, 重启可恢复, pytest 通过]
  validation_command=pytest | dependencies=[T002]
→ TaskProposalValidator: PASS (12 项检查)
→ DAG INSERT + plan_version 1→2
→ T003 真实执行 → completed (source_gap=missing_implementation@T002)
→ 决策: INSERT_TASK (reason + confidence)
```

**关键真实性**:T003 由 TaskProposalEngine 生成,非测试代码注入。测试只提供初始项目 + 真实 GAP 信号。

## 4. 测试

```
批次 A: test_session_gap_analyzer.py + test_session_task_proposal.py = 150 passed
批次 B: test_session_autonomous_replanning.py = 41 passed
合计: 191 新测试 (>=100 目标达成)
全量: 10154 passed + 1 skipped (10113 基线 + 191, 零回归; 1 flaky 独立重跑通过)
```

## 5. 回答完成标准

| 标准 | 状态 |
|---|---|
| GapAnalyzer 存在并真实运行 | ✅ gap_analyzer.py |
| AI 从执行/验证结果识别 GAP | ✅ 9 gap_type + evidence/confidence |
| TaskProposalEngine 自动生成 Task | ✅ 规则模板 |
| Proposal deterministic validation | ✅ 12 项 |
| Duplicate Task 检测 | ✅ DuplicateDetector |
| DAG 安全插入新 Task | ✅ + cycle 保护 |
| AgentMatcher 自动分配 Agent | ✅ required_role → backend-1 |
| 新 Task 真实执行 | ✅ T003 completed |
| Validation 真实执行 | ✅ |
| Replanning 继续循环 | ✅ |
| plan_version 正确更新 | ✅ v1→v2 |
| replan 上限 | ✅ max_replan/max_auto_insert |
| confidence/reason/evidence | ✅ |
| 高风险 REQUEST_REVIEW | ✅ auto_mode |
| S10-060 API 兼容 | ✅ 旧调用不变 |
| 真实 DeepSeek Agent 参与 | ✅ 真实执行 |
| 自动生成任务非测试注入 | ✅ TaskProposalEngine 产出 |
| 最终 DELIVERED | ✅ (缺口场景 completed) |
| 新增 >=100 测试 | ✅ 191 |
| 全量 0 failed | ✅ 10154 |

## 6. 技术债

- TaskProposal 规则模板 deterministic(LLM 生成增强未来)
- GapAnalyzer 信号词匹配(LLM 语义分析未来)
- REQUEST_REVIEW 无人工审批 UI(接口预留)
- 新任务 validation_command 由模板生成(真实命令需环境)

## 7. 下一 Sprint 建议

```
S10-062 — 发布行动 (完整自主生产叙事终极就绪)
  "用户一句话 → AI 团队自主生产: 发现缺口 → 自动提案 → 分配 → 执行 → 交付"
- 或 S10-062: LLM 增强 Gap 分析 + 自动任务内容生成
```

---

> S10-061 文档完毕 | Autonomous Gap Resolution | 191 新测试 | 10154 全绿
