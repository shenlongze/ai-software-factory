# MASTER CONTROL PLANE TREE — STEP 9 (2026-09-02)
> AI Factory 如何选择/组织/执行 AI 能力

```
CONTROL PLANE
│
├── Agent 控制面 (M3, 局部)
│   ├── Registry        [PRODUCTION] agents.json 8
│   ├── Selection       [PRODUCTION] gateway.py:18 _pick_executor → router.route
│   ├── Routing         [PRODUCTION] classify_task + score_candidate (router.py)
│   ├── Runtime         [PRODUCTION] exec agent_runtime (records 100)
│   ├── Execution       [PRODUCTION] records + artifacts
│   ├── Tool            [PRODUCTION] _fc + exec tool
│   ├── Skill           [IMPLEMENTED] skills.json (消费 UNKNOWN)
│   ├── MCP             [IMPLEMENTED] mcp.py (console service.py:818)
│   └── Evidence        [PARTIAL] results/records; 会话链绑定部分
│   → OS 级统一员工编排 (7 角色动态组织): UNKNOWN (角色 Agent 触发入口)
│
├── LLM 控制面 (M4 调用 / M1 选择)
│   ├── Invocation      [M4] llm_fn 统一注入 (console_sessions.py:104)
│   ├── Provider        [M3] providers.json deepseek
│   ├── Config          [M3] api_key_ref env
│   ├── Model Catalog   [M2] models 列表 (无独立 catalog 实体)
│   ├── Model Selection [M1] LLMRouter 生产消费 0
│   ├── Routing         [M1] LLMRouter 定义, 未接入
│   ├── Fallback        [M0] 无生产证据
│   ├── Policy          [M1] budget.py (exec), 生产使用 UNKNOWN
│   └── Observability   [M3] usage.json (latency/cost/success)
│   → 结论: 调用真实统一; 选择/路由未形成生产闭环 (G-LLM-01 TRUE_GAP)
│
├── Orchestration (HYBRID — STEP 7 冻结)
│   ├── 执行层调度     [DYNAMIC] ExecState 依赖门控 (M4)
│   ├── Agent 选择     [DYNAMIC] gateway router (M3)
│   ├── 任务规划       [SEMI-DYNAMIC] plan_development (LLM 内容, 模板结构)
│   ├── 模型选择       [STATIC] provider._default_llm_fn (无路由)
│   ├── 生命周期       [STATIC] plan→approve→task→exec→reconcile 固定链
│   └── Replan         [ABSENT→FUTURE M3]
│
└── 决策点清单 (WHO SELECTS WHAT)
    ├── Agent: gateway._pick_executor (router classify+score)
    ├── Model: provider._default_llm_fn (固定)
    ├── Tool: agent_loop _fc 注册 (LLM 选工具名, 固定枚举)
    ├── Task 顺序: ExecState.next (依赖驱动)
    ├── 计划内容: LLM (plan_development)
    └── 执行方式: 单任务串行 (真并行未实现)
