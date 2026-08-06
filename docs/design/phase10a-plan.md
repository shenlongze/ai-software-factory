# Phase 10A Plan — Intelligence Layer

> 日期: 2026-08-06 | 状态: 架构设计评审, 待确认
> 冻结约束: Core 零修改 / Extension 独立 / Event 驱动 / 不绑定 Hermes / 不绑定 LLM

## 0. 定位

让 AI Software Factory 从**生命周期管理系统**进化为**具备分析、判断、推荐、经验积累能力的 AI 工厂**。

Intelligence Layer 只负责: 分析 + 推荐 + 解释。**不自动执行。**

## 1. 五个架构问题

### Q1: Intelligence Layer 与 Core 边界

```
Core (8 原语, 冻结): 状态/生命周期/调度/执行抽象/事件审计/恢复/观测/组织
Intelligence (新 Extension): 分析/判断/推荐/经验

边界铁律:
- Intelligence 只读 Core 数据 (Event/状态), 不写 Core
- Core 不感知 Intelligence (可删除, Factory 照常运行)
- Intelligence 输出 = 推荐 (Recommendation), 不触发执行
- 执行决策权: 人 (Approval) 或未来编排层显式调用

factory-core/intelligence/
├── models.py       Decision/DecisionContext/DecisionOption/DecisionEvidence/DecisionScore
│                   + Recommendation/RecommendationReason + ExperienceRecord
├── decision.py     DecisionIntelligence (分析/选项/推荐/证据/人工批准)
├── recommend.py    RecommendationEngine (Capability+Cost+Performance+Experience → 推荐+解释)
├── experience.py   统一经验模型 (Provider/Agent/Workflow/Project/Decision Experience)
├── evaluate.py     TaskEvaluator (TaskRequirement → Agent/Provider/Skill 匹配)
├── store.py        独立数据空间 .factory/intelligence/
└── events.py       intelligence.* 事件
```

### Q2: Decision 与 Approval 的关系

```
Decision = 智能产物 (分析 + 选项 + 推荐 + 证据 + 评分)
Approval = 人工闸门 (9c 状态机: pending/approved/rejected/changes_requested/delegated)

关系:
Decision 生成 → 绑定 ApprovalGate (可选) → 人工 decide → 结果回写 Decision
DecisionEvidence 存入 approval 决策依据 (human 看到为什么推荐)
复用 9c Approval 状态机 (不复制): Decision 可携带 approval_request_id
```

### Q3: Experience 如何影响 Recommendation

```
统一经验模型 (ExperienceRecord):
  provider_experience / agent_experience / workflow_experience / project_experience / decision_experience

影响链:
Experience (历史数据) → Performance 权重 → Recommendation 评分 (多因素加权)
   capability_score + cost_score + performance_score + experience_score
   → Recommendation (含 reasons 解释: "该 Provider 在类似任务成功率 92%")

保护: 经验是"推荐依据", 不是"唯一依据" (冷启动: 无经验 → 中性分, 不偏见)
```

### Q4: 如何避免 AI 自我循环错误

```
风险: AI 基于自身(可能错误)的历史输出做推荐 → 错误放大 (自我循环)

防循环机制:
1. 只读隔离: Intelligence 不写 Core 状态 (无法自我强化)
2. 人工闸门: 关键决策必经 Approval (9c)
3. 证据链: 每个推荐附 DecisionEvidence (可追溯/可审计)
4. 反事实记录: Experience 同时记录失败样本 (negative evidence)
5. 置信度阈值: 低 confidence → 降级为"需要人工"而非自动采纳
6. 外部事实源: Git/Event/Artifact 是事实, AI 输出是建议 (事实优先)
```

### Q5: 未来如何支持自我扩展

```
1. 声明式注册: 新 Intelligence 能力 = 注册 (capability 描述), 不修改 Core
2. Skill/Plugin 生态: Intelligence 技能 (market analysis/decision patterns) 经 Skill 注册
3. Experience 驱动: 经验积累 → 新模式/规则 → 新推荐模板
4. MCP 扩展: 外部分析工具接入 (future)
5. 版本化: Intelligence 自身版本记录 (可回滚)
```

