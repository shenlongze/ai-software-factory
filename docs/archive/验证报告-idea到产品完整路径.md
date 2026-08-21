# 验证报告 — 从 Idea 到产品的完整路径

> 验证方式: 实际运行 `factory demo markpad`,保留临时工厂根,逐一核对 SQLite 事件库、JSON 产物、任务、审批、经验记录
> 验证时间: 2026-08-11 | 环境: Python 3.12 + uv 重建 venv

---

## 一、结论先行

**生命周期编排链路真实可跑,且每一步都有持久化证据。** 从 Idea 到 Task 的 8 阶段链路(`idea → research → prd → [审批] → ui → [审批] → architecture → task`)实际执行成功,产出 **50 个审计事件 / 9 个 Artifacts / 3 个决策 / 2 个人工审批 / 1 个 Task / 3 条经验记录**,全部写入事件库(append-only SQLite)和 JSON 存储,可追溯、可复核。

**但要注意边界:"idea 到产品"实际止于"idea 到 Task 计划"。** 链路末端是任务拆解(Backlog),并未继续走 Development → Testing → Release(真正的产品构建)。且内容生成(research/prd/ui)用的是 **Mock Provider**,不是真实 LLM。

---

## 二、实际运行结果(逐阶段)

| # | 阶段 | 动作 | 产物 | 关键事件 |
|:-:|:-----|:-----|:-----|:---------|
| 1 | idea | advance | ART-001 product_idea | idea.created, lifecycle.started |
| 2 | research | generate | ART-002 research(内容) | generation.started/completed, provider.selected |
| 3 | prd | generate | ART-003 prd(内容) | generation.*, **approval.required** |
| 4 | approval(prd) | approve | APR-001 **approved** | approval.approved/granted, DEC-001 |
| 5 | ui | generate | ART-005 ui(内容) | generation.*, **approval.required** |
| 6 | approval(ui) | approve | APR-002 **approved** | approval.approved/granted |
| 7 | architecture | advance | ART-007/008 决策链 | DEC-002 |
| 8 | task | advance | T-001 BACKLOG + DEC-003 task_plan | lifecycle.completed |

**事件流时序正确**: seq=1 idea.created → ... → seq=47 lifecycle.completed → seq=48–50 经验记录。状态机(entered/completed)前后衔接无跳变。

---

## 三、证据核对(文档声称 vs 实测)

| 项目 | 文档声称 | 实测 | 说明 |
|:-----|:-------:|:----:|:-----|
| 事件总数 | 34 | **50** | 文档为 v1.0 基线,实测版已演进(多了经验记录等事件类型)——文档滞后,非缺陷 |
| Artifacts | 6 | **9** | 含 decision 链产物(ART-004/006/008/009),文档口径不同 |
| 人工审批 | 2 | **2** ✅ | APR-001(PRD) + APR-002(UI),状态机 approved,含 decided_by/comment 完整审计 |
| Task | 1 | **1** ✅ | T-001 BACKLOG, workflow=feature-delivery, project=markpad |
| 经验记录 | 2 | **2 + 1 审批经验** | 正向(PRD, rating 5)+ 负向(UI, rating 2)+ 审批经验 |
| 决策链 | architecture + task_plan | **3 决策** | DEC-001 product → DEC-002 architecture → DEC-003 task_plan,source_artifact 链完整 |

---

## 四、真实 vs Mock 判定(诚实评估)

### ✅ 真实逻辑(有真实实现和持久化)
- **生命周期状态机**: ProductLifecycleEngine,8 阶段 entered/completed 转换
- **审批门状态机**: approval.created → pending → required → approved/granted,mandatory 门阻塞推进
- **决策链**: product → architecture → task_plan,source_artifact 引用完整
- **任务落库**: Core TaskStore 写入 T-001
- **经验回环**: ExperienceStore 记录正向/负向 + 审批经验
- **事件溯源**: 全部写入 append-only SQLite,seq 连续,type/stage/action/result/payload 完整

### ⚠️ Mock(占位,非真实 AI)
- **内容生成**: research/prd/ui 的内容是 `demo/markpad.py` 里的**硬编码模板**(`_MOCK_CONTENT`),由 MockSelector + MockAdapter 返回,不是真实 LLM 输出。演示输出也自认:"Mock Provider 只生成内容,生命周期/审批/决策真实"。
- **人工审批**: "shenlongze approve" 是**脚本自动调用的**,不是真实人工点击(注释: demo 自动批准)。

### ❌ 未覆盖(链路边界)
- **Development → Testing → Release**: 演示止于 Task 创建,没有实际写代码、跑测试、发布。exec 执行引擎虽存在但文档自述"生产闭环 0%"。所以严格说这是 **"Idea → Task 计划"的完整闭环**,不是"到产品交付"的闭环。

---

## 五、结论与建议

**链路作为"生命周期管理平台"的验证是可信的**:状态机、审批、决策、任务、经验、事件溯源都是真实实现且相互咬合,不是画饼。这印证了项目的核心定位——它是管理 Agent/流程的平台,不是内容生成器。

**三个使用前提要清楚**:
1. 看 demo 时内容部分是模板,真实 LLM 生成需接真实 Provider Adapter;
2. 审批在 demo 里是自动批准,真实使用需接人工决策点;
3. "产品"一词在演示语境下指"可进入开发的任务计划",不含实际交付。

建议:若要做更硬核的验证,可以接一个真实 LLM Provider 重新跑一遍,并补充 Development→Testing 阶段(exec 引擎)的端到端用例——那才是"完整产品路径"的真正考验。
