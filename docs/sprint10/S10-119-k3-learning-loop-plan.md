# S10-119 — K-3 学习闭环（主线 M4 全 6 项）：设计文档 + 实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-25 | 前置: v1.1.88 · K-1 路由 ✅ + K-2 质量分 ✅ (战役第三战役)
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-119 提示词（K-3: M4-1~6 + B-7/E-1 + D-6 + E-2/E-3）

---

## 0. 现状审计（CTO 独立复核 — 11 项基础设施定位）

| 资产 | 位置 | 缺口 |
|---|---|---|
| ExperienceStore | memory/experience_store.py (load/save/add/records/get/stats) | 执行完不入库 → 下次不引用 (M4-1/B-7) |
| retrieve_experience | retrieval/unified.py:20 | 未被路由/执行引用 |
| LearningEngine | memory/learning_engine.py (trigger_learning actions.py:2728 提取→模式/画像→审计) | 触发点不自动 (执行后需手动) |
| agent_profiles | trigger_learning 产出 | M4-5 画像分未接入 capability_router |
| DECISION_LEARNED | audit_event.py:34 已注册 | M4-3: 审批决策未落组织记忆 |
| CostLedger | cost_ledger.py:191 (record/aggregate) | M4-4/D-6: usage→聚合→告警/阻断→回填 未闭环; board 成本列空 |
| BudgetEnforcer | budget.py:265 (check → ok/warn/review/block) | 未接告警/阻断 |
| execution_replay L4 | snapshot_before/rollback (git 受限) | M4-6: 非 git 工作区不可快照 |
| repair_task | actions.py:1532 | E-2/E-3: 无评估驱动闭环 |
| capability_router | quality_score (K-2) + load 挂点 | M4-5 排序未纳画像分/负载均衡 |
| K-2 | quality_score 回写 | 学习样本数据源 ✅ |

版本: 1.1.88 → 目标 1.1.89。

## 1. 架构决策

### 1.1 学习护栏 (M4-2, 最高优先级 — 先做, 其它项都挂其下)

新模块 `factory-console/memory/learning_guards.py`:

```python
LEARNING_ENABLED_DEFAULT = True   # 总开关 (配置可关)
MIN_SAMPLES = 3                   # 样本数 < 阈值 → 不主导/降权
MIN_QUALITY = 0.5                 # quality_score < 阈值 → 低质量样本不写入
LEARNING_BUDGET = {...}           # 学习存储/引用成本上限

class LearningGuards:
    def enabled(self) -> bool                       # 总开关
    def sample_credible(self, n: int) -> bool       # 样本可信度 (n >= MIN_SAMPLES)
    def sample_quality_ok(self, q: float) -> bool   # 低质量不写入
    def budget_ok(self, usage: dict) -> bool        # 超预算 → False (阻断+告警)
    def snapshot(self, workspace) -> Path           # 学习状态快照 (画像/经验) → 可回退
    def rollback(self, snapshot_path) -> None       # 一键回退
```

- **关闭 → 零行为变化** (引用/入库全跳过, 向后兼容断言)
- 学习导致的画像/经验快照 → 可一键回退

### 1.2 M4-1/B-7/E-1 经验闭环（核心, 新模块 `factory-console/memory/learning_loop.py`）

```python
class LearningLoop:
    def on_execution_complete(self, record: dict, quality: dict, workspace) -> str:
        # 执行完成后自动: 护栏检查 (开关/质量) → 确定性提取
        #   (task/agent/result/quality_score/上下文摘要) → ExperienceStore.add
        #   返回 experience_id; 护栏拒绝 → 不写 (诚实)
    def resolve_for_task(self, objective: str, workspace) -> Optional[ExperienceHit]:
        # 下次同类任务: retrieve_experience → 护栏 (样本可信度) → 命中返回
        #   ExperienceHit{experience_id, summary, reason: "引用经验 X 因为 Y (相似度 0.xx)"}
```

- 路由/执行 prompt 引用: 命中经验 → prompt 注入 "引用经验 X 因为 Y" (带 reason)
- **闭环可断言**: 两次同类任务 fixture → 第二次能查到引用

### 1.3 M4-3 决策记忆回流 E5

- 审批决策 (approved/rejected) → 审计 DECISION_LEARNED 事件 → 组织记忆落盘
  (decision_memory.json: {decision_id, type, outcome, context, learned_at})
- 下次同类审批 → 带历史 (显示 "历史同类决策: N 次, 批准率 X%") + 少审提示
- 可断言: 审批 → DECISION_LEARNED → 组织记忆 → 下次显示历史

### 1.4 M4-4/D-6 成本告警闭环

- CostLedger usage → aggregate (cost_by_task/agent) → BudgetEnforcer.check →
  超预算 → 告警 (audit + 消息) + 阻断 (执行前检查) → 回填 (cost 关联 task/agent)
- board/CLI 成本可视化 (只读): /board cost <project> 或 factory cost — 每项目/每任务实际成本
- 可断言: usage → 聚合 → 超预算告警/阻断 → 回填

### 1.5 M4-5 画像优先分配 + 负载均衡

- capability_router 排序扩展: (priority desc, **persona_score desc** (agent_profiles),
  **load asc**, quality_score desc, version desc, id) — 确定性可解释
- 画像分来源: trigger_learning 产出的 agent_profiles (失败安全: 无画像 → 中性)
- 可断言: 高画像/低负载 Agent 优先

### 1.6 M4-6 快照/回滚 L4 完整化

- 非 git 工作区: 目录级快照 (复制基线到 .factory_snapshots/<ts>/ 或 tar 压缩) → 还原 (覆盖/解压)
- git 路径沿用受限版 (git stash create → reset --hard)
- 失败安全: 不可快照 → 明确 ReplayError, 不静默
- 可断言: 非 git 工作区快照/回滚 fixture 可还原

