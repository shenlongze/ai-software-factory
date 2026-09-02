# AGENTS.md — AI Factory 项目指令 (进入即读)

> 权威事实: 代码 + 运行时 + STEP10 Contract (人工批准 2026-09-02)。
> 历史文档 (docs/sprint*/design/adr/audit 大部分) = 历史证据, 不代表当前系统。
> 文档本身不得形成 Parallel Truth (见 docs/00-index/DOCUMENTATION_GOVERNANCE.md)。

## 0. 必读顺序
1. README.md (根)
2. docs/00-index/README.md
3. docs/00-index/CURRENT_SYSTEM_TRUTH.md ← 当前系统事实
4. docs/audit/product-system-baseline/STEP10_DOMAIN_FREEZE.md ← 冻结契约 (最高约束)
5. docs/audit/project-reality/PROJECT_PROGRESS_SNAPSHOT.md

## 1. 系统身份
AI Software Factory (pyproject 1.1.364) — 已拥有真实生产执行内核的 AI 软件开发平台。
运行时 = factory-console (Web 8011/会话/编排) + factory-org (领域 SSOT) + factory-exec (执行域)。
factory-core + factory-runtime = 独立模块 (不是生产 Core)。
真实成熟度 (STEP7 历史评估, 非总完成率): Reality 85.2 / Fulfillment 75.0 / Closure 49.8。

## 2. 已冻结架构约束 (不得违反, INV-001~015)
- 任一事实只能有一个 Domain SSOT (backlog TASK-* = Task SSOT; exec T00x = 执行记录域;
  execution_plan T-* = 历史冻结)
- 跨 Domain 只引用/映射/投影, 不形成第二个可独立修改的事实源
- 生产链: Plan → Task → Run → {ExecutionRecord, Artifact, Verification}
- Artifact/Verification 归属 Run/Record, Task 经 Run 间接
- Agent: Task → Capability Constraint → Router → Agent
- Model: Task/Agent → Model Policy → Model Selection (治理链; LLMRouter 消费 0 = 已知不修)
- Requirement 保留 → Product Intent/PRD → Plan 演进; PRD = 独立 Domain Entity (M3)

## 3. 状态语义 (冻结)
FAILED = 任务自身执行失败 (Task SSOT 事实) / BLOCKED = 依赖失败传播 (ExecState 派生投影)
CANCELLED = 用户取消 (Task SSOT) / UNKNOWN = recovery 无法证明 Run 结果 (重排队标注)
Ready = todo + 全依赖 done (派生) / 真并行未实现 (单任务串行, 不宣称并行)

## 4. 测试与验证铁律
- 测试: .venv/bin/python -m pytest; 全量 org+console 关键 ≈1049 (console 全量 5700+ 慢)
- 代码存在 ≠ 完成; 占位 UI 不可接受; 修 bug 必列全问题清单
- 实测 bug 必补回归测试; 用户实测 → confirm 才算 CLOSED
- 500/502 先查服务存活; 杀服务后须恢复环境

## 5. 执行纪律
- 架构/UI 工作: 先审计(零代码) → 计划 → 用户批准 → 才实施
- P0/P1 发现: 立即 STOP 报告, 等 FIX 指令; 修复完成不自动 commit
- 分阶段独立 commit; 用户指定只提交哪些文件时严格区分 (git add 指定文件)
- 本仓库关键文件 (controller/file/editor/block) 串行修改 — 注: 此为 MarkPad 项目锁,
  AI Factory 仓库遵循同纪律: 大改动先问

## 6. 当前已知 GAP (STEP11, 待人工批准 Fix)
B 类: FX-01 exec→backlog 引用 / FX-02 execution_plan 冻结 / FX-03 Req 引用 /
FX-04 Run 挂 Artifact / FX-05 Model Policy / FX-06 Agent 触发 / FX-07 分析落盘
D 类: FX-08 Verification SSOT 取证
FUTURE (不视为缺陷): PRD 实体 / Learning / Replan / Release (产品自标 M3/M4)

## 7. 禁止
- 不得把 FUTURE 当 CURRENT / UNKNOWN 当 FAIL / 注册当生产
- 不得重新设计 STEP10 冻结决策 (修改需人工批准)
- 不得在无指令时进入 Fix Sprint / 修改生产代码 / push
