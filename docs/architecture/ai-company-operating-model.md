# AI Software Factory — AI Company Operating Model

> 状态: DESIGN ONLY (蓝图, 未实现或部分实现 — 见 ../audit/architecture-reality-audit.md)

> 日期: 2026-08-07 | 状态: 设计 (Phase 16 Deep Review)
> 核心: 同一组织模型支持 Solo → Enterprise → Multi-tenant → 集团

## 1. 公司如何创建？

```
Company Template → 实例化:
  模板 = Organization + Workflow + Role + Agent + Policy (声明式)

创建流程:
  Human (Founder) → org company create --template software_company
  → Company + Department (Engineering/Product/QA) + Role 集 (CEO/PM/Dev/QA...)
  → 初始员工: 装配默认 Agent (或空, 由 HR 流程招聘)
  → data_root/organizations/<company_id>/ 数据空间就绪
```

## 2. 一人公司如何运行？（Solo Company Mode）

```
不能因为公司小就没有 CEO/财务/PM:

Solo: Human = Founder + CEO + Operator (一人兼多职, Human 层)
      + AI Departments (PM Agent/Developer Agent/QA Agent...)

Enterprise: Board → CEO → VP → Department → Employee (完整层级)

同一组织模型, 不允许两个系统:
  Company 层级深度可配置 (Solo 用扁平: Company→Roles; Enterprise 用嵌套: Company→Dept→Roles)
  角色集可裁剪 (Solo 无 Board/VP; 但 CEO 存在 — Human)
```

## 3. 权限模型（Default Deny，Role Permission 非 Agent Permission）

```
Authority 绑定 Role:
  Developer: 改代码 ✅ / 批准上线 ✗
  QA:        测试 ✅ / 修改生产代码 ✗
  PM:        调度 ✅ / 战略决策 ✗
  CEO:       批准重大决策 ✅ (唯一最终权)

规则:
  默认 deny (未声明 = 拒绝)
  高危 (生产/机密/成本) → 硬拒绝或必经 Approval
  越权 = 拒绝 + 审计
  执行权 != 审核权 (Role 冲突禁组合)
```

## 4. 项目如何管理？（Planning ≠ PM）

```
Analysis Agent (提供事实/数据/风险/建议) ≠ PM Agent (目标/计划/拆分/调度/进度)

Goal → Planning Agent → Task Graph → Role Matching → Execution → Review

方法支持 (不绑定单一):
  Scrum (Sprint/Backlog) / Kanban (列+WIP) / Waterfall (阶段门) / Hybrid / MVP
```

## 5. 扩展到未来跨行业 AI 集团

```
行业模板 (Phase 20): software_company → ecommerce/finance/manufacturing/media 公司
集团 (Phase 21+):    Global HQ → Region → Country → Company → Department

同一 Organization 模型递归嵌套 (Company.parent)
数据/权限/知识/经验四重隔离 (公司为单元)
```

## 6. 长期方向记录（不现在实现）

```
AI Organization Operating System — 未来可能替代/融合:
  ERP / CRM / HRM / Project Management / Knowledge Management / R&D Management

Phase 16 MVP 只做: AI Software Company (第一个行业模板)
```

## 7. Human Leadership

```
Human = Founder/CEO/Manager/Operator (不是普通用户)
AI 可决定: 计划内执行细节/技术选型建议
AI 可建议: 方向/风险/方案
必须 Human Approval: 产品方向/重大投资/架构变更/发布合并/成本增加
```
