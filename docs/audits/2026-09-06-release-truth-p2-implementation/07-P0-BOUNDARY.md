# 07 — P0/P1 BOUNDARY (P2-A IMPL, 2026-09-06)

- P0 生产文件零改动 (node_runtime/verification_domain/evidence_domain/
  artifact_lifecycle/external_executor/factory-org — git diff 空)
- P1 product_truth 零改动 (只读复用 reverse_trace)
- Release consume-only: art/ver/EVD/EXS/run/task 全经 FK 读
- governance_service.py 改动 = subject_type 白名单 + release (非 P0/P1 冻结文件,
  纯增量向后兼容)
