# S10-066 — GAP ANALYSIS

> 日期:2026-08-16 | Sprint: S10-066 | P0 现状审查
> 最高架构原则: 任何新能力必须 Core + CLI + API + Tests + Docs 同时交付

---

## 一、现有基础设施审查

### 1. API 基础设施
```
factory-console/api/ (已存在):
  __init__.py        — 路由函数注册 (chat_route/confirm_project_route/run_status_route/...)
  agent_executor.py  — POST /api/runtime/execute (Agent 全链路执行)
  approvals.py / artifacts.py / backlog.py / decisions.py / intelligence.py
  lifecycle.py / mcp_api.py
  模式: 纯函数路由 + Pydantic response models, 无 Web 依赖 — 未来 FastAPI 薄层做 HTTP 绑定

已有 intelligence API:
  GET /recommendations (RecommendationSummary: candidate/score/factors/explanation)
  GET /experience (ExperienceSummary: provider/agent/skill/workflow/success rate/confidence)
```

### 2. CLI 基础设施
```
cli_factory.py: factory start/stop/status/agent/skill/task/router/rag (服务运维)
session/commands.py: Slash 命令 (交互式)
session/actions.py: 28 个 action (create_product/execute_project/discovery_start/production_session_view/...)
```

### 3. 已有产品能力
```
create_product (ProductIntent: name/problem/user/platform/core_features)
generate_prd / prepare_project / DiscoverySession (S10-065)
产品智能 (industry/competitor/persona/conflict/value/MVP/business/market) 全无
```

## 二、GAP 汇总

| # | 缺失 | Core | CLI | API | 说明 |
|---|---|---|---|---|---|
| G1 | **Industry Understanding** | ❌ | ❌ | ❌ | 行业模式/用户类型/常见功能/痛点/技术趋势 → industry_analysis |
| G2 | **Competitor Analysis** | ❌ | ❌ | ❌ | 已有产品/竞争优势/差异化机会 → competitor_analysis |
| G3 | **User Persona** | ❌ | ❌ | ❌ | 用户画像/使用场景/用户痛点 → user_personas |
| G4 | **Requirement Conflict Detection** | ❌ | ❌ | ❌ | 需求冲突/不合理/技术风险 → requirement_conflicts |
| G5 | **Value Judgment** | ❌ | ❌ | ❌ | 是否值得做/用户价值/技术价值 → product_value_score |
| G6 | **MVP Planning** | ❌ | ❌ | ❌ | MVP/V2/Future 拆分 → mvp_plan |
| G7 | **Business Analysis** | ❌ | ❌ | ❌ | 盈利模式/成本/用户获取/商业风险 |
| G8 | **Market Analysis** | ❌ | ❌ | ❌ | 市场规模/用户趋势/机会窗口 |

## 三、架构方向

```
新增:
  session/product_intelligence.py — ProductIntelligenceEngine (Core)
    analyze(product_intent) -> ProductIntelligenceReport:
      {industry_analysis, competitor_analysis, user_personas,
       requirement_conflicts, product_value_score, mvp_plan,
       business_analysis, market_analysis}
    LLM 模式 (复用 ReasoningProvider S10-062) + deterministic 模式 (规则/模板)
  api/product_intelligence.py — API 路由函数 (纯函数 + Pydantic)
    POST /api/product/intelligence/analyze
    POST /api/product/market-analysis
    POST /api/product/persona
  CLI: factory product analyze / market / persona / mvp (session action + 注册)
  -h 帮助更新

复用: ProductIntent / ReasoningProvider (LLM) / gap_analyzer 规则模式 / actions 注册模式 / api/ 路由模式
```

## 四、测试计划 (Core/CLI/API 三覆盖)

```
Core:   ProductIntelligenceEngine 各分析模块 (industry/competitor/persona/conflict/value/mvp/business/market)
CLI:    factory product 命令路由 + 输出
API:    api/product_intelligence 路由函数 + response schema
合计 >=150
```

## 五、不该现在做 🚫

```
真实市场数据抓取 (用 LLM 知识 + 规则模板, 不做网络爬虫)
SaaS 化 / Web UI (API 纯函数出口已备)
新 Agent 决策类型 / 重写生产引擎
```

---

> GAP 完毕 | G1-G8 缺失 | API/CLI 基础设施可复用 | 每个能力 Core+CLI+API+Tests+Docs
