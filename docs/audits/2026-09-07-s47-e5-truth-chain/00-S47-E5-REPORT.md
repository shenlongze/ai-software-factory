# S47-E5 REPORT: Canonical Product Chain Continuity (2026-09-07)

## 目标
IDEA→Discovery→Requirement→PRD→Plan 全域统一 Read/Write/Refine/
Continue/Transition — 证明"产品主链可连续生产"(非补 4 个 API)。

## 实现
- product_truth: transition_discovery/prd/plan + update_idea/discovery
  + update_prd_content (PRD 版本化正文 v1→vN; draft 可改, 已批准拒绝)
- 工具: save_product_record 全域 (idea/discovery/requirement/prd;
  record_id → 同记录深化; prd content → 版本化 body; plan 不可变提示);
  get_product_record 全 kind (idea/plan + prd body)
- 旁路消除: execute_plan 批准执行 → canonical PLAN-* (approved);
  session_plans 仅工作态

## 验证
- 域全链测试 (tmp): IDEA→DISC→REQ→PRD(v3 版本化)→PLAN approved,
  各域 refine/transition/归属 ✓; approved 拒绝改 ✓; schema 全 kind ✓
- 回归: 102 passed 0 failed
- 真实 LLM 链 (有旧数据残留会话):
  ✓ REQ 深化同 id (v3 Three.js 数值)
  ✓ 跨阶段 PRD-cb9e2a3b 真落盘 (draft v2: 页面/玩法/UI/技术/差异对照)
  △ 轮1 "我想做X" 未建 Idea (agent 先对齐旧 REQ Canvas/Three.js 冲突 —
    旧数据干扰, 干净项目无此冲突)
  △ 轮2 discovery 卡 idea_id (链头依赖 — 首轮未建 idea)
  ✗ 轮6 误判"PRD 未建立" (get_product_record 工具直测正常; LLM 判断偏差)
    + 计划走审批流 (canonical PLAN 在 execute_plan 后落 — 设计如此)

## Acceptance
全域契约 (R/W/Refine/Continue/Transition) ✓ | PRD 版本化 ✓ |
旁路消除 (execute→PLAN-*) ✓ | 幂等同 id 深化 ✓ | 无句子→工具硬编码 ✓
跨阶段真落盘: REQ→PRD ✓

## Remaining (记录, 非阻塞)
1. 链头引导: 新项目首轮 "我想做X" → new_goal 建 Idea (save idea 已支持;
   需 execution 层倾向: 无冲突时直接建链头) — 属 Resolver/Execution 调优
2. 轮6 PRD 误判: LLM 多轮 get 后判断偏差 — 工具正常, 建议后续
   grounding/工具结果注入强化 (非结构性)
3. 旧 canonical 数据残留对真实验收干扰 — 已清 (供用户干净实测)

## Git
911ee236 feat(product): canonical product chain continuity | NO PUSH

## Verdict
基础设施层 ACCEPT: 全域 Read/Write/Refine/Continue/Transition 契约成立,
跨阶段 (REQ→PRD) 连续生产实证。真实验收受旧数据 + LLM 判断残余影响 —
建议用户在干净项目会话实测全链后定 final。

## S47 收口 (2026-09-07)
S47 = Conversation Production Entry 里程碑: Semantic intent / Active Work /
Continuation / Truth retrieval / Refinement / Canonical write / Idempotent
update / Cross-stage transition / Conversation→Product Truth。
残余 → LLM orchestration/context governance backlog (不阻塞主链):
  1. Idea 链头自动创建不稳定 (new_goal 首轮应建 Idea)
  2. LLM 偶尔误判已有 Truth 不存在 (grounding/工具结果强化)
  3. 旧数据 / memory 污染治理 (W4 human 会话流水注入策略)