## 2. 数据模型

```python
class DecisionContext(Pydantic):
    subject: str              # project/task/idea/artifact id
    context_type: str         # project_state/task_execution/product_decision...
    snapshot: dict            # 相关状态快照 (只读)

class DecisionOption(Pydantic):
    id: str; title: str; description: str
    pros: list[str]; cons: list[str]
    estimated_impact: dict

class DecisionEvidence(Pydantic):
    id: str; source: str      # event/artifact/experience/git
    reference: str; detail: str

class DecisionScore(Pydantic):
    option_id: str; score: float; reasons: list[str]

class Decision(Pydantic):
    id: str; context: DecisionContext
    options: list[DecisionOption]
    scores: list[DecisionScore]
    recommendation: str | None   # 推荐 option_id
    evidence: list[DecisionEvidence]
    confidence: float
    approval_request_id: str | None   # 9c 集成
    status: str               # open/recommended/approved/rejected

class Recommendation(Pydantic):
    target: str               # provider/agent/skill/workflow
    target_id: str; score: float
    reasons: list[str]        # 解释
    basis: dict               # capability/cost/performance/experience 分项
    confidence: float

class ExperienceRecord(Pydantic):
    id: str; domain: str      # provider/agent/workflow/project/decision
    subject_id: str
    outcome: str              # success/failure
    metrics: dict
    context: dict
    created_at: str
```

## 3. 模块职责

```
decision.py      DecisionIntelligence: analyze (读状态→DecisionContext) → generate_options
                 → score_options → recommend → save_evidence → bind_approval
recommend.py     RecommendationEngine: recommend(target, requirements) 多因素加权 + 解释
experience.py    ExperienceStore: 统一记录/查询 (五域) + stats (冷启动中性)
evaluate.py      TaskEvaluator: TaskRequirement → 匹配评分 (Agent/Provider/Skill 最适)
```

## 4. Event Namespace

```
intelligence.analysis.started / completed / failed
intelligence.decision.created / decision.updated / decision.recommended
intelligence.recommendation.generated
intelligence.experience.recorded
(复用: approval.* 9c / provider.* 8 / product.* 9)
```

## 5. CLI 规划

```
factory intelligence analyze <subject>             — 分析 → DecisionContext
factory intelligence decide <context_id>           — 生成选项/评分/推荐 → Decision
factory intelligence recommend provider|agent|skill <subject> — 推荐 + 解释
factory intelligence experience record/list        — 经验管理
factory intelligence evaluate task <task_id>       — TaskEvaluation (Agent/Provider/Skill 最适)
```

## 6. Dashboard 规划

```
Intelligence View (21 视图): 决策列表/推荐/证据/经验计数 (默认关零回归)
```

## 7. 分阶段实施

```
10A-1: 基础 — 模型 (Decision 全系 + Recommendation + ExperienceRecord) + store + Event   [+~70 tests]
10A-2: Decision Intelligence — analyze/options/score/recommend/evidence/approval 集成       [+~80 tests]
10A-3: Recommendation Engine — 多因素加权 + 解释 (Capability/Cost/Performance/Experience)   [+~80 tests]
10A-4: Experience Integration + TaskEvaluation — 统一经验 + TaskRequirement 匹配           [+~80 tests]
```

## 8. 确认要点

1. ✅ Core 零修改 (intelligence/ 纯新增)
2. ✅ 独立目录/测试/数据空间 .factory/intelligence/
3. ✅ 只分析+推荐+解释, 不自动执行
4. ✅ 防自我循环 (只读隔离/人工闸门/证据链/负样本/置信度/外部事实优先)
5. ✅ 不绑定 Hermes/LLM (复用 Provider 抽象)
6. ✅ 复用 9c Approval + 8 Provider Intelligence (不复制)
7. ✅ 分阶段 10A-1 → 10A-4
