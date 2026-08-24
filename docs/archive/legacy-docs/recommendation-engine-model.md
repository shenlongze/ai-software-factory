# Recommendation Engine Model — 推荐引擎模型 (Phase 10A-3, ADR-0032)

> 状态: IMPLEMENTED (已实现 — 见 ./audit/architecture-reality-audit.md)

> 日期: 2026-08-06 | 前置: Phase 10A-2 (ADR-0031, decision-intelligence-model.md)
> 范围: 推荐链 — Context → Filter → Evaluation (四因素加权) → Rank → Reasoning →
> Risk → Recommendation Artifact (+ 可选 Decision Artifact / 9c Approval)
> 铁律: **规则驱动, 不绑定 LLM, 只推荐不执行**

本模型描述 Factory 认知层的**推荐引擎** (intelligence/recommend.py): 给定任务
上下文与候选集, 引擎选出"专业的人做专业的事" — 对 provider / agent / skill /
workflow 四类执行资源统一评分, 输出**为什么推荐它** (结构化解释) 与**推荐它的
风险** (规则检测 + 人工审核边界), 高风险推荐经 9c ApprovalGate 提交人工审批。

## 1. 为什么需要推荐 (问题域)

Factory 执行任务时面对一个选择问题: 同一任务类型可以由**多种执行资源**完成 —
外部 Provider (模型服务)、角色化 Agent、能力 Skill、编排 Workflow。选择不当的
代价:

| 选错维度 | 后果 |
|---|---|
| 能力不匹配 | 任务做不了 / 质量差 (无能力证据的 Provider 被推荐 = 8B 教训) |
| 性能差 | 延迟高 / 吞吐低 / 成功率低 |
| 成本失控 | 单位产出成本高, 预算超支 |
| 经验缺失 | 重复踩坑 (但**不惩罚**新候选 — 冷启动保护) |

推荐引擎的职责 = 把"选哪个"从人肉拍脑袋变成**可审计的规则评分**:
同一套权重、同一套公式、逐条解释, 任何人都能复算。引擎**不执行任何动作** —
推荐是建议, 执行决策权在人 (Approval) 或未来编排层显式调用。

## 2. 专业能力匹配 (Capability Match)

候选统一抽象 `Candidate`: `id + type(四类型) + 四因素(capability/performance/
cost/experience, 各 0-1)`。**类型只是属性, 不改变评分公式** (KISS): 同一个
0.9 分的候选, 无论它是 Provider 还是 Workflow, 都意味着"这个候选覆盖任务能力
需求的程度"。

- `capability` (0-1): 能力匹配分 — 覆盖任务所需能力 (required_capabilities)
  的程度。这是**第一权重因素** (0.35)。
- 过滤语义 (同 8B "无能力证据不推荐"): `quality_target` 门槛 — 候选 capability
  < 门槛 → **过滤不推荐** (宁缺毋滥), 不降权凑合。全部被过滤 → 无推荐
  (top_candidate_id=None, risk=high, requires_approval=true — 需要人来决定
  放宽标准还是换资源, 引擎不替人降低标准)。
- `required_capabilities` 进入解释文本 ("任务要求能力: code, reasoning"),
  让能力匹配**看得见**: 评分理由不是黑箱数字。

## 3. 多因素评分 (Multi-Factor Score)

```
Final = Capability×0.35 + Performance×0.30 + Cost×0.20 + Experience×0.15
```

