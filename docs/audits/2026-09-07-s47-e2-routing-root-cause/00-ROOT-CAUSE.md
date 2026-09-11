# 00 — ROOT CAUSE (READ-ONLY forensic, 2026-09-07)

## 核心结论 (全部 FACT)
"接受建议" / "继续分析需求" / "你什么情况，这么乱么" 失控 =
**LLM 自主工具选择被三重缺陷放任** (无强制硬路由; 但无语义护栏):

## PRIMARY OFFENDER
**1. proposal 检测正则过窄 (E1/E2 continuation guide 漏检)** [FACT]
- 会话 [3] assistant 提议结尾: "……需要的话我可以帮你启动需求分析流程。"
  (句号结尾, 无"吗") → _PROPOSAL_PATTERN (需要吗|要我|…|吗[?？]?)$ **不匹配**
- → "接受建议"(确认语义) 无任何 continuation 引导注入 → LLM 自由失控
- 文件: factory-console/session/agent_loop.py _PROPOSAL_PATTERN/_continuation_guide_semantic

## SECONDARY CONTRIBUTORS
**2. CORE_TOOL_IDS 常驻工具面 = 项目诊断四件套** [FACT]
- CORE_TOOL_IDS = [project_status, project_scan, code_scan, bash_exec, web_search]
- 任何会话首轮必见这 5 个; 4/5 是项目诊断
- "你什么情况，这么乱么"(投诉) → LLM 无 complaint 语义类别 → 在核心工具面
  中选全部项目诊断工具自证 → status/scan/code_scan/bash_exec [FACT, 会话trace]
- 无 需求/产品域核心工具; product_lifecycle 需 discover 检索才可见

**3. S35-UI 前端模板整轮覆盖** [FACT]
- AfConversationCenter taskStatsText: 该轮 tool_calls 含 project_tasks →
  displayContent = 任务统计模板 (替换 AI 全部真实文本)
- "接受建议"轮 AI 实际在调查 (code_scan 文本), 用户看到 = "当前项目共有
  20 个任务…" → UI 层硬编码投影放大错配

**4. 无 topic-recovery / complaint 语义; intent 软参考过弱** [PARTIAL]
- run_agent_native: intent 仅软参考; LLM 在历史污染(上轮模板/工具输出)与
  核心工具面下自由选择; "继续分析需求" 无 pending-topic 状态继承

## IS THERE HARD-CODED ROUTING: PARTIAL
- Python 业务路由: NO (无 if message→tool; 无 forced tool; LLM FC 全自主)
- Prompt 业务路由: PARTIAL (intent 软参考 + 工具描述引导; 非强制)
- Keyword: PARTIAL (intent deterministic 规则只产生软参考; S35 前端模板是真
  硬编码渲染: project_tasks→任务统计)
- Project→Project-tool 隐式强制: PARTIAL (CORE 工具面=项目诊断常驻,
  项目会话天然可见性倾斜)

## Conversation State: NO (无持久语义状态; pending_proposal 每轮从文本猜)
## Tool Selection Semantic: PARTIAL (LLM 自主=语义, 但护栏缺失)
