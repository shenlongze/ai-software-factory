# ADR-0032 — Phase 10A-3: Recommendation Engine (推荐引擎 + CLI)

> 日期: 2026-08-06 | 状态: Accepted | 前置: Phase 10A-2 (0031, 3666 tests)

## 背景

10A-2 落了决策链引擎 (DecisionIntelligence, ADR-0031), 解决"选方案"问题; 10A-3
解决**"选执行资源"**问题 — 同一任务可由 provider / agent / skill / workflow
四类候选完成, 需要可审计的推荐: 多因素评分 (能力/性能/成本/经验) + 结构化解释
(为什么推荐它) + 风险检测 (人工审核边界)。冻结约束 (同 10A-1/10A-2): **Core 零
修改 / Extension only / 只读隔离 / 不绑定 LLM / 事件唯一事实源**。**不做**:
自动执行 / Experience 学习与权重自动优化 (10A-4)。

设计文档: docs/recommendation-engine-model.md (专业能力匹配/多因素评分/为什么
推荐/人工审核边界/防止 AI 偏见细节)。

## 决策

### 1. 推荐链 = Filter → Evaluation → Rank → Reasoning → Risk → Result, 只推荐不执行

决策: 引擎公开 `recommend(context)` 全链入口 + `to_decision(result, context)`
Decision 集成。**只推荐不执行铁律**: 引擎不触发任何任务/Provider 切换/执行,
推荐是建议, 执行决策权在人 (Approval) 或未来编排层显式调用 (同 10A-2 决策链
边界)。过滤 (quality_target 能力门槛 / budget 成本门槛) → 四因素加权评分 →
排序 → 解释 → 风险 → RecommendationResult (top_candidate_id / score /
factor_scores / evaluations / reasoning / confidence / risk)。**宁缺毋滥**:
无候选通过过滤 → top_candidate_id=None + risk=high + requires_approval=true
(引擎不替人降低标准, 同 8B "无能力证据不推荐" 语义)。

### 2. 多因素评分, 权重配置化 (缺省 0.35/0.30/0.20/0.15)

