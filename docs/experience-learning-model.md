# Experience Learning Model — 经验学习模型 (Phase 10A-4, ADR-0033)

> 状态: IMPLEMENTED (已实现 — 见 ./audit/architecture-reality-audit.md)

> 日期: 2026-08-06 | 前置: Phase 10A-3 (ADR-0032, recommendation-engine-model.md)
> 范围: 经验闭环 — Task → Recommendation → Execution → Result → Experience → Better Recommendation
> 铁律: **只记录不修改 / 经验 ≠ 自我修改 / 人工反馈优先 / 负经验必记 / 证据驱动**

本模型描述 Factory 认知层的**经验学习** (intelligence/experience.py +
evaluate.py + 10A-3 推荐引擎经验集成): 执行结果如何沉淀为经验事实, 经验如何
影响未来的推荐与评估 — 以及**边界**: 什么可以做, 什么**显式不做** (未来 Self
Evolution 单独设计)。

## 1. 为什么需要经验学习 (问题域)

Factory 是长期运行的 AI 工厂。没有经验的学习系统有三个病:

| 病 | 后果 | 经验学习解法 |
|---|---|---|
| 重复踩坑 | 同样的失败换个任务再犯 | 失败经验负信号 (negative_signal) |
| 记忆衰退 | 三年前的"成功"今天还在主导推荐 | 30 天半衰期 freshness 衰减 |
| 只记成功 | 幸存者偏差, 系统越推越偏 | 正负经验对记 (反事实记录) |

经验学习的产出 = **可审计的聚合分数** (每类执行资源/主体的历史表现), 影响
未来推荐与评估 — 让"用谁干活"从拍脑袋变成**基于事实的复算**。

## 2. Experience ≠ Self Modification (经验 ≠ 自我修改) — 第一边界

**用户强制铁律**: 经验学习**不是**自我修改。本阶段**显式不做**:

- ❌ 自动修改推荐权重 / 评分配置 (权重是配置, 只有人改)
- ❌ 自动生成 Skill / 自我复制 Agent / 自动重构 Core
- ❌ 基于自身输出直接强化 (AI 基于自己的历史输出自我强化 = 错误放大循环)

经验层做且只做两件事:

1. **记录事实** — `record_experience` 把执行结果落库为 `ExperienceRecord`
   (只记录不执行: 不触发任何任务/Provider 切换/推荐)。
2. **只读分析** — `ExperienceAnalyzer.records/aggregate/analyze` 只读历史记录
   并输出聚合 (不修改 store/权重/配置)。

经验是**未来推荐的依据**, 不是**即时反馈**。任何"自动进化"都留给未来 Self
Evolution 阶段单独设计 (phase10a-plan §Q5: Experience 驱动 → 新模式/新模板,
需要独立的安全设计: 版本化、回滚、人工闸门)。

## 3. Human Feedback 优先 (人工反馈重要性)

经验分 **score × confidence × freshness** — 其中 confidence 表达**证据的可信
度**, 而**最高置信度的证据来自人**:

- `Evidence` 六来源 (phase10a-plan §Q4 防自我循环): event / artifact / git /
  external_data / **human_input** / provider_output。
- 人工反馈 (human_input) 与外部事实 (event/artifact/git) 权重最高; AI 自身
  输出 (provider_output) 是建议, 不是事实 (外部事实源优先)。
- **人工闸门不变**: 关键决策仍走 9c Approval (10A-2); 低置信度评估 → 风险
  "建议人工确认"。经验分可以变, **人的决策权不变**。

## 4. Negative Experience (负经验必记)

**只记成功的系统会自我循环偏差** (防"只记成功"): 失败样本 = 反事实记录,
**同样落库**:

- `negative_signal` 派生自 `result == failure` (单一事实源, 不落库)。
- 聚合: `effective_score = clamp01(mean(sign × score×confidence×freshness))`,
  **sign = +1 成功 / −1 失败** — 成功提高未来评分, 失败降低。
- 全失败 → 0.0 (低于中性门槛 → 不推荐, 宁缺毋滥); 失败 > 成功 → 负经验主导
  风险 (谨慎采用)。
- 但**成功经验能克服单次失败**: 多次高分成功 + 单次低分失败 → 聚合分仍可
  ≥ 0.5 中性门槛 (2×0.9 成功 + 1×0.3 失败 → 0.5, 刚好过门槛) — 经验分是
  **平均证据**, 不是"一次失败终身否决"。

## 5. Evidence Driven Learning (证据驱动学习)

经验不是感觉, 是**证据链**:

- 每条 `ExperienceRecord` 携带 `evidence` (六来源, 可追溯 lineage) +
  增强字段 (quality_score / cost / duration / capability / task_type)。
- **只记录不消费, 防自我循环**: 事件/Artifact 是事实, 经验是历史依据 — 经验
  层零 imports product/providers/runtime (Removal Isolation)。
- 匹配语义保守: 按 task_type 相等 + capability 交集过滤; 记录未声明能力 →
  不匹配 (不能证实则不臆造)。

## 6. Recommendation Improvement (推荐改进 — 闭环收尾)

经验闭环的落点 = 未来推荐/评估**自动读到更好依据**:

- **10A-3 推荐引擎集成** (recommend.py): 候选有历史记录 → experience 分 =
  正负聚合有效分 (复用 `aggregate_experience_factor`, 不复制); 无记录 → 声明
  分/中性 0.5 (冷启动不惩罚)。**经验分 ≤ 能力分** (`min(experience,
  capability)`): 历史经验是对能力的背书, **不是能力的替代** — 可证实的失败/
  弱能力候选无法靠经验翻身。
- **10A-4 任务评估** (evaluate.py): `TaskEvaluator` 按 task_type+capability
  过滤 → 按 (subject_type, subject_id) 分组 → 正负聚合有效分 → 推荐
  agent/provider/skill (每类封顶 5, 有效分 ≥ 0.5 中性门槛) + Confidence +
  Reasons + Risks。
- **闭环**: 一次执行 → `record_experience` 落库 → 下一次推荐/评估自动生效。
  事件链可审计: `feedback.learned → experience.analyzed → task.evaluated`。

## 7. 关键公式 (常量即文档)

```
effective_score = score × confidence × freshness        # 单条经验有效分
freshness       = 0.5 ^ (age_days / half_life_days)     # 30 天半衰期
aggregate       = clamp01(mean(sign × effective_score)) # 正负聚合, sign=+成功/−失败
experience_final = min(aggregate, capability)           # 经验分 ≤ 能力分 (推荐引擎)
RECOMMEND_THRESHOLD = 0.5                               # 有效分 ≥ 中性分才推荐
MAX_RECOMMENDED_PER_TYPE = 5                            # 每类封顶 (KISS)
```

## 8. 事件 (唯一事实源)

| 事件 | 触发 | 语义 |
|---|---|---|
| intelligence.feedback.learned | record_experience | 执行结果沉淀为经验事实 |
| intelligence.experience.analyzed | analyze | 只读聚合完成 (链序可审计) |
| intelligence.task.evaluated | evaluate | 任务评估完成 (推荐+置信度+风险) |

logger=None → 静默 (事件非阻塞)。

## 9. 范围外 (明确不做)

自动权重优化 / 自动 Skill 生成 / 自我复制 / Core 重构 / 基于自身输出自我强化
— 全部留给未来 Self Evolution 阶段 (需独立安全设计: 版本化 + 回滚 + 人工闸门)。
