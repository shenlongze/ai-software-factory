# 01 — CONTRACT C1-C18 (P2-A ACCEPTANCE, 2026-09-06)

| # | 要求 | 状态 | Evidence |
|---|---|---|---|
| C1 | Canonical Release entity | PASS | RELEASE-{hex8} (release_truth.py) |
| C2 | Canonical ID | PASS | RELEASE-* (唯一前缀) |
| C3 | Canonical SSOT | PASS | releases/release_truth.json (独立) |
| C4 | Unique writer | PASS | release_truth 模块唯一 (grep 无外部写) |
| C5 | Lifecycle | PASS | CANDIDATE→GATED→RELEASED→SUPERSEDED/REVOKED/REJECTED (受控转换) |
| C6 | Artifact→Release FK | PASS | artifact_ids[] (create 自动收集) |
| C7 | Verification→Release FK | PASS | verification_ids[] |
| C8 | Evidence→Release FK | PASS | evidence_ids[] (经 ver) |
| C9 | TaskRun→Release provenance | PASS | task_run_id/exs_id (真实 canonical) |
| C10 | Gate 消费 ver-* | PASS | get_verification (verification_domain); 禁 pytest/snapshot |
| C11 | Gate 消费 EVD-* | PASS | list_evidence (evidence_domain); completeness 检查 |
| C12 | Release→TASK trace | PASS | task_id → reverse_trace |
| C13 | Release→Product trace | PASS | E2E-1 反查到 IDEA (全 FK) |
| C14 | Legacy rel-* 隔离 | PASS | 独立文件; rel-* 域 0 RELEASE- |
| C15 | No migration/backfill | PASS | rel-* 未动 |
| C16 | Git tag ≠ Release Truth | PASS | metadata 字段 (external ref) |
| C17 | WebUI = projection | PASS | 前端零引用 release_truth |
| C18 | Learning boundary | PASS | 未实现 Learning |

**C1-C18 全 PASS**