四因素 (与 10A-2 决策链同因素集, **权重独立** — 决策是"选方案", 推荐是"选执行
资源", 能力与性能更重):

| 因素 | 权重 | 含义 (高 = 好) | 来源 |
|---|---|---|---|
| capability | 0.35 | 能力匹配度 | 候选声明 (能力矩阵/门槛校验) |
| performance | 0.30 | 延迟低/吞吐高/成功率 | 候选声明 (可接 Usage 聚合, 10A-4) |
| cost | 0.20 | 成本效益 (单位产出成本低) | 候选声明 (可接 CostModel, 8B) |
| experience | 0.15 | 历史经验有效分 | 经验记录集成或候选声明 |

**权重配置化, 禁硬编码**: 引擎构造注入 `weights` (CLI `--weights`), 自动归一
(缺失键补 0, 和为 1)。支持未来 project preference / agent preference / human
override 覆盖, 评分公式本体不动。

**分项可审计**: `score_components` 记录每因素加权贡献, `reasoning` 逐条解释
("capability 0.90 (任务要求能力: code, reasoning)" / "综合评分 = Σ(因素×权重)
= 0.785 → 归一 0.785") — 任何人都能复算为什么是这个分数。

## 4. Experience 集成 (Q3 影响链)

历史经验**影响但绝不支配**推荐 (权重最低 0.15):

- **有记录**: experience 分 = 平均 effective_score, 其中
  `effective_score = score × confidence × freshness` (10A-1 模型层),
  `freshness = 0.5^(age/half_life)` (缺省半衰期 30 天) — **历史经验不永久有效**,
  旧记录衰减, 被验证的经验 (mark_used) 保持新鲜。
- **无记录 (冷启动)**: 候选声明经验分, **缺省 0.5 中性分** — 新候选不被惩罚。
  一个没有历史的新 Agent 不会因为"没干过"就得 0 分; 它拿中性分, 靠能力/性能/
  成本竞争 (第 8 节: 冷启动 → 低置信度 → 需人工确认, 是提示不是歧视)。

## 5. 为什么推荐它 (Reasoning, 不黑箱)

每个候选的评分都带结构化解释 `ReasoningItem(factor, direction, text)`,
方向按阈值 (因素分 ≥ 0.6 正向原因 / ≤ 0.4 负向因素 / 中间中性说明):

```
+ capability 0.90 (任务要求能力: code, reasoning)     ← 正向原因 (支撑推荐)
- performance 0.31 (性能短板: 延迟较高/成功率偏低)     ← 负向因素 (短板不隐藏)
± experience 0.50 (冷启动: 无历史经验, 中性分不惩罚)   ← 中性说明 (不褒不贬)
综合评分 = Σ(因素 × 权重) = 0.785 → 归一 0.785 (0-1)
```

推荐结果 (RecommendationResult) 提供 `positive_reasons()` / `negative_reasons()`
/ `reasons_by_factor()` 机读过滤 — CLI 与未来展示层直接消费。**推荐必须带解释**
(10A-1 模型约束), 解释与评分一起落库 (Recommendation Artifact reasoning),
事后可审计"当时为什么推荐它"。

## 6. 风险与人工审核边界 (Risk & Human Gate)

引擎只推荐, **人永远是最后一道闸门**。风险规则 (纯规则, 不绑定 LLM):

| 规则 | 条件 | 等级 |
|---|---|---|
| 无候选 (全被过滤) | evaluations 空 | **high** + requires_approval |
| R1 竞争激烈 | top − runner-up < 0.1 (≥2 候选) | medium |
| R2 明显短板 | top 候选任一因素 < 0.3 | medium |
| R3 严重短板 | top 候选任一因素 < 0.2 | **high** |
| R4 冷启动 | top 无历史经验 | 提示 (不升级) |
| R5 低置信度 | confidence < 0.5 | medium |

**requires_approval = (high) or (低置信度)** — 高风险或没把握的推荐必须过 9c
ApprovalGate (复用不复制): 引擎零 imports product/, 审批服务构造注入; 已装配
`approval_service` + `context.approval` 绑定点 → 提交审批请求, `approval_request_id`
回填 Decision Artifact。**装配缺失不静默降级**: requires_approval=true 但
approval_request_id=None (标记待人工提交, 引擎不自动执行, 无绕过风险)。

**置信度** = 0.5×分数差距 + 0.3×经验覆盖 + 0.2×候选深度 — 竞争越接近、经验越
少、候选越少, 置信度越低 → 越需要人看。

## 7. Decision 集成 (复用 10A-2, 不复制)

推荐结果可转 Decision Artifact (`to_decision`): 全部候选评分快照 → DecisionOption
(score/factors/reasoning/evidence 全链可追溯), recommendation = top 候选,
confidence/risk/requires_approval 从推荐结果派生 (权重口径一致, 不重复计算);
高风险 + 绑定点 → 经 `DecisionIntelligence.bind_approval` 提交 9c 审批。
无推荐 (全被过滤) → 无可决策对象 (None)。Decision Artifact **不携带任何执行
指令** — 即使审批通过, 执行也由未来编排层显式发起。

## 8. 防止 AI 偏见 (Anti-Bias, §Q4)

| 机制 | 落地 |
|---|---|
| 只读隔离 | 引擎不写任何 Core 状态 (不触发任务/Provider 切换/执行) |
| 证据链 | Candidate.evidence 随 Recommendation/Decision 产物 (事实可追溯) |
| 低置信度降级需人工 | confidence < 0.5 → 必须 Approval, 不自动采纳 |
| 冷启动中性 | 无经验 → 0.5 中性分, **不惩罚新候选** (经验是推荐依据, 不是唯一依据) |
| 经验权重最低 | 0.15 — 历史经验影响但绝不支配 (防"老手迷信") |
| 解释强制 | 推荐必须带结构化解释, 高分低分都说明 (防黑箱偏袒) |
| 风险显式 | 短板/竞争激烈/冷启动全部进入 risk_reasons, 推荐时同步呈现 |

**不实现** (10A-4 边界): 自动学习 / 自动优化权重 / 自我修改 / LLM 调用 —
本引擎是确定性规则引擎, 权重配置化是为未来学习预留**输入口**, 不是学习本身。

## 9. 使用 (CLI)

```bash
factory intelligence recommend \
  --task development \
  --capability code,reasoning \
  --candidate a:0.9:0.8:0.7:0.6   # ID:CAP:PERF:COST:EXP[:TYPE]
  --candidate b:0.6:0.6:0.8:0.5:agent \
  --quality 0.7      # 可选: 能力门槛 (过滤)
  --budget 0.75      # 可选: 成本分门槛 (过滤)
  --weights 0.35:0.30:0.20:0.15   # 可选: 自定义权重
```

输出: Recommendation (score + Reasons 分项 + Risk) + 落库 Recommendation/
Decision Artifact + 事件链 (started → candidate.evaluated×N → explained →
created → completed)。`--approval-artifact` + `--gate` → 高风险推荐提交 9c
审批请求。**只推荐不执行**: 命令不触发任何任务/Provider 切换。
