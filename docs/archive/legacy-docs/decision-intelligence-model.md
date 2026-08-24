# Decision Intelligence Model — 决策智能模型 (Phase 10A-2, ADR-0031)

> 状态: IMPLEMENTED (已实现 — 见 ./audit/architecture-reality-audit.md)

> 日期: 2026-08-06 | 前置: Phase 10A-1 (ADR-0030, intelligence-layer-model.md)
> 范围: 决策链 — Context→Analysis→Options→Evaluation→Recommendation→Risk→
> Decision Artifact (规则驱动, **不绑定 LLM, 不自动执行**)

本模型描述 Factory 认知层的**决策引擎** (intelligence/decision.py): 给定决策
上下文, 引擎产出一个可审计的 Decision Artifact — 分析 + 选项评分 + 推荐 +
解释 + 证据链 + 风险等级, 高风险/低置信度决策经 9c ApprovalGate 提交人工审批。

## 1. Decision 生命周期

```
open ──(引擎给出推荐)──→ recommended ──(人工采纳)──→ accepted
                                  └──(人工否决)──→ rejected
```

- **open**: Decision 已生成但尚未给出推荐 (引擎内部态, 正常流程立即推进)。
- **recommended**: 引擎完成全链, 给出推荐选项 (Decision Artifact 落库态)。
- **accepted / rejected**: 人工决定的**结果回写** — 记录"人后来怎么决定的",
  不是审批工作流本身。状态词用 accepted/rejected 而非 approved/rejected,
  避免 "AI 自我批准" 的歧义 (ADR-0030 决策 1)。

状态推进经 `Decision.with_status()` 返回**新实例** (model_copy 语义) — 调用方
持有的旧引用不自动更新, 落库必须用返回值。

## 2. Decision ≠ Approval

| 维度 | Decision (本层) | Approval (9c) |
|---|---|---|
| 角色 | AI 推荐产物 (只分析+推荐+解释) | 人工闸门状态机 |
| 状态 | open/recommended/accepted/rejected | pending/approved/rejected/changes_requested/delegated |
| 触发 | 引擎规则评分 | 人 decide (approve/reject/...) |
| 绑定 | `approval_request_id` 可选引用 | Artifact Version + Workflow Pause |
| 执行权 | **无任何执行指令字段** | 审批通过 → 工作流恢复 |

**复用不复制**: 高风险决策需要人工确认时, 引擎经 9c ApprovalGate 公共接口
(`request_approval(artifact_id, gate_id=None, *, by, note)`, duck-typed —
9c ProductService 或同签名 Fake) 提交审批请求, `approval_request_id` 回填
Decision。引擎零 imports product/ (Removal Isolation), 装配方 (CLI/测试) 注入
审批服务。低风险决策**不**提交审批。

## 3. Evidence Chain (证据链, 禁无证据)

决策全链强制证据支撑, 任何环节无证据即拒绝:

- **Context 层**: `DecisionContext.evidence_sources` 为空 → `NoEvidenceError`
  (拒绝分析, 零事件)。
- **Option 层**: 选项无自身证据时**继承 context 证据链** (缺省
  `inherit_context_evidence=True`, CLI 便捷路径 — "选项评分基于上下文事实",
  非伪造); 继承关闭且选项无证据 → `NoEvidenceError` (拒绝评分)。
- **Decision 层**: evidence = context 证据 ∪ 各选项证据, 按
  `lineage_ref() = "{source_type}:{source_id}"` **去重** (保序保首条)。

Evidence 六来源 (ADR-0030 决策 4): artifact / event / experience /
external_data / human_input / provider_output — 事实优先 (provider_output
是建议非事实), 防 AI 自我循环。

## 4. Score 模型 (四因素加权归一, 规则评分)

```
score = clamp01( Σ factor_i × weight_i ),  factor_i ∈ [0,1]
```

- **四因素**: capability / cost / performance / experience (键序固定,
  `FACTOR_KEYS`); 缺省权重 capability 0.40 / cost 0.25 / performance 0.20 /
  experience 0.15 (能力匹配最重, 经验最轻 — 静态规则, 经验→权重影响链属 10A-4)。
- **权重归一**: `normalize_weights` — 未知键报错 / 负值报错 / 零和报错; 缺失键
  补 0 再归一 (和 = 1.0)。
- **缺失因素 → 中性分 0.5** (冷启动不偏见: 无数据不夸大也不贬低)。
- **无四因素明细的选项** → 采用 context 提供的评估分 (option.score), reasoning
  注明"未做规则加权" (数据不足不伪造因素)。
- **Result 语义**: 返回 model_copy 新实例 (调用方旧引用不更新)。

