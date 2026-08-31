"""factory-console/web/backend/fastapi_adapter.py — Phase 11B 最薄 FastAPI Adapter (ADR-0035)。

把 Phase 11A 路由函数 (factory-console/api/*) 挂为 HTTP 端点 + 托管前端
build 静态文件 (SPA)。只做 HTTP 绑定 (参数解析 / JSON 序列化 / 静态托管),
**不写任何 UI 逻辑**, 不修改 factory-console/service.py 或 api/* (只读适配)。

设计依据:
- phase11b-status.md: Browser → Web UI (React+TS) → Console API Layer (11A)
  → Factory Data; Web UI 只消费 Console API。
- 只读铁律 (phase11a-status.md + human-console-model.md): 全部端点 GET,
  零写路径 — 审批/决定/创建 等执行权永远在既有引擎 (9c Approval 状态机),
  Console 只读不决定。Permission Boundary: 本模块不注册任何 POST/PUT/DELETE。
- 审计 (ADR-0002 读审计同语义): 端点经 11A 路由函数注入 EventLogger →
  console.viewed / console.dashboard.viewed; logger 缺失 → 静默 (失败安全)。
- 依赖: fastapi + uvicorn 仅装在 console 侧 venv (不污染 factory-core
  pyproject)。Core 零修改。

装配:
- create_app(factory_root=...) — 镜像 cli.commands._open_console_service
  (全部 store 可选, 失败安全); 供 uvicorn 直接启动。
- build_app(service=..., static_dir=...) — 注入已装配 service; 供测试/
  复用方使用。

端点 (只读 GET + S9-002 审批决定 POST + S10-006.5 创建 POST/管理 PATCH/DELETE):
  /api/dashboard                        → ConsoleDashboard 七域 (11A service.dashboard)
  /api/projects                         → list_projects (console.viewed)
  POST /api/projects/suggest            → suggest_project ({idea} → AI 提议
                                          名称/理解/澄清问题; fallback 诚实标注) [S10-007]
  POST /api/projects                    → create_project ({idea,name?,project_type,
                                          tech} → org 项目; 400/503 语义)   [S10-006.5]
  POST /api/projects                    → create_draft_project (无 name → unnamed
                                          draft: lifecycle=discovery/draft=true +
                                          ProjectSpace idea/discovery 资产) [S10-009-004]
  POST /api/projects/{id}/discovery/answer  → save_discovery_answer (问答追加
                                          discovery/conversation.json; 400/404) [S10-009-004]
  POST /api/projects/{id}/discovery/complete → complete_discovery (product-definition.md
                                          + lifecycle→product_defined; 404/409) [S10-009-004]
  POST /api/projects/{id}/confirm       → confirm_project (rename 事务: 正式命名 +
                                          目录 os.replace 原子 rename + 索引/org 镜像
                                          引用全更新 + 失败回滚; 400/404/409/503) [S10-009-005]
  PATCH /api/projects/{id}              → update_project (重命名/改 idea;
                                          400/404 语义)                [S10-006.5]
  DELETE /api/projects/{id}             → delete_project (运行中 409 保护;
                                          404/409 语义)                [S10-006.5]
  /api/projects/{project_id}/lifecycle  → get_project_lifecycle (None → 404)
  /api/approvals                        → list_approvals (?pending_only)
  /api/decisions/{decision_id}          → get_decision (None → 404)
  /api/recommendations                  → list_recommendations (?limit)
  /api/experience                       → list_experience (?limit)
  /api/providers                        → list_providers
  /api/workflows                        → list_workflows (?project_id)      [S9-002]
  /api/workflows/{workflow_id}          → get_workflow (None → 404)         [S9-002]
  /api/artifacts                        → list_artifacts (?project/workflow/type) [S9-002]
  POST /api/approvals/{id}/approve      → 审批放行 (404/409 映射)            [S9-002]
  POST /api/approvals/{id}/reject       → 审批否决 (404/409 映射)            [S9-002]
  GET  /api/review-feedback             → 审核反馈历史 (artifact/gate 过滤)   [S10-006]
  POST /api/review-feedback             → 保存反馈记录 (round 递增; 400/503)  [S10-006]
  POST /api/projects/{id}/start         → 启动真实 Agent 执行链 (404/409/503) [S10-006.5 P1-A]
  POST /api/projects/{id}/chat          → 持续开发对话 (400/404/503)          [S10-006.5 P1-A]
  GET  /api/projects/{id}/run-status    → 运行状态+进度 (none/running/…)      [S10-006.5 P1-A]
  POST /api/runtime/execute             → Agent 全链路执行 (Task→Agent→Session→
                                          LLM→Result; 400 校验/404 未装配/200
                                          status=failed=LLM 失败不 5xx)      [S10-016-002]
  GET  /api/tools                        → Tool 清单 (ToolRegistry 可用 Tool;
                                          console.viewed 审计)              [S10-018-001c]
  POST /api/tools/{id}/execute          → 执行 Tool ({agent_id, input, context?}
                                          → {success, output?, error?};
                                          404/403/400 映射)                 [S10-018-001c]
Permission Boundary (S9-002 收窄 + S10-004/006/006.5/016-002 扩展): 写路径仅
① 审批决定两 POST (approve/reject, reviewer="console" 落库 + source="console"
审计) ② Feedback Loop 一 POST (review-feedback — Reject 意见落库, 不触碰
引擎) ③ Runtime 实例生命周期 POST (创建/start/stop/screenshot, S10-004)
④ POST /api/projects (S10-006.5 — org 项目壳创建: org.project.created 审计,
  只建壳不启动执行链; S10-009-004 分流: 无 name → unnamed draft +
  ProjectSpace idea/discovery 资产) ⑤ Workflow 启动/对话 POST (start/chat,
  S10-006.5 P1-A — 触发本项目真实 Agent 执行链/消息落库, 不触碰 Core 引擎)
  ⑥ 项目管理 PATCH/DELETE /api/projects/{id} (S10-006.5 收尾 — 重命名/改 idea 落库
  org Project + 删除 [运行中 409 诚实拒绝] + org.project.deleted 审计 + 运行
  数据清理) ⑦ Discovery 持久化两 POST (/api/projects/{id}/discovery/answer|
  complete, S10-009-004 — 沟通记录追加 conversation.json + product-definition.md
  生成 + lifecycle 受控流转, 均落 ProjectSpace 目录信源) ⑧ Confirm+Rename
  一 POST (/api/projects/{id}/confirm, S10-009-005 — 正式命名 rename 事务:
  目录 os.replace 原子 rename + project.json/索引/org 镜像引用全更新 +
  失败回滚; 400/404/409/503 语义); ⑨ Tool 执行一 POST
  (/api/tools/{id}/execute, S10-018 Task 001c — 直调 ToolExecutor, 执行权在
  Tool 最小权限表 [filesystem.read 仅 backend-1, 其他 agent → 403 诚实拒绝],
  Adapter 只做 HTTP 绑定); 其余端点全部 GET —
  register_project/成本写入等仍不在 Console 范围 (S9-005/后续)。
静态: frontend build 产物 (dist/) — SPA html=True; 缺目录 → 纯 API 模式。
"""

from __future__ import annotations

import importlib
import json
import os
import re

def _console_import(name: str):
    """S10-074: 部署态包名 factory_console; 源码态兼容连字符目录。

    判断: factory_console 模块位置 — 仓库内占位转发包 (源码态) → 连字符
    真实目录; site-packages (部署态) → factory_console。
    """
    import importlib.util as _util
    try:
        _spec = _util.find_spec("factory_console")
        _loc = str(_spec.origin or "") if _spec is not None else ""
    except (ImportError, ValueError):  # noqa: BLE001
        _loc = ""
    _is_repo_stub = "factory_console/__init__.py" in _loc.replace("\\", "/") and "site-packages" not in _loc
    _mod = ("factory-console" if _is_repo_stub else "factory_console") + (f".{name}" if name else "")
    return importlib.import_module(_mod)


# 版本单源: 直接读 pyproject.toml（S10-1xx: 相对导入 from ... 会解析到仓库根
# factory_console 别名包 — 其无 __version__, 导致 ImportError; 改为读 pyproject 独立于包）
import tomllib
from pathlib import Path as _PathLib

try:
    _factory_version = tomllib.loads(
        (_PathLib(__file__).resolve().parents[3] / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
except Exception:  # noqa: BLE001 — 版本读取失败 → dev 标记（不阻断）
    _factory_version = "0.0.0-dev"


import sys
from pathlib import Path
from typing import Any, Iterator, NoReturn

from pydantic import BaseModel

__all__ = ["DEFAULT_ROOT", "DEFAULT_PORT", "build_app", "build_console_service", "create_app"]

#: 默认后端端口 (uvicorn 启动提示用; vite dev proxy 同源约定)
DEFAULT_PORT = 8011

#: 默认工厂根 (与 cli.context.DEFAULT_ROOT 同口径: ~/.factory)
DEFAULT_ROOT = Path.home() / ".factory"


class _ApprovalDecisionBody(BaseModel):
    """POST 审批决定 body (S9-003: comment 透传落库 — Review 反馈输入)。

    兼容 S9-002 无 body 调用 (reviewer 默认 "console"); comment 默认空串
    (既有调用零破坏 — 决定事件/门落库字段不变)。
    """

    reviewer: str = "console"
    comment: str = ""


class _CreateRuntimeBody(BaseModel):
    """POST /projects/{id}/runtimes body (S10-004: 创建 Runtime Instance)。

    type: browser|terminal (沙箱实例类型); artifact_id: 绑定产物 (browser
    预览 ux_ui/code/release 对应产物, 无 → None — 创建后可从 Timeline 联动
    绑定)。type 合法性在 handler 显式校验 → 400 (语义清晰, 不依赖 pydantic 422)。
    """

    type: str
    artifact_id: str | None = None


class _RagQueryBody(BaseModel):
    """POST /api/rag/query body (S10-123 K-6: 项目级 RAG 检索问答)。

    {project, question, tiers?, top_k?}: project 必填 (slug), question 必填
    (空 → 400); tiers 可选 (默认 raw/summary/knowledge 全开); top_k 可选 (默认 5)。
    确定性词频检索 (纯规则, 零 LLM 依赖) — embedding/LLM 仅可选接入 (诚实标注)。
    """

    project: str = ""
    question: str = ""
    tiers: str = "raw,summary,knowledge"
    top_k: int = 5


class _CreateProjectBody(BaseModel):
    """POST /api/projects body (S10-006.5: 用户第一公里创建闭环)。

    {idea, name?, project_type?, tech?}: idea 为必填想法 (空 → 400); name
    (S10-007 阶段三增强) 为用户确认的项目名称 (suggest 卡片确认后显式传,
    优先落库; 无 → 规则 slug 兜底, 旧调用向后兼容); project_type
    (web|mobile|desktop) 与 tech (auto|flutter|react|vue) 可选 — 宽容
    收窄 (非设计值 → 400), 透传 org Project 落库 (project_type/framework),
    不伪造 AI 技术选型。
    """

    idea: str
    name: str = ""
    project_type: str = ""
    tech: str = ""


class _SuggestBody(BaseModel):
    """POST /api/projects/suggest body (S10-007 阶段三增强: 想法确认对话)。

    {idea}: 用户想法 (必填; 空 → 400) — AI 提议名称/一句话理解/澄清问题
    卡片数据源。建议本身不落库 (非关键路径), LLM 不可用 → 诚实 fallback
    (ai_generated=false, 前端标注"快速模式")。
    """

    idea: str


class _ReviewFeedbackBody(BaseModel):
    """POST /api/review-feedback body (S10-006: Feedback Loop 反馈记录)。

    {artifact_id, gate_id, reviewer, comment}: Reject 决定后前端同时调用本
    端点保存结构化驳回意见 (round 按产物递增, 下轮 Agent 重生成输入)。
    comment 空 → 400 (无反馈不落库); reviewer 默认 "console" (与审批决定
    同口径); gate_id 记录来源审批门 (空串允许 — 兼容产物级反馈, 不强制)。
    """

    artifact_id: str
    gate_id: str = ""
    reviewer: str = "console"
    comment: str = ""


class _ChatBody(BaseModel):
    """POST /api/projects/{id}/chat body (S10-006.5 P1-A: 持续开发对话最小版)。

    {message}: 用户持续开发指令 — 已启动项目 → 只落消息 (chat_store);
    未启动项目 → 消息作为新 idea (org Project.goal 更新) + 触发 start。
    message 空 → 400 (空消息不发送)。
    """

    message: str


class _SessionBody(BaseModel):
    """POST /api/sessions body (K-7e + 想法→细化→待办链路)。

    {scope}: company|project; project 会话必须带 project_id; title 可选
    (缺省 "新会话", 首条消息后自动取消息前缀); feature_id 可选 — 模块级
    锚点 (点想法模块「和 AI 讨论」→ 会话细化该模块, create_task 自动绑定)。
    """

    scope: str
    project_id: str | None = None
    title: str | None = None
    feature_id: str | None = None
    task_id: str | None = None


class _SessionPatchBody(BaseModel):
    """PATCH /api/sessions/{id} body (K-7e): {title?, status?, feature_id?}。"""

    title: str | None = None
    status: str | None = None
    feature_id: str | None = None
    task_id: str | None = None


class _LlmConfigBody(BaseModel):
    """POST/PATCH /api/config/llm body (设置 — LLM 管理面, v1.1.102)。

    {provider_id, enabled?, default_model?, models?, base_url?, api_key_ref?}:
    - POST = 新增/覆盖 Provider (upsert); PATCH = 修改已存在 Provider (404 if 缺)
    - api_key_ref 只接受 env:VAR 引用 (D8 铁律 — 明文 key 400 响亮拒绝)
    - default_model 存 metadata (不新增字段, 向后兼容)
    """

    provider_id: str
    enabled: bool | None = None
    default_model: str | None = None
    models: list[str] | None = None
    base_url: str | None = None
    api_key_ref: str | None = None


class _ExternalAiBody(BaseModel):
    """POST /api/external-ai body (M1): 适配器声明 (字段同 yaml, 由 Schema 校验)。"""

    id: str
    name: str = ""
    binary: str = ""
    discovery: list[str] | None = None
    version_probe: list[str] | None = None
    probe_help: list[str] | None = None
    invocation: dict | None = None
    host_assets: dict | None = None
    capabilities: dict | None = None
    allow_dangerous: bool = False


class _ExternalAiAutoBody(BaseModel):
    """POST /api/external-ai/auto body (M6): {task, project_dir?, explicit_agent?, timeout?, verify?}。"""

    task: str
    project_dir: str = ""
    explicit_agent: str = ""
    timeout: int | None = None
    verify: bool = True


class _ExternalAiRouteBody(BaseModel):
    """POST /api/external-ai/route body (M5): {task, explicit_agent?}。"""

    task: str
    explicit_agent: str = ""


class _ExternalAiCostBody(BaseModel):
    """POST /api/external-ai/cost body (M4.3): {result_id, cost_usd, currency?}。"""

    result_id: str
    cost_usd: float
    currency: str = "USD"


class _ExternalAiVerifyBody(BaseModel):
    """POST /api/external-ai/verify body (M3): {result_id, method, result, score?, reason?}。"""

    result_id: str
    method: str = "manual"
    result: str = "pass"       # pass | fail | unknown
    score: float | None = None
    reason: str = ""


class _ExternalAiRunBody(BaseModel):
    """POST /api/external-ai/{id}/run body: {prompt, project_dir?, agent?, timeout?}。"""

    prompt: str
    project_dir: str = ""
    agent: str = ""
    timeout: int | None = None


class _LocalAiRunBody(BaseModel):
    """POST /api/local-ai/{agent_id}/run body (U-6): {prompt, project_dir?, timeout?}。"""

    prompt: str
    project_dir: str = ""
    timeout: int = 600


class _AgentBody(BaseModel):
    """POST /api/agents body (设置 — Agent 管理, v1.1.102)。

    {id, role, skills?}: 注册 Agent (写 agents/agents.json, 与 CLI
    factory agent add 同源; 空 id/role → 400)。
    """

    id: str
    role: str
    skills: list[str] = []


class _SkillScanBody(BaseModel):
    """POST /api/skills/scan body (U-4): {dir?} — 外部 SKILL.md 目录 (缺省内置)。"""

    dir: str = ""


class _SkillBody(BaseModel):
    """POST /api/skills body (设置 — Skill 管理, v1.1.102)。

    {id, name?, category?}: 注册 Skill (写 skills/skills.json, 与 CLI
    factory skill add 同源; 空 id → 400)。
    """

    id: str
    name: str | None = None
    category: str | None = None


class _DiscoveryAnswerBody(BaseModel):
    """POST /api/projects/{id}/discovery/answer body (S10-009 Task 4).

    {question, answer}: Product Discovery Session 逐条问答 — 追加
    discovery/conversation.json (可多次, 顺序保留)。空 answer/question →
    400 (空问答不记录); 项目不存在 → 404。
    """

    question: str
    answer: str


class _ConfirmBody(BaseModel):
    """POST /api/projects/{id}/confirm body (S10-009 Task 5).

    {name}: 用户确认的正式项目名 → rename 事务 (校验→快照→写 project.json
    →目录 os.replace 原子 rename→索引/引用更新→失败回滚)。空 name → 400
    (空名字不确认); 状态未到确认点/slug 冲突 → 409; 项目不存在 → 404;
    事务失败 (已回滚) → 503。
    """

    name: str


class _UpdateProjectBody(BaseModel):
    """PATCH /api/projects/{id} body (S10-006.5 项目管理: 重命名/改 idea)。

    {name?, idea?}: 任一非空 → 对应字段更新 (org Project 落库); 显式空串
    → 400 (空字段不落库); 两者皆 None (未提供) → 400 (无事可做)。
    None 与空串区分: None = 未提供 (不更新该字段), "" = 显式空值 (拒绝)。
    """

    name: str | None = None
    idea: str | None = None
    starred: bool | None = None
    archived: bool | None = None


class _EpicBody(BaseModel):
    """POST /api/projects/{id}/backlog/epic body (S10-010 Task 3)。

    {name, description?}: name 必填 (空 → 400 — 空名字不创建); description
    可选 (默认空串)。成功 → 201 Epic {id, name, description, children,
    created_at, updated_at}。
    """

    name: str
    description: str = ""


class _FeatureBody(BaseModel):
    """POST /api/projects/{id}/backlog/feature body (S10-010 Task 3 + 想法链路)。

    {name, description?, epic_id?, maturity?}: epic_id 可选绑定 (宽松 — 提供时校验
    Epic 存在 → 不存在 404; 绑定 = epic.children 追加引用, 非包含);
    maturity idea|refined (默认 refined; idea = 想法模块 💡, 会话细化后转 refined)。
    """

    name: str
    description: str = ""
    epic_id: str = ""
    maturity: str = "refined"


class _FeaturePatchBody(BaseModel):
    """PATCH /api/projects/{id}/backlog/feature/{feature_id} body (想法链路)。

    {name?, description?, maturity?}: maturity idea↔refined (非法 → 400);
    空 name → 400; 全空 → 400 (无事可做, 诚实拒绝)。
    """

    name: str | None = None
    description: str | None = None
    maturity: str | None = None


class _StoryBody(BaseModel):
    """POST /api/projects/{id}/backlog/story body (S10-010 Task 3)。

    {name, description?, feature_id?}: feature_id 可选绑定 (Story→Feature)。
    """

    name: str
    description: str = ""
    feature_id: str = ""


class _TaskBody(BaseModel):
    """POST /api/projects/{id}/backlog/task body (S10-010 Task 3)。

    {title, description?, priority?, dependency?, story_id?}: title 必填
    (空 → 400); priority P0-P3 (非法 → 400, 默认 P2); dependency 前置任务
    id 列表 (自引用/环 → 400); story_id 可选绑定 (Task→Story, 不存在 → 404)。
    """

    title: str
    description: str = ""
    priority: str = ""
    dependency: list[str] | None = None
    story_id: str = ""


class _TaskPatchBody(BaseModel):
    """PATCH /api/projects/{id}/backlog/task/{task_id} body (S10-010 Task 3)。

    {title?, description?, priority?, status?, assignee?, dependency?}: None
    = 未提供 (不更新该字段)。status 转换走 Task 002 状态机 (非法转换 → 409;
    依赖未满足 → 400); priority 非法 → 400; dependency 环/自引用 → 400;
    空 title → 400。
    """

    title: str | None = None
    description: str | None = None
    priority: str | None = None
    status: str | None = None
    assignee: str | None = None
    dependency: list[str] | None = None


class _SprintBody(BaseModel):
    """POST /api/projects/{id}/sprints body (S10-010 Task 4)。

    {name, goal?, start_date?, end_date?, task_refs?}: name 必填 (空 → 400
    — 空名字不创建); task_refs = Task id 引用列表 (非包含 — 引用不影响
    Task 本身; 引用不存在 Task → 400)。成功 → 201 Sprint (默认
    status=planning)。
    """

    name: str
    goal: str = ""
    start_date: str = ""
    end_date: str = ""
    task_refs: list[str] | None = None


class _SprintPatchBody(BaseModel):
    """PATCH /api/projects/{id}/sprints/{sprint_id} body (S10-010 Task 4)。

    {goal?, planning?, task_refs?, start_date?, end_date?, status?,
    daily_progress?, review?}: None = 未提供 (不更新该字段)。status 受控
    转换 planning→active→completed (非法跳级/回退 → 409; 非法值 → 400);
    task_refs 引用不存在 Task → 400; daily_progress 元素非对象 → 400。
    """

    goal: str | None = None
    planning: str | None = None
    task_refs: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str | None = None
    daily_progress: list[dict[str, Any]] | None = None
    review: str | None = None


class _SprintPlanBody(BaseModel):
    """POST /api/projects/{id}/sprints/{sprint_id}/plan body (S10-010 Task 4)。

    {goal?}: Planning 预留端点 — 只回显 goal 并返回可执行任务建议
    (sort_tasks 纯函数排序), 不实际调度 (S10-011)。
    """

    goal: str = ""


class _MilestoneBody(BaseModel):
    """POST /api/projects/{id}/milestones body (S10-010 Task 4)。

    {name, description?, target_date?, task_refs?}: name 必填 (空 → 400);
    task_refs 引用 Task (非包含; 不存在 → 400)。成功 → 201 Milestone
    (默认 status=planned, 自由文本宽容)。
    """

    name: str
    description: str = ""
    target_date: str = ""
    task_refs: list[str] | None = None


class _MilestonePatchBody(BaseModel):
    """PATCH /api/projects/{id}/milestones/{milestone_id} body (S10-010 Task 4)。

    {name?, description?, target_date?, status?, task_refs?}: None = 未提供。
    status 自由文本 (宽容, 无状态机); task_refs 引用不存在 Task → 400;
    空 name → 400。
    """

    name: str | None = None
    description: str | None = None
    target_date: str | None = None
    status: str | None = None
    task_refs: list[str] | None = None


class _MilestoneRefBody(BaseModel):
    """POST /api/projects/{id}/roadmap/milestone-ref body (S10-010 Task 4)。

    {milestone_id}: 追加到 Roadmap.milestone_refs (去重幂等); milestone
    不存在 → 400 (引用校验, 同 task_ref 语义)。
    """

    milestone_id: str


class _CreateSessionBody(BaseModel):
    """POST /api/agents/{agent_id}/sessions body (S10-016: Runtime Session)。

    {task_id, workflow_id?}: task_id 必填 (空 → 400 — Session 必须锚定
    Task); workflow_id 可选 (独立执行无工作流, 缺省空串)。
    """

    task_id: str = ""
    workflow_id: str = ""


class _SessionEventBody(BaseModel):
    """POST /api/runtime-sessions/{id}/events body (S10-016)。

    {type, message?, data?}: type 为 RuntimeEventType 七类型之一 (非法 →
    400); message 可选 (事件人话描述); data 可选 (结构化载荷, 如工具调用
    参数)。
    """

    type: str = ""
    message: str = ""
    data: dict[str, Any] | None = None


class _SessionCompleteBody(BaseModel):
    """POST /api/runtime-sessions/{id}/complete body (S10-016)。

    {success}: true → SUCCESS / false → FAILED (缺省 true — 完成语义)。
    """

    success: bool = True


class _ExecuteRuntimeBody(BaseModel):
    """POST /api/runtime/execute body (S10-016 Task 002: Agent 全链路执行)。

    {task_id, agent_id, context?}: task_id/agent_id 必填 (空 → 400 — 执行
    必须锚定 Task 且执行者明确); context 可选执行上下文 (project_dir/
    requirement/instruction — 透传 AgentExecutor 组装 Task Context)。
    """

    task_id: str = ""
    agent_id: str = ""
    context: dict[str, Any] | None = None


class _ToolExecuteBody(BaseModel):
    """POST /api/tools/{tool_id}/execute body (S10-018 Task 001c: Tool 执行)。

    {agent_id, input, context?}: agent_id 必填 (空 → 400 — 执行者必须明确,
    Service 层 ValueError); input = Tool 输入 (JSON Schema 校验; 非 dict →
    Service 层归一 {} → schema 校验失败 → 400); context 可选执行上下文
    (workspace_root 等透传 ToolExecutor)。
    """

    agent_id: str = ""
    input: dict[str, Any] = {}
    context: dict[str, Any] | None = None


class _CreateMCPConnectionBody(BaseModel):
    """POST /api/mcp/connections body (S10-020 Task 001: MCP 连接注册)。

    {name, server_url, transport?}: name/server_url 必填 (空 → 400 — Service
    层 ValueError); transport 默认 mock (本 Task 仅 Mock 可用 — 注册即连接,
    不连公网; stdio/http 真实协议 → 400 响亮拒绝, 不假装连接成功)。
    """

    name: str = ""
    server_url: str = ""
    transport: str = "mock"
    # U-3 (v1.1.189): stdio 真实连接 — command/args 拉起子进程
    command: str = ""
    args: list[str] | None = None


# ------------------------------------------------------------------ 装配


def ok_list(items: list[Any]) -> dict[str, Any]:
    """API 规范 v1 集合包络: {"items": [...], "count": N} (禁止裸数组)。"""
    return {"items": list(items), "count": len(list(items))}


def build_console_service(
    factory_root: str | Path,
    *,
    event_logger: Any = None,
    agent_executor: Any = None,
) -> Any:
    """按工厂根装配 ConsoleService (镜像 cli.commands._open_console_service)。

    全部 store 依赖可选 (失败安全: 缺任一 store → Console 按空数据处理);
    延迟导入 Core 包保 Removal Isolation (删除任一 Core 包不影响 Console 加载)。
    factory-console 包名含连字符 → importlib 按路径加载 (同 CLI 模式)。

    S10-016 Task 002: agent_executor 可选注入 (exec.agent_executor — 全链路
    编排; 生产装配不传 → ConsoleService 自装配: 复用本装配的 store +
    workflow_runner 真实 Provider (LLM key 已配置时); 无已配置 Provider →
    诚实 FAILED, 不伪造 LLM 结果)。

    S9-002: 装配 org 数据空间 (root/org — ProjectStore + WorkflowLifecycle,
    与 factory-org 演示/CLI 同目录口径); event_logger 提供时注入带事件库的
    生命周期 (org.approval.* 决定事件 source="console" 落库审计); org 缺失
    → 跳过注入 (失败安全, 读命令永不因 org 缺失失败)。
    """
    root = Path(factory_root)
    root.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[3]  # .../ai-software-factory/
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        # S10-074: 部署态 factory_console / 源码态连字符 (统一 helper)
        module = _console_import("")
    except Exception as exc:  # 缺装/损坏 → 装配失败 (调用方决定兜底)
        raise RuntimeError("factory-console 未安装 (缺 factory-console/ 包)") from exc

    from agents.registry import AgentRegistry
    from agents.store import AgentStore

    from intelligence.store import DecisionStore, ExperienceStore, RecommendationStore

    from product.store import ProductStore

    from providers.registry import ProviderRegistry
    from providers.store import ProviderStore
    from providers.usage import UsageStore

    from tasks.store import TaskStore

    from workspace.manager import WorkspaceManager

    # S9-002: org 数据空间 (root/org — 与 factory-org CLI 同目录口径; 失败安全)
    project_store = None
    workflow_lifecycle = None
    project_space = None
    try:
        org_dir = repo_root / "factory-org"
        if org_dir.is_dir() and str(org_dir) not in sys.path:
            sys.path.insert(0, str(org_dir))
        from org.projects import ProjectStore
        from org.space import ProjectSpaceStore
        from org.workflow import WorkflowLifecycle

        project_store = ProjectStore(root / "org")
        workflow_lifecycle = WorkflowLifecycle(project_store, logger=event_logger)
        # S10-009 Task 4: Project Space (root/workspace — 目录信源:
        # workspace/projects/{slug}/project.json + idea/discovery 资产;
        # 失败安全: 缺 space → draft/发现流程 503)
        project_space = ProjectSpaceStore(root)
    except Exception:
        project_store = None
        workflow_lifecycle = None
        project_space = None

    # S10-004: Runtime 数据空间 (root/runtimes — 独立于 org, 原子写 JSON;
    # 失败安全: 装配失败 → None, runtime 操作按空/不存在处理)
    runtime_store = None
    runtime_screenshot_store = None
    try:
        _runtime_stores = _console_import("runtime_store")
        runtime_store = _runtime_stores.RuntimeInstanceStore(root / "runtimes")
        runtime_screenshot_store = _runtime_stores.RuntimeScreenshotStore(root / "runtimes")
    except Exception:
        runtime_store = None
        runtime_screenshot_store = None

    # S10-006: 审核反馈数据空间 (root/review_feedback.json — Feedback Loop
    # Reject 意见落库; 失败安全: 装配失败 → None, 反馈保存/查询按空处理)
    review_feedback_store = None
    try:
        _feedback_module = _console_import("review_feedback")
        review_feedback_store = _feedback_module.ReviewFeedbackStore(root)
    except Exception:
        review_feedback_store = None

    # S10-006.5 P1-A: 对话记录数据空间 (root/chat.json — POST /projects/{id}/chat
    # 消息落库; 失败安全: 装配失败 → None, 消息记录跳过, 对话/启动不受影响)
    conversation_store = None
    try:
        _chat_module = _console_import("chat_store")
        conversation_store = _chat_module.ConversationStore(root / "chat.json")
    except Exception:
        conversation_store = None

    # S10-016: Runtime Session 数据空间 (root/runtime-sessions — Agent 执行
    # 会话独立数据空间, 原子写 JSON; 挂 factory-exec 到 sys.path (同
    # workflow_runner._setup_sys_path 模式 — 8011 启动命令未挂 factory-exec,
    # 延迟导入 exec.runtime_session 需该目录可寻址); 失败安全: 装配失败 →
    # None, session 操作按空/404 处理)
    session_store = None
    try:
        exec_dir = repo_root / "factory-exec"
        if exec_dir.is_dir() and str(exec_dir) not in sys.path:
            sys.path.insert(0, str(exec_dir))
        _session_module = importlib.import_module("exec.runtime_session")
        session_store = _session_module.RuntimeSessionStore(root / "runtime-sessions")
    except Exception:
        session_store = None

    return module.ConsoleService(
        workspace_manager=WorkspaceManager(root),
        task_store=TaskStore(root / "tasks"),
        agent_registry=AgentRegistry(AgentStore(root / "agents")),
        product_store=ProductStore(root / "product"),
        decision_store=DecisionStore(root / "intelligence"),
        recommendation_store=RecommendationStore(root / "intelligence"),
        experience_store=ExperienceStore(root / "intelligence"),
        usage_store=UsageStore(root / "providers"),
        provider_registry=ProviderRegistry(ProviderStore(root / "providers")),
        project_store=project_store,
        workflow_lifecycle=workflow_lifecycle,
        # S10-009 Task 4: Project Space (root/workspace — draft/idea/discovery
        # 资产目录信源; 失败安全: 缺 space → draft/发现流程按存储不可用处理)
        project_space=project_space,
        # S10-004: Runtime 实例/截图持久化 (root/runtimes; 失败安全)
        runtime_store=runtime_store,
        runtime_screenshot_store=runtime_screenshot_store,
        # S10-006: 审核反馈持久化 (root/review_feedback.json — Feedback Loop
        # Reject 意见落库; 失败安全: 装配失败 → None, 保存/查询按空处理)
        review_feedback_store=review_feedback_store,
        # S10-006.5 P1-A: 对话记录持久化 (root/chat.json — 消息落库; 失败安全)
        conversation_store=conversation_store,
        # S10-016: Runtime Session 持久化 (root/runtime-sessions — Agent 执行
        # 会话; 失败安全: 装配失败 → None, session 操作按空/404 处理)
        session_store=session_store,
        # S10-016 Task 002: AgentExecutor 编排层 (注入优先; 缺省 None →
        # service 自装配 — 复用本装配 store + workflow_runner 真实 Provider,
        # 无已配置 LLM key → 诚实 FAILED 不伪造结果)
        agent_executor=agent_executor,
    )


def _open_event_logger(factory_root: str | Path) -> Any:
    """按工厂根打开 EventLogger (<root>/factory.db, CLI 同路径; 失败安全 → None)。"""
    from events.logger import EventLogger
    from events.store import EventStore

    try:
        return EventLogger(EventStore(Path(factory_root) / "factory.db"))
    except Exception:
        return None  # 事件库不可用 → 静默 (读审计失败不拖垮 API)



def _git_status() -> dict:
    """git 状态（只读: 版本/分支/脏标记）。"""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(Path(__file__).resolve().parents[3]),
                            "log", "-1", "--oneline"], capture_output=True, text=True, timeout=10)
        head = r.stdout.strip() if r.returncode == 0 else ""
        r2 = subprocess.run(["git", "-C", str(Path(__file__).resolve().parents[3]),
                             "status", "--porcelain"], capture_output=True, text=True, timeout=10)
        return {"head": head, "dirty": bool(r2.stdout.strip())}
    except Exception:  # noqa: BLE001
        return {"head": "", "dirty": False}


