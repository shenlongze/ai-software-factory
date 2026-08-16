# S10-067 — Memory Learning & Experience Intelligence 架构设计

> 日期:2026-08-17 | Sprint: S10-067 | 架构 (基于 GAP 分析 G1-G8)
> 核心理念: Execution → Observation → Learning → Pattern Extraction → Future Recommendation
> 最高原则: Core + CLI + API + Tests + Docs 同时交付

---

## 1. 架构

```
执行 (execution_records/repair/replanning/gap/validation)
              ↓
┌──────────────────────────────────────────────┐
│ Experience Extraction (extraction.py)        │
│  trace/decision/artifact → ExperienceRecord  │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│ Experience Store (experience_store.py)       │
│  experience_store.json + ExperienceRecord    │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│ Learning Engine (learning_engine.py)         │
│  Pattern Learning (成功/失败模式 + confidence)│
│  Agent Learning (能力成长)                    │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│ Retrieval (retrieval.py) → Recommendation    │
│  相似项目查询 → planning/debug 提醒           │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│ learning_trace.json (学习审计)                │
└──────────────────────────────────────────────┘
```

## 2. Core (memory/experience.py)

```
@dataclass ExperienceRecord:
  id/type/project/task/agent/role/context/problem/action/result/
  success/confidence/source/created_at
  TYPES: SUCCESS_PATTERN / FAILURE_PATTERN / DEBUG_EXPERIENCE /
         PLANNING_EXPERIENCE / AGENT_EXPERIENCE / USER_FEEDBACK
  to_dict/from_dict

class ExperienceStore:
  add(record) / records(type=None, project=None) / stats() / save/load
  → experience_store.json (失败安全)
```

## 3. Extraction (memory/extraction.py)

```
class ExperienceExtractor:
  extract_from_records(execution_records) -> list[ExperienceRecord]
    (失败记录 → FAILURE_PATTERN; 成功 → SUCCESS_PATTERN)
  extract_from_repairs(repair_tasks) -> list (DEBUG_EXPERIENCE)
  extract_from_replanning(replanning_decisions) -> list (PLANNING_EXPERIENCE)
  extract_from_gaps(gap_analyses) -> list (PLANNING_EXPERIENCE)
  extract_all(workspace) -> list (聚合全部数据源)
  → 提取到 ExperienceStore
```

## 4. Learning (memory/learning_engine.py)

```
class PatternLearner:
  learn(records) -> list[Pattern] (成功/失败模式 + confidence)
    Pattern: {pattern_id, name, description, success_rate, count, confidence}
    例: database_first_pattern (类似项目数据库设计不足 → 60% 返工)
  learn_agent(records) -> list[AgentProfile]
    AgentProfile: {agent_id, role, total_tasks, success_count, success_rate,
                   common_problems, best_domains}
class LearningEngine:
  run(workspace) -> LearningResult (提取 → 学习 → 模式/Agent 画像 → learning_trace)
```

## 5. Retrieval + Recommendation (memory/retrieval.py + recommendation.py)

```
class ExperienceRetriever:
  search(query, project=None, type=None) -> list[ExperienceRecord]
    (关键词匹配: project/problem/context/result + 类型过滤 + 按 confidence 排序)
  similar_projects(project_features) -> list (特征匹配)
class Recommender:
  recommend_for_planning(project_features) -> list[str] (提醒: "类似项目曾因...失败, 建议...")
  recommend_for_debug(problem) -> list[str] (历史解决方案)
  → 影响未来 (S10-068 Debug 基础)
```

## 6. learning_trace (memory/learning_trace.py)

```
class LearningTrace:
  record(source, learned, confidence, impact, details) → learning_trace.json
  审计: 学习来源/提取内容/confidence/影响范围
```

## 7. API (api/memory.py)

```
POST /api/memory/search   — {query, project?, type?} → [ExperienceRecord]
POST /api/memory/learn    — {workspace} → LearningResult (触发学习)
GET  /api/memory/stats    — → 经验统计 (按类型/成功/Agent)
GET  /api/memory/agent/{agent_id} — → AgentProfile
POST /api/memory/export   — → 全量经验导出
纯函数路由 + error handling + 注册 api/__init__.py
```

## 8. CLI (session/actions.py + intent.py)

```
factory memory search    — "搜索经验/查找经验" → 检索
factory memory learn     — "学习经验/经验学习" → 触发学习
factory memory stats     — "经验统计" → 统计
factory memory analyze-agent — "分析Agent/Agent成长" → Agent 画像
factory memory export    — "导出经验" → 导出
-h: action metadata + intent 关键词
```

## 9. 测试计划 (Core/CLI/API, >=120)

```
Core (>=70): ExperienceRecord/Store/Extraction/Learning/Retrieval/Recommendation/LearningTrace
CLI (>=25): 5 个 memory 命令 + intent 关键词
API (>=25): 5 端点 + schema + error handling
Integration (>=10): 真实项目 (execution_records → 提取 → 学习 → 查询)
```

## 10. 边界

- 不引入向量数据库 (关键词+规则检索)
- 复用现有数据资产 (不造新数据源)
- learning_trace 审计 (S10-069 基础)
- Debug 结果进入 Memory (S10-068 基础)

---

> 架构完毕 | Experience Store + Extraction + Learning + Retrieval + Recommendation + CLI + API
