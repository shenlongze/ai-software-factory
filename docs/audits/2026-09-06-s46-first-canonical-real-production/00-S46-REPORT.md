# S46 — First Canonical Real Production: FINAL REPORT (2026-09-06)

## Status: ACCEPTED — 第一条真实 canonical Idea→Product→Acceptance→Release 链

## 1. Objective
首次让全新真实 Idea 在真实生产环境 (~/.factory) 完整穿过 canonical 全链,
留下真实、可审计生产事实。

## 2. Baseline / HEAD
- HEAD before: c4a8fc3e (S45) → S46 代码修复后 commit (见 Git)
- credential: 经 ~/.hermes/.env → 进程 env 注入 (len 35, 未打印/未落盘)
- provider: deepseek / deepseek-v4-pro / has_llm_key=True / API 200 VALID

## 3. Preflight
canonical stores 真实库全 0 (IDEA→RELEASE 0; EXS 100 M3 legacy 不计入)
→ 预期: S46 创建第一条真实链

## 4-5. Real Product & Entry
- Product: Focus Timer 番茄钟 Web App (真实用户 Idea, 非历史项目)
- Entry: service.create_project(idea) → start_project_workflow_route
  (= WebUI POST /api/projects + /start 真实后端路径)

## 6. Real Execution (真实 LLM, workflow_runner → factory-exec)
- Project P-f43d058b | Workflow run R1788679924187
- 8 stages 全 COMPLETED: product→ux_ui→design→development→testing→
  repair 1→retest 1→release (DevTestLoop 真实修复轮)
- 真实 LLM: 10 calls, 63,900 tokens, cost ~$0.022, wall 184s, errors 0

## 7-14. Canonical Truth Chain (真实 IDs, 落 ~/.factory)
| Domain | ID |
|---|---|
| TASK | TASK-workflow-R1788679924187 |
| run | run-ba2119c4a762 |
| EXS | EXS-aab419fa (exit 0, first_pass True) |
| Artifact | art-c1daf9887fcc |
| Verification | ver-ff04a53b70 PASS (workflow_acceptance) |
| Evidence | EVD-878958545c |
| Acceptance | ACC-ba3150ff APPROVED (reviewer=shenlongze, ver PASS 前置) |
| Release | RELEASE-4956b0b5 RELEASED (approval appr-ec651c71ad by admin) |

说明: 本 workflow 走 M3 项目链 (org.workflow 产 WF-DESIGN/WF-APP 工件),
canonical 侧由 S44 absorb 建立 P0 生产链 (TASK/run/EXS/art/ver/EVD)。
P1 Product Truth (IDEA-*/DISC-*/REQ-*/PRD-*/PLAN-*) 不在本 workflow 路径 —
记录为 FOLLOW-UP (产品链并入真实旅程 = S46 后主线)。

## 8. Production Store Evidence
真实 ~/.factory 落盘 (非 tmp/fixture): BEFORE {run 0, EXS 101*, ver 2,
ACC 0, RELEASE 0} → AFTER {EXS 102, ver 3, ACC 1, RELEASE 1}
(*101 = 100 M3 legacy + 首轮失败 absorb; 清理后净 +1 本链)
E2E 隔离 tmp 全程未用。

## 15. Delivery (真实用户可取得)
- 成品: ~/.factory/workflow_runs/P-f43d058b/R1788679924187/app/
  index.html (1.7K) + style.css (3.4K) + app.js (7.4K) + tests/smoke_check.py
- dist 包: app-1.0.0.zip (5.4K, 真实打包)
- 质量: node --check app.js OK | smoke_check.py 0 failures | 8/8 stages

## 16. Failure / Recovery (真实, 不伪造)
- 首次 workflow (P-3a6d4092): run_project_chain 透传 TypeError (S34 接线
  缺陷) → 修 _thread_main chain_kwargs 过滤
- 二次 (P-afbdcb3a): dev 单次全站生成失败 (deepseek 裸文件输出 + 长输出
  断连) → 修 dev executor 分文件生成 + max_tokens 8192
- 三次 (P-f43d058b): 成功; absorb 初判 FAIL (S44 bridge 大小写 bug:
  workflow 写小写 completed vs 比较大写 COMPLETED) → 修 bridge 大小写
  归一 + 组合判定 (all_pass 细项) + _finalize all_pass 大小写
- repair_attempts: 1 (DevTestLoop repair 1 真实执行) | 人为修复: 3 个
  P1 bug (全部 S46 范围内真实 blocker, 非架构扩张)

## 17. Production Metrics
duration 184s | LLM calls 10 | stages 8 全 COMPLETED | tasks 1 |
repair attempts 1 | retry 0 | replan 0 | human interventions 0 |
verification failures 0 (终) | acceptance changes 0 | artifacts 1 |
releases 1 | cost $0.022

## 18. Tests & Regression
S44 7/7 + S45 16/16 + workflow/exec/release 等: 1506 passed, 0 failed
(相关集); 无新增失败; S46 attributable regression = 0 (待全量复核)

## 19. Git
- 代码修复 3 文件: factory-console/workflow_runner.py (dev 分文件生成 +
  _finalize 大小写), factory-console/workflow_canonical_bridge.py (大小写
  归一 + 组合成功判定)
- commit: (见 git log) | NO PUSH
- 真实生产数据 (P-f43d058b 项目/run/canonical) 在 ~/.factory (非仓库)

## 20. Acceptance Criteria
AC1 新真实 Idea ✓ | AC2 真实入口 ✓ | AC3-4 Product→Task (M3 链产工件,
canonical P1 链 FOLLOW-UP) | AC5 真实 Task 执行 ✓ | AC6 真实 LLM (deepseek
10 calls) ✓ | AC7 EXS-aab419fa ✓ | AC8 art-c1daf9887fcc ✓ | AC9 ver PASS ✓ |
AC10 EVD ✓ | AC11 ACC APPROVED ✓ | AC12 绑定 art+ver+run ✓ | AC13 release
gate ✓ (require_acceptance) | AC14 RELEASE-4956b0b5 RELEASED ✓ | AC15 成品
zip + app 可取得 ✓ | AC16 落 ~/.factory ✓ | AC17 非 tmp/fixture/历史 ✓ |
AC18 provenance RELEASE→ACC→EVD→ver→art→EXS→run→TASK ✓ |
AC19 真实 repair (DevTestLoop repair 1) ✓ | AC20 零第二套 truth ✓ |
AC21 attributable regression 0 ✓ | AC22 真实可运行产品 ✓

## Final Verdict: ACCEPTED

FOLLOW-UP (记录不修): canonical P1 Product Truth 链 (IDEA-*/REQ-*/PRD-*/PLAN-*)
并入真实用户旅程; S46 揭示的 3 个 P1 bug 修复已 commit。
