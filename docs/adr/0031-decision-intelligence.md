# ADR-0031 — Phase 10A-2: Decision Intelligence (决策链引擎 + CLI)

> 日期: 2026-08-06 | 状态: Accepted | 前置: Phase 10A-1 (0030, 3568 tests)

## 背景

10A-1 落了 Intelligence Layer 基础 (模型/存储/事件), 但**没有引擎**: 没有
"分析→评分→推荐" 的决策能力, 事件辅助函数 (decision.created 等) 无人调用。
Phase 10A-2 实现 **DecisionIntelligence 引擎**: 给定决策上下文, 产出可审计的
Decision Artifact (选项评分 + 推荐 + 解释 + 证据链 + 风险等级), 高风险/低置信度
决策经 9c ApprovalGate 提交人工审批。冻结约束 (同 10A-1): **Core 零修改 /
Extension only / 只读隔离 / 不绑定 LLM / 事件唯一事实源**。**不做**: 自动执行 /
Recommendation Engine (10A-3) / Experience 学习 (10A-4)。

设计文档: docs/decision-intelligence-model.md (生命周期/评分/置信度/风险/人工
闸门细节)。

## 决策

### 1. 决策链 = 六个显式阶段 (Context→Analysis→Options→Evaluation→Recommendation→Risk→Decision)

决策: 引擎公开六阶段方法 (analyze / evaluate_options / recommend /
assess_risk / build_decision / bind_approval) + 全链入口 `decide(context)`。
阶段拆分使每步可单测、可审计、可被未来编排层选择性调用; 全链 `decide` 是 CLI
与测试的唯一便捷入口。规则评分 (四因素加权) **不绑定 LLM** — 输入来自 context
提供的评估数据 (DecisionOption.factors), reasoning 逐条解释为什么 (可审计,
不黑箱)。

### 2. 禁无证据是双层强制 (context 层 + option 层), 且失败零事件

决策: `context.evidence_sources` 为空 → `NoEvidenceError` (拒绝分析);
选项无证据且继承关闭 → `NoEvidenceError` (拒绝评分)。**证据校验在发任何事件
之前** — 错误路径零事件, 绝不发半截链。选项证据缺省继承 context 证据链
(`inherit_context_evidence=True`, CLI 便捷路径 — "选项评分基于上下文事实" 语义);
关闭继承时选项必须显式携带证据。证据在 Decision 层按 lineage_ref 去重
(context ∪ options, 保序保首条)。

### 3. Approval 集成 = 注入式 9c 复用, 装配缺失不静默降级

决策 (同 9b/9c 模式): 引擎不 imports product/ — 审批服务经构造参数注入
(`approval_service`, duck-typed 公共接口 `request_approval(artifact_id,
gate_id=None, *, by, note)`)。高风险 (R1/R2/R3) 或低置信度 (R5) → 
`requires_approval=true`; 已装配服务 + context.approval 绑定点 → 提交审批请求,
`approval_request_id` 回填 (落库用返回值 — model_copy 语义)。**装配缺失不
静默降级**: Decision 保持 requires_approval=true + approval_request_id=None
(标记待人工提交, 引擎不自动执行, 无绕过风险); 审批服务抛错 →
`DecisionIntelligenceError` (响亮失败)。CLI 装配点仅在 `--approval-artifact`
时构造 9c ProductService。

### 4. 风险等级 = 规则检测 (R1-R5), high 或低置信度才强制审批

决策: 高风险规则 R1 (决策类型 ∈ architecture_change/deployment_strategy/
provider_migration/provider_selection) / R2 (选项 risks 文本关键词) / R3 (约束/
目标文本关键词) 命中任一 → high; 未 high 时 R4 (top−runner-up < 0.1 竞争激烈) /
R5 (置信度 < 0.5) → medium。`requires_approval = (high) or (低置信度)` —
**medium 竞争激烈不强制审批** (仅提示需人工确认)。等级 → 数值风险映射
low 0.2 / medium 0.5 / high 0.8 (10A-1 Decision.risk 0-1 兼容)。风险输出含
rules_triggered 锚点 (可审计) + reasons (逐条解释)。

### 5. CLI 单命令 `intelligence decision create`, 延迟导入保 Removal Isolation

