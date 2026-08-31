# K7 Real User Journeys

> 日期: 2026-08-29 | HEAD: (K7 commit) | v1.1.359

## 10 个 Golden Journeys (test_k7_journeys.py, 10/10 PASS)
| # | Journey | 关键验证 |
|---|---------|---------|
| J1 | 普通聊天 → 模糊想法 → 多轮澄清 | 讨论不创建 Work |
| J2 | 需求确认 → Requirement/Decision | req/decision 实体可追溯 |
| J3 | Project → Sprint → Task Tree | 全层进度投影 |
| J4 | Agent 真实执行 → Evidence → Result | evidence 实体真实 |
| J5 | Task 失败 → 诚实呈现 | explain_failure evidence-backed |
| J6 | Recovery (S39) → 结果回 Conversation | RECOVERED 状态回写 |
| J7 | Approval 阻塞 → 通过 → 继续 | governance 门不可绕过 |
| J8 | Replan (需求修改) | affected tasks 识别 |
| J9 | 查询进度 / 谁在工作 | 真实投影 |
| J10 | 回原 Conversation 继续 (Resume) | 上下文保持/不遗忘 |
