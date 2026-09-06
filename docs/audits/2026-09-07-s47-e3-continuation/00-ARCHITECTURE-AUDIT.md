# 00 — S47-E3 ARCHITECTURE AUDIT (2026-09-07, READ-ONLY)

## 基线
HEAD ea76a9e5 (S47-E2 docs) | 零改动

## 审计结论
1. 可复用真实结构: product_truth.py 提供 canonical 写 API
   create_discovery / create_requirement / create_prd / create_plan
   (真实生产链; ~/.factory canonical P1 现为空 — 诚实起点);
   project_lifecycle 工具读 canonical+org (E1); plan_development/
   execute_plan (开发计划→审批→backlog); conversation_os
   extract_requirement (org requirements)
2. Product Truth ↔ Conv State 关联: 仅经 project_lifecycle 工具输出文本;
   conv_state 不引用具体 truth 记录
3. 进行中工作表示: 无 (workflow run 在 workflow_runs/ 与执行链, 会话不感知)
4. active_work/stage/source/position/next 确定: 无机制 (全部由 LLM 自由)
5. continue 为何不能恢复: governor guide 止于文本"保持主题"; 无工作恢复
   上下文注入 (审计见 s47-e2-routing-root-cause #3/#4)
6. confirm 为何不能执行 pending: pending 只作文本引用, 无 action 绑定
7. modify/reference 语义承载: 仅 guide 文本
8. 可复用 Planner/Executor: workflow_runner (全自动 8 阶段, 重);
   plan_development (轻, 会话内); product_truth 写 API (canonical 落盘)
9. 第二 orchestrator 风险: 若自建 execution router → 违规;
   E3 只做 恢复上下文 + 暴露既有 canonical 写 API, 交 agent LLM 执行
10. 复用清单: conv_state (扩展) + governor + project_lifecycle (读) +
    product_truth.create_* (写, 工具化暴露) + agent FC (执行)

## E3 设计 (最小)
- conv_state 扩展: active_work / current_stage / next_action /
  last_work_output (由 resolver 写; 引用 truth 非复制)
- ActiveWorkResolver (LLM, continue/confirm/modify/reference 触发):
  输入 = conv_state + 用户消息; 输出 {active_work, current_stage,
  truth_summary 引用, next_action, need_user_input, question}
  → 注入结构化工作恢复引导 (现状+下一步+不必重问已知)
- 新会话工具 save_product_record (kind=discovery|requirement|prd|plan,
  title, content): 代理 product_truth.create_* — 暴露既有 canonical
  写 API 给会话 (能力注册层, 非新 truth / 非新 orchestrator)
- 前端: taskStats 卡仅在"该轮工具调用 = project_tasks 单一查询"时显
  (结构条件; continue 轮混工具不显; 非关键词)
