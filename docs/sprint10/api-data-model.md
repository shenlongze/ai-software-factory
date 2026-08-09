# Sprint 10 — API & Data Model（Runtime Layer）

> 日期: 2026-08-10 | 状态: 设计 (ONLY DESIGN)
> 原则: CLI 与 UI 共用同一 Runtime API

## 1. 数据模型

```
Project
  id / name / idea / project_type (web|mobile|desktop) / tech (auto|flutter|react|vue)
  status (active|paused|completed|failed) / created_at
  workflow_id / progress / total_cost / total_duration

Stage (Workflow 阶段)
  id / workflow_id / name / role_id (pm|ui-designer|architect|developer|tester|devops)
  status: WAITING | RUNNING | SUCCESS | FAILED | APPROVAL_REQUIRED
  input_artifacts[] / output_artifacts[] / depends_on[]
  duration_s / cost_usd / started_at / completed_at

TimelineEvent (Agent Timeline 节点)
  id / project_id / type (user|stage|artifact|review|diff|error)
  stage_id? / agent_id? / message / status / payload
  created_at (SSE 推送顺序)

Artifact
  id / project_id / stage_id / type (product|ux_ui|design|code|test|release|...)
  status (validated|invalid|...) / ref / location / version
  metadata (契约载荷) / producer_role / created_at

ApprovalGate
  id / stage_id / workflow_id / status (pending|approved|rejected)
  reviewer / comment / requested_at / decided_at

ReviewComment
  gate_id / comment / round (第几轮反馈)

LLMSettings
  provider / model / configured (bool) — key 加密存储, 永不返回
```

## 2. Stage 状态机

```
WAITING → RUNNING → SUCCESS
                  ↘ FAILED (reason) → [重试]
                  ↘ APPROVAL_REQUIRED → (approve → SUCCESS | reject → rework → RUNNING)
```

## 3. API 需求

```
类别      方法  路径                            说明
─── ──── ─────────────────────────────── ─────────────────────────────
项目  POST /api/projects                  {idea, project_type, tech} → 建项目+启动 workflow
项目  GET  /api/projects                 项目列表 (name/status/progress/cost)
项目  GET  /api/projects/{id}            项目详情 (8 阶段链 + 统计)
项目  GET  /api/projects/{id}/monitor    阶段状态/成本/耗时 (轮询)
时间线 GET  /api/projects/{id}/timeline   Timeline 事件列表
实时  GET  /api/projects/{id}/events     SSE 事件推送 (Timeline 驱动)
产物  GET  /api/projects/{id}/artifacts  产物列表
产物  GET  /api/artifacts/{id}           产物详情 (metadata + renderer 提示)
产物  GET  /api/artifacts/{id}/content   渲染内容 (markdown/diff/wireframe JSON)
浏览器 GET  /api/projects/{id}/browser/url  沙箱运行 URL
浏览器 POST /api/projects/{id}/browser/start 启动沙箱静态服务器
审批  GET  /api/approval-gates           待审清单
审批  POST /api/approvals/{id}/approve   批准 (+comment)
审批  POST /api/approvals/{id}/reject    驳回 (+comment → 重做)
配置  GET/PUT /api/settings/llm          LLM 配置 (key 加密, 测试连接)
下载  GET  /api/projects/{id}/downloads  发布包列表 (zip)
下载  GET  /api/downloads/{artifact_id}  zip 下载
```

## 4. SSE 事件（Timeline 数据源）

```
event: stage_running   {stage_id, agent_id, name}
event: stage_success   {stage_id, artifact_id, duration, cost}
event: stage_failed    {stage_id, reason}
event: approval_required {stage_id, gate_id}
event: artifact_created {artifact_id, type}
```

## 5. 安全

```
沙箱: 所有 AI 代码/浏览器运行在沙箱 (localhost 独立端口)
Key: 加密存储 + 进程内注入; settings 永不返回 key
审批: 写路径仅 create/approve/reject/browser-start/settings-put
```
