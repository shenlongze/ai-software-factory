# S10-079 — resume_project 生产恢复路由修复

> 日期: 2026-08-17 | Production Pilot Blocker | "继续开发" → 真实执行链闭环

---

## 1. Reality Audit

**根因**: DEFAULT_ROUTES(router.py)缺 `resume_project` 映射——intent 识别成功(继续开发 → resume_project),但路由表无映射 → UnknownIntentError("未配置路由")。

**调用链**(审计):
```
"继续开发" → KeywordIntentParser("继续"规则) → resume_project
→ IntentRouter.route → DEFAULT_ROUTES 无 resume_project → ❌ UnknownIntentError
```

**为什么之前测试没发现**: execute_project/run_task 等意图有路由测试;resume_project 仅存在于 intent 识别层(S10-048 加入),从未有路由测试——意图可识别但不可执行的生产断链,正是用户要求禁止的架构缺陷。

**已有可复用能力**: execute_project action(S10-052)已完整实现:
- _locate_product 用 context.session.current_project
- Lifecycle 检查(EXECUTION_READY/DEVELOPMENT 可恢复)
- ExecutionOrchestrator: needs_resume → resume;否则全新执行
- 复用 execute_task 执行
- 已在 ConfirmationGate 敏感集合

## 2. Architecture

```
修复前: Intent → resume_project → ❌ no route → 用户看到 "未配置路由"
修复后: Intent → resume_project → execute_project (别名)
         → 显式 current_project 检查 (无 → 安全提示)
         → Lifecycle 检查 → Orchestrator.needs_resume → resume/execute
         → 任务执行 (execute_task) → 真实工程结果
```

## 3. 修改文件

- factory-console/session/router.py: DEFAULT_ROUTES + "resume_project": "execute_project"
- factory-console/session/actions.py: resume 场景要求显式 current_project(禁止扫描兜底猜项目;execute_project 保留既有扫描兜底)
- tests/console/test_s10_079_resume_project.py: 新增 11

## 4. 测试结果

```
新增 11 (变体解析/路由注册/无项目安全提示/确认门保留/执行链存在)
console+api: 4509 passed, 0 failed (10 个 execute_project 旧测试恢复)
全量: 11766 passed + 1 skipped, 0 failed (零回归)
```

## 5. 真实 CLI E2E (安装态)

```
> 我想做一个台球计分 App → discovery
> 台球记分麻烦 → discovery
> 台球爱好者 → discovery
> 计分和统计 → product_confirmation
> y → Product Created
> 生成工程计划 → 确认执行? (y/N) ✔ Project Ready For Engineering
> 继续开发 → ✔ 项目执行完成: 1787033910 — 2 任务完成 ✅
```

## 6. 真实生产动作 (明确区分)

```
route 命中:   ✅ resume_project → execute_project
action 调用:  ✅ execute_project (ExecutionOrchestrator)
task 创建/执行: ✅ 2 任务完成 (真实 orchestrator 执行链)
状态更新:     ✅ 项目执行完成 (execution_state 更新)
```

(注: 无 key 环境任务执行走确定性路径; 有 key 时走 LLM 增强 — 执行链本身真实存在)

## 7. Git

```
6eb384f feat(S10-079): resume_project production route
git clean ✅ | HEAD == origin/main ✅ | 已 push ✅
```

## 8. 生产点火链最终状态

```
Natural Language → Intent → Discovery → Product → Project Ready
→ "继续开发" → resume_project → execute_project → 任务执行 → 交付
```
