/**
 * api/client.ts — 前端 API 客户端 (只读)。
 *
 * 只消费 Console API (11A + adapter): 全部方法 GET, 零写路径
 * (Permission Boundary — 审批/决定/创建 等执行权在既有引擎, 前端不提供
 * 任何 POST/PUT/PATCH/DELETE 方法; 后端 adapter 也不注册写路由)。
 *
 * fetch 直接调用 → 组件测试用 vi.stubGlobal('fetch', ...) 注入桩。
 */

import type {
  ApprovalSummary,
  ConsoleDashboard,
  DecisionSummary,
  ExperienceSummary,
  LifecycleSummary,
  ProjectSummary,
  ProviderSummary,
  RecommendationSummary,
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

/** 只读 API 客户端 (全部 GET; 无 post/put/patch/delete 方法)。 */
export const api = {
  dashboard: () => getJson<ConsoleDashboard>('/api/dashboard'),
  projects: () => getJson<ProjectSummary[]>('/api/projects'),
  lifecycle: (projectId: string) =>
    getJson<LifecycleSummary>(
      `/api/projects/${encodeURIComponent(projectId)}/lifecycle`,
    ),
  approvals: (pendingOnly = false) =>
    getJson<ApprovalSummary[]>(`/api/approvals${pendingOnly ? '?pending_only=true' : ''}`),
  decision: (decisionId: string) =>
    getJson<DecisionSummary>(`/api/decisions/${encodeURIComponent(decisionId)}`),
  recommendations: (limit = 10) =>
    getJson<RecommendationSummary[]>(`/api/recommendations?limit=${limit}`),
  experience: (limit = 10) => getJson<ExperienceSummary[]>(`/api/experience?limit=${limit}`),
  providers: () => getJson<ProviderSummary[]>('/api/providers'),
} as const;

export type Api = typeof api;
