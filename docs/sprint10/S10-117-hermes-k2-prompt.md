# S10-117 · K-2 执行质量分 + 优选 — Hermes 提示词（2026-08-25）

> 战役: K-2（docs/战役规划-统一路线.md §2 K-2）· 目标版本 v1.1.86
> 交付后: 待办清单 K-2/C-2/C-3/B-5/B-6 ✅ · 战役规划状态追踪 K-2 ✅

---

请作为 Hermes 派发 Sprint 任务给 Codex，遵守既有纪律（pre-flight → plan → dispatch → verify → acceptance → report）。

【任务】S10-117 · K-2 执行质量分 + 优选（战役规划第二战役）
版本目标：v1.1.86（从实际 HEAD +1；若并发消耗则顺延，不回退版本）

【背景（K-2 是什么）】
战役规划 K 系列第二战役（依赖 K-1 已交付）。解决 Founder 核心问题：
"选中 agent 执行任务但没通过质量评测怎么办？" —— 打分、优选、失败策略。
合并项：C-2 执行结果质量分 · C-3 T5.3 多候选优选启用 · B-5 执行质量评估闭环 · B-6 PRD/工程计划质量评估

【现状（实事求是，pre-flight 必须核对，不限于此）】
1. T5.3 机制已存在但"默认关": exec/evaluator.py CandidateEvaluator（5 层: validation/patch/scope/risk/coverage
   + CandidateScore/EvaluationResult/rejection_reason/evaluator_version）; agent_runtime.py 经
   runner.select_result() 调用, 但默认单候选路径未跑多候选优选 → C-3 = 启用 + 可靠性验证
2. M5-1 重放基础 ✅: execution_records.json 含 result_id/input_snapshot（actions.py _RECORD_KEYS/
   AgentExecutionResult）; ReplayEngine（execution_replay.py dry-run/re-exec/compare）
3. M3d 评估器模板 ✅: decomposition_evaluator.py 六维确定性评分（权重 25/20/20/15/10/10）+ 四档行动
   （≥0.9 adopt / 0.7-0.9 adjust / <0.7 reject / <0.5 ask_user）—— B-6 复用此思路
4. K-1 路由挂点 ✅: capability_router.py CapabilityResource{status, load, priority, version}——
   status/load 已挂字段; K-2 质量分要回写路由可读（K-3 学习闭环前置数据）
5. 现状缺口: 执行结果只有 pass/fail 无量化分数; 失败只重试(≤2 轮)不换资源; 分数不落盘不可审计

【设计与实现要求（先出设计文档 docs/sprint10/S10-117-k2-execution-quality-plan.md，批准后再实现）】
1. C-2 执行结果质量分（核心）:
   - 确定性评分器: 复用 T5.3 五层 / M3d 六维思路 → 每次执行产出 0-1 质量分 + 分维度 breakdown + 规则说明
   - 落盘: execution_records.json 每记录加 quality{score, dimensions, evaluator_version, scored_at} +
     审计可查（分数可审计）
   - 失败安全: 评分器故障 → 记录 score=null + reason, 不阻断执行（诚实标注）
2. C-3 T5.3 多候选优选启用:
   - 多候选模式可用（默认单候选行为不破坏; 显式多候选时启用 CandidateEvaluator 正式选择）
   - 输出: ranking + selected_candidate_id + score_breakdown + reason（可解释）
   - 全候选失败 → rejection_reason 诚实拒绝（不静默选最差）
3. B-5 执行质量评估闭环（失败策略）:
   - 低分 → 明确策略: 重试(有界) → 换 Agent/资源（读 K-1 路由）→ 诚实报分
   - 分数回写 capability_router: 资源质量分可读（新增 score/quality 挂点字段或等价, 供路由排序参考;
     不实现 K-3 学习回写）
4. B-6 PRD/工程计划质量评估:
   - 复用 M3d 评估器思路 → PRD/工程计划确定性打分（维度可定义: 完整性/可行性/可测性等）
   - 产物侧: PRD.md/engineering.json 关联评分落盘 + board 可见（只读展示评分, 不阻塞流程）
5. 入口: /board 或 CLI 可查执行质量（如 /board quality <project> 或 factory exec quality 之类,
   Codex 选简单者; 只读）
6. 注册表门禁（P0-10/11 强制）: 新增 CLI 命令/意图/action/事件/API 必须同步注册表（测试自动红）

【硬边界】
- 只做评分/优选/失败策略/评分展示, 不做 K-3 学习闭环（经验回写/画像/学习护栏）——
  质量分落盘 + 路由可读即停, 回写画像留给 K-3
- 纯规则确定性评分, 不调 LLM（评分必须是确定性规则, 不接受 LLM 打分当唯一依据;
  若 LLM 路径可选, 必须明确标注且规则分始终存在）
- 不破坏 T5.3 现有 evaluator 语义（复用不重写）; 不改变执行链 pass/fail 基本行为
- 不动 S10-115 lifecycle_store 语义; 不碰工作区他人未提交文件
- board 展示只读; 写操作走 CLI/API

【验收标准（独立可验证，非 Codex 自报告）】
1. 质量分: 构造 成功/失败/低质量 三类执行 fixture → 确定性分数 + breakdown + 落盘 execution_records.json
2. 优选: 多候选 fixture → ranking + selected + reason; 全失败 → rejection_reason 非空（诚实）
3. 失败策略: 低分 → 重试有界 → 换资源（fixture 断言换 Agent 行为）; 不无限重试
4. B-6: PRD/工程计划可打分（确定性, fixture 断言分数与维度）
5. 路由回写: capability_router 资源可读质量分（断言分数字段/挂点存在且可排序）
6. 展示: board/CLI 可查执行质量（只读, 渲染后 mtime 不变）
7. 契约测试 ≥10（评分确定性/优选/失败策略/落盘可审计/路由回写/展示只读/注册表）
8. 全量回归 0 新增失败（环境性失败如实标注, 与 HEAD 基线对照）
9. 版本 v1.1.86（pyproject + CHANGELOG + FEATURES + 版本断言 + 待办清单 K-2/C-2/C-3/B-5/B-6 ✅ 同步）
10. 设计文档落盘 docs/sprint10/S10-117-k2-execution-quality-plan.md

【诚实记录】任何无法判定的存量执行如实标注; 评分维度/权重若与既有 M3d/T5.3 冲突 → 列出差异并说明取舍;
改动波及面超预期 → 列出并征询, 不擅自扩大
