# Sprint 10 — Backlog

> 日期: 2026-08-10 | 状态: 设计待审核 | 避免重复建设: 全部复用 Sprint 1-9

## Backlog Tree

```
Sprint 10 — User Experience Layer
├── S10-001 Factory CLI (统一入口: init/start/status/project/workflow/artifact/review/approve/logs)
├── S10-002 API 扩展 (POST projects 一句话建项目 + monitor + settings/llm + downloads)
├── S10-003 Web 工作台 (Dashboard/Create/Workspace 8 阶段管道/Review/Monitor/Artifacts/Settings)
├── S10-004 一键启动 (factory start → 后端+前端+浏览器)
└── S10-005 用户旅程验收 (普通用户场景: 一句话→下载, 端到端真实)
```

## Backlog JSON

```json
{
  "sprint": "10",
  "goal": "AI Factory User Experience Layer: CLI 入口 + 产品 Web 工作台 (普通用户可用)",
  "backlog": [
    {
      "id": "S10-001",
      "title": "Factory CLI 统一入口",
      "priority": "P0",
      "dependency": "Sprint 9 (org CLI/approval CLI 已有)",
      "acceptance": "factory 命令全局可用 (init/start/status/project list/create/workflow list/artifact list/review/approve/reject/logs); 委托现有 CLI 函数零重写; 人类可读 + --json; key 进程内注入禁明文; 测试 ≥20",
      "estimated_complexity": "L"
    },
    {
      "id": "S10-002",
      "title": "API 扩展 (任务提交/监控/配置/下载)",
      "priority": "P0",
      "dependency": "S10-001",
      "acceptance": "POST /api/projects (idea+type+tech → 建项目+启动 workflow 后台); GET /api/projects/{id}/monitor (8 阶段 agent/status/cost/latency); GET/PUT /api/settings/llm (key 加密存储永不返回); GET /api/projects/{id}/downloads (zip); 后台执行防阻塞; 测试 ≥25",
      "estimated_complexity": "L"
    },
    {
      "id": "S10-003",
      "title": "Web 产品工作台",
      "priority": "P0",
      "dependency": "S10-002",
      "acceptance": "7 页面 (Dashboard/Create/Workspace 8 阶段管道/Review PRD+UI/Monitor/Artifacts/Settings); 中文极简风 (S10 设计 token); 轮询 2s 状态刷新; 审批按钮+意见进 gate; 复用 S9 Console 数据逻辑; vitest+tsc 绿",
      "estimated_complexity": "XL"
    },
    {
      "id": "S10-004",
      "title": "一键启动",
      "priority": "P1",
      "dependency": "S10-001/003",
      "acceptance": "factory start → 后端 8011 + 前端 5180 + 打开浏览器; 端口冲突处理 (自动换); 状态健康检查; 测试 ≥10",
      "estimated_complexity": "M"
    },
    {
      "id": "S10-005",
      "title": "用户旅程验收",
      "priority": "P1",
      "dependency": "S10-001~004",
      "acceptance": "普通用户场景端到端: 打开→输入一句话→PM 真实→PRD 审批→UX/UI→设计审批→Dev→Test→Release→下载 (真实 v4-pro); 记录全链; 报告",
      "estimated_complexity": "XL"
    }
  ]
}
```

## 复用清单（避免重复建设）

```
✅ Workflow/Artifact/Approval/Agent Executor (Sprint 1-9) — 全复用, 零重写
✅ org CLI 函数 — factory 包装委托
✅ Console 前端/后端 (S9-002/003) — 重构布局, 保留数据逻辑
✅ events 流 — logs/monitor 数据源
✅ S9 审批门 — review/approve/reject
✅ 沙箱/审批 — 生产保护
🆕 仅新增: 统一 CLI 壳 + 3 个 API 端点 + 产品布局 UI + 一键启动
```

## 执行顺序

```
S10-001 CLI → S10-002 API → S10-003 工作台 → S10-004 一键启动 → S10-005 用户旅程验收
每任务: 设计 → 编码 → 测试 → commit → push (Agile 小步)
```
