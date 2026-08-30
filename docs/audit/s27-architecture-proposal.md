# S27 Architecture Proposal — Production Experiment Reliability & Evaluation Quality

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. Production Outcome Contract (冻结, 投影)
```
COMPLETED: ProductionRun COMPLETED + Artifact + Verification 满足 Evaluation 条件
INCOMPLETE: 执行未形成完整可评价 Outcome
FAILED: 明确失败 + 失败 evidence
BLOCKED: Governance/Approval/Policy/Budget
CANCELLED: 明确取消
```

## 2. Failure Classification (冻结, deterministic projection)
```
AGENT_FAILURE: executor 执行错误/无效输出
PRODUCTION_FAILURE: pipeline 本身失败 (orchestrator/executor/delivery)
VERIFICATION_FAILURE: Production 完成但 verification FAIL (pytest)
EVALUATION_FAILURE: Production+Verification 完成但 Evaluation 无有效 metric
EXPERIMENT_FAILURE: 实验框架失败 (assignment/variant/persistence/measurement)
INFRASTRUCTURE_FAILURE: 基础设施 (LLM provider/网络/超时)
BUDGET_EXCEEDED: 预算超限
TIMEOUT: 超时
GOVERNANCE_BLOCKED: 未批准
UNKNOWN: 证据不足 (不猜测)
classification + confidence + evidence_refs + explain
```

## 3. Classification 规则 (冻结, 确定性)
```
run.state == FAILED 且 failure 含 "内置 pytest 失败" → VERIFICATION_FAILURE
run.state == FAILED 且 failure 含 "未知角色"/executor error → AGENT_FAILURE
run.state == BLOCKED → GOVERNANCE_BLOCKED
run.state == COMPLETED 但 evaluation 无 metric → EVALUATION_FAILURE
样本无 run/无 failure → UNKNOWN
```

## 4. Sample Eligibility (冻结)
```
ELIGIBLE: Production COMPLETED + Verification PASS + Evaluation 有效 + metric 存在 + lineage 完整
INELIGIBLE: 任一不满足 + reason + failure_class + evidence_refs
```

## 5. Selection Bias 保护 (冻结)
```
Reliability summary 必含: total_samples / eligible / ineligible / failed / incomplete / blocked
失败样本保留在 denominator (不静默删除)
```

## 6. Lineage (冻结)
```
ProductionRun → Artifact → Verification → Evaluation → Classification → Eligibility → Sample → Measurement → Outcome
```

## 7. CLI/API
```
factory experiment inspect <id> | samples <exp> | classify <sample> | eligibility <sample> | failures <exp> | reliability <exp>
GET /api/experiments/{id}/samples | /api/experiment-samples/{id} | /api/experiment-samples/{id}/classification |
/api/experiment-samples/{id}/eligibility | /api/experiments/{id}/failures | /api/experiments/{id}/reliability
```
