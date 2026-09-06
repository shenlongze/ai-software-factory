# 00 — S47-E2 Conversation Semantic Continuity & Intent Governance (2026-09-07)

## 1. Root Cause
E1 continuation 用词表 (需要/好→confirm) — 本质 keyword→action:
- 无法表达 "可以，不过先完善登录" (确认+约束)
- 无法表达 "刚才那个方案呢" (指代) / "我想改目标" (转向) / 拒绝变体
- LLM 对单字仍可能困惑 (无结构化 relation 引导)

## 2. Current Architecture
WebUI → api_session_send → run_agent_native (history 4轮注入 + E1 词表
guide) → LLM FC 工具 → answer。

## 3. Semantic Model
回合关系 (Turn Relation) 语义类别: confirm / confirm_modify (约束) /
decline / reference / redirect / ambiguous — LLM 判定, 词表不参与行为。

## 4. Conversation State Model
既有: 历史消息 (fact) + 上轮 assistant 提议 (候选) + 本轮 semantic guide
注入。无新 ContextRuntime (复用 run_agent_native 注入点)。

## 5. Pending Proposal Model
上轮 assistant 提议 (候选检测: 提议问句) → relation 分类 → 引导引用提议。
结构化 summary/约束由 LLM 提取 (无独立 proposal store — 最小充分)。

## 6. Routing Model
User → (上轮提议候选) → LLM 语义分类 relation → 对应引导注入 → 主 agent
自主执行 (工具选择仍由 agent + intent 软参考; 不跑题靠 relation 引导)。

## 7. Truth Model
不变: canonical truth (E1 product_lifecycle 等工具) — 本任务不涉及。

## 8. Changes
- agent_loop: _TURN_RELATION_PROMPT + _classify_turn_relation +
  _continuation_guide_semantic; run_agent_native 注入切换 semantic
  (词表 _continuation_guide 降级保护仅 LLM 不可用)

## 9. Tests
27 新 (语义等价: 确认 7 表达 / confirm_modify 4 / decline 5 / reference 4 /
redirect 3 / ambiguous / 无提议空 / LLM 不可用降级 / 任意表达由 LLM 判)
+ E1 15 = 42; 回归 117 passed 0 failed

## 10. Real E2E (真实 LLM)
5/5: 需要→confirm; 可以不过先完善登录→confirm_modify (summary 提取约束);
不用了先看问题→decline; 刚才那个方案呢→reference; 先别做PRD→redirect

## 11. Natural Language Matrix
确认: 需要/好/可以/行/继续吧/你继续/就按这个来 → confirm
修改确认: 可以不过先完善登录/继续但先别生成代码 → confirm_modify
拒绝: 不用/先不要/算了/暂时不做/先放一下 → decline
指代: 刚才那个方案呢/你提到的PRD → reference
转向: 先别做PRD重新梳理/先做登录不做支付 → redirect
含糊: 嗯/然后呢 → ambiguous (最小澄清)
(矩阵由真实 LLM E2E 抽样验证; 全量等价在单测 mock LLM 层覆盖)

## 12. Anti-Hardcoding Audit
- 无 if message==/contains; 无 per-question 分支; 无 per-project 逻辑
- 词表仅: 提议问句候选检测 (状态判定) + LLM 不可用降级
- 行为 = LLM 语义判定 → 引导; 测试证明任意表达由 LLM 判 (mock)

## 13. Regression
117 passed 0 failed (S47-E1/E2 + S45/S44/session_webui/P1/s10_114/s10_117)

## 14. Git Commit
2b9848f2 feat(conversation): establish semantic continuity and intent governance
NO PUSH

## 15. Remaining Risks
- 提议候选检测仍用句尾正则 (近似; 提议形态多变 → 漏检时无 guide, agent
  仍靠历史)
- 每延续轮 +1 次小 LLM 分类调用 (延迟/成本)
- 约束吸收由主 agent 执行 (LLM 遵循 guide 的质量依赖模型)

## 16. Final Verdict: ACCEPT (语义机制, 零关键词行为; 反硬编码审计通过)
核心问题: 自然交流+保持目标+不跑题+真实事实 → 是 (语义 relation 分类 +
E1 lifecycle 路由 + canonical truth 工具; 歧义最小澄清不猜)。