**Reasoning 生成 (可审计, 不黑箱)**: 每选项 reasoning 逐条:
每因素 `{key} {value:.2f} (权重 {w:.2f}) → 贡献 {c:.3f}` + 最高贡献因素解释 +
综合公式行 (`综合评分 = Σ(因素 × 权重) = ... → 归一 ...`)。

## 5. Confidence 模型 (分数差距 + 证据覆盖 + 因素完整度)

```
confidence = 0.5×spread + 0.3×evidence_coverage + 0.2×factor_completeness
(analysis 存在时: 0.8×base + 0.2×analysis.confidence)
```

- **spread** = top − runner-up (单选项时 = top score, 差距视为自身强度)。
- **evidence_coverage** = 携带证据的选项占比。
- **factor_completeness** = 四因素完整度均值 (len(factors) / (4×N))。
- 空选项 → 0.0 (无可信推荐)。全链 clamp 0-1。
- Analysis 置信度 = `0.4 + 0.15×min(证据数, 4)` (证据越全分析越可信)。

## 6. Risk 模型 (规则检测, 不绑定 LLM)

| 规则 | 条件 | 等级 |
|---|---|---|
| R1 | decision_type ∈ {architecture_change, deployment_strategy, provider_migration, provider_selection} | high |
| R2 | 任一选项 risks 文本含高风险关键词 (architecture/deployment/migration/cost increase/breaking change...) | high |
| R3 | 约束/目标文本含高风险关键词 | high |
| R4 | top − runner-up < 0.1 (竞争激烈) | medium |
| R5 | 置信度 < 0.5 (低置信度, 需人工确认) | medium |

- `risk_level` = high > medium > low; **requires_approval = (high) or (低置信度)**。
- 等级 → 数值风险映射: low 0.2 / medium 0.5 / high 0.8 (Decision.risk, 10A-1
  模型 0-1 兼容)。
- RiskAssessment 输出 reasons (逐条解释) + rules_triggered (规则锚点:
  `decision_type:<t>` / `option:<id>:<risk>` / `context:<text>`, 可审计)。

## 7. Human in the loop (人工闸门)

- **高风险** (R1/R2/R3) → `requires_approval=true` → 装配审批服务 + context
  approval 绑定点时经 9c 提交审批请求; 装配缺失 → **不静默降级**: Decision 保持
  requires_approval=true + approval_request_id=None (标记待人工提交, 引擎不
  自动执行, 无绕过风险)。
- **低置信度** (R5) → requires_approval=true (不自动采纳)。
- **竞争激烈** (R4) → medium + 提示需人工确认 (不强制审批)。
- 审批服务抛错 → `DecisionIntelligenceError` (响亮失败, 不吞错)。

## 8. 引擎装配

```
DecisionIntelligence(
    decision_store: DecisionStore | None = None,   # None = 纯内存 (测试友好)
    logger: EventLogger | None = None,              # None = 事件静默
    *, factor_weights: dict | None = None,          # 覆盖缺省权重 (自动归一)
    approval_service: ApprovalService | None = None,# 9c 公共接口 (duck-typed)
    inherit_context_evidence: bool = True,          # 选项证据继承
    now: Callable[[], str] | None = None,           # 可注入时钟 (测试确定性)
)
```

CLI 装配点 `_open_intelligence_engine` (commands.py, **函数内延迟导入** —
Removal Isolation): DecisionStore(root/intelligence) + logger + 可选 9c
ProductService (仅 --approval-artifact 时装配)。

## 9. 事件链 (4 链序)

```
analysis.started → analysis.completed → option.evaluated (×N)
→ [approval.* 9c, 高风险绑定] → decision.created (链终)
```

- `intelligence.decision.analysis.started/completed`: 载荷含
  subject_id/decision_type/option_count/evidence_count/factors/confidence。
- `intelligence.decision.option.evaluated` (每选项一条): option_id/score/factors/
  reasoning_count/evidence_count。
- `intelligence.decision.created` (链终, 单一): decision_id/decision_type/
  subject_id/recommendation/confidence/risk/risk_level/requires_approval/
  evidence_count/approval_request_id — 事件是唯一事实源, 从 payload 可重建
  落库对象关键字段。
- 禁无证据: 入口校验失败 → 零事件 (不在错误路径发半截链)。

## 10. 只读隔离 + 零执行 (边界铁律)

- 引擎零 imports product/providers/runtime/events.store (Removal Isolation);
  审批集成经注入接口。
- 只分析+推荐+解释, **不触发任何任务/执行**; 执行决策权在人 (Approval) 或未来
  编排层显式调用。
- 不实现: Recommendation Engine (10A-3) / Experience 学习 (10A-4) / LLM 调用 /
  自动执行 — 四因素权重为静态规则。
