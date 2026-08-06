# 反馈闭环模型 (Feedback Model) — 接口设计

> 日期: 2026-08-06 初稿 (Phase 14A) / 2026-08-07 补充分类路由与闭环 (Phase 14B) | 状态: **设计稿, 不实现后台**
> 关联: ADR-0031 (Decision, Phase 10A-2) · ADR-0033 (Experience, Phase 10A-4)
> 铁律: 只定义**接口与数据结构**, 不落库、不建服务、不接 UI — 留待未来 Feedback 阶段实现。

## 1. 为什么需要 (问题域)

Factory 的经验学习 (10A-4) 只记录**系统内执行结果** (provider/agent/workflow 成败)。
但有一类最高价值的证据没有入口: **用户怎么说** — Bug 报告、Feature Request、
"我这么用你的系统"的使用场景。这些是 human_input 类证据, 目前只能由人手工
录入 Experience, 没有结构化通道。

本模型定义未来闭环的**接口契约**:

```
用户反馈 / Issue / Feature Request / 使用场景
        │  (采集, 未来实现)
        ▼
   Feedback (FeedbackRecord) ──decision_link──▶ Decision (10A-2, ADR-0031)
        │                                            │  接受/拒绝 → 计划/产品方向
        └──────────────experience_link───────────────┴──▶ Experience (10A-4, ADR-0033)
```

- **Feedback → Decision**: 反馈若触发产品/架构/范围类决策, 作为 human_input
  证据进入 Decision Context 证据链 (ADR-0031 §3), 由决策引擎评分推荐, 人工裁决。
- **Feedback → Experience**: 反馈 (及其对应决策的结果) 沉淀为经验事实, 经 30 天
  半衰期衰减参与未来推荐 (ADR-0033) — 让"用户说不好用"影响"下次选谁干活"。
- 与现有铁律一致: 反馈只**记录与关联**, 不自动改权重/配置 (经验 ≠ 自我修改)。

## 2. 数据模型 (FeedbackRecord)

```python
# 设计稿 — 未来实现时位于 intelligence/feedback.py, 本阶段不落库
class FeedbackType(str, Enum):
    BUG_REPORT       = "bug_report"        # 缺陷/异常行为
    FEATURE_REQUEST  = "feature_request"   # 新能力/改进
    USAGE_SCENARIO   = "usage_scenario"    # 使用场景描述 (谁/在什么任务/怎么用)
    GENERAL_FEEDBACK = "general_feedback"  # 其他 (体验/性能/文档)

class FeedbackSource(str, Enum):
    GITHUB_ISSUE = "github_issue"
    EMAIL        = "email"
    CONSOLE      = "console"    # Human Console 内置反馈入口 (未来)
    CLI          = "cli"        # factory feedback submit (未来)
    MANUAL       = "manual"     # 维护者手工录入 (中转导入)

@dataclass
class FeedbackRecord:
    id: str                      # feedback:<uuid>
    type: FeedbackType
    source: FeedbackSource
    source_ref: str              # 来源引用: issue 号 / email 主题 / 会话 id
    title: str                   # 一句话摘要
    context: str                 # 自由文本详情 (复现步骤/期望行为/使用场景)
    related: list[str]           # 关联对象 id: project / task / artifact / workflow
    created_at: datetime
    status: str                  # new → triaged → resolved (见 §4)
    decision_link: str | None    # 关联 Decision id (10A-2), 默认 None
    experience_link: str | None  # 关联 Experience id (10A-4), 默认 None
```

**与既有模型的关系**:

- `FeedbackRecord` 与 `ExperienceRecord` (10A-4) **同构不重复**: Feedback 是
  "用户原始输入", Experience 是"执行事实" — Feedback 经 `experience_link`
  引用对应经验, 不复制其字段。
- 作为证据时, Feedback 以 `human_input` 类型进入 Evidence 六来源
  (artifact / event / experience / external_data / human_input / provider_output),
  `lineage_ref() = "human_input:feedback:<id>"`, 与 ADR-0031 §3 去重规则兼容。
- **不变式**: `status == resolved` 时, `decision_link` 或 `experience_link`
  至少一个非空 (闭环才算完成); 只记录不执行, 无任何自动触发副作用。

## 3. Issue 分类路由 (triage 分类映射, Phase 14B 补充)

采集进来的是原始反馈 (issue/email/console/cli), triage 的第一步是**按 Issue 类别
路由到对应目标域**, 决定"这条反馈交给谁处理、是否触发决策、沉淀什么经验"。
分类维度 (对应 GitHub Issue 标签等) 与 `FeedbackType` (采集形态) 正交:
一个 `bug_report` 形态的反馈通常归为 `bug` 类别; 分类结果由维护者在 triage 时
写入, 不自动判定 (LLM 自动分类属未来 Self Evolution 范畴, 见 §6 边界)。