### 1.7 E-2 修复深化 / E-3 优化完善（评估驱动闭环）

- 复用 execution_quality/M3d: 低分任务 → 自动修复建议 (确定性规则: 失败分类 → 建议) →
  应用 (repair_task 机制) → 复评 → 分数提升断言
- 至少一条可断言闭环: 低分 → 建议 → 应用 → 复评提升

### 1.8 注册表门禁（P0-10/11）

- 新增 CLI 命令/意图/action/事件/API → 同步注册表

## 2. 契约测试（tests/console/test_s10_119_learning_loop.py, ≥12）

1. **经验闭环**: 两次同类任务 fixture → 第二次引用第一次 (引用存在 + reason 可解释)
2. **护栏-开关**: 关闭 → 学习/引用零行为变化
3. **护栏-低样本**: 样本数 < 阈值 → 不主导 (引用降权/不引用)
4. **护栏-低质量**: quality_score 低 → 不写入
5. **护栏-预算**: 超预算 → 阻断 + 告警
6. **护栏-回滚**: 学习快照 → 回退后画像/经验还原
7. **决策记忆**: 审批 → DECISION_LEARNED → 组织记忆 → 下次少审/带历史
8. **成本告警**: usage → 聚合 → 超预算告警/阻断 → 回填
9. **画像分配**: 高画像/低负载 Agent 优先 (router 排序)
10. **L4 完整化**: 非 git 工作区快照/回滚 fixture 可还原; 不可快照 → 明确报错
11. **E-2/E-3**: 低分 → 建议 → 应用 → 复评提升 (至少一条闭环断言)
12. **注册表**: 新命令在注册表可见
13. 全量回归 0 新增失败

## 3. 版本与发布

- pyproject `1.1.88` → `1.1.89`; CHANGELOG v1.1.89; 版本断言同步; docs/FEATURES.md;
  docs/sprint10/待办清单-已发现未落地.md: K-3 L16 ✅ + M4-1~6 L58-63 ✅ + B-7 L133 ✅ + E-1 L172 ✅ +
  D-6 L162 ✅ + E-2 L173 ✅ + E-3 L174 ✅

## 4. Codex 实施范围

**Allowed/Files**:
- NEW `factory-console/memory/learning_guards.py` (护栏 — 先做)
- NEW `factory-console/memory/learning_loop.py` (经验闭环: on_execution_complete + resolve_for_task)
- MOD `factory-console/session/actions.py` (执行完成 → LearningLoop 钩子; 审批 → DECISION_LEARNED 组织记忆; 成本回填)
- MOD `factory-console/memory/experience_store.py` (复用, 如需)
- MOD `factory-console/retrieval/unified.py` (复用)
- MOD `factory-console/session/capability_router.py` (M4-5 排序: persona_score + load)
- MOD `factory-console/session/execution_replay.py` (M4-6 非 git 快照)
- MOD `factory-console/session/budget.py` + `cost_ledger.py` (成本闭环)
- MOD `factory-console/session/board.py` 或 CLI (成本/学习可视化, 只读)
- NEW `tests/console/test_s10_119_learning_loop.py`
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs/FEATURES.md / docs/sprint10/待办清单-已发现未落地.md

**Forbidden（硬边界）**:
- 不重造路由 (依赖 K-1/K-2 quality_score/load)
- 学习核心用确定性规则; LLM 仅可选辅助, 规则分始终存在
- 不重写 ExperienceStore/retrieval/CostLedger/BudgetEnforcer/execution_replay 语义 (复用扩展)
- 不动 lifecycle_store (S10-115) / 能力路由核心 (K-1 route 基本逻辑 — 只扩排序键)
- 护栏优先级最高: 任何学习路径可开关、可回滚、有预算上限
- board 展示只读; 禁 git add -A; 禁新增第三方依赖

**Validation**:
- `pytest tests/console/test_s10_119_learning_loop.py -q` 全绿
- env -u 聚焦 (memory/actions/capability_router/execution_replay/budget/cost_ledger/board + 既有相关测试) 全绿
- env -u 全量 console+api 0 新增失败 (并发未提交改动隔离验证, 参照 S10-117 方法)
- 实测: 两次同类任务引用; 护栏 4 项; 决策记忆; 成本告警; 画像分配; L4 非 git 快照; E-2 闭环
- commit: `feat(S10-119): K-3 学习闭环 — M4-1经验闭环+M4-2护栏+M4-3决策记忆+M4-4成本告警+M4-5画像分配+M4-6L4快照 + E-2/E-3, v1.1.89`

## 5. 验收标准（Hermes 独立验证）

- [ ] 1. 两次同类任务 → 第二次引用 (reason 可解释)
- [ ] 2. 护栏 4 项各 1 fixture (关闭零变化/低样本/低质量/超预算阻断)
- [ ] 3. 决策记忆链路 (审批→DECISION_LEARNED→组织记忆→下次少审)
- [ ] 4. 成本告警链路 (usage→聚合→告警/阻断→回填)
- [ ] 5. 画像分配 (高画像/低负载优先)
- [ ] 6. L4 完整化 (非 git 快照可还原; 不可快照明确报错)
- [ ] 7. E-2/E-3 至少一条评估驱动闭环可断言
- [ ] 8. 契约测试 ≥12 全绿
- [ ] 9. 全量回归 0 新增失败 (并发隔离验证)
- [ ] 10. v1.1.89 + K-3/M4-1~6/B-7/E-1/D-6/E-2/E-3 ✅
- [ ] 11. 设计文档落盘

## 6. 诚实记录要求

- 学习闭环任何环节无法确定性证明 → 如实标注不假装闭环
- 波及面超预期 → 列出征询, 不擅自扩大
