# Sprint 10 — Web Console Architecture

> 日期: 2026-08-10 | 状态: 设计 (ONLY DESIGN)
> 目标: 普通用户产品工作台 (不是内部管理台)

## 1. 架构

```
浏览器 (React SPA, 端口 5180)
  ↓ /api
FastAPI 后端 (端口 8011) — 扩展:
  ├─ 现有: GET projects/workflows/artifacts/approval-gates + POST approve/reject
  ├─ 新增: POST projects (一句话建项目+启动 workflow)
  ├─ 新增: GET monitor (阶段实时状态/成本/耗时)
  ├─ 新增: GET/PUT settings (LLM 配置 — key 加密存储)
  └─ 新增: GET downloads (发布包下载)
  ↓
AI Factory Core (Workflow/Artifact/Approval/Agent Executor — 全复用)
```

## 2. 技术栈（现状复用）

```
前端: React + TS + Vite (已有 5180 基础设施, 改造现有 Console 而非重写)
后端: FastAPI (已有 8011 + org 挂载模式)
数据: ~/.factory (唯一数据根)
发布包: dist/ 目录 + 下载端点
```

## 3. 关键新能力

```
1. POST /api/projects:
   输入: {idea: "开发一个记账 App", project_type: web|mobile|desktop, tech: auto|flutter|react|vue}
   行为: 创建 Project → 建 AppLifecycleWorkflow → 启动 PM stage (后台执行)
   返回: project_id + workflow_id + 事件流起点

2. GET /api/projects/{id}/monitor:
   返回: 8 阶段链 (每阶段: agent/status/artifact_ref/cost/latency) — 从 events+execution 聚合
   前端: Build Monitor 轮询 (2s) 或 SSE

3. GET/PUT /api/settings/llm:
   返回: {provider, model, configured: bool} (key 永不返回)
   保存: key 加密写 ~/.factory/llm.key (本机 keychain 或对称加密文件)

4. GET /api/projects/{id}/downloads:
   返回: release artifacts (zip 下载)
```

## 4. 安全与隔离

```
沙箱: 所有代码生成在沙箱 (真实源零修改, 发布需审批门)
Key: 加密存储 + 进程内注入 (禁明文/日志/API 返回)
审批: 写路径仅 approve/reject/create (Permission Boundary 扩展)
```

## 5. 与 AI Factory Core 对接

```
启动 workflow: WorkflowLifecycle + AppLifecycleWorkflow 定义 (S8)
后台执行: 进程内 asyncio 任务 或 独立 worker (防阻塞 API)
状态查询: events (org.workflow.*) + ExecutionResult (cost/latency)
审批: org.approval (S9-001) — Console approve/reject 已有, 补 create
```
