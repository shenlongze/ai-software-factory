# S34-CORE-AUDIT — CLI + API + Web Conversation 核心链路真实性审计

> 日期: 2026-08-31 | 纯审计 (不修改业务代码) | 真实代码 + API + 存储证据

## 1. CLI → Service → API → Web 映射表

| 能力 | CLI 命令 | Service/Kernel | API | Web Conversation | 同一 Core? |
|------|---------|---------------|-----|------------------|-----------|
| 项目列表 | factory projectos | project_os.projects | /api/projects | project_list 工具 | ⚠️ 部分 |
| 项目创建 | projectos create | project_os.create_project | /api/projects (POST) | **org.cli.cmd_project_register (绕过 project_os)** | ❌ 不同路径 |
| 项目状态 | projectos status | project_os.project_status | /api/projects/{id} | project_status 工具 | ✅ |
| 计划 | projectos replan | project_os.replan | (plan API) | **plan_development (纯 LLM JSON)** | ❌ 不同路径 |
| 任务 | tasktree | TaskTree | /api/... | execute_plan → create_task | ⚠️ 部分 |
| 审批 | approval | ApprovalGate | /api/approvals | **无真实审批门** | ❌ 缺失 |
| Run | production | workflow_runner | /api/runs | chain_start | ✅ |
| 会话 | - | console_sessions | /api/sessions | send_message | ✅ |

## 2. Production Core 复用情况

```
✅ CLI (projectos/tasktree/production) → build_console_service / project_os (真实 Core)
✅ API → build_console_service (同一 Service)
❌ Web agent_loop:
   - create_project → org.cli.cmd_project_register (绕过 project_os 的 conv/req 绑定)
   - plan_development → 纯 LLM 生成 JSON (不调 project_os.replan / 不落 Plan Artifact)
   - approval → 无真实审批门 (AI 说"等待审批"但无持久化审批请求)
⚠️ execute_plan → service.create_task (部分真实, 但无 ApprovalGate)
```

**结论: Web Conversation 与 CLI/API 不是同一套完整逻辑链** — 部分工具走 Core,部分自实现。

## 3. Context Resolution 问题定位

```
✅ F1 已修: company scope 不猜项目 (S34-P0-FIX)
✅ F2 已修: create_project 真实注册 + ID 关联
⚠️ F2 残留: Web create_project 绕过 project_os → 无 Requirement 绑定,
           无 projects/{id}/ 目录初始化 (只有 org 记录)
```

## 4. Project Identity / Data Truth

```
✅ F3 已修: org = SSOT, project.json 对齐 (5 漂移→0)
⚠️ create_project 后 projects/{id}/ 目录未初始化 (飞机大战 P-b0adfaa6 无目录)
```

## 5. Plan / Requirement / Project 创建链路定位

```
真实用户输入 "我要做一个飞机大战的游戏app":
  ✅ intent 理解 + create_project (真实 org 注册 P-b0adfaa6)
  ✅ AI 确认需求
  ❌ 无 Requirement Discovery (idea → product_intent → PRD 未落盘)
  ❌ plan_development 未被调用 (AI 说"接下来规划"但没出计划)
  ❌ progress_card 空 (has_card=false)
  ❌ 无 backlog 任务
  ❌ 无 approval 请求
  ❌ 无 projects/P-b0adfaa6/ 目录 (Project Location 缺失)
  ❌ 无 Git 状态
```

**"计划已生成,等待审批" 实际 = AI 回复文本, 不是真实 Plan Artifact。**

## 6. 工具协议泄漏

```
✅ F4 已修: send_message 落库清洗 + migration
✅ 存储层 0 泄漏
```

## 7. P0/P1/P2 Matrix

```
P0:
  C1: Web plan_development 不落 Plan Artifact (计划不可见/不可追踪)
  C2: Web create_project 绕过 project_os (无 Requirement/目录/Git 初始化)
  C3: Web 无真实审批门 (plan 后 AI 说"等待审批"但无持久化)
  C4: 前端未渲染 progress-card (后端有 API, 前端从未拉取)
  C5: 无 Requirement Discovery 落盘 (idea→PRD 未持久化)
P1:
  C6: SSE reconnect / 30+ 轮 / budget 配置 / 多窗口
P2:
  C7: Search / Delete / cost dashboard
```

## 8. 推荐 Fix 顺序

```
1. C4 (最快): 前端渲染 progress-card → 计划可见
2. C1: plan_development 落 Plan Artifact (progress_card 已支持 save_from_plan, 需确认调用)
3. C2: Web create_project 改走 project_os.create_project (统一 Core)
4. C3: 真实审批门 (ApprovalGate + 持久化 + API)
5. C5: Requirement Discovery 落盘 (idea→PRD)
```

## 9. 为什么 CLI+API 做了这么多, Web 仍是半成品

```
根因: agent_loop 工具面是"会话助手"设计 (每个工具独立实现),
      没有强制走 project_os/service 层统一入口。
      plan_development/approval 是 LLM 文本模拟, 不是 Core 调用。
修复方向: 工具面收敛到 project_os/service 层 (One Execution Path)。
```
