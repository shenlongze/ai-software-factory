# 01 — Requirement Analysis Loop 行为路径解剖 (2026-09-07, READ-ONLY)

## 循环形成路径 (代码实证)
1. governor: "继续分析需求" → relation=continue, domain=product_lifecycle
   (判定正确); "分析更多" → continue/execution (domain 次优)
2. continue → Active Work Resolver → next_action (LLM 每轮重推,
   无分析进度输入) → 注入执行引导
3. 工具面无 requirement_analysis 能力 → LLM 自由:
   get_product_record(读) → LLM 文本推理 → save_product_record(写)
4. 下轮 "继续分析" → 状态与上轮几乎相同 → 重读重写 → 循环

## 无 forward progress 证据
conv_state 键: topic/domain/relation/active_work/next_action/
current_stage/need_user_input — **无**:
  已分析维度 / 已发现问题 / 未决决策点 / 用户确认状态 / 迭代计数 /
  分析完成标记
→ 第二次"继续分析"与第一次输入状态无差异 → resolver 重推相似
  next_action → 循环无进展

## 三个语义混淆 (代码定位)
- save_product_record(record_id REFINE) = 写工具 — 被 LLM 当"分析完成"
  (handler 无 analysis 完成语义; 直接 update 无用户确认)
- get_product_record = 读工具 — 被当"分析"
- 用户确认: 无决策门 — agent 在 description 文本自标 "confirmed"
  (记录 status 字段未变 — 内容撒谎, 无状态治理)

## 循环退出条件 (Q10)
不存在: resolver next_action 无"分析收敛→进入下阶段"信号;
continue 无终止语义 (无限重推)

## 结论 (P1 定义确认)
Requirement Analysis Node 缺真实 Analysis Loop / Progress Semantics:
- 无 analysis 执行能力 (工具/skill)
- 无 analysis 进度状态 (维度/发现/决策/确认/迭代)
- 无人类决策门 (写前确认)
- 无退出条件 (收敛→下阶段)
→ "继续分析/分析更多" 退化为 读→写 重复循环

## 最小修复候选 (未实施, 待批准)
1. requirement_analysis 能力: 输入 REQ id + 目标维度 → 结构化 Findings
   (gap/ambiguity/decision_point) → Analysis 记录落盘 (analysis state:
   维度已覆盖/发现/待决/确认) — 迭代有 progress
2. 决策门: needs_user_confirm finding → 提问; 用户答复 → 更新
   requirement (经确认才写; 状态经 transition)
3. continue 语义: state 有 analysis 进度 → 从上次停点继续下一维度;
   全维度收敛(无新发现)→ 才推进下阶段 (退出条件)
