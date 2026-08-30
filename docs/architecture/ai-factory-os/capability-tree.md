# S41 Capability Tree — AI Factory OS

> 日期: 2026-08-29 | 纯审计

```
AI Factory OS
├── Core (REAL): ProductionRun/NodeRun/Artifact/Verification/Evidence/Lineage/Audit
├── Organization (REAL, S30): Org/Department 层级
├── Workforce (REAL, S30): Workforce/AgentProfile/Lifecycle
├── Agent (REAL, S30): AgentProfile + Role/Capability
├── Plugin (REAL, S31): Kernel/Registry/Resolver/Lifecycle/Governance
├── Skill (REAL, S32): Composition binding
├── Tool (REAL, S32): Composition binding
├── Model (REAL, S32): Composition binding
├── Provider (REAL, S31/S32): Provider Plugin + 替换
├── Runtime (REAL, S32): Composition binding
├── Workflow (REAL, S3/S10): Professional Workflow
├── Node (REAL, S2): NodeRun 独立执行/验证循环
├── Execution (REAL, S4): executor_factory 注入
├── Verification (REAL, S5): syntax+pytest subprocess
├── Evidence (REAL, S23): evidence_refs 校验
├── Lineage (REAL, S22/S30/S32): 全链可追溯
├── Audit (REAL, S0.5): AuditEvent Store
├── Context (REAL, S35): Request/Budget/Resolver/Snapshot
├── Memory (REAL, S35): Plugin Contract + Local
├── Retrieval (REAL, S36): Utility Ranking/JIT
├── Learning (REAL, S37): Observation→Candidate→Evaluation
├── Evaluation (REAL, S38): baseline vs candidate
├── Experiment (REAL, S38): budget/sample/sandbox
├── Governance (REAL, S17/S38): approval/human gate/risk
├── Promotion (REAL, S38): governed/canary/snapshot
├── Canary (REAL, S38): bounded scope/runs/cost
├── Rollback (REAL, S21): health→incident→rollback→verify
├── Self-Healing (REAL, S39): incident→diagnosis→repair→recover
├── Self-Optimization (REAL, S40): opportunity→candidate→promote
├── Product (PARTIAL, S10): professional workflow 产品化
├── Market/Competitive/PRD/UX (MISSING→DEFERRED): 企业模块未来
├── Engineering/QA/Release (REAL via professional_workflow)
├── Operations (REAL, S21/S22): health/scheduler/control tower
├── Customer/Sales/Marketing/Finance/HR (MISSING→DEFERRED): 企业模块未来
└── Future Enterprise Modules (DEFERRED): 见 enterprise-capability-audit
```

## 判定依据
- REAL = 真实执行链 + 测试证据
- PARTIAL = 存在但非完整
- MISSING→DEFERRED = 明确不做 (企业 OS 未来模块)
