# S10-111 — M3 收尾三件套：实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-24 | 前置: v1.1.77 · M3 主线 4/7 (M3-1~4 ✅)
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 架构设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-111-hermes-m3-finish-prompt.md

---

## 0. 现状审计（CTO 独立复核）

| 项 | 现状 |
|---|---|
| ux 产物 | expert_factory._ux_md — 12 行模板: "进入 → 操作 → 完成/反馈" 通用一句 + "规则占位, UX 可细化" |
| qa 产物 | expert_factory._qa_md — 10 行模板: 通用测试层级 + "规则占位, QA 可细化" |
| PRD | pipeline.ProductDocument: Overview/Problem/Target User/Core Features/Usage Scenario/Future Direction — **无 用户故事/验收标准** |
| 管线 | pipeline_runner.ProductPipeline: 7 角色链, LLM 可用 → system_prompt+上下文; 否则 deterministic_content |
| prepare_project | actions.py:502 — TaskTree→AgentAssignment→status=**execution_ready** (无审批门) |
| execute_project | orchestrator.py:1018 — 执行入口 (M3a-d 引擎, 硬边界不改) |
| 审批设施 | ConfirmationGate (confirm.py:37) 可复用 |
| ChangeControl | 无代码 — 新模块; PRD.md 落盘 projects/<slug>/PRD.md; tasks.json/plan.json 已有 (M3a) |
| M3 跟踪 | docs/sprint10/待办清单-已发现未落地.md L30-32 M3-5/6/7 未标 ✅; FEATURES.md L471 🚧 待办 |
| 版本 | 1.1.77 → 目标 1.1.78 |

## 1. M3-5 占位角色深化（ux/qa 真引擎 + PRD 深度化）

### 1.1 UX 真引擎（expert_factory._ux_md 重写）

从 ProductIntent (user/core_features/platform) 生成, **不含 "规则占位" 标记**:
- 用户流程: 每个核心功能 → 具体 3-5 步流程 (从功能名推导: 进入X页→选择/输入→操作→完成/反馈), 非通用一句
- 页面结构: 首页 / 每个功能页 (按 core_features) / 个人中心 / 设置
- 信息架构: 主导航按功能 + 用户角色上下文 (user 字段)
- system_prompt 同步深化 (LLM 路径: 消费 user/core_features/platform + PRD)

### 1.2 QA 真引擎（expert_factory._qa_md 重写）

从 ProductIntent + PRD 生成 test_plan, **不含 "规则占位" 标记**:
- 测试层级: 单元/集成/E2E/安全/性能 — 每层列具体用例方向 (按功能推导)
- 验证命令: pytest / 冒烟 (真实命令模板)
- 每核心功能 ≥1 用例方向
- system_prompt 同步深化

### 1.3 PRD 深度化（pipeline.ProductDocument）

追加两章 (确定性生成, 手算对照):
- `## User Stories`: 每核心功能一条: "作为 {user}, 我想要 {feature}, 以便 {problem 价值}"
- `## Acceptance Criteria`: 每核心功能 2-3 条 given/when/then 或清单
- 无 LLM 时确定性兜底仍产出合理 PRD (验收 ④)

边界: 只改 ux/qa/prd 三角色生成; 不改 market/competitive/architect; 不改管线编排顺序 (ROLES 链不变)。

## 2. M3-6 需求变更回流 ChangeControl（新模块 change_control.py）

### 2.1 模块结构

```python
@dataclass
class ChangeProposal:
    id: str; project_slug: str; request: str; reason: str; status: str  # proposed/approved/rejected
    created_at: str

@dataclass
class ImpactAnalysis:
    proposal_id: str; affected_prd_sections: list[str]; affected_tasks: list[str];
    affected_dependencies: list[str]; note: str

class ChangeController:
    def propose(self, slug: str, request: str) -> ChangeProposal
        # 解析变更内容+理由 (确定性: "加导出功能" → request="导出功能", reason="新增需求";
        # 可 LLM 补充 — 规则优先)
    def impact(self, proposal) -> ImpactAnalysis
        # 读 PRD.md + tasks.json + plan.json; 变更关键词匹配 PRD 章节/任务标题/依赖
        # (确定性, 手算可枚举; 过度波及 → 收敛)
    def apply(self, proposal, approved: bool) -> dict
        # approved:
        #   1. PRD 升版: PRD.md → 追加 "# 变更记录 v2: {request}" + changelog 条目
        #      (文件头/尾标记 v2)
        #   2. replan: 复用 M3a DecomposeEngine 拆变更 → 新任务合并 tasks.json + plan.json
        #      (动态 DAG 已有)
        # rejected: 不写 PRD/不动任务; 记录 status=rejected
```

### 2.2 入口

- 会话命令: `/project change <slug> "加导出"` (ProjectCommand 扩展 change 子命令 — 规格入口, 允许改 commands.py)
- 自然语言: "给XX项目加个导出功能" → intent 识别 → ChangeController.propose (intent.py 加规则 — 规格入口, 允许)
- 审批: 复用 ConfirmationGate (交互 y/N) — y → apply(approved=True); n → apply(False), 消息明确 "已拒绝, 未变更"

边界: 不做执行重放/回滚 (M5-1); 不做并行线程化; 只动本项目 PRD/tasks/plan。

## 3. M3-7 架构审批门

### 3.1 门控（最小侵入）

