/**
 * api/client.ts — 前端 API 客户端。
 *
 * 只读 + 审批决定 + S10-004 Runtime 生命周期 + S10-006.5 项目创建/管理
 * (Human Console MVP 收窄 Permission Boundary):
 * - 全部查询 GET (只读投影)
 * - POST 写面: ① 审批决定 (/api/approvals/{id}/approve|reject) —
 *   Approval 页操作按钮触发; ② S10-004 Runtime 实例生命周期
 *   (POST /projects/{id}/runtimes 创建 + /runtimes/{id}/start|stop|screenshot)
 *   — Runtime Panel 操作按钮触发; ③ S10-006.5 项目创建 (POST /api/projects
 *   {idea} → org 项目壳) — Workspace Home 创建入口触发。
 * - S10-006.5 项目收尾: PATCH /api/projects/{id} (重命名/改 idea) +
 *   DELETE /api/projects/{id} (删除, 运行中 409 诚实拒绝) — Home 列表 ⋯
 *   菜单触发; 其余一切写路径 (register_project/成本等) 不在 Console 范围。
 * - S10-002: Runtime 查询 (projectWorkflow/workflowStages/projectTimeline,
 *   只读 GET) + SSE 事件流 — SSE 封装在 runtimeClient.subscribeEvents
 *   (断线重连 + mock 检测), 本文件只保留 REST 查询/写面。
 *
 * fetch 直接调用 → 组件测试用 vi.stubGlobal('fetch', ...) 注入桩。
 */

import {
  type ApprovalDecisionSummary,
  type ApprovalGateSummary,
  type AgentInfo,
  type ApprovalSummary,
  type ArtifactContent,
  type ArtifactDetail,
  type ArtifactSummary,
  type ConsoleDashboard,
  type DecisionSummary,
  type ExperienceSummary,
  type IdeaSuggestion,
  type LifecycleSummary,
  type LlmProviderConfig,
  type ProjectSummary,
  type ProviderSummary,
  type ProjectUpdatedSummary,
  type RecommendationSummary,
  type ReviewFeedback,
  type ProjectCreatedSummary,
  type RuntimeEventPayload,
  type RuntimeInstance,
  type RuntimeScreenshot,
  type RuntimeSessionPayload,
  type ExecuteResponse,
  type ToolInfo,
  type ToolResult,
  type SkillInfo,
  type MCPConnection,
  type MCPTool,
  type RunStatusResponse,
  type SessionMessage,
  type SessionSummary,
  type StageRunSummary,
  type TimelineEventSummary,
  type WorkflowDetail,
  type WorkflowSummary,
} from '../models/types';

export class ApiError extends Error {
  readonly status: number;
  readonly path: string;

  constructor(path: string, status: number) {
    super(`API ${path} 请求失败 (HTTP ${status})`);
    this.name = 'ApiError';
    this.path = path;
    this.status = status;
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new ApiError(path, res.status);
  }
  return (await res.json()) as T;
}

/** POST 公共路径 (审批决定/Runtime 生命周期/项目创建; 命名避开 put/patch/delete 语义)。 */
async function sendJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new ApiError(path, res.status);
  }
  return (await res.json()) as T;
}

/** PATCH 公共路径 (S10-006.5 项目管理: 重命名/改 idea — 空 body 由后端 400 拒绝)。 */
async function patchJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(path, {
    method: 'PATCH',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new ApiError(path, res.status);
  }
  return (await res.json()) as T;
}

/** DELETE 公共路径 (S10-006.5 项目管理: 删除 — 运行中 409 由后端诚实拒绝)。 */
async function deleteJson<T>(path: string): Promise<T> {
  const res = await fetch(path, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    throw new ApiError(path, res.status);
  }
  return (await res.json()) as T;
}

