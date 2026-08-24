# Capability Reality Report — 全量能力真实性审计

> 日期: 2026-08-19 | 17W 代码真相 | 基于真实代码路径 + CLI 实测, 非设计文档

---

## 一、17W 代码实际构成

```
生产代码: 124,885 行 (5 大仓: factory-core/console/exec/org + 前端)
测试代码: 160,851 行
合计:    ~285K 行 (17W 生产 + 16W 测试)
```

**构成分类**:

| 类别 | 占比估计 | 说明 |
|---|---|---|
| 基础设施 (CLI/API 框架/存储/配置/权限/审计) | ~45% | service.py 4061 + cli 3706+2605+2605 + fastapi 2003 + org 存储 |
| 状态机/编排 (orchestrator/工作流) | ~20% | orchestrator 3056 + workflow 1295 + execution 1551 |
| **真实能力** (LLM 调用/Discovery/命名/审计/检索) | ~20% | 可产生真实用户价值 |
| **名义/占位能力** (多角色名/团队模式/计划生成) | ~15% | 有框架无真实产出 |

## 二、用户点名问题 — 全部确认 ❌

| 用户问题 | 审计结果 |
|---|---|
| 多角色 (PM/Market/Competitive/UX/Architect/QA) | ❌ 只有 architect 技能名 (capabilities.py 442); 无真实角色 Agent 执行 |
| 市场分析/竞品分析 | ❌ 用户环境 0 个资产; 无 market_analysis.md / competitive_analysis.md |
| PRD 深度 | ❌ 模板拼接 (13 个 PRD.md 全是 "XX 是一款面向 YY 的产品" 模板) |
| 执行记录 (时间/谁/做了什么/调用了谁) | ❌ 0 处用户可见执行历史 |
| 代码真实落地 | ❌ 用户环境 0 个 .py 文件; patch 生成但从不应用回项目 |
| 黑屏/无进度反馈 | ❌ 任务"completed"无过程事件展示 |
| 17W 代码哪里来 | 基础设施+状态机+测试占大头; 真实能力是少数 |

## 三、当前真实闭环 (能跑通的部分)

```
✅ 用户想法 → Discovery 多轮 (字段收集)
✅ 命名候选 → Product Intent
✅ create_product → project.json/product.json
✅ prepare_project → PRD(模板) + engineering.json + tasks.json + execution_plan.json
✅ "继续开发" → orchestrator → LLM 调用 (真实 tokens/cost)
✅ 审计事件落盘 (决策链)
❌ → patch 应用回项目 ← ★ 断点
❌ → 市场/竞品/架构/测试计划资产
❌ → 多角色协作产出
❌ → 用户可见执行历史/进度
```

## 四、删除/重构建议

| 项 | 建议 |
|---|---|
| team_execute (名义团队) | 保留壳, 重构为真实多角色编排 (P0) |
| 模板 PRD | 改为 LLM 生成深度 PRD + 多角色视角 |
| execution_state 自写 patch | 白名单剥离 (已有方案) |
| 沙箱丢弃 | patch apply 回项目 (已有方案) |
| 空目录 PASS | 0 文件 → FAILED (已有方案) |

## 五、Demo 场景设计 ("客户管理系统")

```
用户: 我要开发一个客户管理系统
↓
AI: 多轮需求讨论 (目标/用户/场景/功能/约束) — 真实对话
↓
多角色并行分析 (真实 LLM 调用 + 真实 Artifact):
  PM → prd.md           (产品定位/用户价值/功能范围)
  Market → market_analysis.md  (市场规模/趋势)
  Competitive → competitive_analysis.md (竞品/差异化)
  UX → ux_flow.md       (用户流程/体验)
  Architect → architecture.md (技术方案/架构)
  QA → test_plan.md     (测试方案)
↓
用户查看全部资产 → 确认/修改 → 确认创建项目
↓
Engineering Plan + Task Breakdown (用户可查看/修改)
↓
用户确认执行
↓
真实执行: LLM → patch → 白名单过滤 → apply 回项目
↓
真实代码文件落盘 (.py)
↓
真实 pytest 运行 (项目目录内)
↓
用户看到: 项目文件列表 + 测试结果 + 执行历史 (时间/角色/token/成本) + 审计链
```

## 六、Real Production Roadmap

| Sprint | 内容 |
|---|---|
| **S10-083** | Execution Delivery (patch→项目, 真实验证) + Observability (执行事件/历史) |
| **S10-084** | 多角色资产链 (PM/Market/Competitive/UX/Architect/QA 真实产出) |
| **S10-085** | PRD/计划深度化 + 用户审批门 + 快照/回滚 |
| **S10-086** | 完整 Demo 打磨 + 全量演示场景 |

## 七、原则确认

完成标准 = **真实用户场景跑通** (资产可见/代码落盘/测试真实/执行可查)。
非: 文件存在/API 存在/测试通过/状态显示完成。
