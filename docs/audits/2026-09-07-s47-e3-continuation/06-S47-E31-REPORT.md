# S47-E3.1 REPORT (2026-09-07)

## 目标
Active Work 锚定 + Truth-aware Resolver + 先做后问。

## 实现
- _ACTIVE_WORK_PROMPT 注入 {truth}: 当前真实 Truth (product_lifecycle
  同源) → resolver 判缺口, 缺什么补什么
- 先做后问规则: 能从现有信息整理 → 直接整理 (标注待确认); 仅真正阻塞
  产出的关键决策才 need_user_input=true (不许"问一遍更稳妥")
- _work_recovery_guide: 基于 Truth 引导直接执行 + save_product_record
  落 canonical + 完成后告知实际完成
- run_agent_native: 注入前读 _project_lifecycle(project_id) 真实摘要;
  active_work 输出锚定 conv_state

## 验证
- 单测 10 (truth 注入占位/先做后问断言/need_input 文案)
- 真实 LLM E2E (P-b0adfaa6 真实 Truth):
  之前 (无 Truth): need_user_input=True ×3/4 (倾向问)
  之后 (带 Truth): need_user_input=False + next_action="基于会话计划
  整理需求清单 (功能/非功能/边界), 标注待确认项" — 先做后问达成
- 回归 backend 137 passed 0 failed | attributable = 0

## Git
f9796ca2 feat(conversation): truth-aware active work anchoring | NO PUSH

## Remaining
- E2 注入链完整验证需真实 WebUI 连续会话 (重启后)
- save_product_record 落 canonical 后 project_lifecycle 即时反映
  (同 store) — 下轮 continue 从新位置继续 (truth 变化 → 新缺口)
