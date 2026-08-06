# ADR-0030 — Phase 10A-1: Intelligence Layer 基础 (认知层模型/存储/事件)

> 日期: 2026-08-06 | 状态: Accepted | 前置: Phase 9d (0029, 3393 tests)

## 背景

Factory 已完成生命周期管理 (9a-9d: Idea→审批→生成→编排) 与 Provider 智能来源
(8: 能力/成本/使用/反馈), 但**所有"判断"都硬编码在业务流程里**: 没有统一的决策
产物、没有推荐+解释、没有经验积累。Phase 10A 引入 **Intelligence Layer (认知层)**:
分析 + 推荐 + 解释, **不自动执行**。10A-1 只落**基础** — 数据模型 + 独立存储 +
事件 (引擎/LLM/学习算法分属 10A-2~4)。冻结约束 (同 9a-9d): **Core 零修改 /
Extension only / 只读隔离 / 不绑定 Hermes / 不绑定 LLM / 事件唯一事实源**。

设计文档: docs/intelligence-layer-model.md (模型/存储/事件/防自我循环落地点)。

## 决策

### 1. Decision ≠ Approval: 智能产物与人工闸门语义分离

9c Approval 是**人工闸门状态机** (pending→approved/rejected/changes_requested/
delegated, 绑定 Artifact Version 与 Workflow Pause)。若把 AI 决策混入 Approval,
会把"机器建议"与"人工确认"两个语义层搅在一起。决策:

- **Decision** (本层) = AI 推荐产物: decision_type/subject_id/options/
  recommendation/confidence/risk/evidence, 状态 open/recommended/accepted/
  rejected — 只记录 AI 的分析与人工决定的**结果回写**, 不含审批工作流。
- **人工确认机制本体仍在 9c** (复用不复制): Decision.approval_request_id 可选
  绑定 ApprovalRequest; 9c decide 终态可回写 Decision 状态 (10A-2 接线)。
- 状态词选 **accepted/rejected** 而非 approved/rejected — 与 Approval 语义
  区隔 (避免"AI 自我批准"的歧义)。

### 2. Recommendation 必须携带解释 (reasoning) + 证据 (evidence)

智能输出的可解释性 = 可审计性。决策: Recommendation 固定字段
reasoning (list[str], 逐条为什么) + evidence (list[Evidence], 六来源事实引用),
不允许"黑箱分数"。评分公式 (capability/cost/performance/experience 多因素加权)
属 10A-3 引擎; 本层只保证**字段存在 + 持久化 + 事件计数** (reasoning 全文不入
事件 payload, 事件只承载锚点与计数, KISS)。

### 3. 统一经验模型五域 + freshness/decay (不实现学习算法)

决策:
- domain ∈ provider/agent/workflow/project/decision — 一个 ExperienceRecord 模型
  覆盖五域 (替代 9b GenerationExperience / 9c ApprovalExperience 各自为政的
  分裂模型; 已有模型保持兼容不回改)。
- **freshness/decay 是模型层确定性数学**: `decay_freshness = 0.5 ** (age/half_life)`
  (缺省半衰期 30 天); `effective_score = score × confidence × freshness`; 衰减锚点
  = last_used (使用即刷新 — 被反复验证的经验保持有效); mark_used 更新
  usage_count/last_used/freshness (model_copy 新实例)。
- **不实现学习算法**: 经验→推荐的影响链 (10A-4)、冷启动中性分 (10A-4)、任何
  加权/训练逻辑均不在本阶段 — 本层只提供数据接口与衰减数学。

### 4. Evidence 六来源 — 防 AI 自我循环的可追溯基石

决策: Evidence.source_type ∈ artifact/event/experience/external_data/
human_input/provider_output; lineage_ref() = `{source_type}:{source_id}` 规范化
锚点。语义分级: **事实优先** (事件/Artifact/经验/外部数据/人工输入是事实, AI
输出 provider_output 是建议) — 与 phase10a-plan §Q4 机制 6 一致: 每个
Decision/Recommendation 附证据链, 全链可回溯 (推荐→决策→事件→事实)。

### 5. 独立数据空间 + 原子写 + 损坏失败安全

决策 (同 product/ 模式, ADR-0026 决策 5):
- `.factory/intelligence/` 独立目录, 三文件单节 (decisions.json/
  recommendations.json/experiences.json), 与 tasks/agents/providers/product 分离。
- 原子写: 临时文件 + os.replace; 目录首次写创建; 零 .tmp 残留。
- 核心目录数据损坏 → `CorruptIntelligenceStoreError` 响亮报错 (不静默返回空);
  文件不存在 = 空库。三文件独立损坏互不影响。
- store.py **零顶层 imports events/product/providers/runtime** (纯 stdlib +
  公共接口) — Removal Isolation 与 product store 同构。

### 6. 事件命名空间 (4 类型, 纯增量枚举)

`intelligence.decision.created` / `intelligence.recommendation.created` /
`intelligence.experience.recorded` / `intelligence.viewed` — 依 ADR-0001 决策 1
扩展路径: **给 EventType 加 4 个成员即可** (120 → 124, 不改表结构/API, 既有
精确枚举断言零影响 — 已 grep 确认无 EventType 集合/计数断言)。写路径事件
source="intelligence"; viewed 为读命令审计 (ADR-0002, source 缺省 "cli" —
本阶段无 CLI, 辅助函数为 10A-5 CLI 预留)。logger=None 全部静默。

### 7. 只读隔离 + 零执行 (Core 边界)

- Intelligence 模块零顶层 imports Core 写路径 (只复用 events 公共接口)。
- 模型无任何执行指令字段; 本阶段无 CLI/Dashboard/Web API/Database。
- 删除 intelligence/ 包 → Factory 模块加载与运行零影响 (源码级零 imports +
  模拟删包 ImportError 测试双保险)。

## 影响

- **Core 修改**: 仅 `events/models.py` EventType 枚举 +4 成员 (纯增量, 允许范围
  内唯一 Core 触碰点); 其余 Core 零修改。
- **新增** `factory-core/intelligence/`: models.py (4 模型 + 3 枚举 +
  decay_freshness) / store.py (基类 + 三 Store) / events.py (4 辅助) /
  __init__.py (导出)。
- **新增** `tests/intelligence/`: conftest + intelligence_helpers + 7 测试文件
  (175 测试): 模型校验 / 三 Store 写读往返 / 原子写+损坏 / 4 事件链序+payload /
  Evidence 六来源+可追溯 / freshness-decay-usage / Removal Isolation +
  Backward compatibility (既有 EventType 值逐位不变, 计数 124)。
- **文档**: docs/intelligence-layer-model.md (本 ADR 的模型细节)。
- 既有 3393 测试零回归: 全量 **3568 passed** (3393 + 175)。

## 冲突消解与记录

- **Decision 状态词**: phase10a-plan.md §2 评审草案用 "approved/rejected" —
  落地取 accepted/rejected 与 Approval 区隔 (决策 1), 记录于此。
- **10A-1 事件名**: phase10a-plan §4 评审草案 (intelligence.analysis.started /
  recommendation.generated 等) 与 phase10a1-status.md 冻结范围 (4 事件:
  decision.created/recommendation.created/experience.recorded/viewed) 冲突 —
  以 status 文档为准 (冻结范围最小化), analysis.* 留待 10A-2 引擎阶段。
- **Experience 模型统一**: 9b/9c 既有 GenerationExperience/ApprovalExperience
  保留不回改 (兼容); 本层五域模型为统一演进方向 (10A-4 汇合)。
