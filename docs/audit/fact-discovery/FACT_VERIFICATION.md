# FACT VERIFICATION — STEP 2 (2026-09-02)

> 逐条验证 STEP 1 候选事实。STATUS: CONFIRMED / PARTIALLY_CONFIRMED / REFUTED / UNKNOWN
> 证据类型: STATIC(import/代码) / RUNTIME(运行链/数据) / COUNTER(反证)

## F-1 runtime only loads console + org
- CLAIM: uvicorn 只启动 factory-console; org 被 console import
- STATIC: fastapi_adapter.py:7953 create_app → build_console_service; 7963-7966 uvicorn.run
- RUNTIME: console import org 69 处 (from org.projects/org.models/org.management/org.events)
- COUNTER: console 还经延迟导入使用 exec 包 (见 F-3)
- FINAL: **CONFIRMED** (核心运行时 console+org; exec 为可选扩展)

## F-2 371 HTTP endpoints
- CLAIM: fastapi_adapter.py 有 371 端点
- STATIC: @app.get/post/put/delete/patch 全量提取 = 371
- RUNTIME: 未逐端点调用验证
- COUNTER: 无
- FINAL: **CONFIRMED (静态)**; 逐端点运行时行为 UNKNOWN

## F-3 five packages zero import
- CLAIM: 5 包互不 import
- STATIC: console → factory_core = 0; console → factory_runtime = 0;
  console → exec(包名) = **6 处延迟导入** (service.py:412/422/445/539/671/818)
- RUNTIME: console 经 importlib/延迟 import 使用 exec (Removal Isolation 注释 service.py:376)
- COUNTER: STEP 1 只 grep "factory_exec" 漏了包名 "exec" — 方法缺陷
- FINAL: **PARTIALLY REFUTED** — console→exec 有运行时依赖 (可选); console→core = 0 (CONFIRMED);
  console→runtime = 0 (CONFIRMED); exec/core/runtime 相互 = UNKNOWN (未扫)

## F-4 175+ LLM calls / 154 direct
- CLAIM: LLM 调用 175+, 154 直接形态 (88%)
- STATIC: grep llm_fn|llm_raw|chat_completion 175+; 但 llm_raw 定义 console_sessions.py:104
  (provider._default_llm_fn 装配), 调用点仅 2 处 — 模块通过 llm_fn 依赖注入
- RUNTIME: llm_fn 参数贯穿 (decomposer/discovery/agent_loop 等)
- COUNTER: 154 处"直接形态"多数是 **llm_fn 参数调用 (统一注入入口)**, 非绕过 router 裸调用;
  LLMRouter (llm_router.py:107 route) 分层真实存在, 但被哪些路径使用 UNKNOWN
- FINAL: **PARTIALLY_CONFIRMED** — 需区分: llm_fn 注入调用 (统一) vs LLMRouter 选择 (范围未验证)

## F-5 console imports org
- CLAIM: console 使用 org 领域
- STATIC: from org.* 69 处
- RUNTIME: E2E 运行链 (org.management 读写 backlog)
- FINAL: **CONFIRMED**

## F-6 three execution systems
- CLAIM: 会话链 / M3 production_run / exec 员工执行器
- STATIC: 会话链 (agent_loop: execute_plan/chain_next/gateway);
  M3 (actions.py:1645/1758 execute_project → orchestrator → execution_plan.json);
  exec 包 (agent_executor/AgentRuntime/runtime_session, console service.py 延迟导入)
- RUNTIME: 会话链 E2E 验证; M3 历史; exec 经 console 懒装配 (runtime-sessions/agents/skills 端点)
- FINAL: **CONFIRMED** — 三系统, exec 被 console 延迟集成 (Removal Isolation)

## F-7 Requirement/PRD persistence
- CLAIM: Requirement/PRD 无结构化持久化
- STATIC: product_intelligence action (actions.py:2864-2893) 返回 markdown, 无 save —
  **分析报告不落盘 (CONFIRMED)**
- COUNTER: **requirements.json 存在** (fastapi:1501-1504 读, agent_loop.py:795-803 会话侧写入,
  ~/.factory/requirements/requirements.json 按 project_id 过滤)
- FINAL: **PARTIALLY REFUTED** — Requirement 有落盘实体 (requirements.json);
  Product Intelligence 分析报告不落盘; PRD 结构化实体 UNKNOWN

## F-8 dual CLI
- CLAIM: console CLI + core CLI 两条
- STATIC: factory-console/cli_factory.py (8145 行, factory 命令);
  factory-core/cli/main.py (2605) + commands.py (3706, init/task/agent/skill/workflow/runtime)
- FINAL: **CONFIRMED** — 另加 exec CLI (exec/cli.py) + runtime CLI = 4 条 CLI 入口
