# AI Software Factory — Knowledge & Learning Model

> 状态: DESIGN ONLY (蓝图, 未实现或部分实现 — 见 ../audit/architecture-reality-audit.md)

> 日期: 2026-08-07 | 状态: 设计 (Phase 16 Deep Review)
> 核心: Knowledge(知道什么) ≠ Experience(做过什么) ≠ Performance(做得怎样); 三层知识隔离

## 1. 企业知识 = Company Context

```
Company Knowledge Base (每公司独立):
  企业文化 / 产品 / 技术文档 / 客户 / 市场 / 历史决策 / SOP / 代码规范
Company B 完全隔离 (公司前缀数据空间 + 权限边界)
```

### 三层知识隔离

```
Layer 1 通用能力 (Global):
  Python/Java/Flutter 技能 — 跨公司通用, 不敏感
Layer 2 企业知识 (Company):
  A 公司代码规范/产品/客户 — 公司级, 员工只读所属公司
Layer 3 项目知识 (Project):
  当前项目架构/决策链/Artifact — 项目级, 按参与角色授权
```

```
Agent 使用 = Role + Knowledge + Capability
  开发 Agent: 通用能力(Python) + 企业知识(A 公司规范) + 项目知识(当前架构)
```

## 2. Knowledge 如何学习/更新/检索/授权

```
学习:  从 Artifact/文档/历史项目提取 (Analysis Agent 建议) → 人工确认入库
更新:  版本化 (version) + Approval (知识变更 = 决策)
检索:  确定性规则 (标签/领域/全文) — 不绑定 LLM; 未来语义检索 (Analysis)
授权:  公司隔离 (Layer 2) + 项目授权 (Layer 3); 敏感域 (财务/客户) 按 Role
```

## 3. 三类学习（明确区分，全部可审计）

```
① Knowledge Learning  学习新知识 (公司知识库更新, 人工确认)
② Experience Learning 总结工作经验 (Execution→Result→Review→ExperienceRecord)
③ Performance Learning 优化员工选择 (经验回流 → 推荐加权 10A-3)

不是无限自动学习:
  知识入库 = 人工确认 (重大知识变更走 Approval)
  经验记录 = 自动 + Review 校验 (QA/人工)
  员工选择 = 推荐 (10A-3), 不自动替换
```

## 4. Experience Loop

```
Task → Execution → Result → Review → Experience Record → Capability Improvement

Review 双重: QA 验证 (客观) + Human/Review Agent (主观)
Experience 回流: 员工 experience_summary 更新 → 未来分配加权
Capability Improvement: 高绩效 → 更难任务; 低绩效 → 培训/降权
```

## 5. 审计

```
三类学习全部 Event 化 (knowledge.*/experience.*/performance.*)
可追溯: 谁学的/学了什么/为什么/何时生效
```
