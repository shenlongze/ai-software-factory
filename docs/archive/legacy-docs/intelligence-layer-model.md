# Intelligence Layer 模型 (Phase 10A-1)

> 状态: IMPLEMENTED (已实现 — 见 ./audit/architecture-reality-audit.md)

> 日期: 2026-08-06 | 状态: Accepted (ADR-0030) | 范围: 基础 — 模型 + 存储 + 事件
> 前置: Phase 9d (3393 tests) | 后续: 10A-2 Decision Intelligence / 10A-3
> Recommendation Engine / 10A-4 Experience Integration

## 1. 定位

Intelligence Layer 是 AI Software Factory 的**认知层**: 只负责 **分析 + 推荐 +
解释**。**不自动执行。**

```
Human Layer → Approval/Decision → Intelligence Layer (认知层) → Capability → Execution → Core
Intelligence 只读 Core 数据 (Event/状态); Core 不感知 Intelligence; 删除后 Factory 正常
```

### 边界铁律

- **只读隔离**: Intelligence 不写 Core 状态 (无法自我强化, 防 AI 自我循环)。
- **执行决策权在人**: Intelligence 输出 = Recommendation/Decision, 不触发执行;
  人工确认走 9c Approval 状态机 (approval.*, 复用不复制)。
- **不绑定 Hermes/OpenAI/Claude/Local**: 零外部依赖 (纯 stdlib + pydantic +
  Core 公共接口)。
- **不自动执行**: 本层无引擎/LLM/学习算法 (属 10A-2~4)。

## 2. 数据模型 (factory-core/intelligence/models.py)

### 2.1 Decision — 智能决策产物 (≠ Approval)

```
Decision:
  id                全局唯一 (uuid4 hex)
  decision_type     决策类型 (provider_selection / task_plan / ... — 10A-2 引擎受控词汇)
  subject_id        决策对象 id (task/project/idea/artifact)
  description       决策问题描述 (分析对象)
  options           list[dict] 选项集合 (结构由 10A-2 引擎定义, 本层只做容器校验)
  recommendation    推荐选项标识 (options 内 key); None = 尚未推荐
  confidence        0-1 推荐置信度 (低置信度 → 降级"需要人工"而非自动采纳)
  risk              0-1 推荐风险
  evidence          list[Evidence] 决策依据证据链 (可追溯)
  status            open / recommended / accepted / rejected
  approval_request_id 可选: 绑定 9c Approval 请求 (复用不复制)
  created_at        UTC 时间戳 (统一存储格式)
```

**Decision ≠ Approval** (phase10a-plan §Q2):

| | Decision (本层) | Approval (9c) |
|---|---|---|
| 语义 | AI 推荐产物 (分析/选项/评分/证据) | 人工闸门 (pending/approved/rejected/...) |
| 状态 | open/recommended/accepted/rejected | pending/approved/rejected/changes_requested/delegated |
| 触发 | 引擎生成 (10A-2) | 人工 decide |
| 关系 | 可携带 approval_request_id 绑定 | 决定结果可回写 Decision |

### 2.2 Recommendation — 推荐 + 解释 (必须支持解释)

```
Recommendation:
  id              全局唯一
  target_type     provider / agent / skill / workflow / ... (10A-3 受控词汇)
  target_id       目标对象 id
  score           0-1 推荐分
  reasoning       list[str] 解释: 逐条说明为什么推荐 (10A-3 引擎生成)
  evidence        list[Evidence] 推荐依据证据链 (六来源)
  confidence      0-1 置信度
  risk            0-1 风险
  created_at      UTC 时间戳
```

模型不携带任何执行指令 — 只推荐不执行 (边界铁律)。

### 2.3 ExperienceRecord — 统一经验 (五域 + freshness/decay)

```
ExperienceRecord:
  id           全局唯一
  domain       provider | agent | workflow | project | decision   (五域)
  subject_id   经验对象 id
  result       success | failure   (负样本 = 反事实记录, 防只记成功的偏差)
  score        0-1 该次表现分 (performance)
  confidence   0-1 记录可靠度
  created_at   UTC 时间戳 (衰减起点)
  last_used    最近使用时间 (None = 从未使用; 使用即刷新衰减锚点)
  usage_count  使用计量
  freshness    0-1 新鲜度 (记录/使用时 = 1.0, 之后按半衰期指数衰减)
```

**freshness/decay** — 历史经验不永久有效:

```
decay_freshness(age_s, half_life_s) = 0.5 ** (age_s / half_life_s)   # 纯函数
  age = 0            → 1.0   (刚记录/刚使用)
  age = half_life    → 0.5   (缺省半衰期 30 天: DEFAULT_HALF_LIFE_DAYS)
  age = 2 × half_life → 0.25
  age → ∞            → 0     (永不为负)

current_freshness(now)  衰减锚点 = last_used 或 created_at (使用过 = 被验证, 保持有效)
effective_score(now)    = score × confidence × freshness   ← 未来评分基础 (Q3 影响链)
mark_used(now)         usage_count +1, last_used = now, freshness = 1.0 (返回新实例)
```

