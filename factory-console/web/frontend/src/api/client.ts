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
  type ApprovalSummary,
  type ArtifactContent,
  type ArtifactDetail,
  type ArtifactSummary,
  type ConsoleDashboard,
  type DecisionSummary,
  type ExperienceSummary,
  type IdeaSuggestion,
  type LifecycleSummary,
  type ProjectSummary,
  type ProviderSummary,
  type ProjectUpdatedSummary,
  type RecommendationSummary,
  type ReviewFeedback,
  type ProjectCreatedSummary,
  type RuntimeInstance,
  type RuntimeScreenshot,
  type RunStatusResponse,
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
  projects: () => getJson<ProjectSummary[]>('/api/projects'),
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
  updateProject: (projectId: string, changes: { name?: string; idea?: string }) =>
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
  approvals: (pendingOnly = false) =>
    getJson<ApprovalSummary[]>(`/api/approvals${pendingOnly ? '?pending_only=true' : ''}`),
  // S9-002: 组织级审批门 (org ApprovalGate) — 可操作
  approvalGates: (pendingOnly = false) =>
    getJson<ApprovalGateSummary[]>(
      `/api/approval-gates${pendingOnly ? '?status=pending' : ''}`,
    ),
  decision: (decisionId: string) =>
    getJson<DecisionSummary>(`/api/decisions/${encodeURIComponent(decisionId)}`),
  recommendations: (limit = 10) =>
    getJson<RecommendationSummary[]>(`/api/recommendations?limit=${limit}`),
  experience: (limit = 10) => getJson<ExperienceSummary[]>(`/api/experience?limit=${limit}`),
  providers: () => getJson<ProviderSummary[]>('/api/providers'),
  // S9-002: 组织级 Workflow / Artifact (只读查询)
  workflows: (projectId?: string) =>
    getJson<WorkflowSummary[]>(`/api/workflows${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`),
  workflow: (workflowId: string) =>
    getJson<WorkflowDetail>(`/api/workflows/${encodeURIComponent(workflowId)}`),
  artifacts: (filters: { projectId?: string; workflowId?: string; type?: string } = {}) => {
    const params = new URLSearchParams();
    if (filters.projectId) params.set('project_id', filters.projectId);
    if (filters.workflowId) params.set('workflow_id', filters.workflowId);
    if (filters.type) params.set('type', filters.type);
    const qs = params.toString();
    return getJson<ArtifactSummary[]>(`/api/artifacts${qs ? `?${qs}` : ''}`);
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
  reviewFeedback: (artifactId?: string, gateId?: string) => {
    const params = new URLSearchParams();
    if (artifactId != null && artifactId.length > 0) params.set('artifact_id', artifactId);
    if (gateId != null && gateId.length > 0) params.set('gate_id', gateId);
    const qs = params.toString();
    return getJson<ReviewFeedback[]>(`/api/review-feedback${qs ? `?${qs}` : ''}`);
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
  workflowStages: (workflowId: string) =>
    getJson<StageRunSummary[]>(`/api/workflows/${encodeURIComponent(workflowId)}/stages`),
  projectTimeline: (projectId: string, limit = 200) =>
    getJson<TimelineEventSummary[]>(
      `/api/projects/${encodeURIComponent(projectId)}/timeline?limit=${limit}`,
    ),
  // S10-004: Runtime Workspace API (写面 = 实例生命周期 + 截图 — Permission
  // Boundary 扩展; 错误语义: 404 项目/实例不存在 / 400 非法 type / 409 状态机)
  projectRuntimes: (projectId: string) =>
    getJson<RuntimeInstance[]>(
      `/api/projects/${encodeURIComponent(projectId)}/runtimes`,
    ),
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
