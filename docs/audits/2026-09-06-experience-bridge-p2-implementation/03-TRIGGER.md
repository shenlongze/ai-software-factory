# 03 — TRIGGER (P2-C IMPL, 2026-09-06)

## Trigger-1 (Production→exp)
- 位置: agent_loop 两处 finalize_node_run 后 (auto worker + chain dispatch)
- node_runtime (P0) 零改动 — C13 zero-diff 保持
- 失败安全: bridge 异常不阻断委派链

## Trigger-2 (Release→exp)
- 位置: CLI release-truth execute (调 execute_release 返回后 record_release)
- release_truth.py (P2-A) 零改动 — C15 zero-diff 保持
- 说明: release 执行当前唯一生产入口 = CLI (governance approval 流程);
  execute action 是真实入口 (API/自动化 future)
