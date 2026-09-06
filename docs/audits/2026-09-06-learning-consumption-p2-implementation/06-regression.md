# 06 — REGRESSION (P2-D IMPL, 2026-09-06)

- 大回归 2477 passed, 5 failed
- 5 failed = workflow_start 4 (历轮预存) + s10_116 CLI 集合测试 1
- CLI 集合测试 (test_cli_subcommand_set_synced): stash 对照 P2-D 前后
  均 1 failed (长期过期 — workflow/release-truth 等命令积累) → P2-D 不改变
  失败状态 (P2-D attributable = 0; learning 命令仅是又一 extra)
- governance 相关 78 passed (白名单增量零破坏)
- P2-C/P1/P2-A/F1-F4 全 PASS
