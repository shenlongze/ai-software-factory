# 00 — S47-E3.2 REPORT (2026-09-07)

## 1. Root Cause (审计确认)
- setdefault("active_work","") 永不更新 + resolver 结果不进 state → 影子
- next_action 仅文本建议, 无执行约束
- needs_tool=False 时注入"工具克制"与执行指令冲突 → LLM 不调工具
- save_product_record handler import_module("product_truth") 恒抛 (顶层
  import 不可用) → LLM 误报"保存通道不可用"
- 工具描述过保守 ("只写用户认可") → 授权语义缺失

## 2. Architecture Change
- state 真写回 (resolver → conv_state replace)
- 执行指令注入 (need_user_input=False → 【本轮执行指令·最高优先级】;
  True → 最小阻塞提问) — ask-user 受 ActiveWork.blocked 控制
- 执行类 relation 排除工具克制; import 修复; 工具描述授权放宽
- resolver prompt 含已锚定 work/prev_next (跨轮从新位置继续)

## 3. Active Work Contract
{goal, current_stage, next_action, need_user_input, question, blocked}
存于 conv_state (会话 projection, 非业务 truth; 引用 canonical)

## 4. Execution Binding
guide 强指令 → agent FC → save_product_record → product_truth.create_*
(requirement → REQ-* canonical)

## 5. State Persistence
conv_state: active_work/next_action/current_stage/need_user_input 跨轮
(replace 语义; 下轮 resolver 输入含锚定)

## 6. Truth Mutation
REQ-1151be38 (飞机大战需求清单: JavaScript/HTML/CSS/Three.js +
玩家控制/射击/敌机/碰撞/得分/生命/流程 功能模块 + 8 待确认) →
~/.factory/product_truth/requirements.json (真实 canonical)

## 7. Real LLM E2E (P-b0adfaa6)
"继续帮忙分析需求" → 恢复 active_work=需求分析 → 执行指令 → agent 真调
save_product_record → 回答 "产出 ID: REQ-1151be38" → 落盘验证存在。
诊断复读 (20任务/Python矛盾) 消除。非"项目查询机器人" — 真推进产出。

## 8. Canonical IDs
REQ-1151be38

## 9. Tests
13 (执行指令/禁 ask/最小 ask/跨轮 state/prompt 锚点/topic 切换/
modify·reference/失败安全/truth-aware)

## 10. Regression
backend 154 passed 0 failed | frontend (未变) | attributable = 0

## 11. Failure/Recovery
resolver 失败 → ("",{}) 不阻断; LLM 可用性依赖真实 provider (E2E 真跑)

## 12. Acceptance
架构 (Active Work first-class state ✓) / 持久化 (resolver→state ✓) /
执行 (next_action→save_product_record→REQ ✓) / User Input (False→禁问
✓) / Production (continue→真 REQ ✓) / Continuity (跨轮锚定 ✓)

## 13. Remaining Risks
- 单轮 agent 仍可列"待确认"后停下 (E2E 本轮已真写; 完整多轮细化依赖
  用户回答待确认项)
- CORE 工具面仍含项目诊断 (执行指令显式禁用; 未从面移除 — 治理层)
- save_product_record 的 title/content 长度与结构由 LLM 决定 (质量依赖
  模型; 已落 draft 可迭代)

## HEAD / Git
ec0a7bc7 feat(conversation): bind active work to next action execution
NO PUSH

## Final: ACCEPT
用户真实对话已从"项目查询机器人"跨到"持续推进工作的 AI 协作者":
continue → 恢复 Active Work → 真执行 → REQ 落盘 → 汇报实际完成。
