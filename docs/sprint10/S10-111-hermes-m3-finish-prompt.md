# S10-111 Hermes 提示词 — M3 收尾三件套（M3-5 角色深化 / M3-6 变更回流 / M3-7 架构审批门）

> 用途: 复制给 Hermes，独立分析 → 派 Codex 实现 → 独立验收。
> 主线: 待办清单 M3-5/6/7 → 完成后 M3 7/7。

---

## 任务标题
**S10-111 M3 收尾三件套**: M3-5 占位角色深化 + M3-6 需求变更回流 ChangeControl + M3-7 架构审批门

## 背景（Founder 选定下一步）

Board 功能已完善（v1.1.77），主线 M3 4/7（M3-1~4 已完成）。剩余 M3-5/6/7 是
"让 Agent 会干活"的最后三块：角色不再占位、需求能回流、架构要审批。

---

## 规格

### M3-5 占位角色深化（ux/qa 真引擎 + PRD 深度化）

**现状**（§4.10.2 逐角色实况）:
- ux → 12 行模板占位（🔴）· qa → 10 行模板占位（🔴）
- pm/market/competitive/prd 已有真引擎/规则复用（🟢/🟡）

**目标**:
1. **UX 流程真引擎**: 从 ProductIntent + PRD 生成 ux_flow（用户流程/页面/信息架构）,
   非 12 行模板占位 — 复用已有资产字段（user/core_features/platform）+ LLM 深度化
2. **QA 测试计划真引擎**: 从任务/PRD 生成 test_plan（测试层级/用例方向/验证命令）,
   非 10 行模板占位
3. **PRD 深度化**: PRD 含**用户故事 + 验收标准**（§10.5.1 步骤 4: 背景/故事/功能P0/验收）

**边界**: 只深化 ux/qa/prd 三个角色的产物生成; 不改市场/竞品/架构角色;
不改产品管线编排（product_pipeline 流程顺序不变）。

### M3-6 需求变更回流 ChangeControl

**目标**（§10.5.1 步骤 10 + §5.11 ChangeControl）:
执行中提出变更（如"加导出功能"）→ **propose → impact → approve → v+1 → replan**:
1. **propose**: 接收变更请求（自然语言/命令）, 生成 ChangeProposal（变更内容+理由）
2. **impact**: 影响分析 — 哪些 PRD 章节/任务/依赖受影响（读当前 PRD + tasks + plan）
3. **approve**: 变更审批（复用 ConfirmationGate / 用户 y-N）
4. **v+1**: PRD 升版 v2（追加变更内容, 记录 changelog）
5. **replan**: 生成新任务（复用 M3a 拆解）, 更新 tasks.json + plan.json（动态 DAG 已有）

**入口**: 会话命令（如 `/project change <slug> "加导出"`）+ 自然语言意图
（"给XX项目加个导出功能"）→ ChangeControl 流程。

**边界**: 只做变更回流闭环; 不做执行重放/回滚（M5-1）; 不做并行线程化。

### M3-7 架构审批门

**目标**（§6.3.5 审批门 + §10.5.1 步骤 5）:
工程计划生成后（engineering/tasks/execution_plan）→ **架构审批门** —
未批准不进任务拆解/执行。

**实现**:
1. 工程计划生成（prepare_project）后状态 = `pending_arch_review`
2. 审批门: 展示计划摘要（架构选型/任务数/工期）→ 用户 approve/reject
   （复用 ConfirmationGate / approval action）
3. approve → 进入拆解/执行; reject → 反馈原因, 计划修订

**边界**: 审批门复用现有 ConfirmationGate/ApprovalGate, 不新建审批系统;
只加"工程计划→执行"之间的门。

---

## 范围声明（硬边界, 必须遵守）

- ✅ 只改: 产品管线角色产物（ux/qa/prd 生成）+ ChangeControl 模块 + 工程计划审批门
  + 对应契约测试
- ❌ 不改: 市场/竞品/架构角色、产品管线编排顺序、M3a-d 已有引擎、调度器、
  board、CLI 其他命令
- ❌ 不扩展: 不做执行重放/回滚、并行线程化、消息平台、Web 入口
- 统一修改: 实现 + 契约测试 + CHANGELOG + 版本断言 + FEATURES.md 同 Sprint

## 验收标准（Hermes 独立验证, 非 Codex 自报告）

### M3-5
1. UX 资产不再含 "12 行模板占位" 特征（真引擎从 ProductIntent 生成流程/页面）
2. QA 资产不再含 "10 行模板占位" 特征（测试层级从任务/PRD 生成）
3. PRD 含**用户故事 + 验收标准** 章节（手算对照: 输入 ProductIntent → 输出含故事/验收）
4. 无 LLM 时确定性兜底仍产出合理资产（诚实降级）

### M3-6
5. 提变更 → ChangeProposal 生成（含变更内容+理由）
6. 影响分析正确（手算: 改 PRD 的 feature → 波及任务/依赖可枚举）
7. 审批 y → PRD v2（含变更）+ 新任务生成（tasks.json 增加）; n → 不执行
8. replan 后 plan.json 更新（依赖/关键路径含新任务）

### M3-7
9. 工程计划生成后状态 = pending_arch_review（不直接可执行）
10. approve → 进入执行; reject → 不执行 + 反馈原因
11. 现有 prepare_project/execute_project 正常路径不受影响（审批通过后行为与原来一致）

### 全局
12. 契约测试: 三件套各 ≥3（共 ≥9）
13. 全量回归 0 新增失败 · 版本 v1.1.78（pyproject + 断言 + CHANGELOG + FEATURES）
14. M3 待办清单 3 项标 ✅（主线 7/7）

## Codex 指令摘要（可嵌入 Hermes 派单）

> 实现 M3 收尾三件套: ①ux/qa 角色从模板占位改真引擎（从 ProductIntent/PRD 生成,
> PRD 加用户故事+验收标准）; ②ChangeControl 变更回流（propose→impact→approve→
> PRD v2→replan, 入口 /project change + 自然语言）; ③工程计划架构审批门
> （prepare_project → pending_arch_review → approve 才可执行, 复用 ConfirmationGate）。
> 各 ≥3 契约测试, 全量回归 0 失败, v1.1.78。不乱改、不扩展、不影响其他功能。

## 诚实纪律

- 三件套如实报告: 哪些场景真引擎、哪些仍规则兜底（LLM 不可用时）
- 变更回流/审批门必须真实生效（不许伪造"已变更/已审批"）
- 若影响分析过度（波及无关任务）→ 报告并收敛
- 不改 M3a-d 已有行为（原子拆解/关键路径/调度/质量评估逐字节不变）
