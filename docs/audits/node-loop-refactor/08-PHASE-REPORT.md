# Phase 1-4 实施报告 — Node Loop 重构 (2026-09-07)

## Commits
2afb4fdc (Phase 1: node_runtime E1/E2) + 9e6961bd (Phase 2: REQ Node)

## Phase 4 E2E 结果 (真实 LLM, 新项目, 9 轮)
✓ 轮1 "需求分析" → agent 选 requirement_analysis_round → 创建
  run-fa03cf1c6770 → WAITING_FOR_USER + 1 PENDING decision (Node 链通)
✓ 轮5/7 → requirement_analysis_answer → decision RESOLVED (actor human)
  → run RUNNING (同 run 恢复, 无重复创建)
✗ checkpoint.completed_dimensions 恒 null (run_round 的 checkpoint
  推进未生效 — 待查: bump_iteration 先建 checkpoint 后 run_round 读
  旧 run 对象/更新路径 bug)
✗ 轮2/3/8/9 agent 间歇回落旧路径 (get+save 深化) — LLM 工具选择不稳定

## 达标项 (架构原则验证)
- 一个 Node = 一个 NodeRun ✓ (requirement-analysis run 唯一, 无重复建)
- LLM 可 Ask User → WAIT ✓ (WAITING_FOR_USER 事实态)
- 用户答 → resume 同 run ✓
- LLM 不能伪确认 (record_decision actor=human 强制) ✓ (单测)
- 无第二 Runtime / 无新 Manager ✓ (扩展 node_runtime + 一个 node 模块)
- TASK execution 未回归 (回归 77+ passed)

## 未达标 / 残余
1. checkpoint 推进 bug (dims null) — Phase 2 代码路径需排查
2. Conversation 收敛 (Phase 3) 未做 — agent 仍可回落旧 save 路径
3. 全链 (至 PRD transition) 未验证 (收敛 COMPLETED 未达)

## 建议下一步
Phase 2.1: 修 checkpoint 推进 (run_round 读/写一致性) + 单测覆盖
  dims 推进 → Phase 3: Conversation 意图→Node 收敛 (旧路径引导退役)
  → Phase 4 完整收敛 E2E (多决策 → COMPLETED → PRD transition)
