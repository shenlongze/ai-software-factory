# S10-067 — GAP ANALYSIS

> 日期:2026-08-17 | Sprint: S10-067 | P0 现状审查
> 目标: 从"每次项目重新开始"升级为"基于历史经验持续改进的软件生产系统"

---

## 一、回答 4 个核心问题

### 1. 哪些数据已经存在?

```
✅ 丰富数据资产 (真实项目 1786773658 已验证):
  exec/execution_records.json      — 56 条执行记录 (intent/action/agent/task/result/error/timestamp)
  projects/<slug>/execution_state.json — 任务状态/生命周期/plan_version
  projects/<slug>/decision_objects.json — Architect 决策 (S10-058)
  projects/<slug>/handoff_decisions.json — Handoff 决策 (S10-059)
  projects/<slug>/replanning_decisions.json — 重规划决策 (S10-060)
  projects/<slug>/gap_analysis.json — 缺口分析 (S10-061)
  planning_trace.json               — LLM 规划轨迹 (S10-062)
  cost_records.json                 — 成本记录 (S10-063)
  team_execution_state.json         — 团队执行状态
  validation_result.json            — 验证结果
  repair_task.json                  — 修复记录
  conflict_resolution.json          — 冲突解决
  agent_metrics.json                — Agent 绩效 (agents.py)
  api/intelligence.py               — GET /experience (ExperienceSummary 只读投影, 已有)
```

### 2. 哪些数据可以成为经验?

| 现有数据 | 可提取经验 | 经验类型 |
|---|---|---|
| execution_records (失败+error) | 失败原因/成功方案 | FAILURE_PATTERN / SUCCESS_PATTERN |
| repair_task (修复方案+结果) | 修复经验 | DEBUG_EXPERIENCE |
| replanning_decisions (INSERT/MODIFY) | 规划缺口模式 | PLANNING_EXPERIENCE |
| gap_analysis (缺口类型) | 缺口模式 | PLANNING_EXPERIENCE |
| agent_metrics (成功率/任务) | Agent 能力画像 | AGENT_EXPERIENCE |
| validation_result (测试失败) | 验证失败模式 | DEBUG_EXPERIENCE |
| planning_trace (LLM 决策) | 决策依据 | PLANNING_EXPERIENCE |

### 3. 缺少哪些学习能力?

```
❌ Experience Store — 无统一经验模型 (ExperienceRecord) + 持久化
❌ Experience Extraction — 无自动提取 (trace/decision/artifact → 经验)
❌ Pattern Learning — 无模式分析 (成功/失败模式识别)
❌ Retrieval — 无相似项目经验查询
❌ Agent Learning — 无 Agent 能力成长记录
❌ Recommendation — 无经验影响未来 (planning/debug 提醒)
❌ learning_trace — 无学习过程审计
```

### 4. 如何避免 Memory 变成普通日志?

```
✅ 现有: 记录已存在 (execution_records 等) — 只是"日志"
❌ 缺失: 学习循环 (提取→模式→检索→推荐→影响未来)

Memory ≠ 日志:
  日志 = 保存数据 (被动)
  Memory = 提取经验 → 学习模式 → 检索应用 → 影响未来 (主动)

S10-067 必须实现完整学习循环:
  Execution → Observation → Learning → Pattern Extraction → Future Recommendation
```

## 二、GAP 汇总

| # | 缺失 | 说明 |
|---|---|---|
| G1 | **ExperienceRecord 模型** | 统一经验模型 (id/type/project/task/agent/role/context/problem/action/result/success/confidence/source/created_at) + 6 类型 |
| G2 | **Experience Store** | 持久化 (experience_store.json) + 失败安全 |
| G3 | **Experience Extraction** | 从 execution_records/repair/replanning/gap/validation 自动提取经验 |
| G4 | **Pattern Learning** | 模式分析 (成功模式/失败模式: database_first 等) + confidence |
| G5 | **Retrieval** | 相似项目经验查询 (project 特征匹配) |
| G6 | **Agent Learning** | Agent 能力成长 (任务数/成功率/常见问题/最佳领域) |
| G7 | **Recommendation** | 经验影响未来 (planning/debug 提醒) |
| G8 | **learning_trace** | 学习过程审计 (来源/提取内容/confidence/影响) |

## 三、可复用 ✅

| 能力 | 复用方式 |
|---|---|
| execution_records / repair_task / replanning_decisions / gap_analysis / validation_result | Experience Extraction 数据源 |
| agent_metrics (agents.py) | Agent Learning 基础 |
| ExperienceSummary API (intelligence.py) | 经验 API 基础 |
| actions 注册模式 (S10-063/065/066) | CLI 命令 |
| api/ 纯函数路由模式 | API 端点 |
| ReasoningProvider (S10-062) | LLM 提取/推荐 (可选) |

## 四、架构方向

```
memory/ (新增):
  experience.py        — ExperienceRecord + 6 类型 (Core)
  experience_store.py  — 持久化 (experience_store.json)
  extraction.py        — 自动提取 (trace/decision/artifact → ExperienceRecord)
  learning_engine.py   — Pattern Learning + confidence
  retrieval.py         — 相似项目查询
  recommendation.py    — 影响未来 (planning/debug 提醒)
  learning_trace.py    — learning_trace.json (审计)

CLI (factory memory *): search/learn/stats/analyze-agent/export
API (/api/memory/*): search/learn/stats/agent/{id}/export
```

## 五、不该现在做 🚫

```
向量数据库/embedding (关键词+规则检索够用)
分布式学习系统
跨用户共享经验 (单机优先)
```

---

> GAP 完毕 | G1-G8 缺失 | 数据资产丰富可提取 | 核心: 完整学习循环 (提取→模式→检索→推荐)