| Issue 类别 | 路由目标 | triage 处理动作 | 闭环去向 (link) |
|:-----------|:---------|:----------------|:----------------|
| `bug` (缺陷/异常行为) | **DecisionIntelligence — 问题定位** | 复现 → 根因分析 → 是否触发修复/回滚决策 | `decision_link` → Decision (fix/scope) + `experience_link` → Experience (失败样本) |
| `architecture` (架构问题/建议) | **架构评审 (ADR 流程)** | 架构影响评估 → 是否新增/修订 ADR | `decision_link` → Decision (architecture) + Experience |
| `feature request` (新能力/改进) | **Recommendation → PRD** | 能力需求评估 → 进入 Product Intelligence 生成 PRD → 产品决策 | `decision_link` → Decision (product) + Experience (产物评审经验) |
| `use case` (使用场景描述: 谁/什么任务/怎么用) | **场景分析** | 场景 → 用例 → 能力缺口分析 | `experience_link` → Experience (usage) 或 `decision_link` → Decision (scope 扩展) |
| `business inquiry` (商业/合作咨询) | **商业评估** | 商业价值/定位评估 → roadmap 方向 | `decision_link` → Decision (产品方向) + Experience |
| 其他 (general) | 直接沉淀 | 不触发决策, 记录为体验/文档改进 | `experience_link` → Experience |

**feedback → decision → experience 三步闭环** (与 §1 图中的两条边对应):

```
用户反馈 (new)
   │ ① triage: 分类路由 (§3 表)
   ▼
triaged ──(决策类)──▶ Decision (10A-2) ──人工裁决──▶ 结果沉淀 ──▶ Experience (10A-4)
   │                        ▲                                  ▲
   └──(执行类/经验类)────────┴────────── experience_link ───────┘
```

- **决策类** (bug / architecture / feature request / business inquiry):
  link Decision → 决策结果 (接受/拒绝/改期) 连同反馈本身沉淀为 Experience,
  使"用户怎么说"影响"下次选谁干活"。
- **执行/经验类** (use case / general): 直接 link Experience, 不经过决策。
- 不变式不变: `status == resolved` 时至少一个 link 非空; 分类路由**只记录与关联**,
  不自动改权重、不自动执行任何动作。

## 4. 生命周期 (状态机)

```
new ──(维护者 triage)──▶ triaged ──(关联 Decision/Experience)──▶ resolved
  │                          │
  └──(垃圾/重复)──▶ closed    └──(不需要决策, 直接沉淀经验)──▶ resolved
```

| 状态 | 含义 | 触发 |
|:-----|:-----|:-----|
| `new` | 已采集, 未处理 | 任意来源进入 |
| `triaged` | 已分类: 按 §3 分类路由 (是否触发决策 / 直接沉淀经验) | 维护者 triage |
| `resolved` | 闭环完成: 已关联 decision 或 experience | 写入 link 字段 |
| `closed` | 无效/重复, 不进入闭环 | triage 时判定 |

状态推进用**新实例**语义 (与 Decision.with_status() 一致, ADR-0031 §1):
`FeedbackRecord.with_status(...)` 返回新对象, 调用方负责落库。

## 5. 接口 (未来实现, 本阶段不写代码)

```
# 全部为"未来接口契约", 本阶段不实现后台
FeedbackService (设计签名):
  submit(record: FeedbackRecord) -> FeedbackRecord   # 采集入口 (issue/email/console/cli)
  triage(id, *, by, note) -> FeedbackRecord   # 按 §3 分类路由 + 标记 closed
  link_decision(id, decision_id, *, by) -> FeedbackRecord   # 关联 10A-2 Decision
  link_experience(id, experience_id, *, by) -> FeedbackRecord  # 关联 10A-4 Experience
  list(filters: type/source/status) -> list[FeedbackRecord]   # 只读查询
```

实现约束 (对齐既有认知层):

- 与 Decision/Experience 同样遵循 **Removal Isolation**: `intelligence/feedback.py`
  零 imports product/, 装配方注入存储与链接服务。
- 写路径全部带 `by` 记录操作人, 与 9c Approval / 10A-2 一致 (人工负责制)。
- 反馈数据量小, 无需事件流; 未来若需要, 复用既有 EventType 机制发
  `feedback.created` 事件, 不新建事件体系。

## 6. 落地顺序 (未来阶段)

1. 采集: GitHub Issue 模板 (含类别标签: bug/architecture/feature request/use case/business inquiry) + email 转发 + 维护者 manual 录入 (最小闭环)。
2. 关联: triage 按 §3 分类路由 — 决策类 link 到 Decision, 执行/经验类 link 到 Experience。
3. 增强 (可选): Human Console 只读展示 Feedback 列表与闭环状态。
4. 不做 (边界): 不自动分类 (LLM triage 属未来 Self Evolution 范畴), 不自动
   修改推荐权重, 不接 AI 自动回复。

## 相关文档

- [decision-intelligence-model.md](./decision-intelligence-model.md) — Decision (10A-2, ADR-0031)
- [experience-learning-model.md](./experience-learning-model.md) — Experience (10A-4, ADR-0033)
- [intelligence-layer-model.md](./intelligence-layer-model.md) — 认知层边界与证据六来源
- [SECURITY.md](../SECURITY.md) — 缺陷反馈的正式安全渠道 (与本文档互补: 安全漏洞走私密渠道, 普通反馈走本模型)
