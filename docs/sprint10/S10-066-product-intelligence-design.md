# S10-066 — Product Intelligence 架构设计

> 日期:2026-08-16 | Sprint: S10-066 | 架构 (基于 GAP 分析 G1-G8)
> 最高原则: 每个能力 Core + CLI + API + Tests + Docs 同时交付

---

## 1. 架构

```
用户想法 → ProductIntent
              ↓
┌─────────────────────────────────────────────┐
│ ProductIntelligenceEngine (Core)            │
│   analyze(intent) → ProductIntelligenceReport│
│   1. industry_analysis (G1)                 │
│   2. competitor_analysis (G2)               │
│   3. user_personas (G3)                     │
│   4. requirement_conflicts (G4)             │
│   5. product_value_score (G5)               │
│   6. mvp_plan (G6)                          │
│   7. business_analysis (G7)                 │
│   8. market_analysis (G8)                   │
│   LLM 模式 (ReasoningProvider) + deterministic 模式   │
└──────────┬──────────────────────────────────┘
           ↓
┌──────────┴──────────┐  ┌─────────────────────┐
│ CLI (session action)│  │ API (纯函数路由)      │
│ factory product X   │  │ POST /api/product/...│
└─────────────────────┘  └─────────────────────┘
```

## 2. Core: ProductIntelligenceEngine (session/product_intelligence.py)

```
@dataclass IndustryAnalysis:
  industry / business_models / user_types / common_features / pain_points / tech_trends

@dataclass CompetitorAnalysis:
  competitors (list) / advantages / differentiation_opportunities

@dataclass UserPersona:
  name / description / scenarios / pain_points

@dataclass RequirementConflict:
  description / severity / affected_fields / suggestion

@dataclass ProductValueScore:
  score (0-100) / user_value / technical_value / justification

@dataclass MvpPlan:
  mvp (list) / v2 (list) / future (list)

@dataclass BusinessAnalysis:
  revenue_models / cost_structure / user_acquisition / business_risks

@dataclass MarketAnalysis:
  market_size / user_trends / opportunity_window

@dataclass ProductIntelligenceReport:
  product_name / analysis timestamp / 8 个模块 + to_dict()

class ProductIntelligenceEngine:
  analyze(product_intent, *, llm_provider=None) -> ProductIntelligenceReport
    - LLM 模式: llm_provider 提供 → 结构化输出 (复用 ReasoningProvider S10-062)
    - deterministic 模式: 规则/模板 (product_intent 字段 → 各分析模块)
    - fallback: LLM 失败 → deterministic (S10-062 模式)
  analyze_industry(intent) / analyze_competitor(intent) / analyze_persona(intent) /
  detect_conflicts(intent) / score_value(intent) / plan_mvp(intent) /
  analyze_business(intent) / analyze_market(intent) — 单模块方法
  save(workspace, report) / load(workspace, product) — product_intelligence.json
```

## 3. API (api/product_intelligence.py)

```
模式: 纯函数路由 + Pydantic models (无 Web 依赖, 同现有 api/ 模式)

POST /api/product/intelligence/analyze
  request: {product_intent: {...}} → response: ProductIntelligenceReport
POST /api/product/market-analysis
  request: {product_intent: {...}} → response: MarketAnalysis
POST /api/product/persona
  request: {product_intent: {...}} → response: list[UserPersona]

所有: error handling (异常 → 明确错误) + 注册到 api/__init__.py
```

## 4. CLI (session/actions.py)

```
新增 action:
  product_intelligence (factory product analyze) — 完整分析报告
  product_market (factory product market) — 市场分析
  product_persona (factory product persona) — 用户画像
  product_mvp (factory product mvp) — MVP 规划
  product_value (factory product value) — 价值评分
注册 + 关键词路由 ("分析产品"/"产品市场"/"产品画像"/"MVP规划"/"产品价值")
```

## 5. 复用

```
ProductIntent (product.py)
ReasoningProvider / LLMGapAnalyzer 模式 (S10-062)
api/ 纯函数路由模式 (agent_executor.py)
actions 注册模式 (S10-063/065)
Pydantic models (factory-console/models.py)
```

## 6. 测试计划 (Core/CLI/API 三覆盖, >=150)

```
Core (>=80): 8 模块分析 (industry/competitor/persona/conflict/value/mvp/business/market)
  + LLM 模式 (mock llm_fn) + deterministic 模式 + fallback + 持久化
CLI (>=40): factory product 命令路由 + 输出 + 关键词
API (>=30): 3 端点路由函数 + request/response schema + error handling
```

## 7. 边界

- 不抓取真实市场数据 (LLM 知识 + 规则模板)
- 不破坏现有 create_product/Discovery
- API 纯函数 (未来 FastAPI 薄层)
- 所有新增 CLI 加入 help

---

> 架构完毕 | 8 模块 ProductIntelligenceEngine + CLI + API | Core+CLI+API+Tests+Docs