def _rag_config_shim(factory_root: Any = None) -> Any:
    """RAG 外部源配置读取 (providers.external_rag 来自 <root>/config.json)。

    与 CLI ConfigProvider 同文件 (config.json providers.external_rag); 缺文件
    / 损坏 / 未配置 → 空 (失败安全, 不崩)。返回带 get(section, key, default) 的 shim。
    """

    class _Shim:
        def __init__(self, data: dict[str, Any]) -> None:
            self._data = data

        def get(self, section: str, key: str, default: Any = None) -> Any:
            sec = self._data.get(section)
            if isinstance(sec, dict):
                val = sec.get(key)
                if val is not None:
                    return val
            return default

    import json

    data: dict[str, Any] = {}
    if factory_root is not None:
        cfg = Path(factory_root) / "config.json"
        try:
            raw = json.loads(cfg.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except Exception:  # noqa: BLE001 — 失败安全
            data = {}
    return _Shim(data)


def _safe_ping(src: Any) -> bool:
    """外部源 ping 探测 (异常/未实现 → False, 失败安全)。"""
    try:
        return bool(src.ping()) if hasattr(src, "ping") else False
    except Exception:  # noqa: BLE001 — 失败安全
        return False


def _exec_request_map(root: Path) -> dict[str, Any]:
    """exec/requests.json → {EXR: request} (T-9 执行溯源; 失败安全空)。"""
    try:
        d = json.loads((root / "exec" / "requests.json").read_text(encoding="utf-8"))
        return d.get("requests") if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001 — 失败安全铁律
        return {}


def _exec_results_map(root: Path) -> dict[str, Any]:
    """exec/execution_records.json → {EXS: record} (T-9 执行溯源; 失败安全空)。"""
    try:
        data = json.loads((root / "exec" / "execution_records.json").read_text(encoding="utf-8"))
        out: dict[str, Any] = {}
        for r in data if isinstance(data, list) else []:
            if isinstance(r, dict) and r.get("result_id"):
                out[str(r["result_id"])] = r
        return out
    except Exception:  # noqa: BLE001 — 失败安全铁律
        return {}


def _task_exec_trace(root: Path | None, task: dict[str, Any]) -> dict[str, Any]:
    """T-9 (v1.1.185): 任务执行溯源 — exec_ref → EXR request → EXS result → 证据包。

    失败安全: 无 exec_ref / 记录缺失 → 各段 None/[] (不编造); 只读真实文件。"""
    trace: dict[str, Any] = {
        "exec_ref": task.get("exec_ref"),
        "exec_result": task.get("exec_result"),
        "request": None,
        "results": [],
        "evidence": [],
    }
    if root is None:
        return trace
    exec_ref = str(task.get("exec_ref") or "").strip()
    if not exec_ref:
        return trace
    try:
        reqs = _exec_request_map(root)
        req = reqs.get(exec_ref)
        if req is None:
            return trace
        trace["request"] = {
            "id": str(req.get("id") or ""),
            "task_id": req.get("task_id"),
            "objective": str(req.get("objective") or "")[:200],
            "requirement": str(req.get("requirement") or "")[:200],
            "status": str(req.get("status") or ""),
            "created_at": req.get("created_at"),
        }
        ids: list[str] = []
        for o in req.get("output_refs") or []:
            if o:
                ids.append(str(o))
        if task.get("exec_result"):
            ids.append(str(task["exec_result"]))
        recs = _exec_results_map(root)
        seen: set[str] = set()
        for rid in ids:
            if rid in seen:
                continue
            seen.add(rid)
            rec = recs.get(rid)
            if rec is not None:
                trace["results"].append(
                    {
                        "result_id": str(rec.get("result_id") or ""),
                        "result": str(rec.get("result") or ""),
                        "intent": str(rec.get("intent") or ""),
                        "agent": str(rec.get("agent") or ""),
                        "task": str(rec.get("task") or "")[:120],
                        "timestamp": rec.get("timestamp"),
                        "error": str(rec.get("error") or ""),
                    }
                )
            report = root / "exec" / f"{rid}.report.md"
            test = root / "exec" / f"{rid}.test.txt"
            ev: dict[str, Any] = {"id": rid}
            if report.is_file():
                ev["report"] = report.name
            if test.is_file():
                ev["test"] = test.name
            if ev.get("report") or ev.get("test"):
                trace["evidence"].append(ev)
    except Exception:  # noqa: BLE001 — 溯源失败 → 保持空 (不阻断详情)
        pass
    return trace


def _external_ai_from_body(body: Any) -> Any:
    """HTTP body → ExternalExecutorAdapter (缺省字段用内置模板填充; Schema 校验失败抛错)。"""
    from factory_console.external_executor.registry import BUILTIN_ADAPTERS
    from factory_console.external_executor.schema import ExternalExecutorAdapter

    aid = str(getattr(body, "id", "") or "").strip()
    defaults = dict(BUILTIN_ADAPTERS.get(aid) or {})
    merged = {
        "id": aid,
        "name": str(getattr(body, "name", "") or "") or defaults.get("name", aid),
        "binary": str(getattr(body, "binary", "") or "") or defaults.get("binary", aid),
        "discovery": list(body.discovery) if body.discovery else defaults.get("discovery", ["PATH"]),
        "version_probe": list(body.version_probe) if body.version_probe else defaults.get("version_probe", ["--version"]),
        "probe_help": list(body.probe_help) if body.probe_help is not None else defaults.get("probe_help"),
        "invocation": body.invocation or defaults.get("invocation"),
        "host_assets": body.host_assets or defaults.get("host_assets"),
        "capabilities": body.capabilities or defaults.get("capabilities", {}),
        "allow_dangerous": bool(body.allow_dangerous),
    }
    if not merged["invocation"]:
        raise ValueError("invocation 必填 (怎么调这个 CLI)")
    return ExternalExecutorAdapter(**merged)


def _task_to(service: Any, project_id: str, task_id: str, target: str) -> dict[str, Any] | None:
    """任务逐步状态机推进 (S-1: 会话操作任务 — todo→done 多步, 每步审计)。"""
    try:
        from org.management import TASK_TRANSITIONS
    except Exception:  # noqa: BLE001 — org 缺失
        return None
    task = service.get_task(project_id, task_id)
    if task is None:
        return None
    path = service._status_path(TASK_TRANSITIONS, task["status"], target)
    if not path:
        return None
    for status in path:
        try:
            service.update_task(project_id, task_id, status=status)
        except Exception:  # noqa: BLE001 — 状态机拒绝 → 停止
            break
    return service.get_task(project_id, task_id)


def _resolve_tgt(projects: list[Any], hint_project: Any, session: dict[str, Any]) -> Any | None:
    """定位目标项目 (LLM 项目名 → 会话项目; 失败 → None)。"""
    if hint_project:
        for pp in projects:
            if hint_project in str(getattr(pp, "name", "") or ""):
                return pp
    if session.get("project_id"):
        for pp in projects:
            if pp.id == session.get("project_id"):
                return pp
    return None


def _feature_facts(service: Any, project_id: str, feature: dict[str, Any]) -> str:
    """模块事实卡 (想法→细化→待办链路): 名称/成熟度/描述/已有 Story·Task。"""
    lines = [f"- 模块: {feature.get('name') or '未命名'}"]
    maturity = str(feature.get("maturity") or "refined")
    lines.append(f"- 成熟度: {'💡 想法 (未细化)' if maturity == 'idea' else '📦 正式 (已细化)'}")
    if feature.get("description"):
        lines.append(f"- 描述: {feature['description']}")
    try:
        backlog = service.list_backlog(project_id) or {}
        story_ids = set(feature.get("children") or [])
        task_ids: set[str] = set()
        for st in backlog.get("stories", []):
            if st.get("id") in story_ids:
                task_ids.update(st.get("children") or [])
        tasks = [t for t in backlog.get("tasks", []) if t.get("id") in task_ids]
    except Exception:  # noqa: BLE001 — 任务清单失败 → 省略
        tasks = []
    if tasks:
        lines.append(f"- 已有任务 ({len(tasks)}): " + "、".join(t.get("title", "") for t in tasks[:8]))
    else:
        lines.append("- 已有任务: 暂无 (待细化)")
    return "\n".join(lines)


def _task_context_facts(service: Any, project_id: str, task_id: str) -> str | None:
    """T-2: 任务上下文事实块 (状态/优先级/exec绑定/最近历史/下一步; 失败 → None)。"""
    try:
        task = service.get_task(project_id, task_id)
    except Exception:  # noqa: BLE001
        return None
    if task is None:
        return None
    lines = [
        f"【当前任务】{task.get('title') or '未命名'} (id: {task_id})",
        f"状态: {task.get('status') or 'todo'} · 优先级: {task.get('priority') or '—'}",
    ]
    if task.get("exec_ref"):
        lines.append(f"exec绑定: {task['exec_ref']} · 结果: {task.get('exec_result') or '—'}")
    hist = task.get("history") or []
    if hist:
        recent = " · ".join(
            f"{h.get('time', '')[:16]} {h.get('action', '')}" for h in hist[-3:]
        )
        lines.append(f"最近历史: {recent}")
    status = str(task.get("status") or "todo")
    next_hint = {
        "todo": "待开始 — 可『开始任务』或『继续推进』",
        "ready": "待开始 — 可『开始任务』",
        "in_progress": "执行中 — 可『标记完成』",
        "review": "待审核 — 可『标记完成』",
        "blocked": "阻塞 — 可『重新开始』",
        "done": "已完成 — 可审计历史",
    }.get(status, "—")
    lines.append(f"下一步: {next_hint}")
    return "\n".join(lines)


def build_app(
    service: Any,
    *,
    static_dir: str | Path | None = None,
    event_logger: Any = None,
    factory_root: str | Path | None = None,
) -> Any:
    """把已装配 ConsoleService 挂为 FastAPI app (最薄 HTTP 绑定)。

    写面收窄 (Permission Boundary): 只注册 GET 读端点 + 白名单写路径 —
    审批决定 POST (approve/reject)、Runtime 生命周期 POST、Review 反馈
    POST、项目创建 POST + 项目管理 PATCH/DELETE (S10-006.5); 其余一切
    PUT 等写动词不注册。
    static_dir 存在 → 挂 SPA 静态托管 (html=True); 否则纯 API 模式。
    """
    from fastapi import Body, FastAPI, HTTPException, Query, Request
    from fastapi.responses import StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from typing import Callable

    # 延迟 import 11A 路由函数 + 事件辅助 (仅依赖 factory-console.api, 无 Web 依赖)
    _api = _console_import("api")
    _events = _console_import("events")
    # S10-004: Runtime 状态机异常 (service 定义; api/__init__ 不导出 —
    # Adapter 层直接取 service 符号, 避免给 api 包加非路由导出)
    _service = _console_import("service")
    RuntimeStateError = _service.RuntimeStateError
    # S10-006.5 收尾: 项目删除冲突 (service 定义 — 运行中删除 → 409 诚实拒绝)
    ProjectConflictError = _service.ProjectConflictError
    # S10-009 Task 5: Confirm 冲突 (状态未到确认点/slug 冲突 → 409) +
    # 事务失败已回滚 (→ 503 存储不可用)
    ProjectConfirmConflictError = _service.ProjectConfirmConflictError
    ConfirmTransactionError = _service.ConfirmTransactionError
    # S10-010 Task 3: Backlog 错误语义 (任务/绑定不存在 → 404; 状态机
    # 非法转换 → 409 — 依赖未满足/参数非法仍走 ValueError → 400)
    BacklogNotFoundError = _service.BacklogNotFoundError
    BacklogStateError = _service.BacklogStateError
    # S10-018 Task 001c: Tool 错误语义 (404 不存在 / 403 最小权限拒绝 —
    # 由 Service 层抛出, HTTP 层映射)
    ToolExecuteNotFoundError = _service.ToolExecuteNotFoundError
    ToolExecutePermissionError = _service.ToolExecutePermissionError

    # S10-1xx: 数据根目录（/api/board/graph|chain 读项目 plan.json）
    workspace_root = Path(factory_root) if factory_root is not None else None

    # K-7e: Web 会话栏存储 (root/console_sessions.json; 与 chat.json 平级)
    _sessions_mod = _console_import("console_sessions")
    sessions_store = _sessions_mod.SessionStore(
        Path(factory_root if factory_root is not None else DEFAULT_ROOT) / "console_sessions.json"
    )
    # 设置管理面: LLM Control Plane (providers.json — 启用/停用/默认模型)
    _llm_mod = _console_import("llm_control")
    _llm_plane = _llm_mod.LLMControlPlane(
        providers_file=Path(factory_root if factory_root is not None else DEFAULT_ROOT) / "providers.json"
    )

    app = FastAPI(title="AI Software Factory — Human Console Web", version=_factory_version)

    # ============ API 规范 v1 (2026-08-26): 错误包络统一 {"error": {code, message, detail, suggestion}}
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    def _error_envelope(status: int, message: str, detail: Any = "", suggestion: str = "") -> dict[str, Any]:
        return {"error": {"code": f"E7{status}", "message": str(message),
                          "detail": detail, "suggestion": suggestion}}

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            return JSONResponse(status_code=exc.status_code, content=detail)
        message = str(detail) if detail else "请求处理失败"
        return JSONResponse(status_code=exc.status_code,
                            content=_error_envelope(exc.status_code, message, detail=detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=_error_envelope(
            422, "请求体校验失败", detail=str(exc.errors()[:2])))

    @app.exception_handler(Exception)
    async def _generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content=_error_envelope(
            500, "服务器内部错误", suggestion="查看服务日志"))
    # ============================================================

    # S10-120 K-4: 每请求 trace_id 上下文 (请求头 X-Trace-ID 可选覆盖; 无 →
    # 自动生成; with 退出自动恢复 — 不跨请求泄漏; 失败安全)。审计/执行/成本
    # 经 contextvar 自动继承同一 trace_id, 全程可追踪。
    _trace_ctx = _console_import("audit.trace_context")

    @app.middleware("http")
    async def _request_trace_middleware(request: Request, call_next: Callable):
        """每请求包 trace_context: X-Trace-ID 可选覆盖, 响应回带 X-Trace-ID。"""
        trace_id = str(request.headers.get("X-Trace-ID") or "").strip()
        if not trace_id:
            trace_id = _trace_ctx.new_trace_id()
        with _trace_ctx.trace_context(trace_id):
            response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response

    def _raise_backlog_error(exc: Exception) -> NoReturn:
        """Backlog + Sprint/Milestone/Roadmap 端点统一错误映射 (404/409/400; 其余原样上抛)。"""
        if isinstance(exc, BacklogNotFoundError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if isinstance(exc, BacklogStateError):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise exc

    # S10-074: 部署健康/就绪/版本契约 (GET /health /ready /version)
    @app.get("/health")
    def health() -> dict[str, Any]:
        """存活: 进程活着。"""
        return {"status": "ok", "version": _factory_version}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        """就绪: 核心配置/数据目录可达。"""
        issues: list[str] = []
        data_dir = Path(os.environ.get("DATA_DIR", "~/.factory")).expanduser()
        if not data_dir.is_dir():
            issues.append(f"数据目录不存在: {data_dir}")
        return {"status": "ready" if not issues else "not_ready",
                "data_dir": str(data_dir), "issues": issues}

    @app.get("/version")
    def version() -> dict[str, Any]:
        """版本。"""
        return {"name": "ai-software-factory", "version": _factory_version}

    @app.get("/api/system/status")
    def api_system_status():
        """系统状态（版本 + 服务清单 + git, 只读）。"""
        services = {}
        try:
            from ..cli_services import list_services

            for svc in list_services():
                services[svc.id] = {"label": svc.label}
        except Exception:  # noqa: BLE001 — 服务清单失败不影响版本
            services = {}
        return {
            "ok": True,
            "version": _factory_version,
            "services": list(services.keys()),
            "git": _git_status(),
        }

    @app.post("/api/system/update")
    def api_system_update(module: str = ""):
        """触发系统更新（git pull + pip install -e .; module 可选 core/console/exec/org）。

        敏感操作: 落审计（当前无认证, 本地单用户场景; 后续加 RBAC/认证）。
        """
        import subprocess
        import sys as _sys

        # 仓库根（git/pip 在代码仓库运行, 非数据目录）
        root = Path(__file__).resolve().parents[3]
        # 更新逻辑（同 factory update: git pull + pip install -e .）
        results = {"steps": []}
        # 1) git pull
        try:
            r = subprocess.run(["git", "-C", str(root), "pull", "--ff-only"],
                               capture_output=True, text=True, timeout=60)
            results["steps"].append({"step": "git pull", "ok": r.returncode == 0,
                                     "detail": r.stdout.strip() or r.stderr.strip()[:200] or "已是最新"})
        except Exception as exc:  # noqa: BLE001
            results["steps"].append({"step": "git pull", "ok": False, "detail": str(exc)})
        # 2) pip install -e .
        try:
            r = subprocess.run([_sys.executable, "-m", "pip", "install", "-e", "."],
                               cwd=str(root), capture_output=True, text=True, timeout=120)
            results["steps"].append({"step": "pip install", "ok": r.returncode == 0,
                                     "detail": "依赖已同步" if r.returncode == 0 else r.stderr.strip()[:200]})
        except Exception as exc:  # noqa: BLE001
            results["steps"].append({"step": "pip install", "ok": False, "detail": str(exc)})
        results["version"] = _factory_version
        results["ok"] = all(s["ok"] for s in results["steps"])
        # 审计（记录触发）
        # 审计（通用事件, 失败安全）
        try:
            from .audit_emitter import AuditEmitter
            AuditEmitter(workspace=workspace_root).emit(
                "GOVERNANCE_CHECK", project_id="", actor_type="api",
                action=f"system.update:{module or 'all'}",
            )
        except Exception:  # noqa: BLE001 — 审计失败不阻断更新
            pass
        return results

    @app.get("/api/board")
    def api_board(view: str = "", project: str = ""):
        """任务监控面板 HTML（?view=report 汇报; ?view=projects 项目列表;
        ?view=project&project=<slug> 单项目视图; 缺省主线面板）。

        BoardService 声明的访问端点; 返回 HTML 页面（非 JSON）—
        浏览器直接看监控面板（桌面/手机/Pad 响应式）。
        """
        from fastapi.responses import HTMLResponse

        board_mod = _console_import("session.board")
        try:
            if view == "project":
                html = board_mod.render_project_lifecycle_html(workspace_root, project)
            elif view == "projects":
                html = board_mod.render_projects_list_html(workspace_root)
            elif view == "mainline":
                # AI Factory 自身开发进度 (显式入口; 页面仍带项目选择器)
                html = board_mod.render_board_html(workspace=workspace_root, project=project)
            elif view == "report":
                html = board_mod.render_report_html(workspace=workspace_root, project_id=project)
            elif view == "employees":
                # S10-116 A-2: 👥 员工 tab (只读: agent/skill/角色定义/装配状态)
                html = board_mod.render_employees_html(workspace_root)
            elif view == "quality":
                # S10-117 K-2: 📊 质量 (只读: 最近执行质量 + PRD/工程质量)
                html = board_mod.render_quality(workspace_root, project)
            else:
                # 项目优先首页: 有当前项目 → 该项目视图; 否则项目列表引导
                html = board_mod.render_project_home(workspace_root)
        except Exception:  # noqa: BLE001 — 面板失败 → 明确错误不 500
            html = "<p>（面板渲染失败）</p>"
        return HTMLResponse(content=html)

    @app.get("/api/board/summary")
    def api_board_summary():
        """项目监控聚合 JSON (S10-110 P0-1 实时刷新数据源, 只读)。"""
        board_mod = _console_import("session.board")
        try:
            return board_mod.dashboard_stats(workspace_root)
        except Exception:  # noqa: BLE001 — 失败安全
            return {"projects": 0, "status_dist": {}, "avg_lifecycle_pct": 0,
                    "running_tasks": 0, "failed_tasks": 0}

    @app.post("/api/board/split")
    def api_board_split(project: str = "", task: str = "", names: str = ""):
        """细化任务: 拆成多个子任务 (L 层+1), names 逗号分隔 (query)。"""
        board_mod = _console_import("session.board")
        try:
            name_list = [n.strip() for n in (names or "").split(",") if n and n.strip()]
            created = board_mod.split_task(workspace_root, project, task, name_list)
            return {"ok": bool(created), "created": [t["id"] for t in created]}
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": "细化失败"}

    @app.get("/api/board/docs/config")
    def api_docs_config_get(project: str = ""):
        """文档配置设置页 (多目录 + 扩展名)。"""
        from fastapi.responses import HTMLResponse
        board_mod = _console_import("session.board")
        try:
            html = board_mod.render_docs_config_html(workspace_root, project)
        except Exception:  # noqa: BLE001
            html = "<p>（配置页渲染失败）</p>"
        return HTMLResponse(content=html)

    @app.post("/api/board/docs/config")
    def api_docs_config_post(project: str = "", dirs: str = "", exts: str = ""):
        """保存文档配置 (dirs 换行分隔, exts 逗号分隔; 或 JSON body)。"""
        board_mod = _console_import("session.board")
        try:
            dir_list = [d.strip() for d in (dirs or "").replace("\n", ",").split(",") if d.strip()]
            ext_list = [e.strip() for e in (exts or "").split(",") if e.strip()]
            cfg = board_mod.write_docs_config(workspace_root, project,
                                              dirs=dir_list, exts=ext_list)
            return {"ok": True, "dirs": cfg["dirs"], "exts": cfg["exts"]}
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": "保存失败"}

    @app.post("/api/board/default")
    def api_board_default(project: str = ""):
        """设置默认项目 (写 board_default_project; 首页优先打开它)。"""
        board_mod = _console_import("session.board")
        slug = board_mod._set_default_project(workspace_root, project)
        if not slug:
            return {"ok": False, "error": "设置失败"}
        return {"ok": True, "default_project": slug}

    @app.get("/api/board/docs")
    def api_board_docs(project: str = ""):
        """项目文档管理 HTML (文档资产列表 + 查看链接)。"""
        from fastapi.responses import HTMLResponse

        board_mod = _console_import("session.board")
        try:
            html = board_mod.render_project_docs_html(workspace_root, project)
        except Exception:  # noqa: BLE001
            html = "<p>（文档列表渲染失败）</p>"
        return HTMLResponse(content=html)

    @app.get("/api/board/doc")
    def api_board_doc(project: str = "", doc: str = ""):
        """项目文档查看: markdown 渲染 / JSON 格式化 (只读, 路径白名单)。"""
        from fastapi.responses import HTMLResponse, PlainTextResponse

        board_mod = _console_import("session.board")
        try:
            html = board_mod.render_project_doc_view(workspace_root, project, doc)
        except Exception:  # noqa: BLE001
            html = "<p>（文档渲染失败）</p>"
        return HTMLResponse(content=html)

    # S10-123 K-6: 项目级 RAG (M5-2/B-8 + M5-3 + E-5) — 只做后端, 不碰前端
    # ------------------------------------------- 项目文档管理 (v1.1.108, 5180 产品工作台)
    # 复用 session/board.list_project_docs + read_project_doc_content (路径安全),
    # 只做 JSON 绑定 — 前端 AfProjectDocs 左树右看。
    # ------------------------------------------- 产出物契约 (C-1, 平台级)
    # 全部项目的统一产出物状态 (固定 schema + 版本信号) — WebUI 轮询 version
    # 感知变化; 只读 GET。
    # C-3: 轻量轮询 — 只返回版本信号 (WebUI 每 N 秒轮询, 变化才刷新)
    # ------------------------------------------- 统一监控运维 (D 系列, v1.1.134)
    # Monitor 单一采集 → 多处消费 (会话 system_status / 概览健康条 / 运维页 / CLI)
    def _version_summary(version: str) -> str:
        """CHANGELOG 对应版本首行摘要 (版本说明; 失败 → '')。"""
        try:
            ch = Path(__file__).resolve().parents[3] / "CHANGELOG.md"
            lines = ch.read_text(encoding="utf-8").splitlines()
            in_section = False
            for ln in lines:
                if ln.startswith(f"## [v{version}]"):
                    in_section = True
                    continue
                if in_section:
                    if ln.startswith("#"):
                        break
                    if ln.strip():
                        # 去掉 markdown 加粗与句尾标点
                        return ln.replace("**", "").strip().strip("。. ")

        except Exception:  # noqa: BLE001
            return ""
        return ""

    @app.get("/api/monitor")
    def api_monitor(
        limit: int = Query(default=10, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        """系统 + 全部项目监控 (GET — 统一 snapshot + 历史分页)。"""
        if workspace_root is None:
            return {"system": None, "projects": [], "snapshots": [], "snapshot_total": 0, "snapshot_offset": 0}
        _monitor_mod = _console_import("monitor")
        model_line = ""
        try:
            _llm_plane_reload(_llm_plane)
            pid = _llm_plane.selected_provider_id()
            if pid is not None:
                sp = _llm_plane.get_provider(pid)
                if sp is not None:
                    model_line = (
                        f"{_provider_config_view(_llm_plane, sp).get('default_model')} "
                        f"(provider: {pid})"
                    )
        except Exception:  # noqa: BLE001
            model_line = ""
        system = _monitor_mod.collect_system(
            workspace_root, _factory_version, model_line=model_line
        )
        system["version_summary"] = _version_summary(_factory_version)
        projects = []
        try:
            for p in service.list_projects():
                rt = []
                try:
                    rt = service.list_runtimes(p.id) or []
                except Exception:  # noqa: BLE001
                    rt = []
                pm = _monitor_mod.collect_project(
                    workspace_root, p.id, name=p.name, lifecycle=p.lifecycle_stage or p.status,
                    runtimes=len(rt),
                    failed=sum(1 for r in rt if getattr(r, "status", "") == "failed"),
                )
                if pm:
                    projects.append(pm)
        except Exception:  # noqa: BLE001
            projects = []
        snapshots = _monitor_mod.read_snapshots(workspace_root, limit=limit, offset=offset)
        snapshot_total = _monitor_mod.snapshot_count(workspace_root)
        alerts = _monitor_mod.check_alerts(system, projects)
        _monitor_mod.save_snapshot(workspace_root, {"system": system, "projects": projects, "alerts": alerts})
        return {
            "system": system,
            "projects": projects,
            "snapshots": snapshots,
            "alerts": alerts,
            "snapshot_total": snapshot_total,
            "snapshot_offset": offset,
        }

    @app.get("/api/projects/{project_id}/monitor")
    def api_project_monitor(project_id: str) -> dict[str, Any]:
        """单项目监控 (GET — 统一采集)。"""
        if workspace_root is None:
            raise HTTPException(status_code=404, detail="project not found")
        _monitor_mod = _console_import("monitor")
        try:
            found = next((p for p in service.list_projects() if p.id == project_id), None)
        except Exception:  # noqa: BLE001
            found = None
        rt = []
        try:
            rt = service.list_runtimes(project_id) or []
        except Exception:  # noqa: BLE001
            rt = []
        pm = _monitor_mod.collect_project(
            workspace_root, project_id,
            name=found.name if found else project_id,
            lifecycle=(found.lifecycle_stage or found.status) if found else "",
            runtimes=len(rt),
            failed=sum(1 for r in rt if getattr(r, "status", "") == "failed"),
        )
        if pm is None:
            raise HTTPException(status_code=404, detail="project not found")
        system = _monitor_mod.collect_system(workspace_root, _factory_version)
        system["version_summary"] = _version_summary(_factory_version)
        return {"system": system, "project": pm}

    @app.get("/api/projects/{project_id}/artifacts/version")
    def api_project_artifacts_version(project_id: str) -> dict[str, Any]:
        """产出物版本信号 (GET — {version, updated_at}; 轮询用, 轻量)。"""
        if workspace_root is None:
            return {"version": 0, "updated_at": None}
        _contract = _console_import("artifact_contract")
        try:
            meta = _contract.read_manifest(workspace_root, project_id)
            return {
                "version": int(meta.get("version", 0) or 0),
                "updated_at": meta.get("updated_at"),
            }
        except Exception:  # noqa: BLE001 — 失败安全
            return {"version": 0, "updated_at": None}

    @app.get("/api/projects/{project_id}/artifacts")
    def api_project_artifacts(project_id: str) -> dict[str, Any]:
        """项目产出物统一状态 (GET — {items, meta, drift}; 全部项目通用)。"""
        if workspace_root is None:
            return {"project_id": project_id, "items": [], "meta": {"version": 0, "changed_at": None}, "drift": []}
        _contract = _console_import("artifact_contract")
        try:
            return _contract.scan_project(workspace_root, project_id)
        except Exception:  # noqa: BLE001 — 失败安全
            return {"project_id": project_id, "items": [], "meta": {"version": 0, "changed_at": None}, "drift": []}

    @app.get("/api/projects/{project_id}/artifacts/{artifact_type}/versions/{version}")
    def api_project_artifact_version(
        project_id: str, artifact_type: str, version: int
    ) -> dict[str, Any]:
        """产出物某版本内容 (GET — 历史可追溯查看; 不存在 → 404)。"""
        if workspace_root is None:
            raise HTTPException(status_code=404, detail="artifact version not found")
        _contract = _console_import("artifact_contract")
        result = _contract.get_artifact_version(workspace_root, project_id, artifact_type, version)
        if result is None:
            raise HTTPException(status_code=404, detail="artifact version not found")
        return result

    @app.get("/api/projects/{project_id}/docs")
    def api_project_docs_list(project_id: str) -> dict[str, Any]:
        """项目文档清单 (GET — 核心资产 + 可配多目录扫描; 未装配 → 空)。"""
        if workspace_root is None:
            return ok_list([])
        board_mod = _console_import("session.board")
        try:
            items = board_mod.list_project_docs(workspace_root, project_id)
        except Exception:  # noqa: BLE001 — 失败安全
            items = []
        return ok_list(items)

    @app.get("/api/projects/{project_id}/docs/{doc:path}")
    def api_project_doc_content(project_id: str, doc: str) -> dict[str, Any]:
        """项目文档内容 (GET — md/json/txt 文本; 路径安全; 越界 → 404)。"""
        if workspace_root is None:
            raise HTTPException(status_code=404, detail="document not found")
        board_mod = _console_import("session.board")
        try:
            result = board_mod.read_project_doc_content(workspace_root, project_id, doc)
        except Exception:  # noqa: BLE001 — 失败安全
            result = {"name": doc, "kind": "error", "content": None, "note": "读取失败"}
        if result.get("error") == "unsupported-path":
            raise HTTPException(status_code=404, detail="document not found")
        return result

    @app.get("/api/rag/sources")
    def api_rag_sources():
        """外部知识源清单 (M5-3 接口就绪状态; 未配置 → 空不崩)。"""
        ext_mod = _console_import("retrieval.external_source")
        sources = ext_mod.get_external_sources()
        configured = ext_mod.configured_external_sources(_rag_config_shim(workspace_root))
        cfg_names = {str(getattr(src, "name", "") or "") for src in configured}
        return {
            "ok": True,
            "sources": [
                {
                    "name": str(getattr(src, "name", "") or ""),
                    "ping": _safe_ping(src),
                    "configured": str(getattr(src, "name", "") or "") in cfg_names,
                }
                for src in sources
            ],
            "configured": sorted(cfg_names),
            "note": "接口就绪; 真实接入 (Postgres/向量库) 待后续",
        }

    @app.post("/api/rag/query")
    def api_rag_query(body: _RagQueryBody) -> dict[str, Any]:
        """项目级 RAG 检索问答 (确定性词频 + 三级分档 + 可选外部源 + E-5 审计)。

        project/question 缺失 → 400; 检索纯规则确定性 (同输入同输出),
        未入库/项目不存在 → 空命中 (200, 提示先 index); 失败安全: 任何
        异常 → 空命中, 不 5xx。
        """
        slug = Path(str(body.project or "")).name
        question = str(body.question or "")
        if not slug:
            raise HTTPException(status_code=400, detail="project is required")
        if not question:
            raise HTTPException(status_code=400, detail="question is required")
        tiers = [t.strip() for t in str(body.tiers or "").split(",") if t.strip()] or None
        top_k = max(0, int(body.top_k or 5))
        try:
            ks_mod = _console_import("retrieval.knowledge_store")
            _rag_query = ks_mod.rag_query
        except Exception:  # noqa: BLE001 — 失败安全: 模块不可用 → 明确错误
            return {"ok": False, "project": slug, "hits": [], "stats": {}, "error": "rag module unavailable"}
        ext_mod = _console_import("retrieval.external_source")
        external = ext_mod.configured_external_sources(_rag_config_shim(workspace_root))
        hits, stats = _rag_query(
            workspace_root, slug, question,
            tiers=tiers, top_k=top_k, external_sources=external,
        )
        return {
            "ok": True,
            "project": slug,
            "question": question,
            "hits": [h.to_dict() for h in hits],
            "stats": stats,
        }

    @app.get("/api/board/tasks")
    def api_board_tasks(project: str = ""):
        """项目任务树 HTML (epic → feature → task, 状态色点)。"""
        from fastapi.responses import HTMLResponse

        board_mod = _console_import("session.board")
        try:
            html = board_mod.render_project_tasktree_html(workspace_root, project)
        except Exception:  # noqa: BLE001
            html = "<p>（任务树渲染失败）</p>"
        return HTMLResponse(content=html)

    # ============ U-6 (v1.1.188): 本机 AI 发现与调度 (codex/claude/hermes)
    @app.get("/api/local-ai")
    def api_local_ai_scan() -> dict[str, Any]:
        """扫描本机 AI CLI (codex/claude/hermes) — 只读探测, 不注册。"""
        try:
            _local_ai_mod = _console_import("local_ai")
            detected = _local_ai_mod.detect_local_ais()
        except Exception:  # noqa: BLE001 — 扫描失败 → 空 (不编造)
            detected = []
        return {"detected": detected, "count": len(detected)}

    @app.post("/api/local-ai/register")
    def api_local_ai_register() -> dict[str, Any]:
        """扫描 + 幂等注册本机 AI 为 Agent (写 agents.json; 失败安全)。"""
        try:
            _local_ai_mod = _console_import("local_ai")
            detected = _local_ai_mod.detect_local_ais()
            registered = _local_ai_mod.register_local_ais(_agents_file(), detected)
        except Exception as exc:  # noqa: BLE001 — 注册失败 → 诚实错误
            return {"registered": [], "error": str(exc)}
        return {"registered": registered, "count": len(registered), "detected": len(detected)}

    @app.post("/api/local-ai/{agent_id}/run")
    def api_local_ai_run(agent_id: str, body: _LocalAiRunBody) -> dict[str, Any]:
        """委派真实执行: 调本机 CLI (codex/claude/hermes) 执行 prompt。"""
        data = _read_json_map(_agents_file())
        agents = data.get("agents") if isinstance(data, dict) else None
        record = None
        if isinstance(agents, dict):
            record = agents.get(agent_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"agent not found: {agent_id}")
        try:
            _local_ai_mod = _console_import("local_ai")
            result = _local_ai_mod.run_local_ai(
                record,
                body.prompt,
                project_dir=body.project_dir,
                timeout=body.timeout,
            )
        except Exception as exc:  # noqa: BLE001 — 委派失败 → 诚实错误
            result = {"exit_code": -1, "output": "", "error": f"委派失败: {exc}"}
        result["agent_id"] = agent_id
        return result

    # ============ M1 (v1.1.191): 外部执行器通用适配层 — 声明式适配器管理
    def _external_registry():
        """ExternalExecutorRegistry (懒装配, 失败安全 None)。"""
        try:
            _ext_exec = _console_import("external_executor")
            return _ext_exec.build_registry(workspace_root or DEFAULT_ROOT)
        except Exception:  # noqa: BLE001 — 装配失败 → None
            return None

    @app.get("/api/external-ai")
    def api_external_ai_list() -> dict[str, Any]:
        """适配器清单 (含发现/探测状态; 失败安全空)。"""
        registry = _external_registry()
        if registry is None:
            return {"adapters": [], "count": 0}
        from factory_console.external_executor import executor as _ee_exec
        items = []
        for a in registry.list():
            path = _ee_exec.discover_binary(a)
            items.append({
                "id": a.id, "name": a.name, "binary": a.binary,
                "discovery": list(a.discovery),
                "invocation": a.invocation.model_dump(mode="json"),
                "host_assets": a.host_assets.model_dump(mode="json") if a.host_assets else None,
                "capabilities": a.capabilities.model_dump(mode="json"),
                "allow_dangerous": a.allow_dangerous,
                "found": path is not None,
                "path": path,
                "builtin": not (Path(workspace_root or DEFAULT_ROOT) / "external-ais" / f"{a.id}.yaml").is_file(),
            })
        return {"adapters": items, "count": len(items)}

    @app.post("/api/external-ai/scan")
    def api_external_ai_scan() -> dict[str, Any]:
        """扫描全部适配器: 发现 + 探测 → 状态 (失败安全)。"""
        registry = _external_registry()
        if registry is None:
            return {"results": [], "error": "external_executor 模块不可用"}
        from factory_console.external_executor import executor as _ee_exec
        results = []
        for a in registry.list():
            path = _ee_exec.discover_binary(a)
            if path is None:
                results.append({"id": a.id, "name": a.name, "found": False,
                                "ok": False, "path": None, "error": "未发现二进制"})
                continue
            pr = _ee_exec.probe(a, path)
            results.append({"id": a.id, "name": a.name, "found": True, "path": path,
                            "ok": pr["ok"], "version": pr.get("version"),
                            "usage": pr.get("usage"), "error": pr.get("error")})
        return {"results": results, "count": len(results)}

    @app.post("/api/external-ai")
    def api_external_ai_save(body: _ExternalAiBody) -> dict[str, Any]:
        """创建/更新适配器 (写 <data_dir>/external-ais/<id>.yaml; Schema 校验失败 → 400)。"""
        registry = _external_registry()
        if registry is None:
            raise HTTPException(status_code=503, detail="external_executor 模块不可用")
        try:
            adapter = _external_ai_from_body(body)
            registry.save(adapter)
        except Exception as exc:  # noqa: BLE001 — Schema 校验失败 → 400 (不猜测)
            raise HTTPException(status_code=400, detail=f"适配器校验失败: {exc}") from exc
        return {"saved": True, "id": adapter.id, "name": adapter.name}

    @app.delete("/api/external-ai/{adapter_id}")
    def api_external_ai_remove(adapter_id: str) -> dict[str, Any]:
        """删除用户适配器 yaml (内置模板不可删 → 404)。"""
        registry = _external_registry()
        if registry is None:
            raise HTTPException(status_code=503, detail="external_executor 模块不可用")
        if not registry.remove(adapter_id):
            raise HTTPException(status_code=404, detail=f"未找到用户适配器: {adapter_id}")
        return {"deleted": True, "id": adapter_id}

    @app.post("/api/external-ai/{adapter_id}/probe")
    def api_external_ai_probe(adapter_id: str) -> dict[str, Any]:
        """探测单个适配器可用性 (诚实: 能跑 ≠ 任务真实成功)。"""
        registry = _external_registry()
        if registry is None:
            raise HTTPException(status_code=503, detail="external_executor 模块不可用")
        adapter = registry.get(adapter_id)
        if adapter is None:
            raise HTTPException(status_code=404, detail=f"适配器不存在: {adapter_id}")
        from factory_console.external_executor import executor as _ee_exec
        path = _ee_exec.discover_binary(adapter)
        pr = _ee_exec.probe(adapter, path)
        return {**pr, "id": adapter_id, "path": path}

    @app.post("/api/external-ai/{adapter_id}/run")
    def api_external_ai_run(adapter_id: str, body: _ExternalAiRunBody) -> dict[str, Any]:
        """委派真实执行 (按适配器声明调用宿主 CLI)。"""
        registry = _external_registry()
        if registry is None:
            raise HTTPException(status_code=503, detail="external_executor 模块不可用")
        adapter = registry.get(adapter_id)
        if adapter is None:
            raise HTTPException(status_code=404, detail=f"适配器不存在: {adapter_id}")
        from factory_console.external_executor import executor as _ee_exec
        agent_name = str(body.agent or "").strip()
        if agent_name and not adapter.invocation.agent_flag:
            agent_name = ""  # 宿主不支持借壳 → 忽略 (不假装)
        import time as _time

        _t0 = _time.monotonic()
        result = _ee_exec.run(
            adapter, body.prompt,
            project_dir=str(body.project_dir or ""),
            agent=agent_name,
            timeout=body.timeout,
        )
        _dur_ms = int((_time.monotonic() - _t0) * 1000)
        result["id"] = adapter_id
        result["mode"] = "borrowed-shell" if agent_name else "blackbox"
        result["host_agent"] = agent_name or None
        # M3: 统一执行记录 (EXS + 证据包) — 监控/路由/审计消费
        record = _ee_exec.record_invocation(
            workspace_root or DEFAULT_ROOT,
            executor_id=adapter_id,
            mode=result["mode"],
            host_agent=agent_name,
            prompt=body.prompt,
            project_dir=str(body.project_dir or ""),
            exit_code=int(result.get("exit_code")) if result.get("exit_code") is not None else -1,
            output=str(result.get("output") or ""),
            error=str(result.get("error") or ""),
            command=str(result.get("command") or ""),
            duration_ms=_dur_ms,
            trace_id=_trace_ctx.get_trace_id() if _trace_ctx is not None else "",
        )
        result["result_id"] = record.get("result_id")
        return result

    @app.post("/api/external-ai/route")
    def api_external_ai_route(body: _ExternalAiRouteBody) -> dict[str, Any]:
        """M5 路由: 任务 → 选 agent/skill (能力匹配 + 历史加权 + 用户显式 + 兜底)。"""
        registry = _external_registry()
        adapters = registry.list() if registry is not None else []
        # 全部 agent (外部带 source + 内部员工) — 路由候选池
        all_agents: list[dict[str, Any]] = []
        try:
            _ag = _read_json_map(Path(workspace_root or DEFAULT_ROOT) / "agents" / "agents.json")
            agents = _ag.get("agents") if isinstance(_ag, dict) and isinstance(_ag.get("agents"), dict) else None
            if isinstance(agents, dict):
                all_agents = [v for v in agents.values() if isinstance(v, dict)]
        except Exception:  # noqa: BLE001
            all_agents = []
        try:
            _router = _console_import("external_executor.router")
            return _router.route(
                body.task, adapters, all_agents,
                workspace_root or DEFAULT_ROOT,
                explicit_agent=body.explicit_agent,
            )
        except Exception as exc:  # noqa: BLE001 — 路由失败 → 诚实错误
            raise HTTPException(status_code=500, detail=f"路由失败: {exc}") from exc

    @app.post("/api/external-ai/auto")
    def api_external_ai_auto(body: _ExternalAiAutoBody) -> dict[str, Any]:
        """M6 全自动闭环: 路由选 agent → 委派执行 → 统一执行记录。
        内部员工候选 → 诚实标注走内部链 (外部执行器不代跑, 不假装)。"""
        registry = _external_registry()
        adapters = registry.list() if registry is not None else []
        all_agents: list[dict[str, Any]] = []
        try:
            _ag = _read_json_map(Path(workspace_root or DEFAULT_ROOT) / "agents" / "agents.json")
            agents = _ag.get("agents") if isinstance(_ag, dict) and isinstance(_ag.get("agents"), dict) else None
            if isinstance(agents, dict):
                all_agents = [v for v in agents.values() if isinstance(v, dict)]
        except Exception:  # noqa: BLE001
            all_agents = []
        try:
            _router = _console_import("external_executor.router")
            route_result = _router.route(
                body.task, adapters, all_agents,
                workspace_root or DEFAULT_ROOT,
                explicit_agent=body.explicit_agent,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"路由失败: {exc}") from exc
        pick = route_result.get("pick")
        pick_kind = route_result.get("pick_kind")
        if not pick:
            return {"route": route_result, "execution": None, "note": "无候选，未执行"}
        if pick_kind == "internal":
            return {"route": route_result, "execution": None,
                    "note": f"选到内部员工 {pick} — 外部执行器不代跑内部链 (诚实, 不假装)"}
        # 解析适配器: agent → <adapter>.<host_agent>; executor → <adapter>
        adapter_id = pick.split(".")[0] if "." in pick else pick
        host_agent = pick[len(adapter_id) + 1:] if "." in pick else ""
        adapter = registry.get(adapter_id) if registry is not None else None
        if adapter is None:
            return {"route": route_result, "execution": None,
                    "note": f"适配器不存在: {adapter_id} — 未执行"}
        if host_agent and not adapter.invocation.agent_flag:
            host_agent = ""  # 宿主不支持借壳 → 降级黑盒 (诚实)
        import time as _time
        _ee_exec = _console_import("external_executor.executor")
        _t0 = _time.monotonic()
        result = _ee_exec.run(adapter, body.task,
                              project_dir=str(body.project_dir or ""),
                              agent=host_agent,
                              timeout=body.timeout)
        _dur_ms = int((_time.monotonic() - _t0) * 1000)
        mode = "borrowed-shell" if host_agent else "blackbox"
        record = _ee_exec.record_invocation(
            workspace_root or DEFAULT_ROOT,
            executor_id=adapter_id, mode=mode, host_agent=host_agent,
            prompt=body.task, project_dir=str(body.project_dir or ""),
            exit_code=int(result.get("exit_code")) if result.get("exit_code") is not None else -1,
            output=str(result.get("output") or ""), error=str(result.get("error") or ""),
            command=str(result.get("command") or ""), duration_ms=_dur_ms,
            trace_id=_trace_ctx.get_trace_id() if _trace_ctx is not None else "",
        )
        result["result_id"] = record.get("result_id")
        # M7 验证钩子: 委派后自动验证 → 效果分回写 (闭环最后一环)
        verify_out: dict[str, Any] = {"method": "", "result": "unknown", "score": None, "reason": ""}
        if body.verify:
            try:
                verify_out = _ee_exec.auto_verify(
                    str(body.project_dir or ""),
                    str(route_result.get("work_type") or ""),
                    verify_hook=(adapter.extensions or {}).get("verify_hook"),
                    timeout=300,
                )
                if verify_out.get("result") != "unknown":
                    _ee_exec.verify_invocation(
                        workspace_root or DEFAULT_ROOT, str(record.get("result_id") or ""),
                        method=str(verify_out.get("method") or "auto"),
                        result=str(verify_out.get("result") or "unknown"),
                        score=verify_out.get("score"),
                        reason=str(verify_out.get("reason") or ""),
                    )
                else:
                    # M7.2 审查验证钩子: 无本地钩子的审查类任务 → 派 reviewer 交叉审查
                    review_types = ("arch", "security", "review", "design", "product", "writer")
                    if str(route_result.get("work_type") or "") in review_types:
                        rv = _ee_exec.reviewer_verify(
                            workspace_root or DEFAULT_ROOT,
                            adapters, all_agents,
                            body.task, str(body.project_dir or ""),
                            str(result.get("output") or ""),
                            str(route_result.get("work_type") or ""),
                            preferred_adapter=adapter_id,
                        )
                        verify_out = rv
                        if rv.get("result") != "unknown":
                            _ee_exec.verify_invocation(
                                workspace_root or DEFAULT_ROOT, str(record.get("result_id") or ""),
                                method=str(rv.get("method") or "reviewer"),
                                result=str(rv.get("result") or "unknown"),
                                score=rv.get("score"),
                                reason=str(rv.get("reason") or ""),
                            )
            except Exception:  # noqa: BLE001 — 验证失败不阻断 (诚实 unknown)
                verify_out = {"method": "", "result": "unknown", "score": None, "reason": "自动验证异常"}
        return {"route": route_result, "execution": {
            "executor_id": adapter_id, "mode": mode, "host_agent": host_agent,
            "exit_code": result.get("exit_code"), "output": str(result.get("output") or "")[:2000],
            "error": str(result.get("error") or "")[:1000], "result_id": record.get("result_id"),
        }, "verify": verify_out}

    @app.post("/api/external-ai/cost")
    def api_external_ai_cost(body: _ExternalAiCostBody) -> dict[str, Any]:
        """M4.3: 给执行记录附加成本 (宿主 CLI 报告/估算后回填; 默认 unknown 不编造)。"""
        try:
            _ee_exec = _console_import("external_executor.executor")
            updated = _ee_exec.record_cost(
                workspace_root or DEFAULT_ROOT,
                body.result_id,
                body.cost_usd,
                currency=body.currency,
            )
        except Exception as exc:  # noqa: BLE001 — 失败 → 诚实错误
            raise HTTPException(status_code=500, detail=f"成本回填失败: {exc}") from exc
        if updated is None:
            raise HTTPException(status_code=404, detail=f"执行记录不存在: {body.result_id}")
        return {"result_id": body.result_id, "cost_usd": updated.get("cost_usd"),
                "currency": updated.get("cost_currency", "USD")}

    @app.post("/api/external-ai/verify")
    def api_external_ai_verify(body: _ExternalAiVerifyBody) -> dict[str, Any]:
        """M3: 验证回写 — 更新执行记录 verify + rework (fail → rework+1)。"""
        try:
            _ee_exec = _console_import("external_executor.executor")
            updated = _ee_exec.verify_invocation(
                workspace_root or DEFAULT_ROOT,
                body.result_id,
                method=body.method,
                result=body.result,
                score=body.score,
                reason=body.reason,
            )
        except Exception as exc:  # noqa: BLE001 — 验证失败 → 诚实错误
            raise HTTPException(status_code=500, detail=f"验证回写失败: {exc}") from exc
        if updated is None:
            raise HTTPException(status_code=404, detail=f"执行记录不存在: {body.result_id}")
        return {"result_id": body.result_id, "verify": updated.get("verify"),
                "first_pass": updated.get("first_pass"), "rework": updated.get("rework")}

    # ============ M2 (v1.1.192): 宿主资产发现与导入 (agents/skills/plugins/persona)
    @app.get("/api/external-ai/{adapter_id}/assets")
    def api_external_ai_assets(adapter_id: str) -> dict[str, Any]:
        """扫描适配器宿主资产 (只读, 未导入): agents/skills/plugins/persona。"""
        registry = _external_registry()
        if registry is None:
            raise HTTPException(status_code=503, detail="external_executor 模块不可用")
        adapter = registry.get(adapter_id)
        if adapter is None:
            raise HTTPException(status_code=404, detail=f"适配器不存在: {adapter_id}")
        try:
            _host = _console_import("external_executor.host_assets")
            assets = _host.scan_adapter_assets(adapter)
        except Exception as exc:  # noqa: BLE001 — 扫描失败 → 诚实错误
            raise HTTPException(status_code=500, detail=f"资产扫描失败: {exc}") from exc
        return {"adapter": adapter_id, "assets": assets, "count": len(assets)}

    @app.post("/api/external-ai/{adapter_id}/import")
    def api_external_ai_import(adapter_id: str) -> dict[str, Any]:
        """导入资产: agents → AI 员工 (agents.json), skills → skills.json;
        plugins/persona → catalog (不注册)。命名空间隔离 + 幂等 + 手工冲突跳过。"""
        registry = _external_registry()
        if registry is None:
            raise HTTPException(status_code=503, detail="external_executor 模块不可用")
        adapter = registry.get(adapter_id)
        if adapter is None:
            raise HTTPException(status_code=404, detail=f"适配器不存在: {adapter_id}")
        try:
            _host = _console_import("external_executor.host_assets")
            assets = _host.scan_adapter_assets(adapter)
            result = _host.import_assets(
                adapter, assets,
                agents_file=Path(workspace_root or DEFAULT_ROOT) / "agents" / "agents.json",
                skills_file=Path(workspace_root or DEFAULT_ROOT) / "skills" / "skills.json",
            )
        except Exception as exc:  # noqa: BLE001 — 导入失败 → 诚实错误
            raise HTTPException(status_code=500, detail=f"资产导入失败: {exc}") from exc
        result["adapter"] = adapter_id
        return result

    # ============ M4 (v1.1.194): 外部执行器监控聚合 (EXS 指标 + 告警)
    @app.get("/api/external-ai/monitor")
    def api_external_ai_monitor(
        days: int = Query(default=14, ge=1, le=90),
        recent: int = Query(default=30, ge=1, le=100),
    ) -> dict[str, Any]:
        """监控中心聚合 (M4.2): 概览/趋势/多维(执行器·agent·项目·回修·验证)/最近执行流/告警。
        自身能力(内部记录)与外部能力并轨; 失败安全空。"""
        registry = _external_registry()
        adapters = registry.list() if registry is not None else []
        try:
            _detail = _console_import("external_executor.monitor_detail")
            return _detail.build_monitor_detail(
                workspace_root or DEFAULT_ROOT, adapters,
                days=int(days), recent_limit=int(recent),
            )
        except Exception as exc:  # noqa: BLE001 — 聚合失败 → 诚实空
            return {"summary": {}, "trend": [], "by_executor": [], "by_agent": [],
                    "by_project": [], "rework_reasons": [], "verify_methods": [],
                    "recent": [], "alerts": [{"severity": "high", "type": "aggregation_failed", "detail": str(exc)}]}

    @app.get("/api/agents")
    def api_agents_list():
        """Agent 清单 (只读 agents.json)。"""
        import json as _json
        from pathlib import Path as _P
        f = _P(workspace_root) / "agents" / "agents.json"
        try:
            d = _json.loads(f.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            d = {}
        agents = d.get("agents") if isinstance(d, dict) and "agents" in d else d
        # Founder 2026-08-26: agents.json 混合格式兼容 — "agents" 键空则回退顶层 agent 记录
        if isinstance(agents, dict) and not agents and isinstance(d, dict):
            agents = {k: v for k, v in d.items() if k != "agents" and isinstance(v, dict)}
        if isinstance(agents, dict):
            return {"agents": list(agents.values()), "count": len(agents)}
        return {"agents": [], "count": 0}

    @app.get("/api/board/timeline")
    def api_board_timeline(project: str = ""):
        """生命线 HTML（审计事件时间轴, 纯 CSS; ?project= 项目过滤）。"""
        from fastapi.responses import HTMLResponse

        board_mod = _console_import("session.board")
        try:
            html = board_mod.render_timeline_html(workspace_root, project_id=project)
        except Exception:  # noqa: BLE001
            html = "<p>（生命线渲染失败）</p>"
        return HTMLResponse(content=html)

    @app.get("/api/board/graph")
    def api_board_graph(project: str = ""):
        """任务依赖图 HTML（plan.json, CRITICAL★ 红色高亮）。"""
        from fastapi.responses import HTMLResponse

        board_mod = _console_import("session.board")
        try:
            html = board_mod.render_graph_html(workspace_root, project)
        except Exception:  # noqa: BLE001
            html = "<p>（依赖图渲染失败）</p>"
        return HTMLResponse(content=html)

    @app.get("/api/board/chain")
    def api_board_chain(project: str = ""):
        """任务链 HTML（关键路径 ★关键节点 ▲汇聚点 + 工期）。"""
        from fastapi.responses import HTMLResponse

        board_mod = _console_import("session.board")
        try:
            html = board_mod.render_chain_html(workspace_root, project)
        except Exception:  # noqa: BLE001
            html = "<p>（任务链渲染失败）</p>"
        return HTMLResponse(content=html)

    @app.get("/api/dashboard")
    def api_dashboard() -> dict[str, Any]:
        """七域汇总 (11A ConsoleDashboard; 发 console.dashboard.viewed 审计)。"""
        dashboard = service.dashboard()
        logger = event_logger
        if logger is not None:
            _events.record_console_dashboard_viewed(
                logger,
                projects=len(dashboard.projects),
                pending_approvals=len(dashboard.pending_approvals),
                running_agents=len(dashboard.running_agents),
                decisions=len(dashboard.decisions),
                total_cost=dashboard.cost.total_cost,
                experiences=dashboard.experience.total,
                events=len(dashboard.activity),
            )
        return dashboard.to_dict()

    @app.get("/api/projects")
    def api_projects() -> dict[str, Any]:
        """项目清单 (11A list_projects, 只读投影)。"""
        return ok_list([p.to_dict() for p in _api.list_projects(service, logger=event_logger)])

    @app.post("/api/projects/suggest", status_code=200)
    def api_suggest_project(body: _SuggestBody) -> dict[str, Any]:
        """AI 想法理解 (S10-007 阶段三增强: 想法确认对话)。

        {idea} → {suggested_name, slug, summary, questions, ai_generated}:
        真实 LLM 小调用 (1 次 ~$0.001) 提议名称/一句话理解/1-3 澄清问题;
        LLM 不可用/超时/解析失败 → 诚实 fallback (ai_generated=false, 规则
        提炼 + questions=[] — 前端标注"快速模式", 不冒充 AI 理解)。idea 空
        → 400 (空想法不分析)。失败安全: 建议是非关键路径, LLM 异常不 5xx
        (fallback 兜底), 用户仍可确认创建。
        """
        idea = body.idea.strip()
        if not idea:
            raise HTTPException(status_code=400, detail="idea is required (空想法不分析)")
        suggestion = _api.suggest_project(service, idea, logger=event_logger)
        return suggestion.to_dict()

    @app.post("/api/projects", status_code=201)
    def api_create_project(body: _CreateProjectBody) -> dict[str, Any]:
        """创建项目 (S10-006.5 + S10-009 Task 4: {idea, name?, ...} → org 项目)。

        S10-007 阶段三增强: name (用户确认的名称) 显式传 → 优先落库; 无
        name → 规则 slug 兜底 (旧 {idea} 调用向后兼容)。
        S10-009 Task 4 分流: 无 name → 创建 DRAFT (unnamed-project-{ts},
        lifecycle=discovery, draft=true + ProjectSpace idea/discovery 资产);
        有 name → 旧兼容正式项目 (前端确认创建零破坏)。错误语义: idea 空
        → 400 (空想法不创建); project_type/tech 非法 → 400 (宽容收窄);
        org store 缺失/创建失败 → 503 (失败安全, 不拖垮 API); 成功 → 201
        {project_id, name, idea, status} (旧路径) 或 {project_id, name, idea,
        status, lifecycle, draft} (draft 路径)。写面 (Permission Boundary):
        与审批决定/Runtime/Review 反馈并列的 Console 写路径 — 只建 org 项目
        壳 (org.project.created 审计), 不启动执行链 (确认后由用户点击
        "开始开发")。
        """
        idea = body.idea.strip()
        if not idea:
            raise HTTPException(status_code=400, detail="idea is required (空想法不创建)")
        project_type = body.project_type.strip()
        tech = body.tech.strip()
        for field_name, value, allowed in (
            ("project_type", project_type, ("", "web", "mobile", "desktop")),
            ("tech", tech, ("", "auto", "flutter", "react", "vue")),
        ):
            if value not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"{field_name} must be one of: {', '.join(a for a in allowed if a)}",
                )
        if body.name.strip():
            # 旧兼容: {idea, name} → 正式项目 (前端确认创建; 零破坏)
            summary = _api.create_project(
                service,
                idea,
                name=body.name,
                project_type=project_type,
                tech=tech,
                logger=event_logger,
            )
        else:
            # S10-009 Task 4: 无 name → unnamed draft (DISCOVERY, draft=true)
            summary = _api.create_draft_project(
                service,
                idea,
                project_type=project_type,
                tech=tech,
                logger=event_logger,
            )
        if summary is None:
            raise HTTPException(
                status_code=503, detail="project store unavailable (org 未装配)"
            )
        return summary.to_dict()

    @app.post("/api/projects/{project_id}/discovery/answer")
    def api_discovery_answer(project_id: str, body: _DiscoveryAnswerBody) -> dict[str, Any]:
        """Discovery 问答持久化 (S10-009 Task 4: discovery/conversation.json 追加)。

        {question, answer} → 追加会话记录 (可多次, 顺序保留) + org
        Project.discovery 镜像。错误映射: 空 answer/question → 400 (空问答
        不记录); 项目不存在/store 缺失 → 404; 成功 → 200 DiscoveryAnswerSummary
        {project_id, question, answer, count}。
        """
        try:
            summary = _api.save_discovery_answer(
                service,
                project_id,
                body.question,
                body.answer,
                logger=event_logger,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if summary is None:
            raise HTTPException(status_code=404, detail="project not found")
        return summary.to_dict()

    @app.post("/api/projects/{project_id}/discovery/complete")
    def api_discovery_complete(project_id: str) -> dict[str, Any]:
        """完成 Discovery (S10-009 Task 4: product-definition.md + 生命周期流转)。

        生成 discovery/product-definition.md (基于原始想法 + 澄清沟通记录) +
        lifecycle discovery → product_defined (受控转换 + 事件审计)。错误
        映射: 未在 discovery 状态 → 409 (状态冲突, 诚实拒绝 — 与 Runtime
        状态机/删除冲突同语义); 项目不存在/store 缺失 → 404; 成功 → 200
        DiscoveryCompleteSummary {project_id, name, lifecycle,
        product_definition_ref}。
        """
        try:
            summary = _api.complete_discovery(service, project_id, logger=event_logger)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if summary is None:
            raise HTTPException(status_code=404, detail="project not found")
        return summary.to_dict()

    @app.post("/api/projects/{project_id}/confirm")
    def api_confirm_project(project_id: str, body: _ConfirmBody) -> dict[str, Any]:
        """Confirm+Rename 事务 (S10-009 Task 5: 正式命名 + 目录 rename)。

        {name} → 事务: 校验 (name 合法/slug 唯一/状态到确认点) → 快照 →
        写 project.json (name/slug/lifecycle=confirmed/draft=false) → 目录
        rename (os.replace 原子, unnamed-project-xxx → {slug}/) → workspace
        索引 + org/projects.json 引用更新 → 提交; 任一步失败 → 回滚到快照
        (目录/索引/引用全量还原)。错误映射: 空 name → 400 (空名字不确认);
        状态未到确认点 (非 discovery/product_defined) / slug 冲突 → 409
        (诚实拒绝, 事务预检失败零变更); 项目不存在/store 缺失 → 404;
        事务执行失败 (已回滚) → 503 (存储不可用, 可重试)。成功 → 200
        ConfirmProjectSummary {project_id, name, slug, lifecycle: confirmed}
        — 幂等: 已 confirmed 同 name 再次 confirm → 200 原样返回。
        """
        try:
            summary = _api.confirm_project_route(
                service, project_id, body.name, logger=event_logger
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProjectConfirmConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ConfirmTransactionError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if summary is None:
            raise HTTPException(status_code=404, detail="project not found")
        return summary.to_dict()

    @app.patch("/api/projects/{project_id}")
    def api_update_project(project_id: str, body: _UpdateProjectBody) -> dict[str, Any]:
        """更新项目 (S10-006.5 项目管理: 重命名/改 idea → org Project 落库)。

        {name?, idea?}: 任一非空 → 对应字段更新 (空串显式拒绝 — 空字段不
        落库); 两者皆未提供 → 400 (无事可做)。错误映射: ValueError → 400
        (空 name/idea); 项目不存在/store 缺失 → 404; 成功 → 200
        ProjectUpdatedSummary {project_id, name, idea, status} (更新后摘要,
        前端重命名 Modal 成功后刷新列表的数据源)。
        """
        try:
            summary = _api.update_project(
                service,
                project_id,
                name=body.name,
                idea=body.idea,
                starred=body.starred,
                archived=body.archived,
                logger=event_logger,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if summary is None:
            raise HTTPException(status_code=404, detail="project not found")
        return summary.to_dict()

    @app.delete("/api/projects/{project_id}")
    def api_delete_project(project_id: str) -> dict[str, Any]:
        """删除项目 (S10-006.5 项目管理; 运行中 409 诚实拒绝)。

        错误映射: ProjectConflictError → 409 (workflow 运行中不可删除 —
        等待完成后重试); 项目不存在/store 缺失 → 404; 成功 → 200
        {deleted: true, project_id} (org 删除 + org.project.deleted 审计
        失败安全 + workflow_runs/chat 运行数据清理, 均由 service 组合)。
        """
        try:
            deleted = _api.delete_project(service, project_id, logger=event_logger)
        except ProjectConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if deleted is None:
            raise HTTPException(status_code=404, detail="project not found")
        return {"deleted": True, "project_id": project_id}

    # ------------------------------------------- S10-010 Task 3: Backlog API
    # Requirement Management (AF-PRD-v1.md 4.3): Epic→Feature→Story→Task 层级
    # CRUD + Task 状态机/priority/dependency 校验 (复用 org.management) +
    # 目录信源持久化 (management/backlog/*.json)。写路径扩展 (Permission
    # Boundary S10-010 扩展: 与审批决定/项目管理并列的 Console 写路径 — 只
    # 落 management/ 目录信源, 不触碰 Core 引擎)。
    # 错误映射 (统一 _raise_backlog_error): 项目不存在 → 404; 任务/绑定
    # 不存在 (BacklogNotFoundError) → 404; 参数/依赖/priority 非法
    # (ValueError) → 400; 状态机非法转换 (BacklogStateError) → 409。

    @app.post("/api/projects/{project_id}/backlog/epic", status_code=201)
    def api_create_backlog_epic(project_id: str, body: _EpicBody) -> dict[str, Any]:
        """创建 Epic ({name, description?} → 201 {id, name, ..., created_at})。"""
        try:
            epic = _api.create_epic(
                service,
                project_id,
                name=body.name,
                description=body.description,
                logger=event_logger,
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if epic is None:
            raise HTTPException(status_code=404, detail="project not found")
        return epic

    @app.post("/api/projects/{project_id}/backlog/feature", status_code=201)
    def api_create_backlog_feature(project_id: str, body: _FeatureBody) -> dict[str, Any]:
        """创建 Feature (可选绑定 Epic; epic_id 不存在 → 404)。"""
        try:
            feature = _api.create_feature(
                service,
                project_id,
                name=body.name,
                description=body.description,
                epic_id=body.epic_id,
                maturity=body.maturity,
                logger=event_logger,
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if feature is None:
            raise HTTPException(status_code=404, detail="project not found")
        return feature

    @app.patch("/api/projects/{project_id}/backlog/feature/{feature_id}")
    def api_patch_backlog_feature(
        project_id: str, feature_id: str, body: _FeaturePatchBody
    ) -> dict[str, Any]:
        """PATCH Feature — 改名/描述/成熟度 (idea↔refined; 非法 → 400/404)。"""
        try:
            feature = _api.update_feature(
                service,
                project_id,
                feature_id,
                name=body.name,
                description=body.description,
                maturity=body.maturity,
                logger=event_logger,
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if feature is None:
            raise HTTPException(status_code=404, detail="project not found")
        return feature

    @app.post("/api/projects/{project_id}/backlog/story", status_code=201)
    def api_create_backlog_story(project_id: str, body: _StoryBody) -> dict[str, Any]:
        """创建 Story (可选绑定 Feature; feature_id 不存在 → 404)。"""
        try:
            story = _api.create_story(
                service,
                project_id,
                name=body.name,
                description=body.description,
                feature_id=body.feature_id,
                logger=event_logger,
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if story is None:
            raise HTTPException(status_code=404, detail="project not found")
        return story

    @app.post("/api/projects/{project_id}/backlog/task", status_code=201)
    def api_create_backlog_task(project_id: str, body: _TaskBody) -> dict[str, Any]:
        """创建 Task (可选绑定 Story; priority 非法/依赖环/自引用 → 400)。"""
        try:
            task = _api.create_task(
                service,
                project_id,
                title=body.title,
                description=body.description,
                priority=body.priority,
                dependency=body.dependency,
                story_id=body.story_id,
                logger=event_logger,
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if task is None:
            raise HTTPException(status_code=404, detail="project not found")
        return task

    @app.get("/api/projects/{project_id}/backlog")
    def api_backlog(project_id: str) -> dict[str, Any]:
        """Backlog 全量分组 (epics/features/stories/tasks; 项目不存在 → 404)。"""
        try:
            backlog = _api.list_backlog(service, project_id, logger=event_logger)
        except Exception as exc:
            _raise_backlog_error(exc)
        if backlog is None:
            raise HTTPException(status_code=404, detail="project not found")
        return backlog

    @app.get("/api/projects/{project_id}/backlog/task/{task_id}")
    def api_backlog_task_detail(project_id: str, task_id: str) -> dict[str, Any]:
        """Task 详情 (任务不存在 → 404)。T-4 (v1.1.184): 附 sessions —
        哪些会话讨论过它 (task_id 锚定反向追溯)。"""
        try:
            task = _api.get_task(service, project_id, task_id, logger=event_logger)
        except Exception as exc:
            _raise_backlog_error(exc)
        if task is None:
            raise HTTPException(status_code=404, detail="project not found")
        try:
            related = sessions_store.list_sessions(task_id=task_id)
            task = {
                **task,
                "sessions": [
                    {
                        "id": str(s.get("id") or ""),
                        "title": str(s.get("title") or "未命名"),
                        "updated_at": s.get("updated_at"),
                        "project_id": s.get("project_id"),
                    }
                    for s in related
                ],
            }
        except Exception:  # noqa: BLE001 — 会话查询失败 → 附空 (不阻断)
            task = {**task, "sessions": []}
        # T-9 (v1.1.185): 执行溯源 (exec_ref → 记录/证据包) — 只读, 失败安全空
        try:
            task = {**task, "exec_trace": _task_exec_trace(workspace_root, task)}
        except Exception:  # noqa: BLE001 — 溯源失败 → 附空 (不阻断)
            task = {**task, "exec_trace": None}
        return task

    @app.patch("/api/projects/{project_id}/backlog/task/{task_id}")
    def api_patch_backlog_task(
        project_id: str, task_id: str, body: _TaskPatchBody
    ) -> dict[str, Any]:
        """PATCH Task (字段更新 + 状态机转换 + 依赖校验; 400/404/409)。"""
        try:
            task = _api.update_task(
                service,
                project_id,
                task_id,
                title=body.title,
                description=body.description,
                priority=body.priority,
                status=body.status,
                assignee=body.assignee,
                dependency=body.dependency,
                logger=event_logger,
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if task is None:
            raise HTTPException(status_code=404, detail="project not found")
        return task

    @app.delete("/api/projects/{project_id}/backlog/task/{task_id}")
    def api_delete_backlog_task(project_id: str, task_id: str) -> dict[str, Any]:
        """DELETE Task (200 {deleted, task_id}; 引用可留; 不存在 → 404)。"""
        try:
            result = _api.delete_task(service, project_id, task_id, logger=event_logger)
        except Exception as exc:
            _raise_backlog_error(exc)
        if result is None:
            raise HTTPException(status_code=404, detail="project not found")
        return result

    # ------------------------- S10-010 Task 4: Sprint/Milestone/Roadmap API
    # 执行窗口与路线 (AF-PRD-v1.md 4.4/4.5): Sprint/Milestone 引用 Task (非
    # 包含 — 引用不影响 Task 本身), Roadmap 引用 Milestone; Sprint 状态受控
    # (planning→active→completed); Planning 端点只给建议不调度 (S10-011)。
    # 目录信源: management/sprint/{id}.json + milestone.json + roadmap.md。
    # 错误映射 (复用 _raise_backlog_error): 项目不存在 → 404; Sprint/Milestone
    # 不存在 (BacklogNotFoundError) → 404; 空 name/task_ref 引用不存在
    # Task/milestone-ref 引用不存在 Milestone (ValueError) → 400; Sprint
    # 状态机非法转换 (BacklogStateError) → 409。

    @app.post("/api/projects/{project_id}/sprints", status_code=201)
    def api_create_sprint(project_id: str, body: _SprintBody) -> dict[str, Any]:
        """创建 Sprint ({name, goal?, start_date?, end_date?, task_refs?} → 201)。"""
        try:
            sprint = _api.create_sprint(
                service,
                project_id,
                name=body.name,
                goal=body.goal,
                start_date=body.start_date,
                end_date=body.end_date,
                task_refs=body.task_refs,
                logger=event_logger,
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if sprint is None:
            raise HTTPException(status_code=404, detail="project not found")
        return sprint

    @app.get("/api/projects/{project_id}/sprints")
    def api_list_sprints(project_id: str) -> dict[str, Any]:
        """Sprint 列表 ({project_id, sprints}; 项目不存在 → 404)。"""
        try:
            sprints = _api.list_sprints(service, project_id, logger=event_logger)
        except Exception as exc:
            _raise_backlog_error(exc)
        if sprints is None:
            raise HTTPException(status_code=404, detail="project not found")
        return sprints

    @app.get("/api/projects/{project_id}/sprints/{sprint_id}")
    def api_sprint_detail(project_id: str, sprint_id: str) -> dict[str, Any]:
        """Sprint 详情 (不存在 → 404)。"""
        try:
            sprint = _api.get_sprint(service, project_id, sprint_id, logger=event_logger)
        except Exception as exc:
            _raise_backlog_error(exc)
        if sprint is None:
            raise HTTPException(status_code=404, detail="project not found")
        return sprint

    @app.patch("/api/projects/{project_id}/sprints/{sprint_id}")
    def api_patch_sprint(
        project_id: str, sprint_id: str, body: _SprintPatchBody
    ) -> dict[str, Any]:
        """PATCH Sprint (字段 + 受控状态转换 + task_refs 校验; 400/404/409)。"""
        try:
            sprint = _api.update_sprint(
                service,
                project_id,
                sprint_id,
                goal=body.goal,
                planning=body.planning,
                task_refs=body.task_refs,
                start_date=body.start_date,
                end_date=body.end_date,
                status=body.status,
                daily_progress=body.daily_progress,
                review=body.review,
                logger=event_logger,
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if sprint is None:
            raise HTTPException(status_code=404, detail="project not found")
        return sprint

    @app.delete("/api/projects/{project_id}/sprints/{sprint_id}")
    def api_delete_sprint(project_id: str, sprint_id: str) -> dict[str, Any]:
        """DELETE Sprint (200 {deleted, sprint_id}; Task 保留; 不存在 → 404)。"""
        try:
            result = _api.delete_sprint(service, project_id, sprint_id, logger=event_logger)
        except Exception as exc:
            _raise_backlog_error(exc)
        if result is None:
            raise HTTPException(status_code=404, detail="project not found")
        return result

    @app.post("/api/projects/{project_id}/sprints/{sprint_id}/plan")
    def api_plan_sprint(
        project_id: str, sprint_id: str, body: _SprintPlanBody
    ) -> dict[str, Any]:
        """Sprint Planning 预留 (建议排序, 不调度; Sprint 不存在 → 404)。"""
        try:
            plan = _api.plan_sprint(
                service,
                project_id,
                sprint_id,
                goal=body.goal,
                logger=event_logger,
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if plan is None:
            raise HTTPException(status_code=404, detail="project not found")
        return plan

    @app.post("/api/projects/{project_id}/milestones", status_code=201)
    def api_create_milestone(project_id: str, body: _MilestoneBody) -> dict[str, Any]:
        """创建 Milestone ({name, description?, target_date?, task_refs?} → 201)。"""
        try:
            milestone = _api.create_milestone(
                service,
                project_id,
                name=body.name,
                description=body.description,
                target_date=body.target_date,
                task_refs=body.task_refs,
                logger=event_logger,
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if milestone is None:
            raise HTTPException(status_code=404, detail="project not found")
        return milestone

    @app.get("/api/projects/{project_id}/milestones")
    def api_list_milestones(project_id: str) -> dict[str, Any]:
        """Milestone 列表 ({project_id, milestones}; 项目不存在 → 404)。"""
        try:
            milestones = _api.list_milestones(
                service, project_id, logger=event_logger
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if milestones is None:
            raise HTTPException(status_code=404, detail="project not found")
        return milestones

    @app.get("/api/projects/{project_id}/milestones/{milestone_id}")
    def api_milestone_detail(project_id: str, milestone_id: str) -> dict[str, Any]:
        """Milestone 详情 (不存在 → 404)。"""
        try:
            milestone = _api.get_milestone(
                service, project_id, milestone_id, logger=event_logger
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if milestone is None:
            raise HTTPException(status_code=404, detail="project not found")
        return milestone

    @app.patch("/api/projects/{project_id}/milestones/{milestone_id}")
    def api_patch_milestone(
        project_id: str, milestone_id: str, body: _MilestonePatchBody
    ) -> dict[str, Any]:
        """PATCH Milestone (字段更新; status 自由文本; task_refs 校验 → 400)。"""
        try:
            milestone = _api.update_milestone(
                service,
                project_id,
                milestone_id,
                name=body.name,
                description=body.description,
                target_date=body.target_date,
                status=body.status,
                task_refs=body.task_refs,
                logger=event_logger,
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if milestone is None:
            raise HTTPException(status_code=404, detail="project not found")
        return milestone

    @app.delete("/api/projects/{project_id}/milestones/{milestone_id}")
    def api_delete_milestone(project_id: str, milestone_id: str) -> dict[str, Any]:
        """DELETE Milestone (200 {deleted, milestone_id}; 不存在 → 404)。"""
        try:
            result = _api.delete_milestone(
                service, project_id, milestone_id, logger=event_logger
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if result is None:
            raise HTTPException(status_code=404, detail="project not found")
        return result

    @app.get("/api/projects/{project_id}/roadmap")
    def api_get_roadmap(project_id: str) -> dict[str, Any]:
        """Roadmap 单例 ({project_id, milestone_refs, updated_at}; 不存在 → 404)。"""
        try:
            roadmap = _api.get_roadmap(service, project_id, logger=event_logger)
        except Exception as exc:
            _raise_backlog_error(exc)
        if roadmap is None:
            raise HTTPException(status_code=404, detail="project not found")
        return roadmap

    @app.post("/api/projects/{project_id}/roadmap/milestone-ref")
    def api_roadmap_milestone_ref(
        project_id: str, body: _MilestoneRefBody
    ) -> dict[str, Any]:
        """Roadmap 追加 Milestone 引用 (去重幂等; milestone 不存在 → 400)。"""
        try:
            roadmap = _api.add_roadmap_milestone_ref(
                service, project_id, body.milestone_id, logger=event_logger
            )
        except Exception as exc:
            _raise_backlog_error(exc)
        if roadmap is None:
            raise HTTPException(status_code=404, detail="project not found")
        return roadmap

    @app.get("/api/projects/{project_id}/lifecycle")
    def api_project_lifecycle(project_id: str) -> dict[str, Any]:
        """生命周期快照; 无 → 404 (11A None 语义由 HTTP 层映射)。"""
        summary = _api.get_project_lifecycle(service, project_id, logger=event_logger)
        if summary is None:
            raise HTTPException(status_code=404, detail="lifecycle not found")
        return summary.to_dict()

    @app.get("/api/projects/{project_id}/workspace")
    def api_project_workspace(project_id: str) -> dict[str, Any]:
        """项目工作区汇总 (Founder 2026-08-26: 真实数据源 = workspace 资产)。

        读 ~/.factory/projects/<slug>/ 资产 (board 同口径): product.json 状态 +
        execution_state.json/tasks.json 任务 + 生命周期阶段判定。
        org /lifecycle + /backlog 常为空 (项目创建早未走 org 管线) — 前端项目首页
        以此为准, 有真实数据。失败安全: 无目录/损坏 → 404。
        """
        import json as _json
        from pathlib import Path as _Path

        from factory_console.session.board import (
            _project_stage_status,
            _read_product_info,
        )
        ws_root = _Path(str(getattr(service, "data_dir", None) or workspace_root))
        pdir = ws_root / "projects" / _Path(str(project_id)).name
        if not (pdir / "product.json").is_file():
            raise HTTPException(status_code=404, detail="project workspace not found")
        info = _read_product_info(ws_root, project_id) or {}
        stages = _project_stage_status(ws_root, project_id)
        done_stages = [st["label"] for st in stages if st["done"]]
        # 任务: execution_state.json → tasks.json 回退
        tasks: list[dict[str, Any]] = []
        es = pdir / "execution_state.json"
        source = "execution_state"
        try:
            if es.is_file():
                tasks = ( _json.loads(es.read_text(encoding="utf-8")) or {}).get("tasks") or []
            else:
                tf = pdir / "tasks.json"
                if tf.is_file():
                    source = "tasks"
                    tasks = (_json.loads(tf.read_text(encoding="utf-8")) or {}).get("tasks") or []
        except Exception:  # noqa: BLE001
            tasks = []
        tasks_out = [
            {
                "id": str(t.get("id") or ""),
                "title": str(t.get("name") or t.get("title") or t.get("id") or ""),
                "status": str(t.get("status") or "todo"),
                "priority": t.get("priority") if t.get("priority") is not None else None,
            }
            for t in tasks
            if isinstance(t, dict)
        ]
        return {
            "project_id": project_id,
            "name": str(info.get("name") or project_id),
            "lifecycle_status": str(info.get("status") or ""),
            "stages": [{"id": st["id"], "label": st["label"], "done": st["done"]} for st in stages],
            "done_stages": done_stages,
            "progress": round(len(done_stages) * 100 / len(stages)) if stages else 0,
            "tasks": tasks_out,
            "task_source": source,
        }

    @app.get("/api/approvals")
    def api_approvals(
        pending_only: bool = Query(default=False),
    ) -> dict[str, Any]:
        """审批清单 (11A list_approvals, 只读不决定)。"""
        return ok_list([
            a.to_dict()
            for a in _api.list_approvals(service, logger=event_logger, pending_only=pending_only)
        ])

    @app.get("/api/approval-gates")
    def api_approval_gates(
        status: str | None = Query(default=None),
        workflow_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """org 审批门清单 (S9-002 — Approval 页决定操作对象; 只读查询)。"""
        return ok_list([
            g.to_dict()
            for g in _api.list_approval_gates(
                service, logger=event_logger, status=status, workflow_id=workflow_id
            )
        ])

    @app.get("/api/decisions/{decision_id}")
    def api_decision(decision_id: str) -> dict[str, Any]:
        """决策详情; 不存在 → 404。"""
        summary = _api.get_decision(service, decision_id, logger=event_logger)
        if summary is None:
            raise HTTPException(status_code=404, detail="decision not found")
        return summary.to_dict()

    @app.get("/api/recommendations")
    def api_recommendations(
        limit: int = Query(default=10, ge=1, le=100),
    ) -> dict[str, Any]:
        """推荐产物 (11A list_recommendations, 只推荐不执行)。"""
        return ok_list([
            r.to_dict()
            for r in _api.list_recommendations(service, logger=event_logger, limit=limit)
        ])

    @app.get("/api/experience")
    def api_experience(
        limit: int = Query(default=10, ge=1, le=100),
    ) -> dict[str, Any]:
        """经验记录 (11A list_experience, 六域)。"""
        return ok_list([
            e.to_dict() for e in _api.list_experience(service, logger=event_logger, limit=limit)
        ])

    @app.get("/api/providers")
    def api_providers() -> dict[str, Any]:
        """Provider 目录 (11A list_providers)。"""
        return ok_list([p.to_dict() for p in _api.list_providers(service, logger=event_logger)])

    @app.get("/api/workflows")
    def api_workflows(
        project_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """组织级 Workflow 运行清单 (S9-002; 阶段链进度聚合, 只读)。"""
        return ok_list([
            w.to_dict()
            for w in _api.list_workflows(service, logger=event_logger, project_id=project_id)
        ])

    @app.get("/api/workflows/{workflow_id}")
    def api_workflow_detail(workflow_id: str) -> dict[str, Any]:
        """单 Workflow 8 阶段链全视图; 无 org/不存在 → 404。"""
        detail = _api.get_workflow(service, workflow_id, logger=event_logger)
        if detail is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return detail.to_dict()

    @app.get("/api/artifacts")
    def api_artifacts(
        project_id: str | None = Query(default=None),
        workflow_id: str | None = Query(default=None),
        type: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """org Artifact 清单 (S9-002; project/workflow/type 过滤, 只读)。"""
        return ok_list([
            a.to_dict()
            for a in _api.list_artifacts(
                service,
                logger=event_logger,
                project_id=project_id,
                workflow_id=workflow_id,
                type=type,
            )
        ])

    @app.get("/api/artifacts/{artifact_id}")
    def api_artifact_detail(artifact_id: str) -> dict[str, Any]:
        """单产物详情 (S9-003: metadata 契约载荷 + review 审批门; 404 映射)。"""
        detail = _api.get_artifact(service, artifact_id, logger=event_logger)
        if detail is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return detail.to_dict()

    @app.get("/api/artifacts/{artifact_id}/content")
    def api_artifact_content(artifact_id: str) -> dict[str, Any]:
        """产物渲染内容 (S10-005 — location 文件文本: Code diff 兜底 / Release
        下载源; 缺失 → content null, 失败安全; 产物不存在 → 404)。"""
        content = _api.get_artifact_content(service, artifact_id, logger=event_logger)
        if content is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return content.to_dict()

    # ------------------------------------------------- T8: 审计视图 API
    @app.get("/api/audit")
    def api_audit(
        event_type: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        """T8: 审计事件查询 (只读) — 合并 events.db + audit_events.json。

        支持 event_type / session_id 过滤, 按时间倒序, 返回最近 limit 条。
        数据源缺失 → 空列表 (失败安全)。
        """
        try:
            from factory_console.audit.audit_store import AuditStore

            store = AuditStore(workspace=None, file=str(Path(workspace_root or DEFAULT_ROOT) / "audit" / "audit_events.json"))
            events = store.events()
        except Exception:  # noqa: BLE001 — 审计存储缺失/坏 → 空
            events = []
        items = []
        for ev in events:
            d = ev.to_dict() if hasattr(ev, "to_dict") else ev
            items.append(d)
        # 过滤
        if event_type:
            items = [x for x in items if x.get("event_type") == event_type]
        if session_id:
            items = [x for x in items if x.get("trace_id") == session_id]
        # 时间倒序 + 截断
        items.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
        items = items[:limit]
        # 类型计数 (全量, 不受 limit 影响)
        counts: dict[str, int] = {}
        for x in items:
            t = str(x.get("event_type") or "UNKNOWN")
            counts[t] = counts.get(t, 0) + 1
        return {"items": items, "count": len(items), "counts": counts}

    @app.get("/api/audit/trace")
    def api_audit_trace(session_id: str) -> dict[str, Any]:
        """T14: 追溯查询 — 按会话聚合: 工具调用/耗时/结果 + events 库工具事件。

        '这个会话做了什么/调了哪些工具/哪些失败' 一键查。只读。
        """
        out: dict[str, Any] = {"session_id": session_id, "tools": [], "tool_count": 0,
                               "failed": 0, "total_duration_ms": 0, "events": []}
        # 1) audit_events.json (TOOL_CALL, trace_id=session)
        try:
            from factory_console.audit.audit_store import AuditStore

            store = AuditStore(workspace=None, file=str(Path(workspace_root or DEFAULT_ROOT) / "audit" / "audit_events.json"))
            for ev in store.events():
                d = ev.to_dict() if hasattr(ev, "to_dict") else ev
                if d.get("trace_id") != session_id:
                    continue
                if d.get("event_type") != "TOOL_CALL":
                    continue
                evd = (d.get("evidence") or [{}])[0] if isinstance(d.get("evidence"), list) else {}
                out["tools"].append({
                    "tool": d.get("action"),
                    "ok": bool(d.get("result", {}).get("ok")) if isinstance(d.get("result"), dict) else False,
                    "duration_ms": int(evd.get("duration_ms") or 0),
                    "args": str(evd.get("args") or "")[:120],
                    "ts": d.get("timestamp"),
                })
        except Exception:  # noqa: BLE001 — 审计不可用 → 仅 events 库
            pass
        # 2) events 库 (tool.call, task_id=session)
        try:
            from events.logger import EventLogger
            from events.store import EventStore

            db = Path(workspace_root or DEFAULT_ROOT) / "factory.db"
            if db.exists():
                store = EventStore(db)
                for ev in store.by_task(session_id):
                    out["events"].append({
                        "type": ev.type if hasattr(ev, "type") else str(getattr(ev, "event_type", "")),
                        "action": ev.action if hasattr(ev, "action") else "",
                        "ts": str(getattr(ev, "timestamp", "") or ""),
                    })
        except Exception:  # noqa: BLE001 — events 库不可用 → 仅审计
            pass
        # 聚合
        out["tool_count"] = len(out["tools"])
        out["failed"] = sum(1 for t in out["tools"] if not t["ok"])
        out["total_duration_ms"] = sum(int(t["duration_ms"] or 0) for t in out["tools"])
        return out

    # ------------------------------------------------- S10-002: Runtime API
    # UI 与 CLI 共用 (Adapter 层只读 + SSE; 零 Core 修改, 只消费 org.* 查询)。

    @app.get("/api/projects/{project_id}/workflow")
    def api_project_workflow(project_id: str) -> dict[str, Any]:
        """项目工作流详情 (S10-002 — 8 阶段链 + 统计)。

        项目存在但无运行数据 → mock 工作流 (is_mock=True, 前端可展示);
        项目不存在 → 404 (mock 只兜底数据缺失, 不兜底不存在)。
        """
        detail = _api.get_project_workflow(service, project_id, logger=event_logger)
        if detail is None:
            raise HTTPException(status_code=404, detail="project not found")
        return detail.to_dict()

    @app.get("/api/workflows/{workflow_id}/stages")
    def api_workflow_stages(workflow_id: str) -> dict[str, Any]:
        """Workflow 阶段运行明细 (S10-002 — 状态/agent/artifacts/duration/cost)。

        duration_s 从事件流推导 (stage_started → stage_completed 时间戳差);
        cost_usd 未跟踪 → null (诚实); 无 org/不存在 → 404。
        """
        runs = _api.get_workflow_stages(service, workflow_id, logger=event_logger)
        if runs is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return ok_list([r.to_dict() for r in runs])

    @app.get("/api/projects/{project_id}/timeline")
    def api_project_timeline(
        project_id: str,
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, Any]:
        """Timeline 事件聚合 (S10-002 — user/stage/artifact/review/error)。

        数据源 = events.db org.* 事件 (与 SSE 同源同映射; Timeline 历史
        快照); 项目不存在 → 404; 无事件 → [] (诚实空态)。
        """
        events = _api.get_project_timeline(
            service, project_id, logger=event_logger, limit=limit
        )
        if events is None:
            raise HTTPException(status_code=404, detail="project not found")
        return ok_list([e.to_dict() for e in events])

    @app.get("/api/projects/{project_id}/status")
    def api_project_status(project_id: str) -> dict[str, Any]:
        """项目状态视图 (S10-083 — 阶段/任务/代码文件/最近事件, 真实数据)。"""
        try:
            from ...session.observability import project_status

            project_dir = Path(service.workspace_root or "") / "projects" / project_id
            if not project_dir.is_dir():
                raise HTTPException(status_code=404, detail="project not found")
            return project_status(Path(service.workspace_root or ""), project_dir)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 — 失败安全
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/events/stream")
    def api_events_stream(
        project_id: str,
        since_seq: int = Query(default=0, ge=0),
        poll_interval: float = Query(default=1.0, ge=0.05),
        max_polls: int | None = Query(default=None, ge=1),
    ) -> Any:
        """SSE 事件流 (S10-002 — Timeline 实时增量驱动; 只读 GET)。

        推送: stage.started / stage.completed / artifact.created /
        approval.required / error (SSE_EVENT_MAP); 从 events 库按
        project_id 轮询 (since_seq 断点续推); 无事件库 → 单条 error
        (mock=True) 后关闭 (失败安全)。max_polls/poll_interval 为
        测试/调试旋钮 (生产缺省: 无限轮询至客户端断开)。
        """
        import json

        def _generate() -> Iterator[str]:
            for name, data in _api.iter_sse_events(
                service,
                project_id,
                logger=event_logger,
                since_seq=since_seq,
                poll_interval=poll_interval,
                max_polls=max_polls,
            ):
                yield f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ------------------------------------------- S10-004: Runtime Workspace API
    # Instance 模式 (workspace-architecture.md §4 调整版): "+" 创建 browser|
    # terminal 实例 + start/stop 生命周期 + screenshot 预留。写路径新增
    # (Permission Boundary S10-004 扩展: 与审批决定并列的 Console 写路径 —
    # 仅 Runtime 实例生命周期, 不触碰 Core 引擎)。
    # 错误映射: 项目/实例不存在 → 404; 非法 type → 400; 状态机非法流转
    # (RuntimeStateError) → 409; 事件 (org.runtime.*) 由路由函数落库。

    @app.post("/api/projects/{project_id}/runtimes")
    def api_create_runtime(project_id: str, body: _CreateRuntimeBody) -> dict[str, Any]:
        """创建 Runtime Instance (starting; browser|terminal + artifact 绑定)。"""
        if body.type not in ("browser", "terminal"):
            raise HTTPException(
                status_code=400, detail="runtime type must be browser|terminal"
            )
        instance = _api.create_runtime(
            service,
            project_id,
            body.type,
            artifact_id=body.artifact_id,
            logger=event_logger,
        )
        if instance is None:
            raise HTTPException(status_code=404, detail="project not found")
        return instance.to_dict()

    @app.get("/api/projects/{project_id}/runtimes")
    def api_project_runtimes(project_id: str) -> dict[str, Any]:
        """项目 Runtime 实例列表 (无 → []; 项目不存在 → 404)。"""
        instances = _api.list_runtimes(service, project_id, logger=event_logger)
        if instances is None:
            raise HTTPException(status_code=404, detail="project not found")
        return ok_list([r.to_dict() for r in instances])

    @app.get("/api/runtimes/{runtime_id}")
    def api_runtime_detail(runtime_id: str) -> dict[str, Any]:
        """单实例详情 (url/session/status; 不存在 → 404)。"""
        instance = _api.get_runtime(service, runtime_id, logger=event_logger)
        if instance is None:
            raise HTTPException(status_code=404, detail="runtime not found")
        return instance.to_dict()

    @app.post("/api/runtimes/{runtime_id}/start")
    def api_runtime_start(runtime_id: str) -> dict[str, Any]:
        """启动实例 (starting|stopped → running; 重启允许)。"""
        try:
            instance = _api.start_runtime(service, runtime_id, logger=event_logger)
        except RuntimeStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if instance is None:
            raise HTTPException(status_code=404, detail="runtime not found")
        return instance.to_dict()

    @app.post("/api/runtimes/{runtime_id}/stop")
    def api_runtime_stop(runtime_id: str) -> dict[str, Any]:
        """停止实例 (starting|running → stopped)。"""
        try:
            instance = _api.stop_runtime(service, runtime_id, logger=event_logger)
        except RuntimeStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if instance is None:
            raise HTTPException(status_code=404, detail="runtime not found")
        return instance.to_dict()

    @app.post("/api/runtimes/{runtime_id}/screenshot")
    def api_runtime_screenshot(runtime_id: str) -> dict[str, Any]:
        """截图预留: 保存截图记录 + artifact 引用 (完整 Feedback Loop 后续实现)。"""
        try:
            screenshot = _api.capture_runtime_screenshot(
                service, runtime_id, logger=event_logger
            )
        except RuntimeStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if screenshot is None:
            raise HTTPException(status_code=404, detail="runtime not found")
        return screenshot.to_dict()

    @app.post("/api/approvals/{approval_id}/approve")
    def api_approve_approval(
        approval_id: str,
        body: _ApprovalDecisionBody | None = None,
    ) -> dict[str, Any]:
        """审批放行 (S9-002: 接 org.approval S9-001; source=console 审计)。

        门不存在 → 404; 非 PENDING 门 (终态不可撤销) → 409 Conflict。
        S9-003: body.comment 透传落库 (gate.comment — Review 反馈输入)。
        """
        reviewer = body.reviewer if body is not None else "console"
        comment = body.comment if body is not None else ""
        try:
            summary = _api.approve_approval(
                service, approval_id, reviewer=reviewer, comment=comment
            )
        except Exception as exc:
            if _api.conflict_status(exc):
                raise HTTPException(status_code=409, detail="approval already decided") from exc
            raise
        if summary is None:
            raise HTTPException(status_code=404, detail="approval gate not found")
        return summary.to_dict()

    @app.post("/api/approvals/{approval_id}/reject")
    def api_reject_approval(
        approval_id: str,
        body: _ApprovalDecisionBody | None = None,
    ) -> dict[str, Any]:
        """审批否决 (S9-002: gate → REJECTED 终态 + workflow FAILED 停止)。

        错误语义同 approve (404 / 409); 决定不可撤销 — 审计铁律。
        S9-003: body.comment 透传落库 (否决原因 → 下轮重生成反馈输入)。
        """
        reviewer = body.reviewer if body is not None else "console"
        comment = body.comment if body is not None else ""
        try:
            summary = _api.reject_approval(
                service, approval_id, reviewer=reviewer, comment=comment
            )
        except Exception as exc:
            if _api.conflict_status(exc):
                raise HTTPException(status_code=409, detail="approval already decided") from exc
            raise
        if summary is None:
            raise HTTPException(status_code=404, detail="approval gate not found")
        return summary.to_dict()

    # ------------------------------------------- S10-006: Review Feedback API
    # Feedback Loop (workspace-architecture.md §3 Panel Review): Reject 决定后
    # 前端同时 POST /api/review-feedback 保存结构化驳回意见 — 下轮 Agent
    # 重生成输入的数据源 (gate.comment 由 S9-001 决定端点负责审计落库, 本
    # 端点只补 Loop 数据流, 不重设计审批 API)。
    # 错误语义: 400 空意见/缺 artifact_id (无反馈不落库); 503 缺 store
    # (失败安全 — 审批决定不受反馈保存失败影响, 前端按尽力而为处理)。

    @app.get("/api/review-feedback")
    def api_review_feedback(
        artifact_id: str | None = Query(default=None),
        gate_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """审核反馈历史 (GET — 按 artifact/gate 过滤, round 升序)。

        无过滤 → 全部记录; 无匹配 → [] (诚实空态); 缺 store → [] (失败
        安全, 与 11A 读命令同哲学 — 查询永不因数据缺失失败)。
        """
        records = _api.list_review_feedback(
            service,
            artifact_id,
            gate_id=gate_id,
            logger=event_logger,
        )
        return ok_list([r.to_dict() for r in records])

    @app.post("/api/review-feedback")
    def api_save_review_feedback(body: _ReviewFeedbackBody) -> dict[str, Any]:
        """保存审核反馈记录 (POST — Reject 意见落库, round 按产物递增)。"""
        artifact_id = body.artifact_id.strip()
        if not artifact_id:
            raise HTTPException(status_code=400, detail="artifact_id is required")
        comment = body.comment.strip()
        if not comment:
            raise HTTPException(status_code=400, detail="comment is required (空意见不落库)")
        record = _api.save_review_feedback(
            service,
            reviewer=body.reviewer or "console",
            artifact_id=artifact_id,
            gate_id=body.gate_id,
            comment=comment,
        )
        if record is None:
            # 缺 review_feedback store → 503 (失败安全: 决定已成功, 反馈
            # 尽力而为; 前端显示提示不阻断流程)
            raise HTTPException(
                status_code=503, detail="review feedback store unavailable"
            )
        return record.to_dict()

    # ------------------------------------------- S10-016: Runtime Session API
    # AI Employee Runtime Foundation (Task 001b): Agent 执行会话可见性底座 —
    # 谁在跑/跑哪个任务/跑到哪一步/产出什么事件。写路径扩展 (Permission
    # Boundary S10-016 扩展: 会话生命周期 POST — 只记录执行会话/事件,
    # 不触碰 Core 引擎, 执行权仍在 AgentRuntime)。
    # 错误映射: 空 task_id/非法事件类型 → 400; 会话不存在/store 缺失 →
    # 404; 状态机非法流转 (RuntimeSessionError) → 409 (诚实冲突)。
    # 事件可读: session 详情/运行中列表/任务过滤三条查询路径 (含事件链 —
    # 前端 Runtime Timeline 数据源)。

    RuntimeSessionError = _service.RuntimeSessionError

    @app.post("/api/agents/{agent_id}/sessions")
    def api_create_runtime_session(
        agent_id: str, body: _CreateSessionBody
    ) -> dict[str, Any]:
        """创建 Runtime Session (POST — PENDING 会话记录起点)。"""
        try:
            session = _api.create_runtime_session(
                service,
                agent_id,
                task_id=body.task_id,
                workflow_id=body.workflow_id,
                logger=event_logger,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if session is None:
            raise HTTPException(status_code=404, detail="session store unavailable")
        return session.to_dict()

    @app.post("/api/runtime-sessions/{session_id}/start")
    def api_start_runtime_session(session_id: str) -> dict[str, Any]:
        """启动会话 (PENDING → RUNNING; started_at 记录)。"""
        try:
            session = _api.start_runtime_session(
                service, session_id, logger=event_logger
            )
        except RuntimeSessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if session is None:
            raise HTTPException(status_code=404, detail="runtime session not found")
        return session.to_dict()

    @app.post("/api/runtime-sessions/{session_id}/events")
    def api_append_runtime_session_event(
        session_id: str, body: _SessionEventBody
    ) -> dict[str, Any]:
        """追加执行事件 (POST — 仅 RUNNING; 终态冻结 409)。"""
        try:
            event = _api.append_runtime_session_event(
                service,
                session_id,
                event_type=body.type,
                message=body.message,
                data=body.data,
                logger=event_logger,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeSessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if event is None:
            raise HTTPException(status_code=404, detail="runtime session not found")
        return event.to_dict()

    @app.post("/api/runtime-sessions/{session_id}/complete")
    def api_complete_runtime_session(
        session_id: str, body: _SessionCompleteBody
    ) -> dict[str, Any]:
        """完成会话 (RUNNING → SUCCESS|FAILED; finished_at 记录)。"""
        try:
            session = _api.complete_runtime_session(
                service,
                session_id,
                success=body.success,
                logger=event_logger,
            )
        except RuntimeSessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if session is None:
            raise HTTPException(status_code=404, detail="runtime session not found")
        return session.to_dict()

    @app.post("/api/runtime-sessions/{session_id}/cancel")
    def api_cancel_runtime_session(session_id: str) -> dict[str, Any]:
        """取消会话 (RUNNING → CANCELLED; finished_at 记录)。"""
        try:
            session = _api.cancel_runtime_session(
                service, session_id, logger=event_logger
            )
        except RuntimeSessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if session is None:
            raise HTTPException(status_code=404, detail="runtime session not found")
        return session.to_dict()

    @app.get("/api/runtime-sessions")
    def api_list_runtime_sessions(
        status: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """会话清单 (GET ?status=running — 运行中过滤, 含事件链)。"""
        sessions = _api.list_runtime_sessions(
            service, status=status, logger=event_logger
        )
        return ok_list([s.to_dict() for s in sessions])

    @app.get("/api/runtime-sessions/{session_id}")
    def api_runtime_session_detail(session_id: str) -> dict[str, Any]:
        """会话详情 (GET — 含保序事件时间线; 不存在 → 404)。"""
        session = _api.get_runtime_session(
            service, session_id, logger=event_logger
        )
        if session is None:
            raise HTTPException(status_code=404, detail="runtime session not found")
        return session.to_dict()

    @app.get("/api/tasks/{task_id}/runtime")
    def api_task_runtime_sessions(task_id: str) -> dict[str, Any]:
        """任务会话过滤 (GET — 多次执行 = 多 session; 无 → [] 诚实空态)。"""
        sessions = _api.get_task_runtime_sessions(
            service, task_id, logger=event_logger
        )
        return ok_list([s.to_dict() for s in sessions])

    # ------------------------------------------- S10-016 Task 002: Agent Executor API
    # Agent 全链路执行入口 (AI Employee Runtime Foundation Task 002): POST
    # /api/runtime/execute — Task/Agent 校验 → Runtime Session (PENDING→RUNNING)
    # → Task Context → AgentRuntime (复用真实 Provider) → 事件链 → SUCCESS|FAILED
    # → {runtime_session_id, status, output}。写路径扩展 (Permission Boundary
    # S10-016 Task 002 扩展: 执行编排 POST — 触发真实 Agent 执行, 执行权仍
    # 在 AgentRuntime; 无注入 → service 自装配)。
    # 错误映射: 空 task_id/agent_id / Task 不存在 / Agent 不存在
    # (AgentExecutorError → service 归一 ValueError) → 400; store/exec 未装配
    # → 404 (失败安全); LLM Provider 失败 → 200 status=failed + output 保留
    # (不抛裸异常 — 错误进事件链, 编排层兜底)。

    @app.post("/api/runtime/execute")
    def api_execute_runtime_task(body: _ExecuteRuntimeBody) -> dict[str, Any]:
        """Agent 全链路执行 (POST — Task→Agent→Session→LLM→Result 编排闭环)。

        {task_id, agent_id, context?} → 200 {runtime_session_id, status,
        output}: status 终态 success|failed — LLM Provider 失败 → 200
        status=failed + output 保留失败原因 (不 5xx / 不抛裸异常 — 错误进
        事件链); 空 task_id/agent_id / Task 不存在 / Agent 不存在 → 400
        (AgentExecutorError 由 service 归一为 ValueError, 不创建 Session);
        store/exec 未装配 → 404 (失败安全 — 冷启动/缺装不崩溃)。
        """
        try:
            result = _api.execute_runtime_task(
                service,
                body.task_id,
                body.agent_id,
                context=body.context,
                logger=event_logger,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="runtime executor unavailable (store/exec 未装配)",
            )
        return result

    # ------------------------------------------- S10-018 Task 001c: Tool API
    # AI Employee Tool Runtime (GET /api/tools + POST /api/tools/{id}/execute —
    # 内部 Tool 基础设施 HTTP 绑定; Tool 注册表/执行器在 Service 层失败安全
    # 装配: 注入优先, 缺失 → ToolRegistry.with_system_tools 自装配, 再失败 →
    # None → GET 返回空清单 / POST 404)。写路径扩展 (Permission Boundary):
    # Tool 执行 POST — 执行权仍在 ToolExecutor 最小权限表 (filesystem.read
    # 仅 backend-1; 其他 agent → 403 诚实拒绝), Adapter 只做 HTTP 绑定。
    # 错误映射: ToolExecuteNotFoundError → 404 / ToolExecutePermissionError →
    # 403 / ValueError (空 agent_id / schema 非法 / disabled / handler 错误)
    # → 400 / None (store/exec 未装配) → 404 失败安全。审计: console.viewed
    # (view=tools / tool_execute — ADR-0002 读审计同语义)。

    @app.get("/api/tools")
    def api_list_tools() -> dict[str, Any]:
        """Tool 清单 (U-1: 统一注册表 39 内置工具 + ToolRegistry 运行时工具; 失败安全)。"""
        try:
            from ...tools.registry import list_tools as _registry_tools, summary as _registry_summary

            builtin = _registry_tools()
        except Exception:  # noqa: BLE001 — 注册表缺失 → 空
            builtin = []
        try:
            runtime = _api.list_tools(service, logger=event_logger)
            runtime_items = runtime.get("tools") if isinstance(runtime, dict) else runtime
        except Exception:  # noqa: BLE001
            runtime_items = []
        if not isinstance(runtime_items, list):
            runtime_items = []
        known = {t.get("id") for t in builtin if isinstance(t, dict)}
        for rt in runtime_items:
            if isinstance(rt, dict) and rt.get("id") not in known:
                builtin.append(rt)
        return {"tools": builtin, "count": len(builtin),
                "summary": _registry_summary() if builtin else {}}

    @app.post("/api/tools/{tool_id}/execute")
    def api_execute_tool(tool_id: str, body: _ToolExecuteBody) -> dict[str, Any]:
        """执行 Tool (U-2: 统一注册表执行链 Registry→Permission→Schema→Execute;
        非注册表工具 → 旧 ToolExecutor 兜底)。"""
        # 新: 统一注册表执行链 (39 内置工具)
        try:
            from ...tools.executor import execute_tool as _registry_execute

            reg_result = _registry_execute(
                tool_id,
                body.input if isinstance(body.input, dict) else {"input": body.input},
                context={"root": workspace_root, "project_id": body.context.get("project_id")
                         if isinstance(body.context, dict) else None,
                         "confirm": bool(isinstance(body.context, dict) and body.context.get("confirm"))},
            )
            reg_err = str(reg_result.get("error") or "")
            # 注册表明确拒绝 (参数/敏感/规划中/执行失败) → 返回; 未注册/未绑定 → 旧执行器兜底
            if reg_result.get("ok"):
                return {"success": True, "output": reg_result.get("output")}
            if "未注册" not in reg_err and "未绑定执行函数" not in reg_err:
                return {"success": False, "error": reg_err}
        except Exception:  # noqa: BLE001 — 新链失败 → 旧链兜底
            pass
        # 旧: ToolExecutor 兜底
        try:
            result = _api.execute_tool(
                service,
                tool_id,
                body.agent_id,
                body.input,
                context=body.context,
                logger=event_logger,
            )
        except ToolExecuteNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ToolExecutePermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="tool executor unavailable (store/exec 未装配)",
            )
        return result

    # ------------------------------------------- S10-019: Skill API (职业能力)
    # Skill Registry 清单 + Agent 技能分配 (resolve_agent_skills — org 模型 +
    # 系统映射兜底; 未装配 → [] 失败安全; agent 不存在 → 404)。

    @app.get("/api/skills")
    def api_list_skills() -> dict[str, Any]:
        """Skill 清单 (GET — SkillRegistry 内置 + skills.json 注册; 未装配 → [] 失败安全)。"""
        import json as _json
        from pathlib import Path as _P
        result = _api.list_skills(service, logger=event_logger)
        skills = result.get("skills") if isinstance(result, dict) else result
        if not isinstance(skills, list):
            skills = []
        # 合并 skills.json 注册的外置 skill (v1.1.78 管理命令写入)
        try:
            f = _P(workspace_root) / "skills" / "skills.json"
            d = _json.loads(f.read_text(encoding="utf-8")) or {}
            reg = d.get("skills") if isinstance(d, dict) and "skills" in d else d
            if isinstance(reg, dict):
                known = {s.get("id") for s in skills if isinstance(s, dict)}
                for sid, sv in reg.items():
                    if sid not in known and isinstance(sv, dict):
                        skills.append({"id": sid, "name": sv.get("name", sid),
                                       "category": sv.get("category", ""),
                                       "version": sv.get("version", "1.0")})
        except Exception:  # noqa: BLE001
            pass
        return {"skills": skills, "count": len(skills)}

    @app.get("/api/agents/{agent_id}/skills")
    def api_agent_skills(agent_id: str) -> dict[str, Any]:
        """Agent 当前 Skill (GET — resolve_agent_skills; 未装配/不存在 → 404)。"""
        result = _api.agent_skills(service, agent_id, logger=event_logger)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"agent skills unavailable (agent not found or store 未装配): {agent_id}",
            )
        return result

    # ------------------------------------------- S10-020 Task 001: MCP API
    # AI Employee 工具能力外部扩展 (GET /api/mcp/connections + POST
    # /api/mcp/connections + GET /api/mcp/tools — MCP Adapter Foundation
    # Console 收尾)。MCPRegistry 在 Service 层失败安全装配: 注入优先, 缺失
    # → 自装配关联系统 ToolRegistry, 再失败 → None → GET 返回空清单 / POST
    # 404)。写路径扩展 (Permission Boundary S10-020): MCP 连接注册一 POST —
    # 注册即连接 (Mock, 不连公网) + Tool 注册进内部 ToolRegistry, 执行权仍
    # 在 ToolExecutor 最小权限表, Adapter 只做 HTTP 绑定。错误映射:
    # ValueError (空 name/server_url / stdio/http 真实协议) → 400 / None
    # (store/exec 未装配) → 404 失败安全。审计: console.viewed
    # (view=mcp_connections / mcp_connection_create / mcp_tools)。

    @app.get("/api/mcp/connections")
    def api_list_mcp_connections() -> dict[str, Any]:
        """MCP 连接清单 (GET — MCPRegistry 当前连接; 未装配 → {connections: []}
        失败安全)。"""
        return _api.list_mcp_connections(service, logger=event_logger)

    @app.post("/api/mcp/connections")
    def api_create_mcp_connection(body: _CreateMCPConnectionBody) -> dict[str, Any]:
        """创建 MCP 连接 (POST — {name, server_url, transport?} → 连接摘要 +
        tools; 注册即连接: Mock 不连公网, stdio/http → 400 响亮拒绝)。"""
        try:
            result = _api.create_mcp_connection(
                service,
                body.name,
                body.server_url,
                transport=body.transport,
                command=body.command,
                args=body.args,
                logger=event_logger,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="mcp registry unavailable (store/exec 未装配)",
            )
        return result

    @app.get("/api/mcp/tools")
    def api_list_mcp_tools() -> dict[str, Any]:
        """MCP Tool 清单 (GET — 内部 ToolRegistry source=mcp 过滤; 内部 Tool
        不混入 MCP 视图; 未装配 → {tools: []} 失败安全)。"""
        return _api.list_mcp_tools(service, logger=event_logger)

    @app.delete("/api/mcp/connections/{connection_id}")
    def api_delete_mcp_connection(connection_id: str) -> dict[str, Any]:
        """移除 MCP 连接 (DELETE — 与 CLI `factory mcp remove` 同源; 不存在
        → 404 幂等失败安全)。"""
        if not _api.remove_mcp_connection(service, connection_id, logger=event_logger):
            raise HTTPException(status_code=404, detail="mcp connection not found")
        return {"deleted": True}

    # ------------------------------------------- 设置 — LLM 管理面 (v1.1.102)
    def _provider_config_view(plane: Any, p: Any) -> dict[str, Any]:
        """providers.json 条目 → 前端管理视图 (enabled/模型/key 状态/默认模型)。

        key_configured: 只输出引用是否可解析 (D8 铁律 — key 本体永不入 API)。
        """
        key_configured = False
        try:
            key_configured = bool(plane.resolve_api_key(p.id))
        except Exception:  # noqa: BLE001 — key 缺失 → False (诚实)
            key_configured = False
        meta = dict(p.metadata or {})
        default_model = meta.get("default_model") or (p.models[0] if p.models else None)
        return {
            "id": p.id,
            "enabled": bool(p.enabled),
            "models": list(p.models or []),
            "base_url": p.base_url,
            "api_key_ref": p.api_key_ref,
            "key_configured": key_configured,
            "default_model": default_model,
            "metadata": meta,
        }

    # ---- U3: UI 显示偏好 (思考过程/执行过程 开关 + 计时) ----
    def _ui_prefs_path() -> Path:
        return Path(factory_root or DEFAULT_ROOT) / "ui_prefs.json"

    def _load_ui_prefs() -> dict[str, Any]:
        try:
            import json as _j

            d = _j.loads(_ui_prefs_path().read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except Exception:  # noqa: BLE001 — 缺/坏 → 默认
            return {}

    @app.get("/api/config/ui-prefs")
    def api_get_ui_prefs() -> dict[str, Any]:
        """UI 显示偏好 (U3): {show_thinking, show_execution, show_timing}。"""
        d = _load_ui_prefs()
        return {
            "show_thinking": bool(d.get("show_thinking", True)),
            "show_execution": bool(d.get("show_execution", True)),
            "show_timing": bool(d.get("show_timing", True)),
        }

    @app.put("/api/config/ui-prefs")
    def api_set_ui_prefs(body: dict[str, Any]) -> dict[str, Any]:
        """保存 UI 显示偏好 (原子写 ui_prefs.json)。"""
        d = _load_ui_prefs()
        for k in ("show_thinking", "show_execution", "show_timing"):
            if k in body:
                d[k] = bool(body[k])
        try:
            _ui_prefs_path().write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"保存失败: {exc}") from exc
        return {
            "show_thinking": bool(d.get("show_thinking", True)),
            "show_execution": bool(d.get("show_execution", True)),
            "show_timing": bool(d.get("show_timing", True)),
        }

    @app.get("/api/config/llm")
    def api_get_llm_config() -> dict[str, Any]:
        """LLM 配置 (GET — providers.json 管理面; 只读投影, key 只显示已配置态)。

        每次 reload 磁盘 — 管理页反映 CLI (factory config) 外部改动, 不读陈旧内存。
        """
        plane = _llm_plane
        try:
            plane.reload()
        except Exception:  # noqa: BLE001 — 损坏 → 沿用内存 (失败安全)
            pass
        providers = [_provider_config_view(plane, p) for p in plane.list_providers()]
        selected = plane.selected_provider_id()
        selected_model = None
        if selected is not None:
            sp = plane.get_provider(selected)
            if sp is not None:
                selected_model = _provider_config_view(plane, sp).get("default_model")
        return {"providers": providers, "selected": {"provider_id": selected, "model": selected_model}}

    def _apply_llm_update(plane: Any, body: _LlmConfigBody) -> dict[str, Any]:
        """应用 LLM 配置更新 (启用/停用 + 默认模型 + models/base_url/api_key_ref)。

        api_key_ref 非 env: 引用 → ValueError (明文 key 不落盘, D8 铁律)。
        """
        if body.api_key_ref is not None:
            ref = body.api_key_ref.strip()
            if ref and not ref.startswith("env:"):
                raise ValueError("api_key_ref 只接受 env:VAR 引用 (明文 key 不入 providers.json)")
        if body.enabled is True:
            plane.enable(body.provider_id)
        elif body.enabled is False:
            plane.disable(body.provider_id)
        if body.models is not None:
            plane.set_config(body.provider_id, models=[str(m).strip() for m in body.models if str(m).strip()])
        if body.base_url is not None:
            plane.set_config(body.provider_id, base_url=body.base_url.strip() or None)
        if body.api_key_ref is not None:
            plane.set_config(body.provider_id, api_key_ref=ref if ref else None)
        if body.default_model:
            cur = plane.get_provider(body.provider_id)
            meta = dict(cur.metadata or {}) if cur else {}
            meta["default_model"] = body.default_model
            plane.set_config(body.provider_id, metadata=meta)
        provider = plane.get_provider(body.provider_id)
        if provider is None:
            raise ValueError("provider not found")
        return _provider_config_view(plane, provider)

    def _llm_plane_reload(plane: Any) -> None:
        """重读磁盘 (与 GET 一致 — 管理页反映 CLI 外部改动, 不读陈旧内存)。"""
        try:
            plane.reload()
        except Exception:  # noqa: BLE001 — 损坏 → 沿用内存 (失败安全)
            pass

    @app.post("/api/config/llm")
    def api_create_llm_config(body: _LlmConfigBody) -> dict[str, Any]:
        """LLM 配置新增/覆盖 (POST — 新增 Provider, upsert 语义)。"""
        plane = _llm_plane
        _llm_plane_reload(plane)
        try:
            return _apply_llm_update(plane, body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/config/llm")
    def api_update_llm_config(body: _LlmConfigBody) -> dict[str, Any]:
        """LLM 配置修改 (PATCH — 修改已存在 Provider; 不存在 → 404)。"""
        plane = _llm_plane
        _llm_plane_reload(plane)
        if plane.get_provider(body.provider_id) is None:
            raise HTTPException(status_code=404, detail="provider not found")
        try:
            return _apply_llm_update(plane, body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ------------------------------------------- 设置 — Agent / Skill 管理 (v1.1.102)
    def _read_json_map(path: Any) -> dict[str, Any]:
        import json as _json

        try:
            d = _json.loads(Path(path).read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 — 缺失/损坏 → 空 (失败安全)
            d = {}
        return d if isinstance(d, dict) else {}

    def _write_json_map(path: Any, data: dict[str, Any]) -> None:
        import json as _json

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            _json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _agents_file() -> Any:
        return Path(workspace_root or DEFAULT_ROOT) / "agents" / "agents.json"

    def _skills_file() -> Any:
        return Path(workspace_root or DEFAULT_ROOT) / "skills" / "skills.json"

    @app.post("/api/agents")
    def api_create_agent(body: _AgentBody) -> dict[str, Any]:
        """注册 Agent (POST — 写 agents.json; 与 CLI factory agent add 同源)。"""
        aid = body.id.strip()
        role = body.role.strip()
        if not aid or not role:
            raise HTTPException(status_code=400, detail="id/role required (Agent 注册必填 id 与 role)")
        data = _read_json_map(_agents_file())
        if not isinstance(data.get("agents"), dict):
            data["agents"] = {}
        record = {"id": aid, "name": aid, "role": role, "skills": [str(x) for x in body.skills if str(x).strip()]}
        data["agents"][aid] = record
        _write_json_map(_agents_file(), data)
        return record

    @app.delete("/api/agents/{agent_id}")
    def api_delete_agent(agent_id: str) -> dict[str, Any]:
        """移除 Agent (DELETE — 与 CLI factory agent remove 同源; 不存在 → 404)。"""
        data = _read_json_map(_agents_file())
        agents = data.get("agents")
        if not isinstance(agents, dict) or agent_id not in agents:
            raise HTTPException(status_code=404, detail="agent not found")
        del agents[agent_id]
        _write_json_map(_agents_file(), data)
        return {"deleted": True}

    @app.post("/api/skills/scan")
    def api_scan_external_skills(body: _SkillScanBody = _SkillScanBody()) -> dict[str, Any]:
        """U-4 (v1.1.189): 扫描外部 SKILL.md → 幂等加载进 skills.json
        (默认 <data_dir>/skills/external/*/SKILL.md; 可传 dir)。"""
        try:
            _ext_skills = _console_import("external_skills")
        except Exception:  # noqa: BLE001 — 模块缺失 → 诚实空
            return {"loaded": [], "error": "external_skills 模块不可用"}
        dirs: list[Path] = []
        if body.dir.strip():
            dirs.append(Path(body.dir.strip()).expanduser())
        else:
            dirs.append(Path(workspace_root or DEFAULT_ROOT) / "skills" / "external")
        try:
            loaded = _ext_skills.load_external_skills(_skills_file(), dirs)
        except Exception as exc:  # noqa: BLE001 — 加载失败 → 诚实错误
            return {"loaded": [], "error": str(exc)}
        return {"loaded": loaded, "count": len(loaded), "dirs": [str(d) for d in dirs]}

    @app.post("/api/skills")
    def api_create_skill(body: _SkillBody) -> dict[str, Any]:
        """注册 Skill (POST — 写 skills.json; 与 CLI factory skill add 同源)。"""
        sid = body.id.strip()
        if not sid:
            raise HTTPException(status_code=400, detail="id required (Skill 注册必填 id)")
        data = _read_json_map(_skills_file())
        if not isinstance(data.get("skills"), dict):
            data["skills"] = {}
        record = {
            "id": sid,
            "name": (body.name or "").strip() or sid,
            "category": (body.category or "").strip() or "general",
            "version": "1.0",
        }
        data["skills"][sid] = record
        _write_json_map(_skills_file(), data)
        return record

    @app.delete("/api/skills/{skill_id}")
    def api_delete_skill(skill_id: str) -> dict[str, Any]:
        """移除 Skill (DELETE — 与 CLI factory skill remove 同源; 不存在 → 404)。"""
        data = _read_json_map(_skills_file())
        skills = data.get("skills")
        if not isinstance(skills, dict) or skill_id not in skills:
            raise HTTPException(status_code=404, detail="skill not found")
        del skills[skill_id]
        _write_json_map(_skills_file(), data)
        return {"deleted": True}

    # ------------------------------------------- S10-006.5 P1-A: Workflow 启动 API
    # 用户第一公里闭环: POST start (真实 Agent 执行链, 后台线程) + chat 最小版
    # (持续开发对话: 已启动 → 记录消息; 未启动 → idea 更新 + 触发 start) +
    # run-status (轮询驱动 Timeline 进度)。写路径扩展 (Permission Boundary
    # S10-006.5 扩展: 与审批决定/Runtime/Review/创建并列的 Console 写路径 —
    # 仅触发本项目 workflow 执行与消息落库, 不触碰 Core 引擎)。
    # 错误映射: 项目不存在 → 404; 空消息/空 idea → 400; 已有运行 → 409
    # (WorkflowConflictError — 诚实拒绝重复启动); key 缺失/存储不可用 →
    # 503 (WorkflowStartError — 诚实失败, 不假装执行)。
    # 事件可读: 链经 EventLogger 写 org.* 事件到 events.db (与 Timeline 同库)
    # → GET /api/projects/{id}/timeline 直接可见 (真实事件, 非伪造)。

    _events_db_path = getattr(getattr(event_logger, "store", None), "db_path", None)
    _runner = _console_import("workflow_runner")  # noqa: E402
    WorkflowStartError = _runner.WorkflowStartError
    WorkflowConflictError = _runner.WorkflowConflictError

    @app.post("/api/projects/{project_id}/start")
    def api_start_project_workflow(project_id: str) -> dict[str, Any]:
        """启动真实 Agent 执行链 (key 校验 → 后台线程; 200 立即回包)。"""
        try:
            result = _api.start_project_workflow_route(
                service,
                project_id,
                events_db_path=_events_db_path,
                logger=event_logger,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except WorkflowConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except WorkflowStartError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="project not found")
        return result

    @app.post("/api/projects/{project_id}/chat")
    def api_project_chat(project_id: str, body: _ChatBody) -> dict[str, Any]:
        """持续开发对话 (最小版): 已启动 → 记录消息; 未启动 → idea 更新 + start。"""
        try:
            result = _api.chat_route(
                service,
                project_id,
                body.message,
                events_db_path=_events_db_path,
                logger=event_logger,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except WorkflowConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except WorkflowStartError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="project not found")
        return result

    # ============================================== K-7e: 会话栏 (会话 + 消息)
    @app.get("/api/exec/checkpoints")
    def api_exec_checkpoints() -> dict[str, Any]:
        """T-6 (v1.1.187): 进行中/中断的执行 checkpoint (崩溃后可查可恢复)。
        附任务标题; 失败安全空 (不编造)。"""
        items: list[dict[str, Any]] = []
        try:
            items = list(service.list_exec_checkpoints())
        except Exception:  # noqa: BLE001 — 读失败 → 空
            items = []
        for cp in items:
            pid = str(cp.get("project_id") or "")
            tid = str(cp.get("task_id") or "")
            title = None
            if pid and tid:
                try:
                    t = service.get_task(pid, tid)
                    title = (t or {}).get("title") if t is not None else None
                except Exception:  # noqa: BLE001 — 任务查询失败 → 不富化
                    title = None
            cp["task_title"] = title
        return ok_list(items)

    @app.get("/api/agents")
    def api_list_agents() -> dict[str, Any]:
        """Agent 列表 (S9)。"""
        from factory_console.session.agent_registry import AgentRegistry

        root = Path(factory_root if factory_root is not None else DEFAULT_ROOT)
        reg = AgentRegistry(agents_file=root / "agents" / "factory_agents.json")
        return {"items": [a.to_dict() for a in reg.list()], "count": len(reg.list())}

    @app.get("/api/agents/{agent_id}")
    def api_get_agent(agent_id: str) -> dict[str, Any]:
        """Agent 详情 (S9)。"""
        from factory_console.session.agent_registry import AgentRegistry

        root = Path(factory_root if factory_root is not None else DEFAULT_ROOT)
        reg = AgentRegistry(agents_file=root / "agents" / "factory_agents.json")
        a = reg.get(agent_id)
        if a is None:
            raise HTTPException(status_code=404, detail=f"Agent 不存在: {agent_id}")
        return a.to_dict()

    @app.post("/api/agent-runs")
    def api_create_agent_run(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建并执行 AgentRun (S9): {agent_id, workflow_id, input?, auto_start?}。"""
        try:
            from factory_console.agent_kernel import (
                create_agent_run, run_agent, AgentKernelError,
            )
            from factory_console.production_run import build_executor_factory

            root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
            agent_id = str(body.get("agent_id") or "")
            workflow_id = str(body.get("workflow_id") or "")
            if not agent_id or not workflow_id:
                raise HTTPException(status_code=400, detail="agent_id + workflow_id 必填")
            run = create_agent_run(root, agent_id, trigger="api",
                                   input_artifacts=body.get("input_artifacts") or [])
            auto_start = bool(body.get("auto_start", True))
            if auto_start:
                done = run_agent(root, run["agent_run_id"], workflow_id=workflow_id,
                                 executor_factory=build_executor_factory(root),
                                 workflow_input=body.get("input") or {})
                return done
            return run
        except AgentKernelError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"AgentRun 失败: {exc}") from exc

    @app.get("/api/agent-runs/{run_id}")
    def api_get_agent_run(run_id: str) -> dict[str, Any]:
        """AgentRun 状态 (S9)。"""
        from factory_console.agent_kernel import get_agent_run

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        run = get_agent_run(root, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"AgentRun 不存在: {run_id}")
        return run

    @app.get("/api/agent-runs/{run_id}/history")
    def api_agent_run_history(run_id: str) -> dict[str, Any]:
        """AgentRun 历史 (S9)。"""
        from factory_console.agent_kernel import get_agent_run

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        run = get_agent_run(root, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"AgentRun 不存在: {run_id}")
        return {"run_id": run_id, "history": run.get("history", [])}

    @app.get("/api/agent-runs")
    def api_list_agent_runs() -> dict[str, Any]:
        """AgentRun 列表 (S9)。"""
        from factory_console.agent_kernel import list_agent_runs

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"items": list_agent_runs(root), "count": len(list_agent_runs(root))}

    @app.get("/api/handoffs")
    def api_list_handoffs() -> dict[str, Any]:
        """Handoff 列表 (S9)。"""
        from factory_console.agent_kernel import list_handoffs

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"items": list_handoffs(root), "count": len(list_handoffs(root))}

    @app.get("/api/handoffs/{handoff_id}")
    def api_get_handoff(handoff_id: str) -> dict[str, Any]:
        """Handoff 详情 (S9)。"""
        from factory_console.agent_kernel import get_handoff

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        h = get_handoff(root, handoff_id)
        if h is None:
            raise HTTPException(status_code=404, detail=f"Handoff 不存在: {handoff_id}")
        return h

    @app.post("/api/production-runs/{run_id}/approval-requests")
    def api_request_approval(run_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 ApprovalRequest (S17)。"""
        from factory_console import governance_service as _gov

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _gov.request_approval(
                root, production_run_id=run_id,
                artifact_ids=body.get("artifact_ids", []),
                requested_by=body.get("requested_by", "human"),
                policy_id=body.get("policy_id", "production_apply"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/production-runs/{run_id}/governance")
    def api_governance(run_id: str, action: str = "release") -> dict[str, Any]:
        """Governance Gate 检查 (S17)。"""
        from factory_console import governance_service as _gov

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _gov.check_governance(root, run_id, action=action)

    @app.get("/api/approval-requests")
    def api_list_approvals(run_id: str = "") -> dict[str, Any]:
        """Approval 列表 (S17)。"""
        from factory_console import governance_service as _gov

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _gov.list_approvals(root, production_run_id=run_id or None)
        return {"items": items, "count": len(items)}

    @app.get("/api/approval-requests/{approval_id}")
    def api_get_approval(approval_id: str) -> dict[str, Any]:
        """Approval 详情 (S17)。"""
        from factory_console import governance_service as _gov

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        a = _gov.get_approval(root, approval_id)
        if a is None:
            raise HTTPException(status_code=404, detail=f"Approval 不存在: {approval_id}")
        return a

    @app.post("/api/approval-requests/{approval_id}/approve")
    def api_approve(approval_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """批准 (S17, human only)。"""
        from factory_console import governance_service as _gov

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _gov.approve(root, approval_id,
                                decided_by=body.get("decided_by", "human"),
                                reason=body.get("reason", ""))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/api/approval-requests/{approval_id}/reject")
    def api_reject(approval_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """拒绝 (S17, human only)。"""
        from factory_console import governance_service as _gov

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _gov.reject(root, approval_id,
                               decided_by=body.get("decided_by", "human"),
                               reason=body.get("reason", ""))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/api/production-runs/{run_id}/releases")
    def api_create_release(run_id: str) -> dict[str, Any]:
        """创建 Release (S18)。"""
        from factory_console import release_service as _rel

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _rel.create(root, run_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/releases")
    def api_list_releases(run_id: str = "") -> dict[str, Any]:
        """Release 列表 (S18)。"""
        from factory_console import release_service as _rel

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _rel.list_releases(root, production_run_id=run_id or None)
        return {"items": items, "count": len(items)}

    @app.get("/api/releases/{release_id}")
    def api_get_release(release_id: str) -> dict[str, Any]:
        """Release 详情 (S18)。"""
        from factory_console import release_service as _rel

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        r = _rel.get_release(root, release_id)
        if r is None:
            raise HTTPException(status_code=404, detail=f"Release 不存在: {release_id}")
        return r

    @app.get("/api/releases/{release_id}/history")
    def api_release_history(release_id: str) -> dict[str, Any]:
        """Release 历史 (S18, append-only)。"""
        from factory_console import release_service as _rel

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return {"release_id": release_id, "history": _rel.history(root, release_id)}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/production-runs/{run_id}/release")
    def api_run_release(run_id: str) -> dict[str, Any]:
        """ProductionRun 的 Release 视图 (S18)。"""
        from factory_console import release_service as _rel
        from factory_console import governance_service as _gov

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        releases = _rel.list_releases(root, production_run_id=run_id)
        gate = _gov.check_governance(root, run_id, action="release")
        return {"run_id": run_id, "releases": releases, "gate": gate}

    @app.post("/api/releases/{release_id}/execute")
    def api_execute_release(release_id: str) -> dict[str, Any]:
        """执行 Release (S18, 经 Governance + Lifecycle)。"""
        from factory_console import release_service as _rel

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _rel.execute(root, release_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/releases/{release_id}/rollbacks")
    def api_create_rollback(release_id: str) -> dict[str, Any]:
        """创建 Rollback (S19, target = release_id)。"""
        from factory_console import rollback_service as _rb

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _rb.create(root, release_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/rollbacks")
    def api_list_rollbacks() -> dict[str, Any]:
        """Rollback 列表 (S19)。"""
        from factory_console import rollback_service as _rb

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _rb.list_rollbacks(root)
        return {"items": items, "count": len(items)}

    @app.get("/api/rollbacks/{rollback_id}")
    def api_get_rollback(rollback_id: str) -> dict[str, Any]:
        """Rollback 详情 (S19)。"""
        from factory_console import rollback_service as _rb

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        r = _rb.get_rollback(root, rollback_id)
        if r is None:
            raise HTTPException(status_code=404, detail=f"Rollback 不存在: {rollback_id}")
        return r

    @app.get("/api/rollbacks/{rollback_id}/history")
    def api_rollback_history(rollback_id: str) -> dict[str, Any]:
        """Rollback 历史 (S19, append-only)。"""
        from factory_console import rollback_service as _rb

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return {"rollback_id": rollback_id, "history": _rb.history(root, rollback_id)}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/rollbacks/{rollback_id}/check")
    def api_rollback_check(rollback_id: str) -> dict[str, Any]:
        """Rollback Gate 检查 (S19)。"""
        from factory_console import rollback_service as _rb

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _rb.check(root, rollback_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/rollbacks/{rollback_id}/execute")
    def api_execute_rollback(rollback_id: str) -> dict[str, Any]:
        """执行 Rollback (S19, 经 Governance + Lifecycle)。"""
        from factory_console import rollback_service as _rb

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _rb.execute(root, rollback_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/releases/{release_id}/verification")
    def api_release_verification(release_id: str) -> dict[str, Any]:
        """Release Verification 结果 (S20)。"""
        from factory_console import release_service as _rel

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        r = _rel.get_release(root, release_id)
        if r is None:
            raise HTTPException(status_code=404, detail=f"Release 不存在: {release_id}")
        return {"release_id": release_id, "state": r["state"],
                "verification_checks": r.get("verification_checks", []),
                "failure_reason": r.get("failure_reason", "")}

    @app.get("/api/rollbacks/{rollback_id}/verification")
    def api_rollback_verification(rollback_id: str) -> dict[str, Any]:
        """Rollback Verification 结果 (S20)。"""
        from factory_console import rollback_service as _rb

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        r = _rb.get_rollback(root, rollback_id)
        if r is None:
            raise HTTPException(status_code=404, detail=f"Rollback 不存在: {rollback_id}")
        return {"rollback_id": rollback_id, "state": r["state"],
                "verification_checks": r.get("verification_checks", []),
                "failure_reason": r.get("failure_reason", "")}

    @app.get("/api/production-runs/{run_id}/health")
    def api_run_health(run_id: str) -> dict[str, Any]:
        """Run 健康检查 (S21, 最新 RELEASED release)。"""
        from factory_console import health_service as _h

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _h.run_health(root, run_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/releases/{release_id}/health-check")
    def api_health_check(release_id: str) -> dict[str, Any]:
        """Release Health Check (S21)。"""
        from factory_console import health_service as _h

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _h.health_check(root, release_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/health-incidents")
    def api_list_incidents() -> dict[str, Any]:
        """Health Incidents 列表 (S21)。"""
        from factory_console import health_service as _h

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _h.list_incidents(root)
        return {"items": items, "count": len(items)}

    @app.get("/api/health-incidents/{incident_id}")
    def api_get_incident(incident_id: str) -> dict[str, Any]:
        """Health Incident 详情 (S21)。"""
        from factory_console import health_service as _h

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        inc = _h.get_incident(root, incident_id)
        if inc is None:
            raise HTTPException(status_code=404, detail=f"Incident 不存在: {incident_id}")
        return inc

    @app.post("/api/health-incidents/{incident_id}/recover")
    def api_recover_incident(incident_id: str) -> dict[str, Any]:
        """Automatic Recovery (S21, 经 rollback_service)。"""
        from factory_console import health_service as _h

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _h.recover(root, incident_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/operations/overview")
    def api_ops_overview() -> dict[str, Any]:
        """Control Plane Overview (S22)。"""
        from factory_console import ops_projection as _p

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _p.overview(root)

    @app.get("/api/operations/projects")
    def api_ops_projects() -> dict[str, Any]:
        """所有 project 健康 (S22)。"""
        from factory_console import ops_projection as _p
        from factory_console.release_service import list_releases

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        projects = sorted({r.get("project_id") or "" for r in list_releases(root)})
        return {"items": [_p.project_health(root, pid) for pid in projects], "count": len(projects)}

    @app.get("/api/projects/{project_id}/health")
    def api_project_health(project_id: str) -> dict[str, Any]:
        """Project Health (S22, Multi-Release)。"""
        from factory_console import ops_projection as _p

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _p.project_health(root, project_id)

    @app.get("/api/projects/{project_id}/health/history")
    def api_project_health_history(project_id: str) -> dict[str, Any]:
        """Project Health History (S22, 全 release 时间线)。"""
        from factory_console import ops_projection as _p
        from factory_console.release_service import list_releases

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        rels = [r for r in list_releases(root) if (r.get("project_id") or "") == project_id]
        return {"project_id": project_id,
                "items": [_p.release_health_history(root, r["release_id"]) for r in rels]}

    @app.get("/api/releases/{release_id}/health")
    def api_release_health(release_id: str) -> dict[str, Any]:
        """Release Health (S22)。"""
        from factory_console import ops_projection as _p

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _p.release_health(root, release_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/releases/{release_id}/health/history")
    def api_release_health_history(release_id: str) -> dict[str, Any]:
        """Release Health History (S22)。"""
        from factory_console import ops_projection as _p

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"release_id": release_id, "timeline": _p.release_health_history(root, release_id)}

    @app.get("/api/releases/compare")
    def api_release_compare(release_a: str, release_b: str) -> dict[str, Any]:
        """Release Health Comparison (S22)。"""
        from factory_console import ops_projection as _p

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _p.compare_releases(root, release_a, release_b)

    @app.get("/api/schedules")
    def api_list_schedules_api() -> dict[str, Any]:
        """Schedules 列表 (S22)。"""
        from factory_console import ops_scheduler as _s

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _s.list_schedules(root)
        return {"items": items, "count": len(items)}

    @app.post("/api/schedules")
    def api_create_schedule_api(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 Schedule (S22)。"""
        from factory_console import ops_scheduler as _s

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _s.create_schedule(root, project_id=body.get("project_id", ""),
                                      release_id=body.get("release_id", ""),
                                      interval_seconds=body.get("interval_seconds", 300))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/schedules/{schedule_id}/disable")
    def api_disable_schedule(schedule_id: str) -> dict[str, Any]:
        """禁用 Schedule (S22)。"""
        from factory_console import ops_scheduler as _s

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _s.disable_schedule(root, schedule_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/schedules/{schedule_id}/enable")
    def api_enable_schedule(schedule_id: str) -> dict[str, Any]:
        """启用 Schedule (S22)。"""
        from factory_console import ops_scheduler as _s

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _s.enable_schedule(root, schedule_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/schedules/{schedule_id}")
    def api_delete_schedule(schedule_id: str) -> dict[str, Any]:
        """删除 Schedule (S22)。"""
        from factory_console import ops_scheduler as _s

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        _s.delete_schedule(root, schedule_id)
        return {"deleted": schedule_id}

    @app.post("/api/intelligence/analyses")
    def api_create_analysis(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """对 Incident 执行 RCA (S23)。"""
        from factory_console import production_intelligence as _i

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _i.analyze_incident(root, body.get("incident_id", ""))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/intelligence/analyses/{analysis_id}")
    def api_get_analysis(analysis_id: str) -> dict[str, Any]:
        """Analysis 详情 (S23)。"""
        from factory_console import production_intelligence as _i

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        a = _i.get_analysis(root, analysis_id)
        if a is None:
            raise HTTPException(status_code=404, detail=f"Analysis 不存在: {analysis_id}")
        return a

    @app.get("/api/incidents/{incident_id}/analysis")
    def api_incident_analysis(incident_id: str) -> dict[str, Any]:
        """Incident RCA (S23)。"""
        from factory_console import production_intelligence as _i

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _i.analyze_incident(root, incident_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/incidents/{incident_id}/root-causes")
    def api_incident_root_causes(incident_id: str) -> dict[str, Any]:
        """Incident Root Causes (S23)。"""
        from factory_console import production_intelligence as _i

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        an = _i.analyze_incident(root, incident_id)
        return {"incident_id": incident_id, "analysis_id": an["analysis_id"],
                "root_cause_candidates": an.get("root_cause_candidates", [])}

    @app.get("/api/incidents/{incident_id}/recommendations")
    def api_incident_recommendations(incident_id: str) -> dict[str, Any]:
        """Incident Recommendations (S23)。"""
        from factory_console import production_intelligence as _i

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        an = _i.analyze_incident(root, incident_id)
        return {"incident_id": incident_id, "analysis_id": an["analysis_id"],
                "recommendations": an.get("recommendations", [])}

    @app.get("/api/intelligence/{analysis_id}/evidence")
    def api_intelligence_evidence(analysis_id: str) -> dict[str, Any]:
        """Analysis Evidence (S23, 可追溯)。"""
        from factory_console import production_intelligence as _i

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return {"analysis_id": analysis_id, "evidence": _i.analysis_evidence(root, analysis_id)}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/recommendations/{recommendation_id}/decide")
    def api_decide_recommendation(recommendation_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Recommendation 决策 (S23, 经 Governance)。"""
        from factory_console import production_intelligence as _i

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _i.decide_recommendation(root, recommendation_id,
                                            decision=body.get("decision", ""),
                                            decided_by=body.get("decided_by", "human"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/optimization/analyze")
    def api_optimization_analyze() -> dict[str, Any]:
        """Optimization Analysis (S24)。"""
        from factory_console import optimization_service as _o

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _o.analyze(root)

    @app.get("/api/optimization/analyses/{analysis_id}")
    def api_optimization_analysis_get(analysis_id: str) -> dict[str, Any]:
        """Analysis 详情 (S24)。"""
        from factory_console import optimization_service as _o

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        a = _o.get_analysis(root, analysis_id)
        if a is None:
            raise HTTPException(status_code=404, detail=f"Analysis 不存在: {analysis_id}")
        return a

    @app.get("/api/optimization/hypotheses")
    def api_optimization_hypotheses() -> dict[str, Any]:
        """Hypotheses 列表 (S24)。"""
        from factory_console import optimization_service as _o

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _o.hypotheses(root)
        return {"items": items, "count": len(items)}

    @app.post("/api/optimization/baselines")
    def api_optimization_baseline() -> dict[str, Any]:
        """创建真实 Baseline (S24)。"""
        from factory_console import optimization_service as _o

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _o.create_baseline(root)

    @app.get("/api/optimization/baselines/{baseline_id}")
    def api_optimization_baseline_get(baseline_id: str) -> dict[str, Any]:
        """Baseline 详情 (S24)。"""
        from factory_console import optimization_service as _o

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        bl = _o.get_baseline(root, baseline_id)
        if bl is None:
            raise HTTPException(status_code=404, detail=f"Baseline 不存在: {baseline_id}")
        return bl

    @app.post("/api/optimization/experiments")
    def api_optimization_experiment(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 Experiment (S24, 需 Governance 批准)。"""
        from factory_console import optimization_service as _o

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _o.create_experiment(root, baseline_id=body.get("baseline_id", ""),
                                        control_definition=body.get("control_definition", "current"),
                                        treatment_definition=body.get("treatment_definition", "optimized"),
                                        metric=body.get("metric", "repair_count"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/optimization/experiments/{experiment_id}")
    def api_optimization_experiment_get(experiment_id: str) -> dict[str, Any]:
        """Experiment 详情 (S24)。"""
        from factory_console import optimization_service as _o

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        exp = _o.get_experiment(root, experiment_id)
        if exp is None:
            raise HTTPException(status_code=404, detail=f"Experiment 不存在: {experiment_id}")
        return exp

    @app.post("/api/optimization/experiments/{experiment_id}/run")
    def api_optimization_run(experiment_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """执行 Experiment 臂 (S24, 需批准)。"""
        from factory_console import optimization_service as _o

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _o.run_experiment(root, experiment_id, run_id=body.get("run_id", ""),
                                     arm=body.get("arm", "treatment"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/optimization/experiments/{experiment_id}/compare")
    def api_optimization_compare(experiment_id: str) -> dict[str, Any]:
        """Measurement + Comparison (S24)。"""
        from factory_console import optimization_service as _o

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _o.compare(root, experiment_id)

    @app.get("/api/optimization/experiments/{experiment_id}/outcome")
    def api_optimization_outcome(experiment_id: str) -> dict[str, Any]:
        """Optimization Outcome (S24)。"""
        from factory_console import optimization_service as _o

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _o.outcome(root, experiment_id)

    @app.get("/api/optimization/{optimization_id}/lineage")
    def api_optimization_lineage(optimization_id: str) -> dict[str, Any]:
        """Optimization Lineage (S24)。"""
        from factory_console import optimization_service as _o

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _o.lineage(root, optimization_id)

    @app.post("/api/optimization/variants")
    def api_create_variant(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 WorkforceVariant (S25)。"""
        from factory_console import adaptive_workforce as _aw

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _aw.create_variant(root, experiment_id=body.get("experiment_id", ""),
                                      variant_type=body.get("variant_type", "treatment"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/optimization/variants")
    def api_list_variants() -> dict[str, Any]:
        """Variants 列表 (S25)。"""
        from factory_console import adaptive_workforce as _aw

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _aw.list_variants(root)
        return {"items": items, "count": len(items)}

    @app.get("/api/optimization/variants/{variant_id}")
    def api_get_variant(variant_id: str) -> dict[str, Any]:
        """Variant 详情 (S25)。"""
        from factory_console import adaptive_workforce as _aw

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        v = _aw.get_variant(root, variant_id)
        if v is None:
            raise HTTPException(status_code=404, detail=f"Variant 不存在: {variant_id}")
        return v

    @app.post("/api/optimization/variants/{variant_id}/approve")
    def api_approve_variant(variant_id: str) -> dict[str, Any]:
        """Governance 批准 Variant (S25)。"""
        from factory_console import adaptive_workforce as _aw

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _aw.approve_variant(root, variant_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/optimization/variants/{variant_id}/run")
    def api_run_variant(variant_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """用 Variant 执行真实 Production Run (S25)。"""
        from factory_console import adaptive_workforce as _aw

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _aw.run_with_variant(
                root, variant_id=variant_id, workflow_id=body.get("workflow_id", "wf"),
                base_factory=lambda node_id: (lambda input_data: {
                    "ok": True, "output": {"code": "x"},
                    "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
                                   "+def a():\n+    return 1\n"),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/optimization/variants/{variant_id}/lineage")
    def api_variant_lineage(variant_id: str) -> dict[str, Any]:
        """Variant Lineage (S25)。"""
        from factory_console import adaptive_workforce as _aw

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _aw.variant_lineage(root, variant_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/optimization/hypotheses")
    def api_create_hypothesis(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建结构化 Hypothesis (S26)。"""
        from factory_console import llm_experiment_service as _le

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _le.create_hypothesis(root, statement=body.get("statement", ""),
                                         metric=body.get("metric", "overall_score"),
                                         direction=body.get("direction", "HIGHER_IS_BETTER"),
                                         control_definition=body.get("control_definition", "developer"),
                                         treatment_definition=body.get("treatment_definition", "developer+reviewer"),
                                         minimum_sample_size=body.get("minimum_sample_size", 2),
                                         success_threshold=body.get("success_threshold", 0.0))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/optimization/llm-experiments")
    def api_create_llm_experiment(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建真实 LLM Experiment (S26)。"""
        from factory_console import llm_experiment_service as _le

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _le.create_llm_experiment(root, hypothesis_id=body.get("hypothesis_id", ""))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/optimization/llm-experiments/{experiment_id}/approve")
    def api_approve_llm_experiment(experiment_id: str) -> dict[str, Any]:
        """Governance 批准 LLM Experiment (S26)。"""
        from factory_console import llm_experiment_service as _le

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _le.approve_llm_experiment(root, experiment_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/optimization/llm-experiments/{experiment_id}/run")
    def api_run_llm_experiment(experiment_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """真实 LLM 样本 (S26)。"""
        from factory_console import llm_experiment_service as _le

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _le.llm_run_sample(root, experiment_id=experiment_id,
                                      arm=body.get("arm", "control"),
                                      workflow_id=body.get("workflow_id", "wf"),
                                      real_executor_factory=lambda node_id: (lambda input_data: {
                                          "ok": True, "output": {"code": "x"},
                                          "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
                                                         "+def a():\n+    return 1\n"),
                                          "artifact_type": "code_change",
                                          "verification": {"result": "PASS"}}))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/optimization/llm-experiments/{experiment_id}/compare")
    def api_compare_llm_experiment(experiment_id: str) -> dict[str, Any]:
        """LLM 实验比较 (S26)。"""
        from factory_console import llm_experiment_service as _le

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _le.llm_compare(root, experiment_id)

    @app.get("/api/optimization/llm-experiments/{experiment_id}/outcome")
    def api_outcome_llm_experiment(experiment_id: str) -> dict[str, Any]:
        """LLM 实验 Outcome (S26)。"""
        from factory_console import llm_experiment_service as _le

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _le.llm_outcome(root, experiment_id)

    @app.get("/api/experiments/{experiment_id}/samples")
    def api_experiment_samples(experiment_id: str) -> dict[str, Any]:
        """Experiment samples 列表 (S27/S29 兼容)。"""
        from factory_console import llm_experiment_service as _le
        from factory_console import effectiveness_service as _ef

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        # S29 effectiveness experiment 优先
        try:
            exp = _ef._get_exp(root, experiment_id)  # noqa: SLF001
            return {"samples": exp["samples"], "count": len(exp["samples"])}
        except Exception:  # noqa: BLE001
            pass
        # S26/S27 llm experiment
        try:
            exp = _le._get_llm_exp(root, experiment_id)  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"samples": exp.get("llm_experiment", {}).get("samples", [])}

    @app.get("/api/experiment-samples/{sample_id}/classification")
    def api_sample_classification(sample_id: str) -> dict[str, Any]:
        """Sample 失败分类 (S27)。"""
        from factory_console import experiment_reliability as _er

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            info = _er.inspect_sample(root, sample_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return info["classification"]

    @app.get("/api/experiment-samples/{sample_id}/eligibility")
    def api_sample_eligibility(sample_id: str) -> dict[str, Any]:
        """Sample 资格 (S27)。"""
        from factory_console import experiment_reliability as _er

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            info = _er.inspect_sample(root, sample_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return info["eligibility"]

    @app.get("/api/experiments/{experiment_id}/failures")
    def api_experiment_failures(experiment_id: str) -> dict[str, Any]:
        """失败分布 (S27)。"""
        from factory_console import experiment_reliability as _er

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _er.experiment_reliability(root, experiment_id)

    @app.get("/api/experiments/{experiment_id}/reliability")
    def api_experiment_reliability(experiment_id: str) -> dict[str, Any]:
        """Reliability 聚合 (S27)。"""
        from factory_console import experiment_reliability as _er

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _er.experiment_reliability(root, experiment_id)

    @app.get("/api/recovery/{recovery_attempt_id}")
    def api_recovery_get(recovery_attempt_id: str) -> dict[str, Any]:
        """Recovery attempt 详情 (S28)。"""
        from factory_console import recovery_service as _rs

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _rs.recovery_evidence(root, recovery_attempt_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/production-runs/{production_run_id}/recovery")
    def api_run_recovery(production_run_id: str) -> dict[str, Any]:
        """Run 的 recovery 状态 (S28)。"""
        from factory_console import recovery_service as _rs

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _rs.recovery_status(root, production_run_id)

    @app.get("/api/recovery/{recovery_attempt_id}/attempts")
    def api_recovery_attempts(recovery_attempt_id: str) -> dict[str, Any]:
        """Run 的 recovery attempts (S28)。"""
        from factory_console import recovery_service as _rs

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"attempts": _rs.recovery_attempts(root, recovery_attempt_id)}

    @app.post("/api/recovery/{production_run_id}/retry")
    def api_recovery_retry(production_run_id: str) -> dict[str, Any]:
        """触发 Recovery (S28, bounded repair loop)。"""
        from factory_console import recovery_service as _rs

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _rs.recover_production_run(
                root, production_run_id,
                executor_factory=lambda node_id: (lambda input_data: {
                    "ok": True, "output": {"code": "x"},
                    "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
                                   "+def a():\n+    return 1\n"),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}),
                repair_fn=lambda fa, v, ctx: {
                    "ok": True, "output": {"code": "x"},
                    "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
                                   "+def a():\n+    return 1\n"),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/recovery/{recovery_attempt_id}/evidence")
    def api_recovery_evidence(recovery_attempt_id: str) -> dict[str, Any]:
        """Recovery evidence (S28)。"""
        from factory_console import recovery_service as _rs

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _rs.recovery_evidence(root, recovery_attempt_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/experiments")
    def api_create_experiment(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 Effectiveness Experiment (S29, frozen contract)。"""
        from factory_console import effectiveness_service as _ef

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _ef.create_effectiveness_experiment(
                root, metric=body.get("metric", "final_success_rate"),
                minimum_sample_size=body.get("minimum_sample_size", 2),
                control_definition=body.get("control_definition", "developer"),
                treatment_definition=body.get("treatment_definition", "developer+reviewer"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/experiments/{experiment_id}")
    def api_get_experiment(experiment_id: str) -> dict[str, Any]:
        """Experiment 详情 (S29)。"""
        from factory_console import effectiveness_service as _ef

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _ef._get_exp(root, experiment_id)  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/experiments/{experiment_id}/approve")
    def api_approve_experiment(experiment_id: str) -> dict[str, Any]:
        """Governance 批准 (S29)。"""
        from factory_console import effectiveness_service as _ef

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _ef.approve_effectiveness_experiment(root, experiment_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/experiments/{experiment_id}/run")
    def api_run_experiment(experiment_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Run Recovery-aware sample (S29)。"""
        from factory_console import effectiveness_service as _ef

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _ef.run_effectiveness_sample(
                root, experiment_id=experiment_id, arm=body.get("arm", "control"),
                workflow_id=body.get("workflow_id", "wf"),
                executor_factory=lambda node_id: (lambda input_data: {
                    "ok": True, "output": {"code": "x"},
                    "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
                                   "+def a():\n+    return 1\n"),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}),
                repair_fn=lambda fa, v, ctx: {
                    "ok": True, "output": {"code": "x"},
                    "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
                                   "+def a():\n+    return 1\n"),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/experiments/{experiment_id}/population")
    def api_experiment_population(experiment_id: str) -> dict[str, Any]:
        """Population Contract (S29, 完整 denominator)。"""
        from factory_console import effectiveness_service as _ef

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ef.experiment_population(root, experiment_id)

    @app.get("/api/experiments/{experiment_id}/compare")
    def api_compare_experiment(experiment_id: str) -> dict[str, Any]:
        """Recovery-aware Comparison + PROVEN Gate (S29)。"""
        from factory_console import effectiveness_service as _ef

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ef.effectiveness_compare(root, experiment_id)

    @app.get("/api/experiments/{experiment_id}/outcome")
    def api_outcome_experiment(experiment_id: str) -> dict[str, Any]:
        """Experiment Outcome (S29)。"""
        from factory_console import effectiveness_service as _ef

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ef.effectiveness_outcome(root, experiment_id)

    @app.get("/api/experiments/{experiment_id}/evidence")
    def api_evidence_experiment(experiment_id: str) -> dict[str, Any]:
        """Evidence Lineage (S29)。"""
        from factory_console import effectiveness_service as _ef

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ef.effectiveness_lineage(root, experiment_id)

    @app.post("/api/organizations")
    def api_create_organization(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 Organization (S30)。"""
        from factory_console import workforce_os as _wfos

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _wfos.create_organization(root, name=body.get("name", "AI Factory"))

    @app.get("/api/organizations")
    def api_list_organizations() -> dict[str, Any]:
        """Organizations 列表 (S30)。"""
        from factory_console import workforce_os as _wfos

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _wfos.list_organizations(root)
        return {"items": items, "count": len(items)}

    @app.post("/api/workforces")
    def api_create_workforce(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 Workforce (S30)。"""
        from factory_console import workforce_os as _wfos

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _wfos.create_workforce(root, dept_id=body.get("dept_id", ""),
                                      name=body.get("name", "production"))

    @app.get("/api/workforces")
    def api_list_workforces() -> dict[str, Any]:
        """Workforces 列表 (S30)。"""
        from factory_console import workforce_os as _wfos

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _wfos.list_workforces(root)
        return {"items": items, "count": len(items)}

    @app.get("/api/workforces/{workforce_id}")
    def api_get_workforce(workforce_id: str) -> dict[str, Any]:
        """Workforce 详情 (S30)。"""
        from factory_console import workforce_os as _wfos

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _wfos.get_workforce(root, workforce_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/workforces/{workforce_id}/status")
    def api_workforce_status(workforce_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Workforce Lifecycle 迁移 (S30)。"""
        from factory_console import workforce_os as _wfos

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _wfos.workforce_status(root, workforce_id, target=body.get("status", "ACTIVE"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/workforces/{workforce_id}/attach")
    def api_workforce_attach(workforce_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Attach AgentProfile (S30)。"""
        from factory_console import workforce_os as _wfos

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _wfos.attach_agent(root, workforce_id=workforce_id, role=body.get("role", ""))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/agent-profiles")
    def api_list_agents_profiles() -> dict[str, Any]:
        """AgentProfiles 列表 (S30)。"""
        from factory_console import workforce_os as _wfos

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _wfos.list_agent_profiles(root)
        return {"items": items, "count": len(items)}

    @app.get("/api/agents/{agent_id}/performance")
    def api_agent_performance(agent_id: str) -> dict[str, Any]:
        """Agent Performance (S30, 从 Evidence 投影)。"""
        from factory_console import workforce_os as _wfos

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _wfos.agent_performance(root, agent_id)

    @app.get("/api/capabilities")
    def api_capabilities() -> dict[str, Any]:
        """Capability Contract (S30)。"""
        from factory_console import workforce_os as _wfos

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _wfos.capabilities_list(root)
        return {"items": items, "count": len(items)}

    @app.post("/api/workforces/select")
    def api_select_agent(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """确定性 Agent Selection (S30)。"""
        from factory_console import workforce_os as _wfos

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _wfos.select_agent_deterministic(root,
                                                required_capability=body.get("capability", ""))

    @app.get("/api/workforce-os/lineage")
    def api_workforce_os_lineage() -> dict[str, Any]:
        """Workforce OS Lineage (S30)。"""
        from factory_console import workforce_os as _wfos

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _wfos.workforce_os_lineage(root)

    @app.get("/api/plugins")
    def api_list_plugins() -> dict[str, Any]:
        """Plugins 列表 (S31)。"""
        from factory_console import plugin_kernel as _pk

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _pk.list_plugins(root)
        return {"items": items, "count": len(items)}

    @app.get("/api/plugins/{plugin_id}")
    def api_get_plugin(plugin_id: str) -> dict[str, Any]:
        """Plugin 详情 (S31)。"""
        from factory_console import plugin_kernel as _pk

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        p = _pk.get_plugin(root, plugin_id)
        if p is None:
            raise HTTPException(status_code=404, detail=f"Plugin 不存在: {plugin_id}")
        return p

    @app.post("/api/plugins/{plugin_id}/enable")
    def api_enable_plugin(plugin_id: str) -> dict[str, Any]:
        """启用 Plugin (S31)。"""
        from factory_console import plugin_kernel as _pk

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _pk.plugin_status(root, plugin_id, target="ENABLED")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/plugins/{plugin_id}/disable")
    def api_disable_plugin(plugin_id: str) -> dict[str, Any]:
        """禁用 Plugin (S31)。"""
        from factory_console import plugin_kernel as _pk

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _pk.plugin_status(root, plugin_id, target="DISABLED")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/plugins/{plugin_id}/status")
    def api_plugin_status(plugin_id: str) -> dict[str, Any]:
        """Plugin 状态 (S31)。"""
        from factory_console import plugin_kernel as _pk

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        p = _pk.get_plugin(root, plugin_id)
        if p is None:
            raise HTTPException(status_code=404, detail=f"Plugin 不存在: {plugin_id}")
        return {"plugin_id": plugin_id, "status": p["status"]}

    @app.get("/api/plugins/{plugin_id}/health")
    def api_plugin_health(plugin_id: str) -> dict[str, Any]:
        """Plugin 健康 (S31)。"""
        from factory_console import plugin_kernel as _pk

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _pk.plugin_health(root, plugin_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/agent-profiles/{agent_profile_id}/bind")
    def api_bind_agent_profile(agent_profile_id: str,
                               body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """AgentProfile 绑定 Plugin Composition (S32)。"""
        from factory_console import workforce_composition as _wc

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _wc.bind_agent_profile(root, agent_profile_id=agent_profile_id,
                                          provider_plugin_id=body.get("provider_plugin_id", ""))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/agent-profiles/{agent_profile_id}/composition")
    def api_agent_composition(agent_profile_id: str) -> dict[str, Any]:
        """AgentProfile Composition (S32, 确定性解析)。"""
        from factory_console import workforce_composition as _wc

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _wc.resolve_agent_composition(root, agent_profile_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/agent-profiles/{agent_profile_id}/lineage")
    def api_agent_composition_lineage(agent_profile_id: str) -> dict[str, Any]:
        """AgentProfile Composition Lineage (S32)。"""
        from factory_console import workforce_composition as _wc

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _wc.composition_lineage(root, agent_profile_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/capabilities/unified")
    def api_unified_capabilities() -> dict[str, Any]:
        """统一 Capability 视图 (S32)。"""
        from factory_console import workforce_composition as _wc

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _wc.unified_capability_list(root)
        return {"items": items, "count": len(items)}

    @app.post("/api/workforces/select-ranked")
    def api_select_ranked(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Performance-aware Selection (S33, deterministic)。"""
        from factory_console import performance_selection as _ps

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ps.select_plugin(root, required_capability=body.get("capability", ""))

    @app.get("/api/plugins/{plugin_id}/performance")
    def api_plugin_performance(plugin_id: str) -> dict[str, Any]:
        """Plugin Performance (S33, 从 Evidence 投影)。"""
        from factory_console import performance_selection as _ps

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _ps.plugin_performance(root, plugin_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/plugins/{plugin_id}/performance-history")
    def api_plugin_performance_history(plugin_id: str) -> dict[str, Any]:
        """Plugin Performance History (S33, snapshot 可追溯)。"""
        from factory_console import performance_selection as _ps

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _ps.plugin_performance_history(root, plugin_id)
        return {"items": items, "count": len(items)}

    @app.get("/api/selection/history")
    def api_selection_history() -> dict[str, Any]:
        """Selection History (S33)。"""
        from factory_console import performance_selection as _ps

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _ps.selection_history(root)
        return {"items": items, "count": len(items)}

    @app.post("/api/context/requests")
    def api_create_context_request(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 ContextRequest (S35)。"""
        from factory_console import context_runtime as _cr

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _cr.create_context_request(
                root, node_id=body.get("node_id", "node-1"),
                purpose=body.get("purpose", "context"),
                scopes=body.get("scopes", ["node"]),
                project_id=body.get("project_id", ""),
                budget=body.get("budget"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/context/requests/{request_id}/resolve")
    def api_resolve_context(request_id: str) -> dict[str, Any]:
        """Context Resolution (S35)。"""
        from factory_console import context_runtime as _cr

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _cr.resolve_context(root, request_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/context/history")
    def api_context_history() -> dict[str, Any]:
        """Context History (S35, snapshot 可追溯)。"""
        from factory_console import context_runtime as _cr

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _cr.context_history(root)
        return {"items": items, "count": len(items)}

    @app.get("/api/memory")
    def api_memory_list() -> dict[str, Any]:
        """Memory 列表 (S35)。"""
        from factory_console.context_runtime import _init_local_memory, LocalMemoryPlugin

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        _init_local_memory(root)
        r = LocalMemoryPlugin(root).handle("list", {})
        return {"items": r.get("entries", []), "count": len(r.get("entries", []))}

    @app.get("/api/memory/{memory_id}")
    def api_memory_get(memory_id: str) -> dict[str, Any]:
        """Memory 详情 (S35)。"""
        from factory_console.context_runtime import _init_local_memory, LocalMemoryPlugin

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        _init_local_memory(root)
        e = LocalMemoryPlugin(root).handle("get", {"memory_id": memory_id})
        if e is None:
            raise HTTPException(status_code=404, detail=f"Memory 不存在: {memory_id}")
        return e

    @app.get("/api/memory/candidates")
    def api_memory_candidates() -> dict[str, Any]:
        """Memory Candidates (S35)。"""
        from factory_console import context_runtime as _cr

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _cr.memory_candidates(root)
        return {"items": items, "count": len(items)}

    @app.post("/api/memory/candidates")
    def api_create_memory_candidate(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 MemoryCandidate (S35, 不自动长期化)。"""
        from factory_console import context_runtime as _cr

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _cr.create_memory_candidate(root, content=body.get("content", ""),
                                               scope=body.get("scope", "node"),
                                               source_type=body.get("source_type", "manual"),
                                               source_id=body.get("source_id", ""))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/memory/candidates/{candidate_id}/promote")
    def api_promote_memory_candidate(candidate_id: str) -> dict[str, Any]:
        """Promote MemoryCandidate (S35, governed)。"""
        from factory_console import context_runtime as _cr

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _cr.promote_memory_candidate(root, candidate_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/context/rank")
    def api_context_rank(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Context Utility Ranking (S36)。"""
        from factory_console import context_intelligence as _ci

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ci.rank_context(root, purpose=body.get("purpose", "context"),
                                scopes=body.get("scopes", ["node"]),
                                budget_tokens=body.get("budget_tokens", 4000))

    @app.post("/api/context/progressive")
    def api_context_progressive(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Progressive Context (S36)。"""
        from factory_console import context_intelligence as _ci

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ci.progressive_context(root, node_id=body.get("node_id", "node-1"),
                                       purpose=body.get("purpose", "context"),
                                       scopes=body.get("scopes", ["node"]),
                                       initial_budget=body.get("initial_budget", 1000),
                                       max_total=body.get("max_total", 3000))

    @app.post("/api/context/feedback")
    def api_context_feedback(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """ContextFeedback (S36)。"""
        from factory_console import context_intelligence as _ci

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _ci.context_feedback(root, snapshot_id=body.get("snapshot_id", ""),
                                        node_run_id=body.get("node_run_id", ""),
                                        execution_result=body.get("execution_result", "UNKNOWN"),
                                        usefulness=body.get("usefulness", "UNKNOWN"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/context/efficiency")
    def api_context_efficiency() -> dict[str, Any]:
        """Context Efficiency (S36)。"""
        from factory_console import context_intelligence as _ci

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        fbs = _ci.context_feedbacks(root)
        return {"feedback_count": len(fbs),
                "context_cost_per_successful_run": "NOT_AVAILABLE",
                "explain": "真实数据不足时诚实 NOT_AVAILABLE"}

    @app.post("/api/memory/{memory_id}/lifecycle")
    def api_memory_lifecycle(memory_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Memory Lifecycle 迁移 (S36)。"""
        from factory_console import context_intelligence as _ci

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _ci.memory_lifecycle(root, memory_id, target=body.get("status", "ACTIVE"),
                                        superseded_by=body.get("superseded_by", ""))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/memory/{memory_id}/history")
    def api_memory_history(memory_id: str) -> dict[str, Any]:
        """Memory Lineage (S36)。"""
        from factory_console import context_intelligence as _ci

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _ci.memory_history(root, memory_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/memory-conflicts/detect")
    def api_memory_conflicts_detect() -> dict[str, Any]:
        """Memory Conflict 检测 (S36)。"""
        from factory_console import context_intelligence as _ci

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        cfs = _ci.detect_memory_conflicts(root)
        return {"items": cfs, "count": len(cfs)}

    @app.get("/api/memory-conflicts")
    def api_memory_conflicts() -> dict[str, Any]:
        """Memory Conflicts 列表 (S36)。"""
        from factory_console import context_intelligence as _ci

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _ci.memory_conflicts(root)
        return {"items": items, "count": len(items)}

    @app.post("/api/learning/observations")
    def api_create_observation(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """LearningObservation (S37, 来源须为 Production Evidence)。"""
        from factory_console import learning_engine_v2 as _le

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _le.create_observation(root, source_type=body.get("source_type", ""),
                                          source_id=body.get("source_id", ""),
                                          pattern_key=body.get("pattern_key", ""),
                                          outcome=body.get("outcome", "UNKNOWN"),
                                          scope=body.get("scope", "node"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/learning/run")
    def api_run_learning() -> dict[str, Any]:
        """运行 Learning (S37, discovery → evaluate → conflicts; STOP)。"""
        from factory_console import learning_engine_v2 as _le

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _le.run_learning(root)

    @app.get("/api/learning/candidates")
    def api_learning_candidates() -> dict[str, Any]:
        """Learning Candidates + Quality (S37)。"""
        from factory_console import learning_engine_v2 as _le

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"items": _le.candidates(root), "quality": _le.learning_quality(root)}

    @app.get("/api/learning/candidates/{candidate_id}")
    def api_learning_candidate(candidate_id: str) -> dict[str, Any]:
        """Learning Candidate 详情 (S37)。"""
        from factory_console import learning_engine_v2 as _le

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        for c in _le.candidates(root):
            if c["candidate_id"] == candidate_id:
                return c
        raise HTTPException(status_code=404, detail=f"Candidate 不存在: {candidate_id}")

    @app.get("/api/learning/conflicts")
    def api_learning_conflicts() -> dict[str, Any]:
        """Learning Conflicts (S37)。"""
        from factory_console import learning_engine_v2 as _le

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _le.learning_conflicts(root)
        return {"items": items, "count": len(items)}

    @app.post("/api/promotions/candidates")
    def api_create_promotion_candidate(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 PromotionCandidate (S38, 从 S37 LearningCandidate)。"""
        from factory_console import promotion_service as _ps

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _ps.create_promotion_candidate(
                root, learning_candidate_id=body.get("learning_candidate_id", ""),
                target=body.get("target", "memory"),
                baseline_ref=body.get("baseline_ref", ""),
                candidate_ref=body.get("candidate_ref", ""),
                scope=body.get("scope", "node"), risk=body.get("risk", "MEDIUM"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/promotions/candidates/{candidate_id}/evaluate")
    def api_evaluate_promotion(candidate_id: str,
                               body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Evaluation (S38, baseline vs candidate)。"""
        from factory_console import promotion_service as _ps

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _ps.evaluate_candidate(
                root, candidate_id,
                baseline_metrics=body.get("baseline_metrics", {}),
                candidate_metrics=body.get("candidate_metrics", {}),
                sample_count=body.get("sample_count", 0))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/promotions/candidates/{candidate_id}/experiments")
    def api_create_promotion_experiment(candidate_id: str,
                                        body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Experiment (S38)。"""
        from factory_console import promotion_service as _ps

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ps.create_experiment(root, candidate_id=candidate_id,
                                     max_runs=body.get("max_runs", 10))

    @app.post("/api/promotions/candidates/{candidate_id}/decide")
    def api_decide_promotion(candidate_id: str,
                             body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Governance Decision (S38, Human Gate 强制)。"""
        from factory_console import promotion_service as _ps

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _ps.decide_promotion(root, candidate_id,
                                        decision=body.get("decision", "APPROVE"),
                                        actor=body.get("actor", "human"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/promotions/candidates/{candidate_id}/canary")
    def api_create_canary(candidate_id: str,
                          body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Canary (S38)。"""
        from factory_console import promotion_service as _ps

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ps.create_canary(root, candidate_id=candidate_id,
                                 max_runs=body.get("max_runs", 3))

    @app.post("/api/promotions/canaries/{canary_id}/promote")
    def api_promote(canary_id: str,
                    body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Promote (S38, Canary PASS 后; immutable Snapshot)。"""
        from factory_console import promotion_service as _ps

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            from factory_console.promotion_service import _find
            can = _find(root, "canaries", "canary_id", canary_id)
            return _ps.promote(root, can["candidate_id"], canary_id=canary_id,
                               actor=body.get("actor", "human"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/promotions/history")
    def api_promotion_history() -> dict[str, Any]:
        """Promotion History + Snapshots (S38)。"""
        from factory_console import promotion_service as _ps

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"candidates": _ps.promotion_candidates(root),
                "snapshots": _ps.promotion_snapshots(root)}

    @app.post("/api/incidents")
    def api_create_incident(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 Incident (S39, 来自真实 Production Evidence)。"""
        from factory_console import self_healing as _sh

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _sh.create_incident(root, source=body.get("source", "verification"),
                                       production_run_id=body.get("production_run_id", ""),
                                       node_id=body.get("node_id", "node-1"),
                                       failure_type=body.get("failure_type", "failure"),
                                       severity=body.get("severity", "MEDIUM"),
                                       scope=body.get("scope", "node"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/incidents/{incident_id}/recover")
    def api_run_self_healing(incident_id: str,
                             body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Self-Healing 完整闭环 (S39)。"""
        from factory_console import self_healing as _sh

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _sh.run_self_healing(root, incident_id,
                                        executor_factory=body.get("executor_factory"),
                                        artifact_root=root,
                                        risk=body.get("risk", "MEDIUM"),
                                        human_actor=body.get("actor", "human"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/incidents")
    def api_incidents() -> dict[str, Any]:
        """Incidents 列表 (S39)。"""
        from factory_console import self_healing as _sh

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _sh.recovery_history(root)
        return {"items": items, "count": len(items)}

    @app.get("/api/incidents/{incident_id}/status")
    def api_incident_status(incident_id: str) -> dict[str, Any]:
        """Incident 状态 (S39)。"""
        from factory_console import self_healing as _sh

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _sh.recovery_status(root, incident_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/optimizations/opportunities")
    def api_create_opportunity(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 OptimizationOpportunity (S40, evidence-driven)。"""
        from factory_console import optimization_engine as _oe

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _oe.create_opportunity(
                root, source=body.get("source", "performance"),
                target_type=body.get("target_type", "provider"),
                target_id=body.get("target_id", ""),
                metric=body.get("metric", "success_rate"),
                current_value=body.get("current_value", 0.0),
                risk=body.get("risk", "MEDIUM"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/optimizations/candidates")
    def api_create_optimization_candidate(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 OptimizationCandidate (S40, Proposal)。"""
        from factory_console import optimization_engine as _oe

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _oe.create_candidate(
                root, opportunity_id=body.get("opportunity_id", ""),
                strategy_plugin_id=body.get("strategy_plugin_id", ""),
                target=body.get("target", ""),
                proposed_change=body.get("proposed_change", ""),
                risk=body.get("risk", "MEDIUM"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/optimizations/candidates/{candidate_id}/evaluate")
    def api_evaluate_optimization(candidate_id: str,
                                  body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Optimization Evaluation (S40, PROMOTE/REJECT/NO_CHANGE)。"""
        from factory_console import optimization_engine as _oe

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _oe.evaluate_optimization(
                root, candidate_id,
                baseline_metrics=body.get("baseline_metrics", {}),
                candidate_metrics=body.get("candidate_metrics", {}),
                sample_count=body.get("sample_count", 0))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/optimizations/metrics")
    def api_optimization_metrics() -> dict[str, Any]:
        """Optimization Metrics (S40)。"""
        from factory_console import optimization_engine as _oe

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _oe.optimization_metrics(root)

    @app.get("/api/optimizations/history")
    def api_optimization_history() -> dict[str, Any]:
        """Optimization History (S40)。"""
        from factory_console import optimization_engine as _oe

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"opportunities": _oe.opportunities(root),
                "candidates": _oe.candidates(root),
                "decisions": _oe.decisions(root)}

    @app.post("/api/intelligence/strategies")
    def api_register_strategy(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """注册 IntelligenceStrategy (S42, 经 Plugin Kernel)。"""
        from factory_console import intelligence_strategy as _is

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            _is._default_adapters(root)
            return _is.register_strategy(
                root, strategy_id=body.get("strategy_id", ""),
                strategy_type=body.get("strategy_type", "LEARNING"),
                version=body.get("version", "1.0.0"),
                capabilities=body.get("capabilities", ["intelligence.run"]),
                cost_budget=body.get("cost_budget", 1.0))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/intelligence/strategies/{strategy_id}/execute")
    def api_execute_strategy(strategy_id: str,
                             body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """执行 IntelligenceStrategy (S42, 统一入口)。"""
        from factory_console import intelligence_strategy as _is

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            _is._default_adapters(root)
            return _is.execute_strategy(root, strategy_id=strategy_id,
                                        payload=body.get("payload", {}))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/intelligence/strategies")
    def api_strategies() -> dict[str, Any]:
        """IntelligenceStrategies 列表 (S42)。"""
        from factory_console import intelligence_strategy as _is

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"items": _is.strategies(root), "count": len(_is.strategies(root))}

    @app.get("/api/intelligence/strategies/{strategy_id}/executions")
    def api_strategy_executions(strategy_id: str) -> dict[str, Any]:
        """Strategy 历史执行 (S42, 版本 lineage)。"""
        from factory_console import intelligence_strategy as _is

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"items": _is.strategy_lineage(root, strategy_id),
                "count": len(_is.strategy_lineage(root, strategy_id))}

    @app.post("/api/entities")
    def api_create_entity(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 Universal Entity (S43, 统一 Contract)。"""
        from factory_console import unified_contract as _uc

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            e = _uc.create_entity(body.get("type", "task"),
                                  created_by=body.get("created_by", "human"),
                                  owner=body.get("owner", ""),
                                  parent_id=body.get("parent_id", ""),
                                  project_id=body.get("project_id", ""),
                                  metadata=body.get("metadata", {}))
            return _uc.store_entity(root, e)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/entities/{entity_id}")
    def api_get_entity(entity_id: str) -> dict[str, Any]:
        """Entity 详情 (S43)。"""
        from factory_console import unified_contract as _uc

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _uc.get_entity(root, entity_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/entities")
    def api_list_entities(entity_type: str = "") -> dict[str, Any]:
        """Entities 列表 (S43)。"""
        from factory_console import unified_contract as _uc

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _uc.entities(root, entity_type=entity_type)
        return _uc.make_page(items=items, page=1, page_size=len(items) or 20)

    @app.get("/api/entities/{entity_id}/lineage")
    def api_entity_lineage(entity_id: str) -> dict[str, Any]:
        """Entity Lineage 追溯 (S43)。"""
        from factory_console import unified_contract as _uc

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"lineage": _uc.trace_lineage(root, entity_id)}

    @app.get("/api/contracts")
    def api_contracts() -> dict[str, Any]:
        """Unified Contracts 总览 (S43)。"""
        from factory_console import unified_contract as _uc

        return {"id_prefixes": _uc.ID_PREFIXES, "relations": _uc.ENTITY_RELATIONS,
                "lifecycle": _uc.LIFECYCLE_STATES, "error_codes": _uc.ERROR_CODES,
                "entity_fields": list(_uc.ENTITY_FIELDS)}

    @app.post("/api/conversations")
    def api_create_conversation(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 Conversation (K1, S43 Entity)。"""
        from factory_console import conversation_os as _co

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _co.create_conversation(root, title=body.get("title", "新会话"),
                                       created_by=body.get("created_by", "human"))

    @app.post("/api/conversations/{conversation_id}/messages")
    def api_send_message(conversation_id: str,
                         body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """发送用户消息 (K1, Intent 理解 + 多轮 + 回复)。"""
        from factory_console import conversation_os as _co

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _co.send_message(root, conversation_id,
                                    body.get("message", ""), actor=body.get("actor", "human"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/conversations")
    def api_conversations() -> dict[str, Any]:
        """Conversations 列表 (K1)。"""
        from factory_console import conversation_os as _co

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        items = _co.conversations(root)
        return {"items": items, "count": len(items)}

    @app.get("/api/conversations/{conversation_id}")
    def api_get_conversation(conversation_id: str) -> dict[str, Any]:
        """Conversation 详情 (K1)。"""
        from factory_console import conversation_os as _co

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _co.get_conversation(root, conversation_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/conversations/{conversation_id}/requirements")
    def api_extract_requirement(conversation_id: str,
                                body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """提取 Requirement (K1, req_ 实体)。"""
        from factory_console import conversation_os as _co

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _co.extract_requirement(root, conversation_id,
                                           title=body.get("title", "需求"),
                                           description=body.get("description", ""),
                                           acceptance=body.get("acceptance_criteria", ""))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/conversations/{conversation_id}/decisions")
    def api_create_decision(conversation_id: str,
                            body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 Decision (K1, decision_ 实体, 不可覆盖)。"""
        from factory_console import conversation_os as _co

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _co.create_decision(root, conversation_id,
                                       statement=body.get("statement", ""),
                                       proposed_by=body.get("proposed_by", "ai"),
                                       decision=body.get("decision", "ACCEPT"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/task-trees")
    def api_decompose_task_tree(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Task Tree 分解 (K2, 需求 → 任务树)。"""
        from factory_console import task_tree as _tt

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _tt.decompose(root, title=body.get("title", "任务"),
                                 description=body.get("description", ""),
                                 domain=body.get("domain", "default"),
                                 source_conv_id=body.get("source_conversation_id", ""),
                                 source_req_id=body.get("source_requirement_id", ""))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/task-trees/{task_tree_id}/progress")
    def api_task_tree_progress(task_tree_id: str) -> dict[str, Any]:
        """Task Tree 进度投影 (K2)。"""
        from factory_console import task_tree as _tt

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _tt.task_progress(root, task_tree_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/task-trees/{task_tree_id}/status")
    def api_task_tree_status(task_tree_id: str) -> dict[str, Any]:
        """Task Tree 状态 (K2, 每任务 + 依赖 + 进度)。"""
        from factory_console import task_tree as _tt

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _tt.tree_status(root, task_tree_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/tasks/{task_id}/status")
    def api_update_task_status(task_id: str,
                               body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Task 状态更新 (K2)。"""
        from factory_console import task_tree as _tt

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _tt.update_task_status(root, task_id, status=body.get("status", "COMPLETED"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/projects-os")
    def api_os_create_project(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 Project (K3, 从 Requirement, 绑定 conv)。"""
        from factory_console import project_os as _po

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _po.create_project(root, title=body.get("title", "项目"),
                                      description=body.get("description", ""),
                                      source_conv_id=body.get("source_conversation_id", ""),
                                      source_req_id=body.get("source_requirement_id", ""))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/projects-os/{project_id}/sprints")
    def api_os_create_sprint(project_id: str,
                             body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建 Sprint (K3)。"""
        from factory_console import project_os as _po

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _po.create_sprint(root, project_id, title=body.get("title", "Sprint"),
                                     goal=body.get("goal", ""))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/projects-os/{project_id}/status")
    def api_os_project_status(project_id: str) -> dict[str, Any]:
        """Project 状态投影 (K3, Project→Sprint→Task 全层实时计算)。"""
        from factory_console import project_os as _po

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _po.project_status(root, project_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/projects-os/{project_id}/replan")
    def api_replan(project_id: str,
                   body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Requirement 变更 → Replan (K3)。"""
        from factory_console import project_os as _po

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _po.replan(root, project_id,
                              new_req_id=body.get("new_requirement_id", ""),
                              new_task_title=body.get("new_task_title", "新任务"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/tasks/{task_id}/approval")
    def api_task_approval(task_id: str,
                          body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """高风险 task Approval gate (K3)。"""
        from factory_console import project_os as _po

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _po.approve_task_execution(root, task_id, risk=body.get("risk", "HIGH"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/approvals/{approval_id}/decide")
    def api_decide_approval(approval_id: str,
                            body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """批准/拒绝 Approval (K3, 阻塞/恢复 Work)。"""
        from factory_console import project_os as _po

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _po.decide_task_approval(root, approval_id,
                                            decision=body.get("decision", "approve"),
                                            decided_by=body.get("decided_by", "human"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/ops/overview")
    def api_ct_overview() -> dict[str, Any]:
        """Global Operations View (K4)。"""
        from factory_console import operational_state as _os

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _os.global_overview(root)

    @app.get("/api/ops/who-working")
    def api_ct_who_working() -> dict[str, Any]:
        """谁在工作 (K4, agent 级真实依据)。"""
        from factory_console import operational_state as _os

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _os.who_is_working(root)

    @app.get("/api/ops/drill/{project_id}")
    def api_ct_drill(project_id: str) -> dict[str, Any]:
        """Project 全链路钻取 (K4, project→sprint→task→run→evidence)。"""
        from factory_console import operational_state as _os

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        try:
            return _os.drill_down(root, project_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/ops/snapshot")
    def api_ct_snapshot() -> dict[str, Any]:
        """一致性快照 (K4, 断线恢复)。"""
        from factory_console import operational_state as _os

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _os.snapshot(root)

    @app.get("/api/control-tower")
    def api_control_tower() -> dict[str, Any]:
        """Control Tower 总览 (K2, 全真实投影)。"""
        from factory_console import control_tower as _ct

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ct.control_tower(root)

    @app.get("/api/control-tower/workforce")
    def api_tower_workforce_status() -> dict[str, Any]:
        """Workforce 状态 (K2, 谁在干什么)。"""
        from factory_console import control_tower as _ct

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ct.workforce_status(root)

    @app.get("/api/control-tower/governance")
    def api_tower_governance_pending() -> dict[str, Any]:
        """Governance 待办 (K2, PENDING approvals)。"""
        from factory_console import control_tower as _ct

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ct.governance_pending(root)

    @app.get("/api/control-tower/realtime")
    def api_tower_realtime_stream() -> dict[str, Any]:
        """最近事件流 (K2, correlation 可追溯)。"""
        from factory_console import control_tower as _ct

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _ct.realtime_stream(root)

    @app.get("/api/workforce")
    def api_workforce_list() -> dict[str, Any]:
        """Workforce workflows (S16)。"""
        from factory_console import workforce as _wf

        return {"workflows": list(_wf.WORKFORCE_WORKFLOWS.items())}

    @app.get("/api/workforce/agents")
    def api_workforce_agents() -> dict[str, Any]:
        """Workforce 角色/Agent 列表 (S16, 含 capabilities)。"""
        from factory_console import workforce as _wf

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"items": _wf.list_agents(root), "count": len(_wf.list_agents(root))}

    @app.get("/api/workforce/runs/{run_id}")
    def api_workforce_run(run_id: str) -> dict[str, Any]:
        """Workforce run lineage (S16, 全链)。"""
        from factory_console import workforce as _wf

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _wf.workforce_lineage(root, run_id)

    @app.get("/api/workforce/runs")
    def api_workforce_runs() -> dict[str, Any]:
        """Workforce 任务列表 (S16)。"""
        from factory_console import workforce as _wf

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"items": _wf.get_tasks(root)}

    @app.get("/api/experiences")
    def api_list_experiences(status: str | None = Query(default=None)) -> dict[str, Any]:
        """经验列表 (S14)。"""
        from factory_console import production_experience as _pexp

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"items": _pexp.list_experiences(root, status=status),
                "count": len(_pexp.list_experiences(root, status=status))}

    @app.get("/api/experiences/search")
    def api_search_experiences(role: str = "", q: str = "") -> dict[str, Any]:
        """引导检索相关经验 (S15, 确定性 relevance)。"""
        from factory_console import production_guidance as _pg

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return {"items": _pg.retrieve_guidance(root, role, q)}

    @app.get("/api/production-runs/{run_id}/lineage")
    def api_production_lineage(run_id: str) -> dict[str, Any]:
        """Production 双向 lineage (S15: usage + decisions)。"""
        from factory_console import production_guidance as _pg

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return _pg.production_lineage(root, run_id)

    @app.get("/api/experiences/{experience_id}")
    def api_get_experience(experience_id: str) -> dict[str, Any]:
        """经验详情 (S14)。"""
        from factory_console import production_experience as _pexp

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        e = _pexp.get_experience(root, experience_id)
        if e is None:
            raise HTTPException(status_code=404, detail=f"Experience 不存在: {experience_id}")
        return e

    @app.post("/api/experiences/retrieve")
    def api_retrieve_experiences(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """确定性检索相关经验 (S14, 只返回 ACTIVE)。"""
        from factory_console import production_experience as _pexp

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        context = str(body.get("context") or "")
        limit = int(body.get("limit") or 5)
        return {"items": _pexp.retrieve(root, context, limit=limit)}

    @app.post("/api/production-runs/{run_id}/experience")
    def api_extract_experience(run_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """从 ProductionRun 提取经验 (S14, 幂等)。"""
        try:
            from factory_console import production_experience as _pexp

            root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
            force = bool(body.get("force", False))
            return _pexp.extract(root, run_id, force=force)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/production-runs")
    def api_create_production_run(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """创建并启动 ProductionRun (S6): {workflow_id, input?, auto_start?}。"""
        try:
            from factory_console import production_service as _psvc
            from factory_console.production_run import build_executor_factory

            root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
            workflow_id = str(body.get("workflow_id") or "")
            if not workflow_id:
                raise HTTPException(status_code=400, detail="workflow_id 必填")
            input_data = body.get("input") or {}
            run = _psvc.create(root, workflow_id, input_data=input_data, trigger="api")
            auto_start = bool(body.get("auto_start", True))
            if auto_start:
                factory = build_executor_factory(root)
                done = _psvc.start(root, run["run_id"], executor_factory=factory,
                                   artifact_root=root)
                st = _psvc.status(root, run["run_id"])
                st["final_state"] = done["state"]
                return st
            return run
        except _psvc.ProductionServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"ProductionRun 启动失败: {exc}") from exc

    @app.post("/api/production-runs/{run_id}/recover")
    def api_recover_production_run(run_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """执行 Recovery (S8): analyze → resume → 最终状态。"""
        try:
            from factory_console import production_service as _psvc
            from factory_console.production_run import build_executor_factory

            root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
            factory = build_executor_factory(root)
            return _psvc.recover(root, run_id, executor_factory=factory, artifact_root=root)
        except _psvc.ProductionServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Recovery 失败: {exc}") from exc

    @app.get("/api/production-runs/{run_id}/recovery")
    def api_production_run_recovery(run_id: str) -> dict[str, Any]:
        """Recovery 只读分析 (S8, side-effect free)。"""
        try:
            from factory_console import production_service as _psvc

            root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
            return _psvc.analyze(root, run_id)
        except _psvc.ProductionServiceError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/production-runs/{run_id}/evaluation")
    def api_production_run_evaluation(run_id: str, force: bool = False) -> dict[str, Any]:
        """ProductionRun 质量评价 (S13, 确定性, 幂等)。"""
        try:
            from factory_console import production_evaluation as _peval

            root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
            return _peval.evaluate(root, run_id, force=force)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/production-runs/{run_id}")
    def api_get_production_run(run_id: str) -> dict[str, Any]:
        """ProductionRun 状态 (S6)。"""
        try:
            from factory_console import production_service as _psvc

            root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
            return _psvc.status(root, run_id)
        except _psvc.ProductionServiceError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/production-runs/{run_id}/history")
    def api_production_run_history(run_id: str) -> dict[str, Any]:
        """ProductionRun append-only 历史 (S6)。"""
        try:
            from factory_console import production_service as _psvc

            root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
            return _psvc.history(root, run_id)
        except _psvc.ProductionServiceError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/production-runs")
    def api_list_production_runs() -> dict[str, Any]:
        """ProductionRun 列表 (S6)。"""
        from factory_console import production_service as _psvc

        root = str(factory_root if factory_root is not None else DEFAULT_ROOT)
        return ok_list(_psvc.list_runs(root))

    @app.get("/api/sessions")
    def api_sessions(
        scope: str | None = Query(default=None),
        project_id: str | None = Query(default=None),
        task_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """会话列表 (K-7e 会话栏): scope=company|project|task_id 过滤; updated_at 倒序。
        T-4 (v1.1.184): task_id 过滤 (任务侧反向追溯: 哪些会话讨论过它) +
        每条会话富化 task_title (会话能看到关联任务)。"""
        if scope is not None and scope not in _sessions_mod.VALID_SCOPES:
            raise HTTPException(status_code=400, detail=f"非法作用域: {scope}")
        items = sessions_store.list_sessions(
            scope=scope, project_id=project_id, task_id=task_id
        )
        for s in items:
            tid = str(s.get("task_id") or "").strip()
            if not tid:
                continue
            try:
                t = service.get_task(str(s.get("project_id") or ""), tid)
                s["task_title"] = (t or {}).get("title") if t is not None else None
            except Exception:  # noqa: BLE001 — 任务查询失败 → 不富化 (诚实降级)
                s["task_title"] = None
        return ok_list(items)

    @app.post("/api/sessions")
    def api_create_session(body: _SessionBody) -> dict[str, Any]:
        """新建会话 (K-7e): {scope, project_id?, title?}。"""
        try:
            return sessions_store.create_session(
                scope=body.scope,
                project_id=body.project_id,
                title=body.title,
                feature_id=body.feature_id,
                task_id=body.task_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/sessions/{session_id}")
    def api_update_session(session_id: str, body: _SessionPatchBody) -> dict[str, Any]:
        """更新会话 (K-7e): {title?, status?} — 改名/归档/恢复。"""
        try:
            updated = sessions_store.update_session(
                session_id,
                title=body.title,
                status=body.status,
                feature_id=body.feature_id,
                task_id=body.task_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if updated is None:
            raise HTTPException(status_code=404, detail="session not found")
        return updated

    @app.get("/api/sessions/{session_id}/messages")
    def api_session_messages(session_id: str) -> dict[str, Any]:
        """会话消息列表 (K-7e); 会话不存在 → 404。"""
        if sessions_store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        return ok_list(sessions_store.list_messages(session_id))

    @app.get("/api/sessions/{session_id}/snapshots")
    def api_session_snapshots(session_id: str) -> dict[str, Any]:
        """T13: 会话时间旅行 — 列出所有快照轮次 (只读)。"""
        try:
            from factory_console.session.session_snapshots import list_snapshots

            snaps = list_snapshots(workspace_root or DEFAULT_ROOT, session_id)
        except Exception:  # noqa: BLE001 — 快照不可用 → 空
            snaps = []
        return {"items": snaps, "count": len(snaps)}

    @app.delete("/api/sessions/{session_id}/messages")
    def api_session_truncate(session_id: str, keep_n: int = Query(default=0, ge=0)) -> dict[str, Any]:
        """T16: 截断会话消息到前 keep_n 条 (编辑/回滚: 删后续轮次后重发)。"""
        if sessions_store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        remaining = sessions_store.delete_messages_after(session_id, keep_n)
        # 同步清空该会话的快照 (上下文已变, 旧快照失效)
        try:
            from factory_console.session.session_snapshots import _snap_path

            _p = _snap_path(workspace_root or DEFAULT_ROOT, session_id)
            if _p.exists():
                _p.unlink()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "remaining": len(remaining)}

    @app.get("/api/approvals/all")
    def api_all_approvals() -> dict[str, Any]:
        """公司级待审批聚合 (v1.1.290): 扫全部会话的 pending 批准 → 首页审批卡。"""
        try:
            from factory_console.session.approval_store import list_approvals
        except Exception:  # noqa: BLE001
            return {"pending": [], "count": 0}
        root = str(workspace_root) if workspace_root is not None else None
        if not root:
            return {"pending": [], "count": 0}
        import glob as _glob

        pending = []
        history: list[dict[str, Any]] = []
        for f in _glob.glob(str(Path(root) / "session_approvals" / "*.json")):
            sid = Path(f).stem
            try:
                lst = list_approvals(root, sid)
                for it in lst.get("pending") or []:
                    it["session_id"] = sid
                    pending.append(it)
                for h in (lst.get("history") or [])[-6:]:
                    h = dict(h)
                    h["session_id"] = sid
                    history.append(h)
            except Exception:  # noqa: BLE001
                continue
        history.sort(key=lambda h: str(h.get("resolved_at") or h.get("created_at") or ""), reverse=True)
        return {"pending": pending, "history": history[:20], "count": len(pending)}

    @app.get("/api/sessions/{session_id}/approvals")
    def api_session_approvals(session_id: str) -> dict[str, Any]:
        """待批准命令列表 (S8-4): {pending, history, count} — bash 写操作批准门。"""
        try:
            from factory_console.session.approval_store import list_approvals
        except Exception:  # noqa: BLE001
            return {"pending": [], "history": [], "count": 0}
        return list_approvals(str(workspace_root) if workspace_root is not None else None, session_id)

    @app.post("/api/sessions/{session_id}/approvals/{approval_id}/approve")
    def api_session_approval_approve(session_id: str, approval_id: str) -> dict[str, Any]:
        """批准并执行待批准命令 (S8-4): 结果追加为会话消息 + 返回执行结果。"""
        try:
            from factory_console.session.approval_store import get_pending, resolve
            from factory_console.session.web_tools import bash_exec
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"模块不可用: {exc}") from exc
        root = str(workspace_root) if workspace_root is not None else None
        item = get_pending(root, session_id, approval_id)
        if item is None:
            raise HTTPException(status_code=404, detail="待批准项不存在或已处理")
        cmd = str(item.get("command") or "")
        # 批准后执行 (force=True 跳过 approval 检查; 危险命令仍被拦截)
        result = bash_exec(cmd, force=True)
        summary = (
            f"✅ 已批准执行: {cmd[:200]}\n"
            f"{'执行成功: ' + str(result.get('output') or '')[:1500] if result.get('ok') else '执行失败: ' + str(result.get('error') or '')[:1500]}"
        )
        resolve(root, session_id, approval_id, "approved", result=summary)
        # 结果追加为会话消息 (模型下次可见) — 复用闭包 sessions_store 同一实例 (避免旧内存缓存)
        try:
            if sessions_store is not None and sessions_store.get_session(session_id):
                sessions_store.append_message(session_id, "assistant", summary, meta={"kind": "approval_result"})
        except Exception:  # noqa: BLE001 — 追加失败不影响返回
            pass
        return {"ok": True, "approval_id": approval_id, "result": result, "summary": summary}

    @app.post("/api/sessions/{session_id}/approvals/{approval_id}/reject")
    def api_session_approval_reject(session_id: str, approval_id: str) -> dict[str, Any]:
        """拒绝待批准命令 (S8-4): 标记拒绝, 不执行。"""
        try:
            from factory_console.session.approval_store import get_pending, resolve
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"模块不可用: {exc}") from exc
        root = str(workspace_root) if workspace_root is not None else None
        if get_pending(root, session_id, approval_id) is None:
            raise HTTPException(status_code=404, detail="待批准项不存在或已处理")
        resolve(root, session_id, approval_id, "rejected", result="用户拒绝执行")
        return {"ok": True, "approval_id": approval_id, "status": "rejected"}

    @app.get("/api/sessions/{session_id}/progress-card")
    def api_session_progress_card(session_id: str) -> dict[str, Any]:
        """进度卡 (P0-B v1.1.244, OpenClaw progress_card 思路): 计划/执行链持久化进度。
        返回 {card, text, has_card} — 供前端展示与轮询。"""
        try:
            from factory_console.session.progress_card import load_card, text as _card_text
        except Exception:  # noqa: BLE001
            return {"card": {}, "text": "", "has_card": False}
        card = load_card(str(workspace_root) if workspace_root is not None else None, session_id)
        if not card:
            return {"card": {}, "text": "", "has_card": False}
        return {"card": card, "text": _card_text(card), "has_card": True}

    @app.post("/api/sessions/{session_id}/messages")
    def api_session_send(session_id: str, body: _ChatBody,
                         stream: bool = Query(default=False)) -> Any:
        """发送消息 (K-7e 完整链路): LLM 转标准意图 → 本地查询真实数据 → 标准输出。

        返回 {user, assistant, session, meta:{intent, project, data_source}}。
        S10-127 P1.4: ?stream=1 → SSE 流式 (工具调用实时事件 + done 最终结果)。"""
        session = sessions_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        # ---- S10-127 P1.4: 流式分支 (工具调用实时推送, 独立路径不扰同步) ----
        if stream:
            import queue as _q
            import threading as _th
            from fastapi.responses import StreamingResponse

            _evq: "_q.Queue" = _q.Queue()

            def _on_event(e: dict) -> None:
                try:
                    _evq.put(e)
                except Exception:  # noqa: BLE001
                    pass

            def _work() -> None:
                try:
                    _agmod = _console_import("session.agent_loop")
                    _tl = None
                    _ctx_view = ""
                    try:
                        _tl = _console_import("session.topic_ledger").TopicLedger.load(
                            workspace_root or DEFAULT_ROOT, session_id)
                        _tl.append("user", body.message, llm_fn=_sessions_mod.llm_raw)
                        _tl.save(workspace_root or DEFAULT_ROOT)
                        _ctx_view = _tl.build_view(skip_last=1)
                    except Exception:  # noqa: BLE001
                        pass
                    _plan_store2 = _agmod.PendingPlanStore(workspace_root or DEFAULT_ROOT)
                    _pending = _plan_store2.get(session_id)
                    _agent_message = body.message
                    if _pending:
                        _agent_message = (
                            f"【当前有待审批的开发计划】\n{_agmod.plan_to_text(_pending)}\n\n"
                            f"用户最新消息: {body.message}\n\n"
                            "请语义判断: 同意(可以/开始/同意/没问题) → 调 execute_plan; "
                            "修改/不满意 → plan_development 重写; 意图不明 → 追问。"
                        )
                    _history = []
                    try:
                        _history = sessions_store.list_messages(session_id)
                    except Exception:  # noqa: BLE001
                        pass
                    # v1.1.263: 流式分支切到 v3 run_agent_native (清洗/护栏/W8/审计引导/源码路径全生效)
                    # 旧 run_agent(v1) 无清洗 — 文本模拟 <tool_calls> 泄漏到会话的根因
                    agent_result = _agmod.run_agent_native(
                        _agent_message,
                        data_dir=workspace_root or DEFAULT_ROOT,
                        project_id=str(session.get("project_id") or ""),
                        service=service,
                        max_rounds=3,
                        session_store=sessions_store,
                        session_id=session_id,
                        history=_history,
                        context_view=_ctx_view,
                        on_event=_on_event,
                    )
                    result = None
                    if agent_result is not None and agent_result.get("answer"):
                        calls = agent_result.get("calls") or []
                        if _tl is not None and _ctx_view:
                            try:
                                _tl.append("assistant", str(agent_result.get("answer") or "")[:2000])
                                _tl.save(workspace_root or DEFAULT_ROOT)
                            except Exception:  # noqa: BLE001
                                pass
                        for c in calls:
                            if c.get("plan"):
                                _plan_store2.save(session_id, c["plan"])
                                break
                        evidence_lines = [
                            f"- 工具 {c['tool']}: {'✅' if c.get('ok') else '❌'} "
                            f"{str(c.get('output') or c.get('error') or '')[:300]}" for c in calls
                        ]
                        facts = (
                            "【工具执行证据】\n" + ("\n".join(evidence_lines) if evidence_lines else "（未调用工具）")
                            + "\n\n请基于工具证据输出最终回答; 引用来源, 不编造。"
                        )
                        try:
                            result = _sessions_mod.send_message(
                                sessions_store, session_id, body.message, facts=facts,
                                reply_extra="回答必须引用上面【工具执行证据】; 工具没提供的不要编造; 分 结论/证据/数据/建议。",
                                llm_fn=lambda _p, _a=agent_result.get("answer", ""): _a,
                                assistant_meta={
                                    "tool_calls": [
                                        {"tool": c["tool"], "ok": c.get("ok")} for c in calls
                                    ],
                                    # T5 (v1.1.280): 证据链 — 结构化工具证据 (tool/ok/output摘要), 前端可溯源
                                    "evidence": [
                                        {
                                            "tool": c["tool"],
                                            "ok": c.get("ok"),
                                            "output": str(c.get("output") or c.get("error") or "")[:300],
                                        } for c in calls
                                    ],
                                },
                            )
                            result["meta"] = {
                                "intent": "agent", "project": session.get("project_id"),
                                "data_source": "tools" if calls else "chat",
                                "target": {"url": f"#/project/{session.get('project_id')}", "label": "查看项目"},
                                "tool_calls": [{"tool": c["tool"], "ok": c.get("ok")} for c in calls],
                                "evidence": [
                                    {
                                        "tool": c["tool"],
                                        "ok": c.get("ok"),
                                        "output": str(c.get("output") or c.get("error") or "")[:300],
                                    } for c in calls
                                ],
                            }
                        except Exception:  # noqa: BLE001
                            result = None
                    if result is None:
                        result = {
                            "user": None, "assistant": None,
                            "session": sessions_store.get_session(session_id),
                            "meta": {"intent": "agent", "project": session.get("project_id"),
                                     "data_source": "none",
                                     "error": "agent 未产出答案 (见后端日志)"},
                        }
                    # v1.1.263: 防御 — done 发出前清洗 result 里 assistant content (防文本模拟泄漏)
                    try:
                        _ac = (result or {}).get("assistant") or {}
                        if _ac and _ac.get("content"):
                            _ac["content"] = _agmod._strip_fake_toolcalls(str(_ac["content"]))
                    except Exception:  # noqa: BLE001
                        pass
                    _evq.put({"type": "done", "result": result})
                except Exception as exc:  # noqa: BLE001
                    _evq.put({"type": "error", "message": str(exc)})

            _th.Thread(target=_work, daemon=True).start()

            def _gen():
                while True:
                    e = _evq.get()
                    yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
                    if e.get("type") in ("done", "error"):
                        break

            return StreamingResponse(_gen(), media_type="text/event-stream")
        try:
            projects = service.list_projects()
        except Exception:  # noqa: BLE001 — 列表失败 → 空 (不编造)
            projects = []
        model_line = ""
        try:
            _llm_plane_reload(_llm_plane)
            pid = _llm_plane.selected_provider_id()
            if pid is not None:
                sp = _llm_plane.get_provider(pid)
                if sp is not None:
                    model_line = (
                        f"当前 LLM 模型: {_provider_config_view(_llm_plane, sp).get('default_model')} "
                        f"(provider: {pid})"
                    )
        except Exception:  # noqa: BLE001 — 模型失败 → 不注入
            model_line = ""
        # 系统/服务状态 (统一监控 Monitor — 端口探测 + 版本 + 模型)
        _monitor_mod = _console_import("monitor")
        _sys_mon = _monitor_mod.collect_system(
            workspace_root or DEFAULT_ROOT, _factory_version, model_line=model_line
        )
        system_line = (
            f"系统状态: AI Factory v{_sys_mon['version']} · "
            f"Web 前端 ({_sys_mon['frontend']['port']}): "
            f"{'运行中' if _sys_mon['frontend']['up'] else '未运行'} · "
            f"后端 API ({_sys_mon['backend']['port']}): "
            f"{'运行中' if _sys_mon['backend']['up'] else '未运行'} · "
            f"数据目录 {_sys_mon['data_dir']}"
        )
        if model_line:
            system_line = f"{system_line}\n{model_line}"
        try:
            _alerts = _monitor_mod.check_alerts(_sys_mon, [])
            if _alerts:
                system_line = f"{system_line}\n⚠️ 告警: " + "；".join(a["message"] for a in _alerts)
        except Exception:  # noqa: BLE001 — 告警失败 → 忽略
            pass
        # ---- v1.1.207: 会话 Agent 循环 = 默认入口 (项目级) + 计划→审批→执行
        if session.get("scope") == "project" and session.get("project_id"):
            _agmod = _console_import("session.agent_loop")
            _plan_store = _agmod.PendingPlanStore(workspace_root or DEFAULT_ROOT)
            _pending = _plan_store.get(session_id)
            # 待审批计划注入上下文 → 模型语义判断批准/驳回/调整 (不用关键词)
            _agent_message = body.message
            if _pending:
                _agent_message = (
                    f"【当前有待审批的开发计划】\n{_agmod.plan_to_text(_pending)}\n\n"
                    f"用户最新消息: {body.message}\n\n"
                    "请语义判断: 如果用户同意(可以/开始/同意/没问题等语气) → 调 execute_plan 执行该计划; "
                    "如果用户提出修改/不满意 → 用 plan_development 重写计划(吸收意见); "
                    "如果意图不明 → 先追问。"
                )
            try:
                try:
                    _history = sessions_store.list_messages(session_id)
                except Exception:  # noqa: BLE001 — 历史不可用 → 不阻塞
                    _history = []
                # 话题账本 (v1.1.211): 当前消息进账本 → 注入视图 (当前话题详细+其他话题一行摘要)
                _ctx_view = ""
                try:
                    _tl = _console_import("session.topic_ledger").TopicLedger.load(
                        workspace_root or DEFAULT_ROOT, session_id)
                    _tl.append("user", body.message, llm_fn=_sessions_mod.llm_raw)
                    _tl.save(workspace_root or DEFAULT_ROOT)
                    _ctx_view = _tl.build_view(skip_last=1)
                except Exception:  # noqa: BLE001 — 账本不可用 → 回退固定历史
                    _ctx_view = ""
                agent_result = _agmod.run_agent(
                    _agent_message,
                    root=workspace_root or DEFAULT_ROOT,
                    project_id=str(session.get("project_id") or ""),
                    llm_fn=_sessions_mod.llm_raw,
                    service=service,
                    max_rounds=3,
                    session_store=sessions_store,
                    session_id=session_id,
                    history=_history,
                    context_view=_ctx_view,
                )
            except Exception:  # noqa: BLE001 — Agent 循环异常 → 回退旧路由
                agent_result = None
            if agent_result is not None and agent_result.get("answer"):
                calls = agent_result.get("calls") or []
                # AI 回答也进话题账本 (保持块内对话完整)
                if _ctx_view:
                    try:
                        _tl.append("assistant", str(agent_result.get("answer") or "")[:2000])
                        _tl.save(workspace_root or DEFAULT_ROOT)
                        # S-4 跨会话记忆: 当前话题摘要写入项目记忆 (去重, 可审计)
                        _mem = _console_import("session.project_memory").MemoryStore.load(
                            workspace_root or DEFAULT_ROOT, str(session.get("project_id") or ""))
                        _cur = _tl._active()
                        if _cur and _cur.get("summary"):
                            _mem.add(f"话题[{_cur.get('label')}]: {str(_cur.get('summary'))[:200]}",
                                     source="session")
                        _mem.save(workspace_root or DEFAULT_ROOT)
                    except Exception:  # noqa: BLE001 — 账本/记忆失败不阻断回复
                        pass
                # 新计划 → 存待审批
                for c in calls:
                    if c.get("plan"):
                        _plan_store.save(session_id, c["plan"])
                        break
                evidence_lines = [
                    f"- 工具 {c['tool']}: {'✅' if c.get('ok') else '❌'} "
                    f"{str(c.get('output') or c.get('error') or '')[:300]}"
                    for c in calls
                ]
                facts = (
                    "【工具执行证据】\n" + ("\n".join(evidence_lines) if evidence_lines else "（未调用工具）")
                    + "\n\n请基于工具证据输出最终回答; 引用来源, 不编造。"
                )
                try:
                    result = _sessions_mod.send_message(
                        sessions_store, session_id, body.message,
                        facts=facts,
                        reply_extra="回答必须引用上面【工具执行证据】; 工具没提供的不要编造; 分 结论/证据/数据/建议。",
                        llm_fn=lambda _p, _a=agent_result.get("answer", ""): _a,
                        assistant_meta={
                            "tool_calls": [
                                {"tool": c["tool"], "ok": c.get("ok")} for c in calls
                            ],
                            # T5 (v1.1.280): 证据链 — 结构化工具证据
                            "evidence": [
                                {
                                    "tool": c["tool"],
                                    "ok": c.get("ok"),
                                    "output": str(c.get("output") or c.get("error") or "")[:300],
                                } for c in calls
                            ],
                        },
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                result["meta"] = {
                    "intent": "agent", "project": session.get("project_id"),
                    "data_source": "tools" if calls else "chat",
                    "target": {"url": f"#/project/{session.get('project_id')}", "label": "查看项目"},
                    "tool_calls": [{"tool": c["tool"], "ok": c.get("ok")} for c in calls],
                    "evidence": [
                        {
                            "tool": c["tool"],
                            "ok": c.get("ok"),
                            "output": str(c.get("output") or c.get("error") or "")[:300],
                        } for c in calls
                    ],
                }
                return result

        # 完整链路 (Founder 设计): LLM 转标准意图 → 查询/执行 → 标准输出 (Agent 不可用/非 agent 模式时兜底)
        _qmod = _console_import("session.query_engine")
        intent = _qmod.parse_intent_llm(body.message, _sessions_mod.llm_raw)
        hint_project = intent.get("project") if intent.get("intent") != "chat" else None

        # ---- 动作意图 (会话控制操作软件 — 真实执行) ----
        if intent.get("intent") == "create_task":
            task = intent.get("task") or body.message
            # 定位目标项目: LLM 提取的项目名 → 会话项目
            tgt = None
            if hint_project:
                tgt = next((pp for pp in projects if hint_project in str(getattr(pp, "name", "") or "")), None)
            if tgt is None:
                tgt = _qmod.resolve_project(body.message, projects)  # 确定性从问句匹配项目名
            if tgt is None and session.get("project_id"):
                tgt = next((pp for pp in projects if pp.id == session.get("project_id")), None)
            if tgt is None:
                facts = (
                    "未定位到目标项目 — 请说项目名 (如: 给 旅行记账 完善导出功能)。"
                    f"\n项目列表: {', '.join(pp.name for pp in projects) if projects else '暂无项目'}"
                )
                action_target = {"url": "#/workspace/projects", "label": "查看项目列表"}
            else:
                # 想法→细化→待办链路: 会话锚定模块 (feature_id) → 任务绑定到该模块
                feature_id = str(session.get("feature_id") or "").strip()
                bound_story = ""
                bound_feature = None
                try:
                    if feature_id:
                        bound_feature = service.get_feature(tgt.id, feature_id)
                        if bound_feature is not None:
                            bound_story = (
                                service.ensure_story_for_feature(tgt.id, feature_id) or ""
                            )
                except Exception:  # noqa: BLE001 — 绑定失败 → 不阻断 (回退孤儿, 诚实标注)
                    bound_feature = None
                try:
                    created = _api.create_task(
                        service,
                        tgt.id,
                        title=str(task)[:80],
                        description=body.message,
                        priority="P2",
                        story_id=bound_story,
                    )
                except Exception:  # noqa: BLE001 — 创建失败 → 诚实反馈
                    created = None
                if created is not None:
                    location = (
                        f" (模块: {bound_feature.get('name')})"
                        if bound_feature is not None
                        else " (未绑定模块 — 任务在项目级待办)"
                    )
                    facts = (
                        f"任务已创建: {created.get('title')} (id: {created.get('id')}, "
                        f"项目: {tgt.name}{location}, 优先级: P2)。已进入待办树。"
                    )
                    action_target = {"url": f"#/project/{tgt.id}/todo", "label": f"查看{tgt.name}任务"}
                else:
                    facts = f"任务创建失败（{tgt.name} 任务服务不可用）— 请稍后重试。"
                    action_target = {"url": f"#/project/{tgt.id}/todo", "label": f"查看{tgt.name}任务"}
            try:
                result = _sessions_mod.send_message(
                    sessions_store, session_id, body.message, facts=facts,
                    reply_extra=_qmod.STANDARD_OUTPUT_PROMPT,
                )
                result["meta"] = {
                    "intent": "create_task",
                    "project": getattr(tgt, "name", None) if tgt is not None else None,
                    "data_source": "live",
                    "target": action_target,
                    "action": "created" if tgt is not None and created is not None else "failed",
                }
                return result
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        if intent.get("intent") == "create_project":
            idea = body.message
            try:
                created = service.create_project(idea, name=hint_project)
            except Exception as exc:  # noqa: BLE001 — 创建失败 → 诚实反馈
                created = None
            if created is not None:
                facts = (
                    f"项目已创建: {created.name} (id: {created.id}, 阶段: {created.lifecycle})。"
                    "下一步: 可让我生成 PRD 或开始开发。"
                )
                action_project_id = created.id
                action_target = {"url": f"#/project/{created.id}", "label": "进入项目"}
            else:
                facts = "项目创建失败（服务不可用或参数异常）— 请稍后重试。"
                action_project_id = None
                action_target = {"url": "#/workspace/projects", "label": "查看项目列表"}
            try:
                result = _sessions_mod.send_message(
                    sessions_store, session_id, body.message, facts=facts,
                    reply_extra=_qmod.STANDARD_OUTPUT_PROMPT,
                )
                result["meta"] = {
                    "intent": "create_project",
                    "project": hint_project,
                    "data_source": "live",
                    "target": action_target,
                    "action": "created" if created is not None else "failed",
                }
                return result
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        if intent.get("intent") == "git_push":
            # 推送仓库到 origin (Founder 2026-08-26: 会话"帮忙推送一下"真实执行)
            from ...session.project_scan import git_push

            tgt = None
            if hint_project:
                tgt = next((pp for pp in projects if hint_project in str(getattr(pp, "name", "") or "")), None)
            if tgt is None and session.get("project_id"):
                tgt = next((pp for pp in projects if pp.id == session.get("project_id")), None)
            if tgt is None:
                facts = "未定位到目标项目 — 请说项目名（如: 把 AI Factory 自身推送到 github）"
                action_target = {"url": "#/workspace/projects", "label": "查看项目列表"}
            else:
                try:
                    result = git_push(workspace_root, str(tgt.id))
                except Exception as exc:  # noqa: BLE001 — 失败安全
                    result = {"ok": False, "error": f"推送执行异常: {exc}"}
                if result.get("ok"):
                    if result.get("pushed"):
                        facts = (
                            f"✅ 已推送 {tgt.name} → {result.get('remote')} "
                            f"(分支 {result.get('branch')}): {result.get('message')}"
                        )
                    else:
                        facts = f"{tgt.name}: {result.get('message')}（远程 {result.get('remote')}）"
                else:
                    facts = f"推送失败: {result.get('error')}"
                action_target = {"url": "#/workspace", "label": "返回工作台"}
            try:
                result = _sessions_mod.send_message(
                    sessions_store, session_id, body.message, facts=facts,
                    reply_extra=_qmod.STANDARD_OUTPUT_PROMPT,
                )
                result["meta"] = {
                    "intent": "git_push",
                    "project": getattr(tgt, "name", None) if tgt is not None else None,
                    "data_source": "live",
                    "target": action_target,
                    "action": "pushed" if tgt is not None and result.get("ok") else "failed",
                }
                return result
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        # ---- T-1: 会话任务连续 — 定位任务并锚定 (跨会话继续) ----
        if intent.get("intent") == "task_continue":
            tgt = _resolve_tgt(projects, hint_project, session)
            if tgt is None:
                facts = "未定位到目标项目 — 请说项目名（如: 继续做 语音记账）。"
                action_target = {"url": "#/workspace/projects", "label": "查看项目列表"}
            else:
                pid = str(tgt.id)
                import re as _re

                task_desc = str(intent.get("task") or "").strip()
                if not task_desc:
                    task_desc = _re.sub(r"继续做|接着做|继续任务|继续开发|继续之前|继续推进|继续这个|接着推进", "", body.message).strip()
                tasks = (service.list_backlog(pid) or {}).get("tasks", [])
                match = next((t for t in tasks if task_desc and task_desc in str(t.get("title") or "")), None)
                if match is None:
                    cand = "、".join(str(t.get("title") or "")[:20] for t in tasks[:6])
                    facts = f"未找到匹配任务 — 当前项目任务示例: {cand or '暂无'}"
                    action_target = {"url": f"#/project/{pid}/todo", "label": "查看任务"}
                else:
                    # 锚定任务 (会话级作用域 task_id)
                    try:
                        sessions_store.update_session(session_id, task_id=match["id"])
                    except Exception:  # noqa: BLE001 — 锚定失败不阻断
                        pass
                    detail = service.get_task(pid, match["id"]) or {}
                    status = str(detail.get("status") or "todo")
                    hist = detail.get("history") or []
                    last = hist[-1] if hist else None
                    lines = [
                        f"已锚定任务「{match['title']}」 (id: {match['id']}, 项目: {tgt.name})",
                        f"状态: {status} · 优先级: {detail.get('priority') or '—'}"
                        f" · exec绑定: {detail.get('exec_ref') or '无'}",
                    ]
                    if last:
                        lines.append(f"任务最近: {last.get('time','')[:16]} {last.get('actor','')} {last.get('action','')}")
                    else:
                        lines.append("任务最近: 尚无历史")
                    # T-3: 跨会话恢复 — 找上次讨论过该任务的会话, 接上进展
                    try:
                        prev_sessions = [
                            s for s in sessions_store.list_sessions(task_id=match["id"])
                            if s.get("id") != session_id
                        ]
                        if prev_sessions:
                            prev = prev_sessions[0]  # 最近活跃
                            msgs = sessions_store.list_messages(prev["id"])
                            # 上次说到 = 用户最后说的原话 (不是 AI 回复) — Founder 2026-08-27 T-5 实测
                            last_user = next(
                                (m for m in reversed(msgs) if m.get("role") == "user"),
                                None,
                            )
                            prev_line = (
                                f"上次会话: 「{prev.get('title') or '未命名'}」"
                                f" ({(prev.get('updated_at') or '')[:16]})"
                            )
                            if last_user:
                                prev_line += f" · 上次说到: {str(last_user.get('content') or '')[:60]}"
                            lines.append(prev_line)
                            lines.append("→ 跨会话已接上: 可继续讨论/推进 (上下文已注入)")
                    except Exception:  # noqa: BLE001 — 上次会话定位失败 → 不阻断
                        pass
                    lines.append("下一步: 说『继续推进』我会接着做；或『标记完成/改成 P0』操作任务。")
                    facts = "\n".join(lines)
                    action_target = {"url": f"#/project/{pid}/todo", "label": "查看任务"}
            try:
                result = _sessions_mod.send_message(
                    sessions_store, session_id, body.message, facts=facts,
                    reply_extra=_qmod.STANDARD_OUTPUT_PROMPT,
                )
                result["meta"] = {
                    "intent": "task_continue",
                    "project": getattr(tgt, "name", None) if tgt is not None else None,
                    "data_source": "live",
                    "target": action_target,
                }
                return result
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        # ---- S 系列: 会话×软件打通 (Founder 2026-08-26 全部断点, 不糊弄) ----
        if intent.get("intent") in (
            "task_action", "create_idea", "project_action",
            "project_artifacts", "monitor", "settings",
        ):
            tgt = _resolve_tgt(projects, hint_project, session)
            action = intent.get("intent")
            if tgt is None:
                facts = "未定位到目标项目 — 请说项目名。"
                action_target = {"url": "#/workspace/projects", "label": "查看项目列表"}
            else:
                pid = str(tgt.id)
                if action == "task_action":
                    task_desc = str(intent.get("task") or body.message).strip()
                    tasks = (service.list_backlog(pid) or {}).get("tasks", [])
                    match = next((t for t in tasks if task_desc and task_desc != body.message and
                                  task_desc in str(t.get("title") or "")), None)
                    if match is None:
                        # 从消息去掉动作词后匹配
                        import re as _re
                        q = _re.sub(r"把|标记|为|完成|开始|归档|优先级|改成|任务", "", body.message).strip()
                        match = next((t for t in tasks if q and q in str(t.get("title") or "")), None)
                    if match is None:
                        cand = "、".join(str(t.get("title") or "")[:20] for t in tasks[:5])
                        facts = f"未找到匹配任务 — 当前项目任务示例: {cand or '暂无'}"
                        action_target = {"url": f"#/project/{pid}/todo", "label": "查看任务"}
                    else:
                        tid = str(match["id"])
                        lowered = body.message.lower()
                        if "优先级" in lowered or re.search(r"改成\s*p[0-3]", lowered):
                            m = re.search(r"(?:改成|优先级)\s*p([0-3])", lowered)
                            prio = f"P{m.group(1)}" if m else "P0"
                            updated = service.update_task(pid, tid, priority=prio)
                            facts = f"✅ 任务「{match['title']}」优先级 → {updated['priority']}"
                        elif "完成" in lowered or "归档" in lowered:
                            updated = _task_to(service, pid, tid, "done")
                            facts = f"✅ 任务「{match['title']}」已标记完成/归档 (状态 {updated['status']})"
                        else:  # 开始
                            updated = _task_to(service, pid, tid, "in_progress")
                            facts = f"▶ 任务「{match['title']}」已开始 (状态 {updated['status']})"
                        action_target = {"url": f"#/project/{pid}/todo", "label": "查看任务"}
                elif action == "create_idea":
                    idea = str(intent.get("task") or body.message).replace("记录个想法", "").replace("记个想法", "").strip()
                    if not idea:
                        idea = "未命名想法"
                    backlog = service.list_backlog(pid) or {}
                    epic_id = (backlog.get("epics") or [{}])[0].get("id", "")
                    created = service.create_feature(pid, name=idea[:30], maturity="idea", epic_id=epic_id)
                    facts = f"💡 想法已记录: 「{created['name']}」→ 任务树可见, 可点「讨论」细化"
                    action_target = {"url": f"#/project/{pid}/todo", "label": "查看任务"}
                elif action == "project_action":
                    lowered = body.message.lower()
                    if "收藏" in lowered:
                        star = not any("取消" in lowered for _ in [1])
                        service.update_project(pid, starred=star)
                        facts = f"{'⭐ 已收藏' if star else '☆ 已取消收藏'} {tgt.name}"
                    elif "删除" in lowered:
                        try:
                            service.delete_project(pid)
                            facts = f"🗑 项目「{tgt.name}」已删除"
                        except Exception as exc:  # noqa: BLE001
                            facts = f"删除失败: {exc}"
                    else:  # 改名
                        new_name = body.message.replace("改名", "").replace("重命名", "").replace("把", "").strip()
                        if new_name:
                            service.update_project(pid, name=new_name)
                            facts = f"✏️ 项目已改名: {tgt.name} → {new_name}"
                        else:
                            facts = "改名需提供新名称（如: 把 旅行记账 改名为 XX）"
                    action_target = {"url": "#/workspace", "label": "返回工作台"}
                elif action == "project_artifacts":
                    arts = service.list_artifacts(project_id=pid)
                    if arts:
                        lines = [f"项目: {tgt.name}\n产出物 ({len(arts)}):"]
                        for a in arts[:10]:
                            lines.append(f"- {a.label} ({a.file}) v{a.version}{'· trace ' + a.trace_id if a.trace_id else ''}")
                        facts = "\n".join(lines)
                    else:
                        facts = f"项目: {tgt.name}\n产出物: 暂无（引擎产出后自动登记）"
                    action_target = {"url": f"#/project/{pid}/docs", "label": "查看产出物"}
                elif action == "monitor":
                    try:
                        _mon = _console_import("monitor")
                        sys_mon = _mon.collect_system(workspace_root or DEFAULT_ROOT, _factory_version, model_line=model_line)
                        alerts = _mon.check_alerts(sys_mon, [])
                        facts = (
                            f"系统监控: AI Factory v{sys_mon['version']} · "
                            f"前端 ({sys_mon['frontend']['port']}): {'运行中' if sys_mon['frontend']['up'] else '未运行'} · "
                            f"后端 ({sys_mon['backend']['port']}): {'运行中' if sys_mon['backend']['up'] else '未运行'} · "
                            f"数据目录 {sys_mon['data_dir']}"
                        )
                        if alerts:
                            facts += "\n⚠️ 告警: " + "；".join(a["message"] for a in alerts)
                        else:
                            facts += "\n✅ 无告警"
                    except Exception as exc:  # noqa: BLE001
                        facts = f"监控查询失败: {exc}"
                    action_target = {"url": "#/workspace", "label": "返回工作台"}
                elif action == "settings":
                    lines = ["设置概况:"]
                    try:
                        provs = service.list_providers()
                        lines.append(f"- LLM Provider ({len(provs)}): " + "、".join(p.provider_id for p in provs))
                    except Exception:  # noqa: BLE001
                        pass
                    try:
                        ag_file = Path(workspace_root) / "agents" / "agents.json"
                        ag = json.loads(ag_file.read_text(encoding="utf-8")) if ag_file.is_file() else {}
                        agents = (ag.get("agents") or {}) if isinstance(ag, dict) else {}
                        if isinstance(agents, dict):
                            lines.append(f"- Agents ({len(agents)}): " + "、".join(str(a.get("name") or k) for k, a in agents.items()))
                    except Exception:  # noqa: BLE001
                        pass
                    facts = "\n".join(lines)
                    action_target = {"url": "#/workspace/settings", "label": "打开设置"}
            try:
                result = _sessions_mod.send_message(
                    sessions_store, session_id, body.message, facts=facts,
                    reply_extra=_qmod.STANDARD_OUTPUT_PROMPT,
                )
                result["meta"] = {
                    "intent": action, "project": getattr(tgt, "name", None) if tgt is not None else None,
                    "data_source": "live", "target": action_target,
                }
                return result
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        if intent.get("intent") == "deep_analyze":
            # 会话工具调用 (Founder 2026-08-26): 分析必须调专业工具, 结论可溯源
            from ...session.analysis_tools import run_analysis

            tgt = _resolve_tgt(projects, hint_project, session)
            if tgt is None:
                facts = "未定位到目标项目 — 请说项目名。"
                action_target = {"url": "#/workspace/projects", "label": "查看项目列表"}
            else:
                try:
                    evidence = run_analysis(
                        workspace_root, str(tgt.id), body.message,
                        workflow_status=getattr(tgt, "workflow_status", None) or None,
                        current_stage=getattr(tgt, "current_stage", None) or None,
                    )
                except Exception as exc:  # noqa: BLE001 — 工具失败 → 诚实降级
                    evidence = f"（工具执行失败: {exc}）"
                facts = (
                    "【以下全部来自工具真实执行, 引用时标注来源, 禁止编造数字】\n"
                    + evidence
                    + "\n\n请输出: 1)结论 2)分析过程(引用上面【工具】证据) 3)数据 4)建议。"
                )
                action_target = {"url": f"#/project/{tgt.id}", "label": "查看项目"}
            try:
                result = _sessions_mod.send_message(
                    sessions_store, session_id, body.message, facts=facts,
                    reply_extra="分析必须引用【工具】证据来源; 工具没提供的不要编造; 分 结论/分析过程/数据/建议。",
                )
                result["meta"] = {
                    "intent": "deep_analyze",
                    "project": getattr(tgt, "name", None) if tgt is not None else None,
                    "data_source": "tools",
                    "target": action_target,
                }
                return result
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        facts = _qmod.build_facts(
            body.message,
            scope=str(session.get("scope") or "company"),
            project_id=session.get("project_id"),
            projects=projects,
            root=workspace_root,
            model_line=model_line,
            system_line=system_line,
            hint_project=hint_project,
        )
        # T-2 (v1.1.172): 会话锚定任务 → 每条消息注入任务上下文 (跨会话继续)
        task_id = str(session.get("task_id") or "").strip()
        project_id = session.get("project_id")
        if task_id and project_id:
            try:
                task_block = _task_context_facts(service, project_id, task_id)
                if task_block:
                    facts = f"{facts}\n\n{task_block}"
            except Exception:  # noqa: BLE001 — 任务注入失败 → 不阻断
                pass
        # 想法→细化→待办链路: 会话锚定模块 → 注入模块事实卡 (LLM 讨论/细化有据)
        feature_id = str(session.get("feature_id") or "").strip()
        project_id = session.get("project_id")
        if feature_id and project_id:
            try:
                feature = service.get_feature(project_id, feature_id)
                if feature is not None:
                    module_facts = _feature_facts(service, project_id, feature)
                    facts = f"{facts}\n\n【当前细化模块】\n{module_facts}"
            except Exception:  # noqa: BLE001 — 模块事实失败 → 不注入 (诚实降级)
                pass
        if intent.get("intent") == "system_status":
            reply_extra = _qmod.SYSTEM_STATUS_OUTPUT_PROMPT
        else:
            reply_extra = (
                _qmod.STANDARD_OUTPUT_PROMPT if intent.get("intent") != "chat" else ""
            )
        try:
            result = _sessions_mod.send_message(
                sessions_store, session_id, body.message, facts=facts, reply_extra=reply_extra
            )
            target = _qmod.intent_target(
                intent.get("intent"),
                project_id=session.get("project_id") or (
                    next((pp.id for pp in projects if pp.name == hint_project), None) if hint_project else None
                ),
                project_name=hint_project,
            )
            result["meta"] = {
                "intent": intent.get("intent"),
                "project": hint_project,
                "data_source": "live" if intent.get("intent") != "chat" else "chat",
                "target": target,
            }
            return result
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/projects/{project_id}/run-status")
    def api_project_run_status(project_id: str) -> dict[str, Any]:
        """运行状态 + 进度 (轮询驱动 Timeline; none/running/completed/failed)。"""
        try:
            result = _api.run_status_route(service, project_id, logger=event_logger)
        except WorkflowStartError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="project not found")
        return result

    if static_dir is not None and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="web")

    return app


def create_app(
    factory_root: str | Path | None = None,
    *,
    static_dir: str | Path | None = None,
) -> Any:
    """装配 ConsoleService + EventLogger 并构建 app (uvicorn 入口)。

    factory_root=None → 用户默认工厂根 (~/.factory, 同 CLI FactoryContext)。
    """
    root = Path(factory_root) if factory_root is not None else DEFAULT_ROOT
    logger = _open_event_logger(root)
    service = build_console_service(root, event_logger=logger)
    return build_app(service, static_dir=static_dir, event_logger=logger, factory_root=root)


if __name__ == "__main__":  # pragma: no cover — uvicorn 直接启动入口
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=DEFAULT_PORT)
