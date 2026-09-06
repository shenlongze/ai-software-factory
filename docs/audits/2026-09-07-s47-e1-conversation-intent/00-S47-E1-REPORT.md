# 00 — S47-E1 Conversation Intent & Product Truth Answering Repair (2026-09-07)

## 1. Problem
用户问 "需求分析完成了吗" → Factory 回答 "当前项目共有 20 个任务…" —
意图与事实域不匹配 (答非所问)。

## 2. Root Cause (代码取证)
- conversation 工具层 (agent_loop tool_schemas + handler) 无产品链查询能力:
  只有 project_status (项目 org 状态+任务统计) / project_tasks — 无
  REQ/PRD/PLAN 生命周期查询工具
- intent 域 (query_engine _INTENT_RULES + LLM prompt + VALID_INTENTS +
  intent_core route guide) 无 product-lifecycle 语义域 → 需求状态问题无
  意图 → LLM function calling 只能选到最接近的 project_tasks
- S35-UI 前端: 有 project_tasks 工具输出 → 固定模板渲染任务统计 (替换
  AI 文本), 放大错配
- P1 canonical product_truth 真实 store 为空 (诚实事实: 需求产品链从未
  落 canonical) — 但 org 有真实需求资产 (requirements.json
  req_33846c95b001 VALIDATED) 未被会话查询利用

## 3. Current Conversation → Tool Call Chain
user msg → understand_intent (LLM 软参考) → run_agent_native LLM
function calling (tool_schemas 全量) → 模型自选工具 → (需求问题错选
project_tasks) → S35 模板任务统计 → 错误回答

## 4. Product Truth availability
- canonical P1 (product_truth): ~/.factory 全 0 (IDEA/DISC/REQ/PRD/PLAN)
- org 资产: requirements/requirements.json (P-b0adfaa6 req_… VALIDATED
  测试飞机大战); session_plans.json (P-b0adfaa6 plan_… planning 飞机大战)

## 5. Fix
通用三层修复 (零硬编码):
- intent 域: + product_lifecycle (确定性信号簇 + LLM prompt 规则 +
  VALID_INTENTS + _ROUTE_GUIDE) — "产品链完成度" 与 "项目进度" 语义分离
- tool: + project_lifecycle 通用生命周期查询 — 读 canonical 5 域 +
  org requirements + session_plans, 各阶段 存在/状态/ID/缺失 独立如实
- (S35 前端模板不触碰 — 仅 project_tasks 输出触发; lifecycle 走 AI 文本)

## 6. Why not hard-coded
无 per-question/关键词补丁 (无 "需求分析" 专用分支); 修复 = 语义 intent
域 + 一个通用 lifecycle 工具 + tool 描述引导 LLM function calling;
泛化到 需求/PRD/方案/原型/拆解/计划 全类。

## 7. Intent/domain routing model
需求/PRD/方案/拆解完成度 → product_lifecycle; 项目进度/状态 →
project_status; 任务统计 → project_tasks; 执行/发布域留 LLM 自主 (工具
层 P2 补 release 查询)。

## 8. Tests
7/7: 需求/PRD/方案/拆解 6 问句 → product_lifecycle; 项目状态→status;
任务数→tasks; intent ∈ VALID; tool schema 暴露 + 描述引导; handler 空
store 诚实缺失; org 需求读取; 不编造完成。

## 9. Real Project Validation (P-b0adfaa6 飞机大战)
project_lifecycle → canonical 5 域 未建立 (诚实) + org 需求 VALIDATED
[req_33846c95b001] + 会话计划 planning — 回答基础真实。

## 10. Before / After
Before: "需求分析完成了吗" → project_tasks → "共有 20 个任务…"
After: intent=product_lifecycle → 工具 → "canonical 需求未建立; org 需求
已确认 (req…VALIDATED); 有计划(规划中); 不能凭任务数量判断需求分析完成"

## 11. Regression
111 passed + 1 pre-existing (test_cli_subcommand_set_synced — stash 对照
零差异) | attributable = 0

## 12. Git
42c593e1 fix(session): route product lifecycle questions to product truth
NO PUSH

## 13. Remaining Gaps
- Acceptance/Release 问句 (验收了吗/可以发布了吗) 无查询工具 — LLM 只能
  引导/答 Review 页; P2 (release 查询 tool)
- canonical P1 真实域为空 — S46 follow-up 主链 (REQ/PRD/PLAN 真实旅程)
  未接; 工具已诚实反映
- LLM function-calling 真实端到端 (需真实 LLM) 未跑 — 工具描述 + intent
  引导 + deterministic 测试覆盖; 可下轮用真实会话验证
