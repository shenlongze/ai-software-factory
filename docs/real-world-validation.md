# Phase 12B — Real World Validation (MarkPad 生命周期验证)

> 日期: 2026-08-06 | 验证项目: MarkPad | 需求: 表格编辑器增强
> 环境: 临时工厂根 + Mock Provider 生成 (生命周期/审批/决策/经验全部真实逻辑)

## 1. 输入需求

```
MarkPad 表格编辑器增强:
- 表格单元格逐格编辑 (当前仅整表编辑)
- Tab 键单元格导航
- 内联编辑, Typora 极简风格
```

## 2. Factory 过程 (真实输出)

### Idea 创建 → Lifecycle 启动

```
idea: PI-001 "MarkPad 表格编辑器增强" (goals: cell-edit, tab-nav)
lifecycle: LC-001 software_project 8 阶段链:
  idea → research → prd → approval(prd) → ui → approval(ui) → architecture → task
```

### Research Artifact (Provider 生成)

```
ART-002 type=research provider=mock
content: "## MarkPad 表格编辑器市场研究
  - 目标用户: PC 笔记用户 / 竞品: Typora, Notion / 机会: 表格逐格编辑缺失"
```

### PRD Artifact + Approval Gate (自动申请 → 人工批准)

```
ART-003 type=prd  → 自动申请 APR-001 (PRD mandatory, 9b 机制)
→ 人工 decide approve (by=shenlongze, comment="PRD 合理, 批准")
```

### UI Artifact + Approval Gate

```
ART-005 type=ui → 自动申请 APR-002 (UI mandatory) → 人工 approve
```

### Architecture Decision + Task Plan (决策链)

```
decision_artifact: architecture (source: ART-003 PRD)
decision_artifact: task_plan (source: ART-005 UI)
```

### Development Task (交 Core Workflow)

```
T-001 "MarkPad 表格编辑器增强-开发" workflow=feature-delivery project=markpad
```

## 3. AI 决策 (真实 Recommendation 输出)

```
输入: task=development, capabilities=[code, reasoning]
输出: score=0.738
  + capability 0.90 (任务要求能力: code, reasoning)
  + performance 0.80 (性能表现佳)
  + cost 0.70 (成本效益好)
  - experience 0.28 (负向: 含失败经验记录, 经验分≤能力分)
  综合评分 = Σ(因素 × 权重) = 0.738
```

**可解释性验证 ✅**: 每项分数 + 方向 (+/-) + 原因文本, 可逐项复算。

### Decision 验证

```
intelligence.decision: recommendation=mock confidence=0.35 risk=high requires_approval=True
(高风险 → 绑定 Approval, 人工最终决定 — Decision≠Approval 语义)
```

## 4. Human Approval (全部人工确认)

```
APR-001 (PRD):  shenlongze approve "PRD 合理, 批准"
APR-002 (UI):   shenlongze approve "UI 方向确认"
Decision:       requires_approval=True (高风险, 等待人工)
```

## 5. 输出结果

```
Artifacts: 6 (idea/research/prd/ui + decision 链)
Tasks:     T-001 (workflow=feature-delivery)
Decisions: architecture + task_plan 决策链 + provider_selection 决策
Experience: 成功经验 (score 0.9) + 失败经验 (score 0.3, negative_signal)
```

## 6. 数据证明

```
事件总数: 34 (idea.created → product.lifecycle.started → stage.entered/completed
         → approval.required/approved → provider.selected → generation.* → task 生成)
经验记录: 2 (positive + negative)
正负聚合: factor=0.285 (成功 0.9×0.9 + 失败 -0.3×0.8 → 混合, 失败降低)
Task:     1
Artifacts: 6
测试:     4090 pytest 全绿 (零回归)
```

## 发现的问题

```
1. (验证脚本用法) idea/artifact id 显示需注意前缀 (PI-001 非 PI-PI-001) — 系统正常, 脚本日志前缀重复
2. 生成阶段需显式 advance 推进 (generate 不自动推进阶段) — 设计如此, 文档化
3. Mock Provider 需返回 ok/usage 字段 (ProviderResponse 契约) — 真实 adapter 满足, 已验证
4. 队列唯一性守卫: 生成自动申请审批后手动 request 会拒 (同 artifact pending) — 正确防重复
```

## 改进建议

```
1. CLI: product lifecycle status 输出 current_stage 可加阶段进度条 (8 阶段 x/y)
2. 生成链路: 可增加 "生成后自动 advance" 选项 (当前需手动) — 或保持显式控制
3. Experience: 聚合 factor 0.285 显示负向影响 — 未来可加 "失败率趋势" 视图
4. Demo 友好: real-world-validation 的 CLI 原文可生成脚本化 demo (factory demo 命令)
```

## 结论

```
✅ Idea→Research→PRD→[Approval]→UI→[Approval]→Architecture→Task→Experience 完整闭环验证通过
✅ 每阶段产生 Artifact + Event + Decision + Evidence
✅ Recommendation 四因素可解释 (Capability/Cost/Performance/Experience)
✅ Experience Loop: 成功+失败信号影响推荐 (负向 0.28 < 冷启动 0.5)
✅ Core 零修改
```
