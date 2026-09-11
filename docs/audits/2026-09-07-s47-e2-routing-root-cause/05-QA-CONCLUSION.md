# 05 — 10 问答 + 最终结论 (READ-ONLY, 2026-09-07)

## Q1 谁决定 Tool?
LLM (function calling 自主) [FACT: 会话 trace 各轮 tool_calls 由模型产生;
无 Python 单工具强制]

## Q2 LLM 是否拥有真实 Tool Selection 权?
是 (全 FC 工具面)。但可见工具面被 CORE_TOOL_IDS 倾斜 (项目诊断 4/5 常驻)。

## Q3 是否存在 Python 硬编码路由?
无业务路由 (无 if message→tool; 无 forced/default/fallback tool)。
[FACT: grep 无 tool_choice/forced/fallback_tool]
有状态检测正则 (_PROPOSAL_PATTERN) + 降级词表 — 属护栏, 非业务路由。

## Q4 是否存在 Prompt 硬编码路由?
PARTIAL: intent 软参考 (understand_intent LLM 分类 + route_for 提示);
_initial_tools 工具面提示; E2 guide (条件注入)。均非强制。

## Q5 是否存在 Keyword Routing?
PARTIAL: intent deterministic 关键词 (只产软参考);
S35-UI 前端模板 (project_tasks→任务统计覆盖整轮) = 真硬编码 UI 投影。

## Q6 是否存在 Project Context → Project Tool 隐式强制?
PARTIAL (结构性倾斜): CORE_TOOL_IDS 恒含项目诊断四件套 → 项目会话 LLM
倾向选它们; 无 project_id 分支强制工具。

## Q7 是否存在 Unknown → Project Diagnostic fallback?
无专用 fallback 代码 [FACT]。现象等同: 投诉/含糊输入 → LLM 在常驻核心
工具面 (项目诊断) 中自选 → 看起来像 UNKNOWN→diagnostic。机制 = LLM 自主
+ 无 complaint/recovery 语义 + 工具面倾斜, 非 fallback 硬编码。

## Q8 Continuation 为什么没有保持语义?
双因:
1. proposal 检测 = 上轮 assistant 句尾正则; "需要的话我可以帮你启动
   需求分析流程。" (句号结尾) → 不中 → confirm 无 guide [FACT]
2. 无结构化 pending state — 即便 guide 命中, 也靠文本猜, 且被后续
   工具输出/错误回复覆盖

## Q9 Conversation State 是否真实存在?
NO (仅有 messages 历史 + 前端 meta; 无 topic/domain/pending_proposal/
constraints 状态层) [FACT]

## Q10 最小正确修复架构?
1. pending_proposal 结构化: assistant 含提议动作 → 存会话语义状态
   (proposal+domain+topic); 下轮 confirm/decline/redirect 直接指向
2. proposal 检测放宽: 提议=含"需要的话/我可以/建议/要我…" 句式 (LLM
   判定有无提议, 非句尾正则)
3. complaint/recovery 语义: 用户反馈跑题/混乱 → 恢复会话 topic 引导,
   不触发诊断工具自证
4. CORE 工具面平衡: 项目诊断 + 产品/需求域核心工具, 或按 conversation
   state 动态给工具
5. S35 前端模板降级: project_tasks 统计作卡片, 不整轮覆盖 AI 文本

## WHY "接受建议" FAILED
proposal 正则漏 (句号尾) → 无 confirm 引导 → LLM 在项目工具面自由选 4 工具
→ S35 模板把含 project_tasks 的整轮覆盖成任务统计 → 用户看到答非所问。

## WHY "继续分析需求" FAILED
无 pending topic/domain 继承 (继续分析需求 = 需求域, 但 state 无此概念) +
上轮无提议 guide + CORE 工具面倾斜 → LLM 重复选项目/任务工具调查。

## WHY "你什么情况" TRIGGERED PROJECT DIAGNOSTICS
投诉输入无 complaint 语义 → LLM 唯一可靠可见动作 = CORE 项目诊断四件套
(project_status/scan/code_scan/bash_exec) → 全选自证。非硬编码 fallback,
是工具面倾斜 + 无语义类别的结构性结果。

## 建议
以下为报告, 非修复。修复方案建议在独立任务书批准后实施 (Q10 五条)。

## 停止条件检查
无 P0 强制硬路由 (LLM 有真实选择权); 无 Core contract 冲突;
E1/E2 修复与 Router 无架构冲突 (缺陷=检测过窄+无状态, 非架构冲突);
Conversation State 缺失 = 核心能力缺口 (已报告)。 本轮 STOP → 报告完毕。
