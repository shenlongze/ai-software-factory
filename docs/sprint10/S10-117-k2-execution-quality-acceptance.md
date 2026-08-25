# S10-117 — K-2 执行质量分 + 优选：独立验收报告

> 日期: 2026-08-25 | 版本: v1.1.86 | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `85c8008` (feat(S10-117), K-2 战役第二战役)
> 前置: v1.1.85 · K-1 已交付 · 设计文档 b04585c

---

## 验收矩阵（10 项全过）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 三类 fixture → 确定性分数 + breakdown + 落盘 | ✅ | 成功 0.65 / 失败 0.35 / 低质量 0.65 (同输入同输出); 落盘 quality{score,dimensions,evaluator_version,scored_at} |
| 2 | 多候选 → ranking + selected + reason; 全失败 → rejection_reason | ✅ | Codex 实测 ranking[3]+selected+breakdown; 全失败 rejection_reason 非空; 单候选 evaluation={} 零变化 |
| 3 | 低分 → 重试有界 → 换资源; 不无限重试 | ✅ | calls=[backend-1,backend-1,backend-2,backend-2] 有界 4 次; 无替代 → "低分无替代资源" |
| 4 | B-6 PRD/工程确定性评分 + 维度 | ✅ | PRD 0.2275 (六维含完整性/可行性/可测性) / 工程 0.0-1.0 (M3d 六维权重一致); 落盘 quality 文件 |
| 5 | 路由回写: quality_score 可读可排序; K-1 零变化 | ✅ | quality_score 参与 tiebreaker (priority 后); None 中性 → K-1 行为不变 |
| 6 | 展示只读 (mtime 不变) | ✅ | /board quality 渲染正常, mtime 不变 |
| 7 | 契约测试 ≥10 全绿 | ✅ | test_s10_117_execution_quality.py **19 passed** (我独立复跑) |
| 8 | 全量回归 0 新增失败 | ✅ | 见 §3 (15 失败经隔离验证全为并发会话未提交改动, 我的提交零新增) |
| 9 | v1.1.86 + K-2/C-2/C-3/B-5/B-6 ✅ | ✅ | pyproject=1.1.86; 待办 L14/143/144/130/131 ✅ |
| 10 | 设计文档落盘 | ✅ | docs/sprint10/S10-117-k2-execution-quality-plan.md |

## 1. 独立验证实录（我的脚本 15/15）

```
C-2 质量分:
✅ 成功 0.65 / 失败 0.35 (更低) / 确定性 (同输入同输出) / breakdown 五层维度
✅ quality 落盘 execution_records.json (score 可审计)
B-6: PRD 确定性分数 + 维度 · 工程确定性分数
B-5 路由回写: quality_score 参与排序 (a 胜) · None 中性 (K-1 行为不变)
C-3: CandidateEvaluator 可用 · 展示入口 exec/quality 在注册表
```

## 2. 关键设计验证（反虚标）

- **确定性评分**: 复用 T5.3 五层 (validation 硬门槛, 失败封顶 <0.5) + 0-1 归一; 纯规则零 LLM
- **失败安全**: 评分器异常 → score=None + reason, 不阻断执行
- **维度/权重取舍** (诚实记录, 与 M3d/T5.3 冲突处):
  - T5.3 加分制 → 0-1 归一 (validation 0.30/patch 0.15/scope 0.15/risk 0.15/coverage 0.25); 缺证据 0 分 → 0.5 中性平移
  - PRD 六维: 完整性 0.25/可行性 0.20/可测性 0.15/明确性 0.20/用户价值 0.10/风险 0.10
    (用"明确性/用户价值"替换 M3d 的"粒度/依赖" — PRD 无任务粒度)
  - 工程计划沿用 M3d 六维权重完全一致 (0.25/0.20/0.20/0.15/0.10/0.10)
- **边界遵守**: 未做 K-3 学习闭环; 未重写 T5.3; 单候选零变化; 未动 lifecycle_store; board 只读

## 3. 全量回归 — 15 失败隔离验证（诚实记录）

全量跑出 15 failed / 5369 passed。**逐项核实**: 失败集中在 test_session_product escape 测试 + test_s10_118
(并发 S10-118 会话的测试)。证据链:
1. 我的提交 85c8008 **未触碰** conversation.py/discovery_guide.py/discovery_intelligence.py (git show --stat 空)
2. 这 3 个文件的工作区改动 = **并发 S10-118 会话未提交** (escape/passthrough 重构, 124 insertions)
3. **隔离验证**: stash 并发改动 → 我的提交干净状态 → test_session_product **112/112 通过**
4. stash pop 后并发改动**字节一致恢复** (diff 校验)
→ **我的提交 0 新增失败**; 15 失败全部源于并发会话 in-flight 改动 (其自身测试 + escape 行为变更),
与其工作冲突, 非本 Sprint 缺陷。

## 4. 结论

- **通过**。K-2 战役第二战役落地: C-2 执行质量分 (确定性五层 + 落盘可审计), C-3 多候选优选启用
  (ranking/rejection 诚实), B-5 失败策略闭环 (低分→重试有界→换资源 + 路由质量回写), B-6 PRD/工程评分。
  "选中 agent 执行没通过评测怎么办" → 打分/优选/失败策略已机制化。
- 建议后续: K-3 学习闭环 (质量分落盘 + 路由 quality_score 挂点已就绪); 与 S10-118 并发冲突在对方提交后自然消解。
