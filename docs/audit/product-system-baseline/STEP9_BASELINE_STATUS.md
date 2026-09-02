# STEP 9 BASELINE STATUS — Completion Report (2026-09-02)

## Files Created (10)
1. MASTER_PRODUCT_TREE.md       — 产品能力树 (11 组, 每叶 M+证据)
2. MASTER_CAPABILITY_TREE.md    — 29 能力状态树 (CLOSED_LOOP/PRODUCTION/...)
3. MASTER_DOMAIN_SSOT_TREE.md   — Domain × SSOT/Projection + Task 三套 Truth 冻结
4. MASTER_LIFECYCLE_TREE.md     — 真实流程 + 断链 + Future 流程
5. MASTER_CONTROL_PLANE_TREE.md — Agent/LLM/Orchestration 控制面
6. PROJECT_STATE_TREE.md        — 项目状态入口 (REAL/CLOSED→UNKNOWN)
7. USER_REALITY_TREE.md         — 用户 CAN/CANNOT/WILL
8. SYSTEM_BOUNDARY.md           — 各包职责边界
9. BASELINE_MATRIX.md           — 30 行 Sprint 基础表
10. STEP9_BASELINE_STATUS.md    — 本文件

## Evidence Sources
docs/audit/fact-discovery/ (STEP 1-5) + docs/audit/capability-maturity/ (STEP 7)
+ docs/audit/project-reality/ (STEP 8) — 全部结论可追溯

## Trees Completed
Product ✅ / Capability ✅ / Domain-SSOT ✅ / Lifecycle ✅ / Control Plane ✅
+ State / User Reality / System Boundary / Baseline Matrix

## Task Domain Boundary Status (冻结)
- 三套 Truth 正式建模: backlog TASK-* (M4 主链) / execution_plan T-* (M3) /
  exec T00x (员工执行, records 100)
- 关系: backlog→execution_plan ABSENT / backlog→exec UNKNOWN / execution_plan→exec ABSENT
- 归属判断: 本 STEP 不裁决 (域边界契约未冻结 = UNKNOWN, 留给后续决策)

## SSOT Status
CONFIRMED: Session/Requirement/Plan/Task(backlog)/Run/Artifact(exec)/Audit/Agent/Skill/Provider/Project/Experience(写)
MULTIPLE: Task (3 套)
PROJECTION: ExecState/Intent/Verification(部分)
ABSENT: PRD/Learning/Release
UNKNOWN: Model Selection SSOT / Verification SSOT

## Lifecycle Status
主链 (会话→计划→任务→依赖→执行→聚合→审计) = PROVEN M4
需求产品链 (Req→PRD→Plan) = 断
产物链 (Exec→Artifact→Verify→Release) = 半开 (exec 域真实)

## Control Plane Status
Agent 控制 = M3 (选择+执行真实)
LLM 控制 = 调用 M4 / 选择 M1 (LLMRouter 消费 0)
Orchestration = HYBRID (执行动态/规划半动态/模型静态)

## Unknown Count: 12
factory-core 职责 / factory-runtime 职责 / factory.db / exec 角色触发 / Release runtime /
Learning runtime / Verification downstream / 独立模块义务 / WebUI 全量一致性 /
371 API 未触发 / Task 域归属 / Model Selection SSOT

## 计量
Code Changes = 0
Score Changes = 0 (沿用 STEP 7: Reality 85.2 / Fulfillment 75.0 / Closure 49.8 — 非总完成率)
Roadmap = 0
Fixes = 0

---

# 12 问回答 (STEP 9)

1. **AI Factory 现在到底是什么?**
   已拥有真实生产执行内核 (M4) 的 AI Software Factory; 产品智能层 (Req→PRD→Plan) 与控制面 (模型选择) 未闭环。

2. **真正生产可用能力?**
   会话/意图/计划/任务/依赖/执行/取消/恢复/聚合/审计/LLM 调用/项目管理/Agent 执行 (exec 域)。

3. **核心执行闭环?**
   用户会话 → plan_development → 批准 → backlog 任务+依赖 → ExecState 门控 → gateway 执行 →
   回写 → recover/reconcile → audit (E2E PROVEN)。

4. **用户现在能完成什么?**
   提开发意图 → 计划 → 批准 → 自动任务+执行+取消/重试/恢复 → 看结果/审计/进度 (项目/任务管理全程)。

5. **用户现在不能完成什么?**
   需求→PRD→工程→发布完整产品生命周期; 需求追踪; 模型选择; 产物回链; 学习。

6. **Product Intelligence 完成到哪里?**
   捕获 M2 (落盘) / 分析 M1 (不落盘) / 澄清 M1 / PRD M0 → 整体 M0-M2, 未形成产品链。

7. **Task Domain 几套 Truth?**
   三套: backlog TASK-* / execution_plan T-* / exec T00x (冻结记录, 不裁决)。

8. **谁是真 SSOT?**
   已冻结: Session/Plan/Task(backlog)/Run/Audit/Project 等; 未冻结: Task 域归属 / Model Selection / Verification。

9. **Agent 系统是生产还是注册?**
   混合: 执行域 5+ agents PRODUCTION (records 100); 角色 Agent 类模块 IMPLEMENTED (触发 UNKNOWN); 注册 ≠ 生产。

10. **LLM Control Plane 完成到哪里?**
    调用 M4 + Provider M3 + 观测 M3; 选择 M1 + 路由 M1 + fallback M0 → 调用真实, 控制面未闭环。

11. **哪些只是 Future?**
    Experience→Learning (M4) / Replan+变更回流 (M3) / Release (M3/M4) / PRD 深度化 (M3)。

12. **哪些仍不知道?**
    见 Unknown Count: factory-core 职责, factory.db, exec 角色触发, Release/Learning 运行时,
    Verification downstream, Task 域归属等 12 项。

---

## Final Statement (基于 STEP 1-8 事实)

> AI Factory 当前 = **执行内核真实且已闭环 (M4) 的 AI Software Factory** —
> 用户能从自然语言走到真实任务执行、依赖调度、失败恢复、取消与审计,
> 这条链有 E2E、持久化、执行记录与审计事件四重证据;
> 它还未形成的是"需求→产品→工程"的智能上游链 (PRD 实体缺失, 需求无下游引用)、
> 模型/Provider 的选择控制面 (LLMRouter 无生产消费者) 以及执行产物的任务级闭环 (Artifact/Verification M2);
> 上层学习/发布是产品自标的 M3/M4 里程碑, 当前不视为缺陷。