/** API 客户端 (查询全 GET; 写路径 = 审批决定/项目创建/Runtime 生命周期 POST + 项目管理 PATCH/DELETE)。 */
export const api = {
  dashboard: () => getJson<ConsoleDashboard>('/api/dashboard'),
  // API 规范 v1 (2026-08-26): 集合统一 {items, count} — 前端解包
  projects: async () => (await getJson<{ items: ProjectSummary[] }>('/api/projects')).items,
  // S10-007 阶段三增强: AI 想法理解 (POST /api/projects/suggest → 建议名称/
  // 一句话理解/澄清问题; ai_generated=false → 规则 fallback, 前端标注"快速模式")
  suggestProject: (idea: string) => sendJson<IdeaSuggestion>('/api/projects/suggest', { idea }),
  // S10-006.5: 用户第一公里创建 (POST /api/projects {idea} → org 项目壳;
  // S10-007: name 可选 — 用户确认的名称优先落库, 无 → 规则 slug 兜底;
  // project_type/tech 可选透传; 空 idea 由后端 400 拒绝)
  createProject: (
    idea: string,
    options: { name?: string; projectType?: string; tech?: string } = {},
  ) =>
    sendJson<ProjectCreatedSummary>('/api/projects', {
      idea,
      ...(options.name != null && options.name.length > 0 ? { name: options.name } : {}),
      ...(options.projectType != null && options.projectType.length > 0
        ? { project_type: options.projectType }
        : {}),
      ...(options.tech != null && options.tech.length > 0 ? { tech: options.tech } : {}),
    }),
  // S10-006.5 收尾: 项目管理 — 重命名/改 idea (PATCH → ProjectUpdatedSummary
  // {project_id, name, idea, status}; 空 name/idea / 无事可做 → 400 诚实拒绝)
  updateProject: (projectId: string, changes: { name?: string; idea?: string; starred?: boolean; archived?: boolean }) =>
    patchJson<ProjectUpdatedSummary>(
      `/api/projects/${encodeURIComponent(projectId)}`,
      changes,
    ),
  // S10-006.5 收尾: 项目管理 — 删除 (DELETE → {deleted: true, project_id};
  // 运行中 → 409 由后端拒绝, 前端提示"正在开发中")
  deleteProject: (projectId: string) =>
    deleteJson<{ deleted: boolean; project_id: string }>(
      `/api/projects/${encodeURIComponent(projectId)}`,
    ),
  lifecycle: (projectId: string) =>
    getJson<LifecycleSummary>(
      `/api/projects/${encodeURIComponent(projectId)}/lifecycle`,
    ),
  // S10-006.5 P1-A: 启动真实 Agent 执行链 + chat + run 状态
  startWorkflow: (projectId: string) =>
    sendJson<{ status: string; run_id?: string }>(
      `/api/projects/${encodeURIComponent(projectId)}/start`,
      {},
    ),
  sendChat: (projectId: string, message: string) =>
    sendJson<{ status: string; message: string; started?: boolean }>(
      `/api/projects/${encodeURIComponent(projectId)}/chat`,
      { message },
    ),
  runStatus: (projectId: string) =>
    getJson<RunStatusResponse>(
      `/api/projects/${encodeURIComponent(projectId)}/run-status`,
    ),
  approvals: async (pendingOnly = false) =>
    (await getJson<{ items: ApprovalSummary[] }>(`/api/approvals${pendingOnly ? '?pending_only=true' : ''}`)).items,
  // S9-002: 组织级审批门 (org ApprovalGate) — 可操作
  approvalGates: async (pendingOnly = false) =>
    (await getJson<{ items: ApprovalGateSummary[] }>(
      `/api/approval-gates${pendingOnly ? '?status=pending' : ''}`,
    )).items,
  decision: (decisionId: string) =>
    getJson<DecisionSummary>(`/api/decisions/${encodeURIComponent(decisionId)}`),
  recommendations: async (limit = 10) =>
    (await getJson<{ items: RecommendationSummary[] }>(`/api/recommendations?limit=${limit}`)).items,
  experience: async (limit = 10) => (await getJson<{ items: ExperienceSummary[] }>(`/api/experience?limit=${limit}`)).items,
  providers: async () => (await getJson<{ items: ProviderSummary[] }>('/api/providers')).items,
  // S9-002: 组织级 Workflow / Artifact (只读查询)
  workflows: async (projectId?: string) =>
    (await getJson<{ items: WorkflowSummary[] }>(`/api/workflows${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`)).items,
  workflow: (workflowId: string) =>
    getJson<WorkflowDetail>(`/api/workflows/${encodeURIComponent(workflowId)}`),
  artifacts: async (filters: { projectId?: string; workflowId?: string; type?: string } = {}) => {
    const params = new URLSearchParams();
    if (filters.projectId) params.set('project_id', filters.projectId);
    if (filters.workflowId) params.set('workflow_id', filters.workflowId);
    if (filters.type) params.set('type', filters.type);
    const qs = params.toString();
    return (await getJson<{ items: ArtifactSummary[] }>(`/api/artifacts${qs ? `?${qs}` : ''}`)).items;
  },
  // S9-002: 审批决定 (Console 唯一写路径; source=console 审计由后端落库)
  // S9-003: 可选 comment 透传 (Review 页反馈输入 → gate.comment 持久化;
  //         空串不发送键 — S9-002 无 body 调用兼容)
  approveApproval: (approvalId: string, comment = '') =>
    sendJson<ApprovalDecisionSummary>(
      `/api/approvals/${encodeURIComponent(approvalId)}/approve`,
      { reviewer: 'console', ...(comment ? { comment } : {}) },
    ),
  rejectApproval: (approvalId: string, comment = '') =>
    sendJson<ApprovalDecisionSummary>(
      `/api/approvals/${encodeURIComponent(approvalId)}/reject`,
      { reviewer: 'console', ...(comment ? { comment } : {}) },
    ),
  // S9-003: 单产物详情 (Review 数据源: metadata 契约载荷 + review 审批门)
  artifact: (artifactId: string) =>
    getJson<ArtifactDetail>(`/api/artifacts/${encodeURIComponent(artifactId)}`),
  // S10-005: 产物渲染内容 (location 文件文本 — Code diff 兜底 / Release 下载源)
  artifactContent: (artifactId: string) =>
    getJson<ArtifactContent>(`/api/artifacts/${encodeURIComponent(artifactId)}/content`),
  // S10-006: 审核反馈历史 (Feedback Loop — GET /api/review-feedback?artifact_id=&gate_id=
  // 过滤均可选; round 升序, 下一轮 Agent 重生成输入按序消费; 缺 store → [] 失败安全)
  reviewFeedback: async (artifactId?: string, gateId?: string) => {
    const params = new URLSearchParams();
    if (artifactId != null && artifactId.length > 0) params.set('artifact_id', artifactId);
    if (gateId != null && gateId.length > 0) params.set('gate_id', gateId);
    const qs = params.toString();
    return (await getJson<{ items: ReviewFeedback[] }>(`/api/review-feedback${qs ? `?${qs}` : ''}`)).items;
  },
  // S10-006: 保存审核反馈 (POST /api/review-feedback — Reject 决定时同步保存结构化
  // 意见; 空意见 → 400 不落库; 缺 store → 503 失败安全)
  saveReviewFeedback: (input: {
    artifact_id: string;
    gate_id: string;
    reviewer?: string;
    comment: string;
  }) =>
    sendJson<ReviewFeedback>('/api/review-feedback', {
      reviewer: input.reviewer ?? 'console',
      artifact_id: input.artifact_id,
      gate_id: input.gate_id,
      comment: input.comment,
    }),
  // S10-002: Runtime API (UI 与 CLI 共用; 全部只读 GET)
  projectWorkflow: (projectId: string) =>
    getJson<WorkflowDetail>(`/api/projects/${encodeURIComponent(projectId)}/workflow`),
  workflowStages: async (workflowId: string) =>
    (await getJson<{ items: StageRunSummary[] }>(`/api/workflows/${encodeURIComponent(workflowId)}/stages`)).items,
  projectTimeline: async (projectId: string, limit = 200) =>
    (await getJson<{ items: TimelineEventSummary[] }>(
      `/api/projects/${encodeURIComponent(projectId)}/timeline?limit=${limit}`,
    )).items,
  // S10-004: Runtime Workspace API (写面 = 实例生命周期 + 截图 — Permission
  // Boundary 扩展; 错误语义: 404 项目/实例不存在 / 400 非法 type / 409 状态机)
  projectRuntimes: async (projectId: string) =>
    (await getJson<{ items: RuntimeInstance[] }>(
      `/api/projects/${encodeURIComponent(projectId)}/runtimes`,
    )).items,
  runtimeDetail: (runtimeId: string) =>
    getJson<RuntimeInstance>(`/api/runtimes/${encodeURIComponent(runtimeId)}`),
  createRuntime: (projectId: string, type: 'browser' | 'terminal', artifactId: string | null = null) =>
    sendJson<RuntimeInstance>(`/api/projects/${encodeURIComponent(projectId)}/runtimes`, {
      type,
      ...(artifactId != null && artifactId.length > 0 ? { artifact_id: artifactId } : {}),
    }),
  startRuntime: (runtimeId: string) =>
    sendJson<RuntimeInstance>(`/api/runtimes/${encodeURIComponent(runtimeId)}/start`, {}),
  stopRuntime: (runtimeId: string) =>
    sendJson<RuntimeInstance>(`/api/runtimes/${encodeURIComponent(runtimeId)}/stop`, {}),
  screenshotRuntime: (runtimeId: string) =>
    sendJson<RuntimeScreenshot>(`/api/runtimes/${encodeURIComponent(runtimeId)}/screenshot`, {}),
  // S10-016: Runtime Session API (AI Employee 执行会话 — 创建/生命周期/事件 +
  // 查询; 错误语义: 400 空 task_id/非法事件类型 / 404 不存在 / 409 状态机非法)
  createRuntimeSession: (
    agentId: string,
    taskId: string,
    workflowId: string | null = null,
  ) =>
    sendJson<RuntimeSessionPayload>(
      `/api/agents/${encodeURIComponent(agentId)}/sessions`,
      {
        task_id: taskId,
        ...(workflowId != null && workflowId.length > 0 ? { workflow_id: workflowId } : {}),
      },
    ),
  startRuntimeSession: (sessionId: string) =>
    sendJson<RuntimeSessionPayload>(
      `/api/runtime-sessions/${encodeURIComponent(sessionId)}/start`,
      {},
    ),
  appendRuntimeSessionEvent: (
    sessionId: string,
    type: string,
    message: string = '',
    data: Record<string, unknown> | null = null,
  ) =>
    sendJson<RuntimeEventPayload>(
      `/api/runtime-sessions/${encodeURIComponent(sessionId)}/events`,
      { type, message, ...(data != null ? { data } : {}) },
    ),
  completeRuntimeSession: (sessionId: string, success: boolean = true) =>
    sendJson<RuntimeSessionPayload>(
      `/api/runtime-sessions/${encodeURIComponent(sessionId)}/complete`,
      { success },
    ),
  cancelRuntimeSession: (sessionId: string) =>
    sendJson<RuntimeSessionPayload>(
      `/api/runtime-sessions/${encodeURIComponent(sessionId)}/cancel`,
      {},
    ),
  runtimeSessions: async (status: 'running' | null = null) =>
    (await getJson<{ items: RuntimeSessionPayload[] }>(
      `/api/runtime-sessions${status ? '?status=running' : ''}`,
    )).items,
  runtimeSessionDetail: (sessionId: string) =>
    getJson<RuntimeSessionPayload>(
      `/api/runtime-sessions/${encodeURIComponent(sessionId)}`,
    ),
  taskRuntimeSessions: async (taskId: string) =>
    (await getJson<{ items: RuntimeSessionPayload[] }>(`/api/tasks/${encodeURIComponent(taskId)}/runtime`)).items,
  // S10-016 Task 002: Agent Executor — 让 AI Employee 真正执行任务 (POST /api/runtime/execute)
  executeRuntimeTask: (taskId: string, agentId: string, context?: Record<string, unknown>) =>
    sendJson<ExecuteResponse>(
      '/api/runtime/execute',
      { task_id: taskId, agent_id: agentId, context },
    ),
  // S10-018 Task 001: Tool Runtime — 工具清单 + 执行 (filesystem.read 等)
  tools: () => getJson<{ tools: ToolInfo[] }>('/api/tools'),
  executeTool: (toolId: string, agentId: string, toolInput: Record<string, unknown>) =>
    sendJson<ToolResult>(`/api/tools/${encodeURIComponent(toolId)}/execute`, {
      agent_id: agentId,
      input: toolInput,
    }),
  // S10-019 Task 001: Skill — 职业能力清单 + Agent 技能分配
  skills: () => getJson<{ skills: SkillInfo[] }>('/api/skills'),
  agents: async () => {
    const d = await getJson<{ agents: AgentInfo[]; count?: number }>('/api/agents');
    return d.agents ?? [];
  },
  agentSkills: (agentId: string) =>
    getJson<{ agent_id: string; skills: string[] }>(
      `/api/agents/${encodeURIComponent(agentId)}/skills`,
    ),
  // S10-020 Task 001: MCP — 外部 MCP 服务连接 + 导入 Tool
  mcpConnections: () => getJson<{ connections: MCPConnection[] }>('/api/mcp/connections'),
  createMCPConnection: (name: string, serverUrl: string, transport?: string) =>
    sendJson<{ id: string; tools: MCPTool[] }>('/api/mcp/connections', {
      name,
      server_url: serverUrl,
      transport,
    }),
  mcpTools: () => getJson<{ tools: MCPTool[] }>('/api/mcp/tools'),
  deleteMCPConnection: (id: string) =>
    deleteJson<{ deleted: boolean }>(`/api/mcp/connections/${encodeURIComponent(id)}`),
  // v1.1.102: 设置管理面 (LLM 配置 + Agent/Skill 管理)
  llmConfig: () => getJson<{ providers: LlmProviderConfig[]; selected: { provider_id: string | null; model: string | null } }>('/api/config/llm'),
  updateLlmConfig: (providerId: string, body: { enabled?: boolean; default_model?: string }) =>
    patchJson<LlmProviderConfig>('/api/config/llm', { provider_id: providerId, ...body }),
  createAgent: (id: string, role: string, skills: string[]) =>
    sendJson<{ id: string; name: string; role: string; skills: string[] }>('/api/agents', { id, role, skills }),
  deleteAgent: (id: string) => deleteJson<{ deleted: boolean }>(`/api/agents/${encodeURIComponent(id)}`),
  createSkill: (id: string, name?: string, category?: string) =>
    sendJson<{ id: string; name: string; category: string; version: string }>('/api/skills', { id, name, category }),
  deleteSkill: (id: string) => deleteJson<{ deleted: boolean }>(`/api/skills/${encodeURIComponent(id)}`),
  // K-7e: Web 会话栏 (会话 + 消息 + 回复)
  sessions: async (scope?: string, projectId?: string) => {
    const params = new URLSearchParams();
    if (scope) params.set('scope', scope);
    if (projectId) params.set('project_id', projectId);
    const qs = params.toString();
    return (await getJson<{ items: SessionSummary[] }>(`/api/sessions${qs ? `?${qs}` : ''}`)).items;
  },
  createSession: (body: { scope: 'company' | 'project'; project_id?: string | null; title?: string }) =>
    sendJson<SessionSummary>('/api/sessions', body),
  updateSession: (id: string, body: { title?: string; status?: string }) =>
    patchJson<SessionSummary>(`/api/sessions/${encodeURIComponent(id)}`, body),
  sessionMessages: async (id: string) =>
    (await getJson<{ items: SessionMessage[] }>(`/api/sessions/${encodeURIComponent(id)}/messages`)).items,
  sendSessionMessage: (id: string, message: string) =>
    sendJson<{ user: SessionMessage; assistant: SessionMessage; session: SessionSummary }>(
      `/api/sessions/${encodeURIComponent(id)}/messages`,
      { message },
    ),

} as const;

export type Api = typeof api;

/** mock fallback (S10-002): 请求失败 (404/网络) → mock 数据 (is_mock 标记)。

 * 只兜底 ApiError (后端不可达/数据缺失), 其他异常照抛; mock 数据必须携带
 * is_mock: true — 前端据此显示演示标识, 不冒充真实数据。
 */
export async function withMockFallback<T>(
  request: () => Promise<T>,
  mock: T & { is_mock: true },
): Promise<T & { is_mock: boolean }> {
  try {
    const data = await request();
    return { ...data, is_mock: (data as { is_mock?: boolean }).is_mock ?? false };
  } catch (err) {
    if (err instanceof ApiError) {
      return mock;
    }
    throw err;
  }
}
