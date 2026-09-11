# Requirement Analysis Capability — 缺失/误路由审计 (2026-09-07, READ-ONLY)

## 用户 10 问实证回答
1. 是否存在 requirement_analysis: **仅字符串标签** — roles.py(PM
   capabilities)/agents.py(supported_tasks)/workforce_os.py(skills)
   — 无任何实现实体
2. 它是什么: 角色能力关键词, 非可执行能力
3. 注册到 SkillRegistry/CapabilityRegistry? 否 — skill_search 库仅 4
   个技能, 无 requirement_analysis; dispatch 工具面无此工具
4. Agent 能否发现它: skill_search 检索不到实现 (只能撞到角色标签名)
5. Agent 能否调用它: 不能 — 无 handler/无产物 contract
6. 输入输出 Contract: 不存在
7. Analysis Finding/Decision/Question 结构化产物: 不存在
8. 用户确认后才写 Truth: 无强制 — 实例: agent 未经用户批准自标
   "REQ-97d28735 已 confirmed"(用户对话证据)
9. "继续分析"代码路径: LLM 自由循环 — governor continue →
   无专用能力 → get_product_record + project_lifecycle + LLM 文本推理
10. 为何落 get+save: 工具面只有读写工具; "分析" = LLM 临时推理,
   无分析工作结构

## 根因 (架构级)
- 会话能力面缺 "Requirement Analysis" 执行能力 — 角色能力标签与
  可执行工具/技能断链
- "需求分析 Loop"(目标→维度→逐项检查→Findings→Human Decision→
  Truth 更新→重分析)无载体
- 工具写 Truth 无 "人类决策确认门"(save 可自改状态 — 越权)

## 修复方向 (建议, 未实施 — 待用户批准)
A. 最小: 新增 requirement_analysis 会话工具/skill —
   输入 requirement_id, 输出结构化 Findings
   {gap|ambiguity|missing_constraint|decision_point, 维度,
    问题, 建议默认, needs_user_confirm} — 存 Analysis record;
   Human Decision 后由用户确认才写 requirement
B. 工具契约: save_product_record 状态字段改 protected
   (draft→confirmed 需 transition 走用户确认 — gate 已有 transition
   但 agent 直改 description 冒充 — 需禁止 content 内嵌状态)
C. "继续分析"路由到该能力; governor continue + domain=product →
   优先 requirement_analysis(若 REQ 存在未收敛)

## 判定
能力缺失(非路由错 — 无能力可路由); P1 级架构缺口。