只提供确定性衰减数学, **不含学习/加权算法** (经验→推荐的影响链属 10A-4)。

### 2.4 Evidence — 六来源 + 可追溯 (防 AI 自我循环)

```
Evidence:
  source_type   artifact | event | experience | external_data | human_input | provider_output
  source_id     原始来源引用 id
  description   该证据支撑什么
  confidence    0-1 证据本身可靠度
  timestamp     UTC 时间戳
```

- **lineage_ref()** = `f"{source_type}:{source_id}"` — 规范化可追溯锚点
  (如 `event:<event_id>` / `artifact:<artifact_id>` / `experience:<experience_id>`)。
- **六来源语义 (事实优先, §Q4 机制 6)**: artifact/event/experience/
  external_data/human_input 是事实 (Factory 内部只读数据/外部事实/人工输入);
  provider_output 是 AI 建议 — 事实优先级最高, AI 输出是建议不是依据。
- 每个 Decision/Recommendation 附 evidence 链 → 可审计、可追溯、可证伪。

## 3. 存储 (factory-core/intelligence/store.py)

独立数据空间 `.factory/intelligence/` (与 tasks/agents/providers/product 完全分离):

```
.factory/intelligence/
├── decisions.json        {"decisions": {id: Decision dict}}
├── recommendations.json  {"recommendations": {id: Recommendation dict}}
└── experiences.json      {"experiences": {id: ExperienceRecord dict}}
```

- **三 Store 独立**: DecisionStore / RecommendationStore / ExperienceStore (共享
  目录, 独立文件, 互不干扰 — 一个文件损坏不影响另外两个)。
- **原子写**: 临时文件 `.{filename}.{pid}.tmp` + `os.replace` (同 product/
  providers 模式); 目录由首次写创建; 正常路径零 .tmp 残留。
- **损坏失败安全**: 核心目录数据 — JSON 解析失败/结构不符/模型校验失败 →
  `CorruptIntelligenceStoreError` 响亮报错 (不静默返回空); 文件不存在 = 空库
  (首次写前合法状态)。
- **零顶层依赖**: store.py 零顶层 imports events/product/providers/runtime
  (纯 stdlib + 公共接口); 无业务逻辑 (引擎在 10A-2~4)。

## 4. 事件 (4 类型, 经 EventLogger)

| 事件 | 语义 | payload 要点 |
|---|---|---|
| `intelligence.decision.created` | Decision 落库 (AI 推荐产物) | decision_id/decision_type/subject_id/recommendation/confidence/risk/evidence_count/approval_request_id |
| `intelligence.recommendation.created` | Recommendation 落库 (推荐+解释) | recommendation_id/target_type/target_id/score/confidence/risk/reasoning_count/evidence_count |
| `intelligence.experience.recorded` | 经验记录落库 (只记录不消费) | experience_id/domain/subject_id/result/score/confidence |
| `intelligence.viewed` | 读命令审计 (ADR-0002, source=cli) | view/count |

- 写路径事件 source="intelligence"; 读审计 source="cli" (本阶段无 CLI, viewed
  辅助函数为 10A-5 预留)。
- logger 为 None 时全部静默 (纯存储场景)。
- 事件是唯一事实源: 从事件 payload 可重建落库对象的关键字段。

## 5. 防 AI 自我循环 (phase10a-plan §Q4 落地点)

1. **只读隔离**: Intelligence 不写 Core 状态 — 无法自我强化。
2. **人工闸门**: Decision 可绑定 9c Approval (approval_request_id 预留)。
3. **证据链**: 每个 Decision/Recommendation 附 Evidence (可追溯/可审计)。
4. **反事实记录**: Experience 同时记录失败样本 (result=failure)。
5. **置信度阈值**: confidence/risk 字段量化, 低置信度 → 需要人工。
6. **外部事实源**: Evidence 六来源 — 事件/Artifact 是事实, AI 输出是建议。

## 6. 阶段边界 (10A-1 不做)

- 10A-2: Decision Intelligence — analyze/options/score/recommend/evidence/approval 集成
- 10A-3: Recommendation Engine — 多因素加权 + 解释 (Capability/Cost/Performance/Experience)
- 10A-4: Experience Integration + TaskEvaluation — 经验→推荐影响链 / TaskRequirement 匹配
- 无 Database / Web API / CLI / Dashboard (10A-1 只落模型 + 存储 + 事件)

## 7. 验证

- tests/intelligence/ 175 测试全绿 (≥70 达标): 模型校验 / 三 Store 写读往返 /
  原子写 (零 .tmp/损坏检测) / 4 事件链序+payload / Evidence 六来源+可追溯 /
  freshness-decay-usage / Removal Isolation (Core 零感知 + 模拟删包) /
  Backward compatibility (EventType 120→124 纯增量)。
- 全量 3393 + 175 = **3568 passed**; git diff = Core 仅 events/models.py 枚举扩展。
