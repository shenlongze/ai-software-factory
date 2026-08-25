# S10-117 — K-2 执行质量分 + 优选：设计文档 + 实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-25 | 前置: v1.1.85 · K-1 已交付 (战役第二战役)
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-117 提示词（K-2: C-2/C-3/B-5/B-6 合并）

---

## 0. 现状审计（CTO 独立复核）

| 资产 | 现状 | 缺口 |
|---|---|---|
| T5.3 evaluator | exec/evaluator.py: CandidateScore (5层: validation/patch/scope/risk/coverage) + score_candidate (纯函数确定性) + CandidateEvaluator.evaluate; agent_runtime.py L341 runner.select_result() 调用 | 默认单候选路径不跑多候选优选 (C-3=启用) |
| 执行记录 | actions.py _RECORD_KEYS (L93): intent/action/agent/task/result/result_id/timestamp/error; record_execution 写 execution_records.json | 无 quality 字段 (C-2 落盘) |
| M3d | decomposition_evaluator.py: 六维 (完整性25/粒度20/依赖20/可行性15/可测性10/风险10) + 四档 (adopt/adjust/reject/ask_user) | B-6 复用此思路打 PRD/计划分 |
| K-1 路由 | capability_router.py: CapabilityResource{status,load,priority,version} — K-2 挂点已注明 | 无质量分字段 (B-5 回写) |
| 失败策略 | 失败只重试 (≤2 轮) 不换资源 (orchestrator._execute_with_retry) | B-5: 低分 → 重试有界 → 换资源 |
| PRD/工程 | PRD.md + engineering.json (actions.py:569) | 无关联评分 |

版本: 1.1.85 → 目标 1.1.86。

## 1. 架构决策

### 1.1 C-2 执行结果质量分（核心, 新模块 `factory-console/session/execution_quality.py`）

```python
@dataclass
class ExecutionQuality:
    score: Optional[float]          # 0-1; 评分器故障 → None (失败安全, 诚实)
    dimensions: dict[str, float]    # 分维度 breakdown
    evaluator_version: str
    scored_at: str
    rules: list[str]                # 规则说明 (为什么是这个分, 可审计)

def score_execution(record: dict, evidence: dict) -> ExecutionQuality:
    """确定性评分: 复用 T5.3 五层思路 (validation/patch/scope/risk/coverage) —
    validation 硬条件 (失败 → 低分) + 补丁/范围/风险/覆盖 规则评分。
    纯规则, 不调 LLM; 评分器异常 → ExecutionQuality(score=None, reason=...) 不阻断执行。"""
```

**落盘**: actions.py record_execution 的记录 += `quality: {score, dimensions, evaluator_version, scored_at}`
(+ _RECORD_KEYS 加入 quality) — 分数可审计; score=None + reason 诚实标注。

### 1.2 C-3 T5.3 多候选优选启用

- 默认单候选行为不破坏 (单候选 → 现状路径); **显式多候选** (候选列表 >1 或 multi_candidate 标志) →
  CandidateEvaluator 正式选择
- 输出: ranking (排序候选) + selected_candidate_id + score_breakdown + reason (可解释)
- 全候选失败 → rejection_reason 非空 (诚实拒绝, 不静默选最差)
- 复用 T5.3 evaluator 语义 (不重写; 只"启用"多候选路径 + 输出增强)

### 1.3 B-5 执行质量评估闭环（失败策略）

- 低分 (score < LOW_SCORE_THRESHOLD, 可配置默认 0.5) → 策略: 重试 (有界, 复用 ≤2 轮) →
  换 Agent/资源 (读 K-1 capability_router: route by quality) → 诚实报分
- 集成点: orchestrator._execute_with_retry 加**附加钩子** (不改 pass/fail 基本行为):
  低分且重试耗尽 → 经 router 查替代资源 → 有替代 → 换资源再试一次 (记录 resource_switched);
  无替代 → 诚实报告 "低分无替代资源"
- **路由回写**: CapabilityResource += `quality_score: Optional[float] = None` — 资源质量分可读;
  route() 排序 key 扩展: quality_score 参与 tiebreaker (priority desc → quality desc → version desc →
  load asc → id); **None 中性** (K-1 既有 fixture 无 quality_score → K-1 行为零变化)
- 不实现 K-3 学习回写 (画像/经验落盘留给 K-3)

### 1.4 B-6 PRD/工程计划质量评估

- 复用 M3d 六维思路: `score_prd(prd_text, product) -> QualityScore` + `score_engineering(plan, product) -> QualityScore`
  (维度: 完整性/可行性/可测性 等; 确定性规则)
- 落盘: PRD.md 侧 `PRD.quality.json` + engineering.json 侧 `engineering.quality.json` (或 engineering.json 内嵌 quality)
- board 只读展示 (不阻塞流程)

### 1.5 入口（只读）

- `/board quality <project>` (board 子命令) 或 `factory exec quality` — Codex 选简单者
- 展示: 最近执行 quality (score/dimensions/version) + PRD/工程质量

