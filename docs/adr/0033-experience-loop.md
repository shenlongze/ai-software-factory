# ADR-0033 — Phase 10A-4: Experience Loop (经验闭环 + TaskEvaluation)

> 日期: 2026-08-06 | 状态: Accepted | 前置: Phase 10A-3 (0032, 3803 tests)

## 背景

10A-3 落了推荐引擎 (ADR-0032), 解决"选执行资源" — 但当时的 experience 因素
只是平均 effective_score, **没有正负经验语义, 没有闭环**。10A-4 解决**"经验
学习"**问题: 执行结果如何沉淀为经验事实, 经验如何改进未来推荐与评估 —
Task → Recommendation → Execution → Result → Experience → Better
Recommendation。冻结约束 (同 10A-1/2/3): **Core 零修改 / Extension only /
只读隔离 / 不绑定 LLM / 事件唯一事实源**。**用户强制铁律**: 经验学习 ≠ 自我
修改 — **不做**自动权重优化 / 自动生成 Skill / 自我复制 Agent / 自动重构 Core
(未来 Self Evolution 单独设计)。

设计文档: docs/experience-learning-model.md (经验≠自我修改/人工反馈优先/负经验
必记/证据驱动/推荐改进细节)。

## 决策

### 1. ExperienceRecord 增强 + ExperienceAnalyzer: 只读聚合, 非自我修改

决策: `ExperienceRecord` 全字段 (subject_type/task_type/capability/
quality_score/cost/duration/evidence/... 六域 provider/agent/skill/workflow/
project/decision, 10A-4 增补 skill)。`ExperienceAnalyzer` 只读历史记录并输出
聚合 (records/aggregate/analyze), `record_experience` 只"记录事实"落库 + 发
feedback.learned — **全部方法零修改副作用** (不改权重/配置/不触发执行; 经验
分析 ≠ 自我修改, 未来 Self Evolution 单独设计)。分析器聚合 = 纯函数
`aggregate_records`/`aggregate_experience_factor` (注入时钟/半衰期, 测试确定
性), 零顶层 imports product/providers/runtime (Removal Isolation, 同 store.py
铁律)。

### 2. 正负经验聚合 (negative_signal): 成功提高 / 失败降低

决策: `effective_score = score × confidence × freshness` (10A-1 模型层复用,
30 天半衰期); 聚合 `effective = clamp01(mean(sign × effective_score))`,
**sign = +1 成功 / −1 失败** — 失败样本 = 反事实记录 (phase10a-plan §Q4 机制
4, 防"只记成功"自我循环偏差)。全成功 → 平均 effective_score (与 10A-3 语义
一致, 向后兼容); 全失败 → 0.0 (惩罚可证实的失败); 无记录 → 0.0 (冷启动中性
0.5 由调用方处理, 不惩罚新候选)。**成功经验能克服单次失败**: 2×0.9 成功 +
1×0.3 失败 → 0.5 刚好过门槛 (平均证据语义, 非"一次失败终身否决")。

### 3. Experience 不允许覆盖真实能力 (经验分 ≤ 能力分)

决策: 10A-3 推荐引擎 experience 因素 = 正负聚合有效分 (复用
`aggregate_experience_factor`, 不复制), **且 `experience = min(experience,
capability)`** — 历史经验是对能力的**背书**, 不是能力的替代; 叠加最低权重
0.15, 可证实的失败/弱能力候选无法靠经验翻身。声明经验分同样受能力上限约束
(规则统一, 声明 ≠ 豁免)。10A-4 TaskEvaluator 同理只读聚合, 有效分 ≥ 0.5
中性门槛 (RECOMMEND_THRESHOLD, 与决策层 NEUTRAL_FACTOR 同值) 才推荐。

### 4. TaskEvaluator: TaskRequirement → TaskEvaluation (推荐执行资源)

决策: 新增 `evaluate.py` — 评估链 = ExperienceAnalyzer 过滤 (task_type +
capability) → 按 (subject_type, subject_id) 分组正负聚合 → 排序 → 推荐
agent/provider/skill (workflow/project/decision 域记录是编排/项目/决策经验,
**非执行资源候选**, 不参与推荐; 每类封顶 5 个) + Confidence (0.5×分数差距 +
0.3×类型覆盖 + 0.2×候选深度, 与推荐引擎同构不复制) + Reasons + Risks (冷启动
/负经验主导/低于中性门槛/低置信度)。**只读评估**: evaluate() 只产出
TaskEvaluation, 不触发任何任务/Provider 切换/执行。

