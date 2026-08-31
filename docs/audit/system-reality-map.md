# AI Factory OS — 系统 Reality Map (以真实代码为准)

> 日期: 2026-08-31 | 方法: 只读真实代码/运行状态, 不依赖 docs(已确认过期)
> 结论: 后端 = 能力库(零件齐全); 产品 = 未组装完成(闭环断)

## 1. 规模基线

| 项 | 数值 | 说明 |
|----|------|------|
| 总提交 | 1340 | 未推送 326 |
| factory-console | 264 py / 110,199 行 | 主代码 |
| factory-core | 138 py / 33,814 行 | 核心域 |
| factory-exec | 52 py / 22,154 行 | 执行器 |
| factory-org | 18 py / 11,885 行 | 组织 |
| 前端 src | 183 文件 | React/TS |
| 后端测试 | 586 文件 | |
| 文档 | 828 md(159 审计) | **已过期** |
| 后端 API | 349 端点 | 前端只调 27 |

## 2. 后端能力库存(真实存在,有实体)

```
✅ 会话: conversation_os (464行) + conversation_quality (156行) + golden_suite (292行)
✅ 任务: task_tree (206行) + project_os (270行, Project/Sprint/Task/Replan/审批)
✅ 执行: professional_workflow (711行, 真实LLM+codex) + workflow_runner
✅ 运营: operational_state (249行) + control_tower (126行) + ops_projection
✅ 治理: governance_service (334行, 审批单链路)
✅ 上下文: context_runtime (417行) + context_intelligence (320行)
✅ LLM: llm_router (410行) + llm_control
✅ 智能: production_intelligence (495行) + optimization_engine (393行)
✅ 恢复: recovery_service + self_healing (370行) + promotion_service
✅ 学习: learning_engine_v2 (369行)
✅ 插件: plugin_kernel (308行)
✅ 统一契约: unified_contract (318行)
```

## 3. 前端实际消费(三栏 + 壳)

| 组件 | 调用的 API | 覆盖 |
|------|-----------|------|
| AfConversationCenter | conversations/create/get/sendMessage | 会话聊 |
| AfWorkspace | artifactContent/osProjectStatus/opsDrill | 看产物/状态 |
| AfContextNav | conversations/opsOverview/osProjects | 左栏导航 |
| AfMessageCard | osDecideApproval | 审批 |
| (旧) AfSidebar | createProject | 旧壳, 已不用 |

**前端只用 27/349 API。核心执行链(execute/decompose/runtime)前端未调用。**

## 4. 闭环断点(产品核心问题)

```
用户对话 → 后端理解 → 创建项目 → 拆任务 → 执行 → 结果回对话
   ❓?      ⚠️关键词     ❓?      ❓?   ❓?   ❓?
```

**全部环节 = 未验证。** 任何"能聊/能用"的结论都不可信——此前所有打勾都来自测试环境或过期文档, 非真实运行确认。

- `trigger_work`(conversation_os:307)存在 — 后端有"从对话触发工作"能力, 但**前端/API 未接**
- `runtime/execute` 存在 — 后端能全链路执行, 但**前端三栏未调用**
- golden_suite G1-G20 是**测试级**验证(真实 codex), 非产品级 UI 闭环
- 真实服务加载旧代码(幽灵进程) → 连"当前跑的是什么"都未确认

## 5. 会话理解现状(用户已否定的方向)

- INTENT_PATTERNS 纯正则关键词: "进展|有哪些|帮我做|目标用户是"
- 用户说"这软件给谁用" → 不命中 → DISCUSS(错)
- 用户说"现在干嘛呢" → 不命中"在做什么" → DISCUSS(错)
- **必须升级: LLM 理解语义(保留规则 fallback)**

## 6. 运行机制问题

- factory start 后端加载旧代码(幽灵进程/路径解析)
- 前端改源码需 rebuild(5180 服务 dist, 非 vite dev)
- `factory_console/`(别名) vs `factory-console/`(源码) 共存, editable finder 复杂

## 7. 真实优先修复清单

| 优先级 | 项 | 状态 |
|--------|-----|------|
| P0 | 会话理解: 关键词 → LLM | 待授权(架构变更) |
| P0 | 闭环: 对话→执行→结果回对话 | 断着 |
| P1 | 文档全面过期 | 需重建(以代码为准) |
| P1 | 运行机制(factory start 旧代码) | 未解决 |
| P1 | 工作区 2 未提交(会话修复) | 挂着 |
| P2 | 326 未推送 | 堆积 |