### 1.6 注册表门禁（P0-10/11）

- 新增 CLI 命令/意图/action/事件/API → 同步注册表 (测试自动红)

## 2. 契约测试（tests/console/test_s10_117_execution_quality.py, ≥10）

1. **C-2 质量分确定性**: 成功/失败/低质量 三类 fixture → 分数确定 + breakdown + 落盘 quality 字段
2. **评分器失败安全**: 评分器异常 → score=None + reason, 不阻断执行
3. **C-3 多候选优选**: 多候选 fixture → ranking + selected + breakdown + reason; 全失败 → rejection_reason 非空
4. **单候选不破坏**: 单候选路径行为与改造前一致
5. **B-5 失败策略**: 低分 fixture → 重试有界 → 换 Agent (router 替代资源) ; 不无限重试
6. **路由回写**: CapabilityResource.quality_score 字段存在且可排序 (priority 后 tiebreaker); K-1 无分 fixture 行为零变化
7. **B-6 PRD 评分**: PRD fixture → 确定性分数 + 维度; 落盘 quality 文件
8. **B-6 工程计划评分**: engineering fixture → 分数 + 维度
9. **展示只读**: /board quality 或 CLI 渲染后 mtime 不变
10. **注册表门禁**: 新命令在注册表可见
11. 全量回归 0 新增失败

## 3. 版本与发布

- pyproject `1.1.85` → `1.1.86`; CHANGELOG v1.1.86; 版本断言同步; docs/FEATURES.md;
  docs/sprint10/待办清单-已发现未落地.md: K-2 (L14) ✅ + C-2 (L143) ✅ + C-3 (L144) ✅ + B-5 (L130) ✅ + B-6 (L131) ✅

## 4. Codex 实施范围

**Allowed/Files**:
- NEW `factory-console/session/execution_quality.py` (score_execution + score_prd + score_engineering + ExecutionQuality)
- MOD `factory-console/session/actions.py` (record_execution += quality 落盘 + _RECORD_KEYS)
- MOD `factory-exec/exec/agent_runtime.py` (多候选启用路径 + 输出增强; 单候选零变化)
- MOD `factory-exec/exec/evaluator.py` (如需输出增强 — 复用不重写)
- MOD `factory-console/session/orchestrator.py` (失败策略附加钩子: 低分 → 换资源; 不改 pass/fail 基本行为)
- MOD `factory-console/session/capability_router.py` (CapabilityResource.quality_score + 排序 tiebreaker)
- MOD `factory-console/session/board.py` 或 `factory-console/session/commands.py` (quality 展示入口, 只读)
- NEW `tests/console/test_s10_117_execution_quality.py`
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs/FEATURES.md / docs/sprint10/待办清单-已发现未落地.md

**Forbidden（硬边界）**:
- 不做 K-3 学习闭环 (经验回写/画像/学习护栏) — 质量分落盘 + 路由可读即停
- 纯规则确定性评分, 不调 LLM (LLM 可选路径必须标注且规则分始终存在)
- 不重写 T5.3 evaluator 语义; 不改变执行链 pass/fail 基本行为
- 不动 S10-115 lifecycle_store; 禁 git add -A; 禁新增第三方依赖
- board 展示只读; 写操作走 CLI/API

**Validation**:
- `pytest tests/console/test_s10_117_execution_quality.py -q` 全绿
- env -u 聚焦 (actions/agent_runtime/evaluator/orchestrator/capability_router/board + 既有执行/路由/评估测试) 全绿
- env -u 全量 console+api 0 新增失败
- 实测: 三类 fixture 分数; 多候选 ranking/rejection; 低分换资源; PRD/工程评分; 展示只读
- commit: `feat(S10-117): K-2 执行质量分+优选 — C-2质量分落盘 + C-3多候选启用 + B-5失败策略闭环 + B-6 PRD/工程评分, v1.1.86`

## 5. 验收标准（Hermes 独立验证）

- [ ] 1. 三类 fixture → 确定性分数 + breakdown + 落盘
- [ ] 2. 多候选 → ranking + selected + reason; 全失败 → rejection_reason
- [ ] 3. 低分 → 重试有界 → 换资源 (fixture 断言); 不无限重试
- [ ] 4. B-6: PRD/工程计划确定性评分 + 维度
- [ ] 5. 路由回写: quality_score 字段可读可排序; K-1 行为零变化
- [ ] 6. 展示只读 (mtime 不变)
- [ ] 7. 契约测试 ≥10 全绿
- [ ] 8. 全量回归 0 新增失败
- [ ] 9. v1.1.86 + K-2/C-2/C-3/B-5/B-6 ✅
- [ ] 10. 设计文档落盘

## 6. 诚实记录要求

- 评分维度/权重若与既有 M3d/T5.3 冲突 → 列出差异并说明取舍
- 无法判定的存量执行如实标注; 波及面超预期 → 列出征询, 不擅自扩大
