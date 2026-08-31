/**
 * router.tsx — AI Factory 两级路由表 + hash 解析 (S10-014-plan §2.3)。
 *
 * 路由设计 (§2.3):
 *   Workspace 级 (7): #/workspace (dashboard 默认) + projects/team/workflows/
 *                      runtime/audit/settings
 *   Project 级 (11):  #/project/:id (overview 默认) + vision/discovery/prd/
 *                      roadmap/backlog/sprint/todo/workflow/runtime/logs
 * 直链兼容 (§2.3):    #/workspace?project=<id> (S10-003 直链) → project/overview
 *
 * Task 002 范围: 只定义路由配置 + parseHash 解析 (纯函数, 无 React 依赖);
 * 页面组件由 Task 004 (Workspace Shell) / Task 005 (Project Shell) 实现。
 */

/** Workspace 级路由 (S32-001 IA Freeze: 唯一 Conversation 主入口)。

 * 旧路由 (work/tower/projects/monitor/production/settings/manage) 已删除 —
 * 死页面清理 (S31-007: 17 UNUSED) 后无产品职责, 旧 URL 自动回退 conversation。
 */
export const WORKSPACE_ROUTES: readonly { path: string; page: string }[] = [
  { path: '#/workspace', page: 'conversation' },
  { path: '#/workspace/conversation', page: 'conversation' },
];

/** Project 级路由 (11 条, §2.3; :id = 项目 id 路径段)。 */
export const PROJECT_ROUTES: readonly { path: string; page: string }[] = [
  { path: '#/project/:id', page: 'overview' },
  { path: '#/project/:id/docs', page: 'docs' },
  { path: '#/project/:id/todo', page: 'todo' },
  { path: '#/project/:id/workflow', page: 'workflow' },
  { path: '#/project/:id/runtime', page: 'runtime' },
  { path: '#/project/:id/quality', page: 'quality' },
  { path: '#/project/:id/ops', page: 'ops' },
];

/** 合法页面名集合 (parseHash 校验用, 从路由表派生 — 单一数据源)。 */
export const WORKSPACE_PAGES: readonly string[] = WORKSPACE_ROUTES.map((r) => r.page);
export const PROJECT_PAGES: readonly string[] = PROJECT_ROUTES.map((r) => r.page);

/** 路由解析结果: level (两级) + page (子页) + projectId (project 级必有)。 */
export interface ParsedRoute {
  level: 'workspace' | 'project';
  page: string;
  projectId?: string;
}

/** 默认路由 (无法识别 / 空 hash → Workspace Conversation 首页)。 */
export const DEFAULT_ROUTE: ParsedRoute = { level: 'workspace', page: 'conversation' };

/**
 * 解析 URL hash → 两级路由。
 *
 * 规则:
 * - #/workspace[?project=id]        → workspace 级; ?project=id (S10-003 直链)
 *                                     → project/overview 重定向 (§2.3)
 * - #/workspace/<page>              → workspace 子页; 未知子页 → dashboard
 * - #/project/<id>[/<page>]         → project 级; id URL 解码; 未知子页 → overview
 * - 其他 (空/未知/缺 id/非法编码)    → DEFAULT_ROUTE (不抛异常)
 */
export function parseHash(hash: string): ParsedRoute {
  const raw = (hash ?? '').replace(/^#/, '').replace(/\/+$/, '');
  const qIndex = raw.indexOf('?');
  const pathPart = qIndex >= 0 ? raw.slice(0, qIndex) : raw;
  const query = qIndex >= 0 ? raw.slice(qIndex + 1) : '';

  // S32-004B: #/workspace?project=<id> → workspace 级 + project context
  // (不再重定向独立 Project Page — 项目是 Context, 不是页面)
  const projectFromQuery = (() => {
    if (pathPart === '/workspace' && query.length > 0) {
      const projectId = new URLSearchParams(query).get('project');
      return projectId != null && projectId.length > 0 ? projectId : null;
    }
    return null;
  })();
  if (projectFromQuery != null) {
    return { level: 'workspace', page: 'conversation', projectId: projectFromQuery };
  }

  const segments = pathPart.split('/').filter((s) => s.length > 0);
  if (segments.length === 0) return DEFAULT_ROUTE;

  if (segments[0] === 'workspace') {
    const page = segments[1];
    return {
      level: 'workspace',
      page: page != null && WORKSPACE_PAGES.includes(page) ? page : 'conversation',
    };
  }

  if (segments[0] === 'project') {
    if (segments.length < 2) return DEFAULT_ROUTE;
    let projectId: string;
    try {
      projectId = decodeURIComponent(segments[1]);
    } catch {
      return DEFAULT_ROUTE; // 非法 URL 编码 → 默认, 不抛
    }
    if (projectId.length === 0) return DEFAULT_ROUTE;
    const page = segments[2];
    return {
      level: 'project',
      page: page != null && PROJECT_PAGES.includes(page) ? page : 'overview',
      projectId,
    };
  }

  return DEFAULT_ROUTE;
}