- `prepare_project` (actions.py): 生成工程计划后 → `project.json status = "pending_arch_review"` (不再直接 execution_ready)
  + 计划摘要存 `arch_review = {summary, requested_at}`
- 审批命令/流程: 展示摘要 (架构选型/任务数/工期) → ConfirmationGate y/N
  - approve → status = execution_ready (进入拆解/执行)
  - reject → status = pending_arch_review + `arch_review.feedback` (计划修订: 重新 prepare 覆盖)
- `execute_project` (orchestrator): 执行前检查 status — 非 execution_ready → 明确错误 "工程计划待架构审批"
  (M3a-d 引擎内部逐字节不改 — 硬边界)

### 3.2 兼容

- 验收 ⑪ "现有 prepare_project/execute_project 正常路径不受影响": 审批通过后行为与 v1.1.77 一致;
  既有测试中直接断言 execution_ready 的 → 按新门控更新 (注入自动批准或先走审批), 逐条注释
- 审批复用 ConfirmationGate, 不新建审批系统

## 4. 契约测试（各 ≥3, 共 ≥9 — tests/console/test_s10_111_m3_finish.py）

M3-5:
1. ux 资产不含 "规则占位"/"进入 → 操作 → 完成/反馈" 特征; 含每功能具体流程
2. qa 资产不含 "规则占位"; 含测试层级 + 验证命令 + 每功能用例方向
3. PRD 含 "User Stories" + "Acceptance Criteria" 章节 (手算对照: 功能数=故事数)
4. 无 LLM (env -u / llm_fn=None) 确定性兜底仍产出以上 (验收 ④)

M3-6:
5. propose → ChangeProposal (request/reason 解析)
6. impact → 波及任务/PRD 章节可枚举 (手算对照)
7. approve y → PRD v2 (含变更记录) + 新任务进 tasks.json + plan.json 更新; n → 无变更
8. /project change 入口 + 自然语言入口

M3-7:
9. prepare_project → status=pending_arch_review
10. approve → execution_ready; reject → 不 execution_ready + feedback 记录
11. execute_project 在 pending_arch_review 时拒绝执行; 审批通过后正常执行 (与 v1.1.77 一致)

全局: 12. 版本 v1.1.78 (pyproject+断言+CHANGELOG+FEATURES.md) + 待办清单 M3-5/6/7 标 ✅ (主线 7/7)

## 5. 版本与发布

- pyproject `1.1.77` → `1.1.78`; CHANGELOG v1.1.78 (三件套条目); 版本断言同步;
  docs/FEATURES.md (头版本 + M3-5/6/7 行 🚧→✅); docs/sprint10/待办清单-已发现未落地.md L30-32 标 ✅

## 6. Codex 实施范围

**Allowed/Files**:
- MOD `factory-console/session/expert_factory.py` (ux/qa 引擎 + prd 深化)
- MOD `factory-console/session/pipeline.py` (ProductDocument 用户故事/验收标准)
- NEW `factory-console/session/change_control.py` (ChangeController)
- MOD `factory-console/session/actions.py` (prepare_project 门控 + 变更/审批 action 入口 — 仅新增/门控, 不改既有 action 语义)
- MOD `factory-console/session/commands.py` (/project change 子命令 — 规格入口)
- MOD `factory-console/session/intent.py` (自然语言变更意图规则 — 规格入口, 纯新增)
- MOD `factory-console/session/orchestrator.py` (execute_project 审批检查 — 最小, M3a-d 内部不改)
- NEW `tests/console/test_s10_111_m3_finish.py`
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs/FEATURES.md / docs/sprint10/待办清单-已发现未落地.md

**Forbidden（硬边界）**:
- 改 market/competitive/architect 角色产物; 改管线编排顺序 (ROLES 链); 改 M3a-d 引擎内部
  (DecomposeEngine/CriticalPathEngine/TaskScheduler/DecompositionEvaluator 逐字节)
- 改调度器 / board / 其它 CLI 命令 (除 /project change 入口)
- 不做执行重放/回滚 / 并行线程化 / 消息平台 / Web 入口
- 禁 git add -A; 禁新增第三方依赖
- 禁 stub/fake: 变更回流/审批门必须真实落盘生效; 影响分析过度波及 → 收敛

**Validation**:
- `pytest tests/console/test_s10_111_m3_finish.py -q` 全绿
- env -u 聚焦 (pipeline/expert_factory/actions/orchestrator/commands/intent/confirm + 既有管线测试) 全绿
- env -u 全量 console 0 新增失败
- 实测: ux/qa 资产无占位; PRD 含故事/验收; 变更 y → PRD v2+任务; n → 无; prepare → pending → approve → 执行
- commit: `feat(S10-111): M3 收尾 — ux/qa真引擎+PRD深度化 + ChangeControl变更回流 + 架构审批门, v1.1.78`

## 7. 验收标准（Hermes 独立验证）

- [ ] ①UX 无 12 行占位特征 ②QA 无 10 行占位特征 ③PRD 含用户故事+验收标准 (手算) ④无 LLM 兜底合理
- [ ] ⑤ChangeProposal 生成 ⑥影响分析手算可枚举 ⑦y→PRD v2+新任务; n→不执行 ⑧plan.json 更新
- [ ] ⑨prepare→pending_arch_review ⑩approve→执行; reject→不执行+反馈 ⑪既有正常路径不受影响
- [ ] ⑫契约 ≥9 ⑬全量回归 0 新增 ⑭M3 待办 3 项 ✅ (主线 7/7) · v1.1.78