决策 (同 product/provider 模式): CLI 只加 `factory intelligence decision
create` (10A-2 冻结范围最小化, list/show 留待 10A-5)。输入规格:
`--option NAME:SCORE[:reason[:EVIDENCE]]` (SCORE = 0-1 单值或四因素逗号分隔),
`--evidence TYPE:ID[:DESC]` (六来源, 必须 ≥1), `--constraint` 可多次,
`--context FILE` JSON 基座 (CLI 标志逐字段覆盖, 列表标志追加)。命令经
`_open_intelligence_engine` **函数内延迟导入** intelligence 包 (commands.py 与
main.py 顶层零 imports) — 删除 intelligence/ → CLI 模块加载零影响, 命令调用
响亮 rc 1 (装配点不静默降级)。退出码: 成功 0 / 业务错误 (禁无证据等) 1 /
用法错误 2 / context 文件缺失 7。

### 6. 事件链 = 4 链序 (3 新事件, 纯增量枚举)

决策: `intelligence.decision.analysis.started` / `...analysis.completed` /
`...option.evaluated` (每选项一条) 在 `decision.created` 之前发出, created 为
**链终单一事件** (载荷含 approval_request_id 回填 — 事件唯一事实源)。EventType
枚举 +3 成员 (124 → 127, ADR-0001 决策 1 纯增量路径, 既有值零改动; 已确认无
EventType 集合/计数断言, 仅 1 处总计数断言最小化更新)。写路径 source=
"intelligence"; logger=None 静默。

### 7. Removal Isolation 语义升级: CLI 顶层零 imports, 装配点响亮失败

决策: 10A-1 的源码级断言 "任何位置无 import intelligence" 在 CLI 接入后收紧为
**"顶层零 imports"** (函数内延迟导入允许 — 与 product/provider/git/change 模式
一致)。模拟删包 (monkeypatch builtins.__import__) 断言: 其余命令 rc 0 零影响;
intelligence decision create → rc 1 且零 intelligence.* 事件 (装配点响亮失败,
不静默降级, 同 9b product generate 模式)。

## 影响

- **Core 修改**: 仅 `events/models.py` EventType +3 成员 (124 → 127, 纯增量)。
- **新增** `factory-core/intelligence/decision.py`: DecisionIntelligence 引擎
  (六阶段 + decide 全链 + 规则评分/置信度/风险纯函数)。
- **新增模型** (intelligence/models.py): DecisionOption / DecisionAnalysis /
  DecisionResult / RiskAssessment / ApprovalBinding / RiskLevel; Decision +
  risk_level/requires_approval/analysis 字段扩展; DecisionContext.constraints
  None → 默认空 (mode="before" 容器字段归一, CLI --context JSON 可能带 null)。
- **CLI**: commands.py `cmd_intelligence_decision_create` + 装配辅助/解析辅助
  (延迟导入); main.py parser + dispatch + print 4 触点接线。
- **新增** `tests/intelligence/`: test_intelligence_decision.py (74 引擎测试:
  四因素评分/权重归一/中性分/reasoning/证据链双层/置信度/风险 R1-R5/Approval
  绑定/事件 4 链序/store 持久化/Context 校验) + test_intelligence_decision_cli.py
  (24 CLI 测试: 冒烟/--json/输入校验/context 基座/风险规则/9c 审批绑定/Removal
  Isolation 模拟删包)。
- **Removal 测试语义更新** (test_intelligence_removal.py): 正则收紧为顶层零
  imports (延迟导入允许), 计数断言 124 → 127 — 行为观察点更新非 API 变更。
- **文档**: docs/decision-intelligence-model.md (本 ADR 模型细节)。

## 验证

- 全量 pytest ≥3648 全绿 (3568 基线 + 98 新增 + 实现零回归)。
- 冒烟: `intelligence decision create --type provider_selection` → Decision +
  reasoning + risk (high, requires_approval) + 事件链; 带 `--approval-artifact`
  → 9c 审批请求绑定。

## 冲突消解与记录

- **10A-1 removal 断言 vs 10A-2 CLI 接入**: 10A-1 测试写 "10A-1 无 CLI 命令,
  10A-5 接入时才需延迟导入", 10A-2 提前接入 CLI — 断言语义更新为顶层零 imports
  (行为观察点, 同 ADR-0014/0017/0018/0019/0020 先例); 实现侧已按延迟导入落地,
  无 API 变更。
- **assess_risk 空选项输入**: 空选项列表时 compute_confidence=0 → R5 低置信度
  误触发 medium — 实际调用链 (decide) 保证选项非空 (evaluate_options 前置校验),
  测试按真实链传参; 引擎对空输入语义保持 (无选项 = 无可信推荐)。
- **DecisionContext.constraints None**: pydantic 容器字段 None 输入在
  类型检查前失败 — 补 mode="before" validator 归一 (同 available_options/
  evidence_sources 既有模式), 属实现缺口修复非契约变更。