决策: `Final = Capability×0.35 + Performance×0.30 + Cost×0.20 + Experience×0.15`
— 能力匹配最重, 经验最轻。四因素与 10A-2 同因素集但**权重独立** (决策是"选
方案", 推荐是"选执行资源")。权重经构造注入 (`weights`, CLI `--weights`), 归一
化复用 `decision.normalize_weights` (DRY, 不复制); **score_candidate 纯函数内部
同样归一** (部分键输入 {capability: 0.7, performance: 0.3} → 补 0 再归一 —
收尾实测 KeyError 修复: 引擎路径已归一, 纯函数路径漏归一)。Candidate 四类型
(provider/agent/skill/workflow) 统一抽象 — 类型只是属性, 不改变评分公式 (KISS)。

### 3. Experience 集成 + 冷启动中性分不惩罚

决策: 候选有历史记录 (historical_context 优先, 其次 ExperienceStore.find) →
experience 分 = 平均 effective_score (score×confidence×freshness, 10A-1 模型层
复用; 衰减锚点 last_used — 使用即刷新); 无记录 → 候选声明经验分, **缺省 0.5
中性分 (NEUTRAL_FACTOR)** — 冷启动不惩罚新候选 (phase10a-plan §Q3 保护)。
experience_source ∈ records/declared/neutral 记录来源 (可审计)。经验权重最低
(0.15): 历史经验影响但绝不支配 (防"老手迷信")。

### 4. Reasoning 解释系统 = 结构化三态 + 逐条可审计

决策: 每候选解释 `ReasoningItem(factor, direction, text)`, direction ∈
positive (正向原因, 因素分 ≥ 0.6) / negative (负向因素, ≤ 0.4) / neutral
(中性说明, 冷启动不褒不贬); text 带符号前缀 (+/-/±) 可读展示, factor 可机读
过滤 (result.positive_reasons()/negative_reasons()/reasons_by_factor())。推荐
**必须带解释** (10A-1 模型约束), reasoning 与评分一起落库, 事后可审计。

### 5. Risk = 规则检测 (R1-R5), requires_approval = high 或低置信度

决策: 无候选 → high (宁缺毋滥); R1 竞争激烈 (top−runner_up < 0.1) → medium;
R2 明显短板 (top 因素 < 0.3) → medium; R3 严重短板 (< 0.2) → high; R4 冷启动
(top 无历史经验) → **提示不升级** (无经验不惩罚, 经验非唯一依据); R5 低置信度
(confidence < 0.5) → medium。`requires_approval = high or 低置信度` (同 10A-2
决策 4 语义: medium 竞争激烈不强制)。置信度 = 0.5×分数差距 + 0.3×经验覆盖 +
0.2×候选深度 (封顶 5) — 冷启动 → 低置信度 → 需人工确认 (§Q4 机制 5)。

### 6. Decision 集成 = 复用 10A-2, 9c Approval 注入式绑定

决策: `to_decision` 将 RecommendationResult → Decision Artifact (options =
候选评分快照 / recommendation = top / confidence+risk+requires_approval 从推荐
结果派生 — 权重口径一致, 不重复评分; evidence = top 候选证据链)。高风险 +
已装配 approval_service + context.approval → 复用 `DecisionIntelligence.
bind_approval` 提交 9c 审批, approval_request_id 回填。装配缺失不静默降级
(requires_approval=true + 无请求 id)。审批服务抛错 → DecisionIntelligenceError
响亮 — **CLI 捕获元组须含该独立异常层级** (收尾实测: 原 only
RecommendationEngineError, to_decision 绑定失败漏到 main 兜底 rc 1 但错误信息
丢失; 补 `except (RecommendationEngineError, DecisionIntelligenceError)`)。

### 7. CLI `intelligence recommend`, 延迟导入保 Removal Isolation

决策 (同 10A-2 模式): `--task` required + `--capability a,b` + `--candidate
ID:CAP:PERF:COST:EXP[:TYPE]` (可多次, 四类型) + `--constraint` + `--quality`
/ `--budget` 过滤 + `--weights W1:W2:W3:W4` + `--approval-artifact`/`--gate`
(9c 绑定)。命令经**函数内延迟导入** intelligence 包 (commands.py/main.py 顶层
零 imports) — 删除 intelligence/ → CLI 模块加载零影响, 命令调用响亮 rc 1。
退出码: 成功 0 / 业务错误 (无候选等) 1 / 用法错误 (候选/权重格式) 2 / argparse
缺参 SystemExit 2。

### 8. 事件链 = 4 新事件纯增量枚举 (127 → 131)

决策: `intelligence.recommendation.started` → `...candidate.evaluated` (×N,
每候选一条, 载荷含 factors 分项) → `...explained` (载荷含 positive/negative/
neutral 计数) → [`...created` 落库时, 10A-1 既有事件复用] → `...completed`
(链终, 载荷含 top/score/confidence/risk_level/requires_approval)。EventType
枚举 +4 成员 (127 → 131, ADR-0001 决策 1 纯增量路径, 既有值零改动)。写路径
source="intelligence"; logger=None 静默。

## 影响

- **Core 修改**: 仅 `events/models.py` EventType +4 成员 (127 → 131, 纯增量)。
- **新增** `factory-core/intelligence/recommend.py`: RecommendationEngine
  (Filter/Evaluation/Rank/Reasoning/Risk/Result + to_decision) + 规则评分/
  置信度/风险纯函数 (score_candidate / evaluate_factors / compute_recommendation_
  confidence / assess_recommendation_risk)。
- **新增模型** (intelligence/models.py): CandidateType / Candidate (四类型 ×
  四因素, experience 缺省 0.5 中性) / ReasoningDirection / ReasoningItem /
  RecommendationContext (容器字段 None → 默认空 mode="before" 归一) /
  CandidateEvaluation / RecommendationResult (positive_reasons()/negative_
  reasons()/reasons_by_factor()/to_artifact())。
- **CLI**: commands.py `cmd_intelligence_recommend` + `_parse_candidate_spec` /
  `_parse_weights` / `_build_recommendation_context` 辅助 (延迟导入);
  main.py parser + dispatch + print 4 触点接线。
- **修复实现 bug 1**: score_candidate 纯函数路径 weights 漏归一 → 部分键输入
  KeyError (引擎路径已归一, 纯函数路径补 `normalize_weights`)。CLI 捕获元组补
  DecisionIntelligenceError (审批绑定失败响亮转 rc 1)。
- **新增** `tests/intelligence/`: test_intelligence_recommend.py (108 引擎测试:
  Candidate 模型/权重默认+自定义+归一/评分计算/排序/过滤/经验集成 effective_
  score+freshness/冷启动中性/解释正负向/置信度/风险 R1-R5/决策集成+审批绑定/
  事件链 4 链序/store 持久化/无候选异常) + test_intelligence_recommend_cli.py
  (29 CLI 测试: 冒烟/--json/退出码/权重与过滤/9c 真实审批绑定/Removal Isolation
  模拟删包)。tests/intelligence 273 → 410。
- **文档**: docs/recommendation-engine-model.md (本 ADR 模型细节)。

## 验证

- 全量 pytest ≥3746 全绿 (3666 基线 + 137 新增 + 实现零回归; tests/intelligence
  410 passed)。
- 冒烟: `intelligence recommend --task development --capability code,reasoning`
  → Recommendation (score + Reasons 分项 + Risk) + 事件链; 高风险 + 
  `--approval-artifact --gate prd` → 9c 审批请求绑定。

## 冲突消解与记录

- **test_total_member_count 127 → 131**: 10A-3 推荐链 +4 事件 — 纯增量枚举
  扩展 (ADR-0001 决策 1 路径), 计数断言最小化更新 + 注释记录, 同 0031 先例。
- **score_candidate 部分权重 KeyError**: 测试按 docstring 契约 (权重自动归一)
  传部分键 {capability: 0.7, performance: 0.3} → 实现漏归一 (引擎路径已归一,
  纯函数路径直接索引 weights) — 修实现 (补 normalize_weights), 非测试期望错;
  引擎构造路径已归一, normalize 幂等无副作用。
- **to_decision 审批绑定失败异常层级**: bind_approval (10A-2) 抛
  DecisionIntelligenceError, 与 RecommendationEngineError 独立 — 测试断言具体
  异常类型; CLI 捕获元组补 DecisionIntelligenceError (推荐链可预期错误响亮转
  rc 1, 不依赖 main 兜底)。
- **冷启动低置信度**: 单候选无经验 → coverage=0 → confidence 0.43 < 0.5 →
  requires_approval=true — 设计行为 (§Q4 机制 5: 冷启动需人工确认), 测试按
  设计断言; "低风险不审批"测试须提供经验覆盖使置信度 ≥ 0.5。
- **historical_context 时间敏感**: 引擎 now 缺省真实 UTC — 用 created_at 与
  当前时间同期的记录做断言会因日期漂移失败; 确定性断言注入 `now=lambda: TS_*`
  固定时钟 (测试可重复性)。