### 5. CLI `intelligence experience list|evaluate`, 延迟导入保 Removal Isolation

决策 (同 10A-2/3 模式): `experience list [--subject-type X] [--subject-id Y]`
只读清单 (发 intelligence.viewed 审计) + `experience evaluate --task T
[--capability C]` 任务评估 (发 intelligence.task.evaluated)。命令经**函数内
延迟导入** intelligence 包 — 删除 intelligence/ → CLI 模块加载零影响。CLI
冒烟路径: experience list (有记录) → evaluate --task development --capability
code → TaskEvaluation (推荐 + Confidence + Risks)。

### 6. 事件 = 3 新事件纯增量枚举 (131 → 134)

决策: `intelligence.experience.recorded` (10A-1 既有, 记录落库) +
`intelligence.feedback.learned` (10A-4: 执行结果 → 经验落库, 闭环收尾) +
`intelligence.experience.analyzed` (只读聚合完成) + `intelligence.task.evaluated`
(评估完成, 载荷含推荐/置信度/风险)。EventType 枚举 +3 成员 (131 → 134,
ADR-0001 决策 1 纯增量路径, 既有值零改动)。链序可审计:
feedback.learned → experience.analyzed → task.evaluated。logger=None 静默。

## 影响

- **Core 修改**: 仅 `events/models.py` EventType +3 成员 (131 → 134, 纯增量)。
- **新增** `factory-core/intelligence/experience.py`: ExperienceAnalyzer
  (records/aggregate/analyze/record_experience) + 纯函数
  aggregate_experience_factor / matches_experience / aggregate_records。
- **新增** `factory-core/intelligence/evaluate.py`: TaskEvaluator
  (TaskRequirement → TaskEvaluation: 过滤/分组聚合/排序/推荐/置信度/风险)。
- **增强** (intelligence/models.py): ExperienceRecord 全字段 + ExperienceDomain
  + skill; ExperienceAggregation / ExperienceAnalysis / TaskRequirement /
  TaskEvaluation 新模型; DEFAULT_HALF_LIFE_DAYS。
- **集成** (intelligence/recommend.py): experience 因素改正负聚合 +
  经验分 ≤ 能力分上限 (min(experience, capability))。
- **CLI**: commands.py cmd_intelligence_experience_list /
  cmd_intelligence_experience_evaluate; main.py parser + dispatch 接线。
- **新增** `tests/intelligence/`: test_intelligence_experience_loop.py (增强
  字段/聚合/正负/半衰期/feedback loop/analyze/事件链/store isolation/failure
  cases) + test_intelligence_evaluate.py (冷启动/推荐分组排序封顶/非执行域排除/
  正负聚合/置信度/过滤/事件/failure cases)。tests/intelligence 410 → 522。
- **文档**: docs/experience-learning-model.md (本 ADR 模型细节) +
  docs/design/phase10a4-status.md。

## 验证

- 全量 pytest ≥3908 全绿 (3803 基线 + 新增; tests/intelligence 522 passed)。
- 冒烟: `intelligence experience list` (有记录) → `intelligence experience
  evaluate --task development --capability code` → TaskEvaluation (Reasons/
  Confidence/Risks) + 事件链。

## 冲突消解与记录

- **test_total_member_count 131 → 134**: 10A-4 经验闭环 +3 事件 — 纯增量枚举
  扩展 (ADR-0001 决策 1 路径), 计数断言最小化更新 + 注释记录, 同 0031/0032
  先例。
- **test_success_overcomes_single_failure 期望错**: 测试注释假设失败记录按
  原分 0.3 扣 (0.9+0.9−0.3)/3=0.5, 但 `_agent_fail` 缺省 confidence=0.8 →
  有效分 0.3×0.8=0.24 → 实现得 0.52 — **实现符合 ADR-0033 公式** (sign ×
  score×confidence×freshness, 与 test_failure_subtracts/test_stats_computed
  一致), 测试期望错 → 修测试 (失败记录显式 confidence=1.0, 保留"刚好过门槛"
  边界语义), 非实现 bug。
- **test_combined_filters 顺序敏感**: `list_all()` 按记录 id (uuid4) 排序
  (store 文档语义, test_list_all_sorted_by_id 既证), 非插入序 — 断言改集合
  相等 (sorted), 不依赖记录顺序。
- **历史真实 UTC 漂移**: 聚合 now 缺省真实 UTC — 确定性断言注入
  `now=lambda: TS_LATE` (测试固定时钟), 同 0032 historical_context 先例。
