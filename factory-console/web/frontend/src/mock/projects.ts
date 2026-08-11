/**
 * mock/projects.ts — AI Factory 示例项目 Mock 数据骨架 (S10-014-plan §6.3-4)。
 *
 * ⚠️ MOCK 使用声明 (S10-014 用户铁律):
 *   Mock 数据仅用于 UI 开发早期占位 / Storybook / 单元测试。
 *   禁止作为最终实现数据源; 页面必须接真实后端 API (GET /api/projects 等)。
 *
 * 结构 = 真实后端响应 (ProjectSummary, 验证于 2026-08-11);
 * 后端可用后由真实 API + Domain Adapter 替换 (Mock 先行原则 §6.3-4)。
 * S10-014 Task 008 扩展: MOCK_PROJECT_SUMMARIES / toMockWorkspaceProject /
 * MOCK_USAGE_DECLARATION。
 */

import type { ProjectSummary } from '../models/types';
import type { TodoTree, WorkspaceProject } from '../models/domain';
import { toWorkspaceProject } from '../api/domain';

/** 文件头声明锚点 (mock-data.test.ts 断言存在 — 与上方注释同步)。 */
export const MOCK_USAGE_DECLARATION =
  '⚠️ Mock 数据仅用于 UI 开发早期占位 / Storybook / 单元测试; 禁止作为最终实现数据源; 页面必须接真实后端 API (禁接生产)';

/** 示例项目列表 (Workspace Dashboard / Projects 页, Frontend Domain Model)。 */
export const MOCK_PROJECTS: readonly WorkspaceProject[] = [
  {
    id: 'score-pocket',
    name: 'ScorePocket',
    lifecycleStage: 'development',
    lifecycleLabel: '开发中',
    progress: 62,
    pendingApprovals: 1,
    riskCount: 2,
  },
  {
    id: 'ledger-app',
    name: '记账 App',
    lifecycleStage: 'discovery',
    lifecycleLabel: '探索中',
    progress: 18,
    pendingApprovals: 0,
    riskCount: 0,
  },
];

/**
 * 示例项目 (结构 = GET /api/projects 真实响应, ProjectSummary 19 键;
 * 验证于 2026-08-11 — 与真实 markpad/ledger-app 字段一致)。
 */
export const MOCK_PROJECT_SUMMARIES: readonly ProjectSummary[] = [
  {
    id: 'score-pocket',
    name: 'ScorePocket',
    description: '台球计分 App — 自动计分/排名/赛事管理',
    language: 'dart',
    repository: '',
    tech_stack: ['flutter', 'dart'],
    status: 'active',
    lifecycle_stage: 'development',
    lifecycle_status: 'development',
    pending_approvals: 1,
    tasks: { total: 12, done: 7 },
    last_activity: '2026-08-11T10:00:00Z',
    workflow_id: 'WF-SP-001',
    workflow_name: 'ScorePocket 开发链',
    workflow_status: 'running',
    current_stage: 'design',
    current_stage_status: 'running',
    progress: 0.62,
    stage_counts: { completed: 2, running: 1, failed: 1, blocked: 1 },
  },
  {
    id: 'ledger-app',
    name: '记账 App',
    description: '',
    language: '',
    repository: '',
    tech_stack: [],
    status: 'idea',
    lifecycle_stage: 'discovery',
    lifecycle_status: 'discovery',
    pending_approvals: 0,
    tasks: {},
    last_activity: null,
    workflow_id: null,
    workflow_name: null,
    workflow_status: null,
    current_stage: null,
    current_stage_status: null,
    progress: 0.18,
    stage_counts: {},
  },
];

/** 默认示例 = ScorePocket (完整字段)。 */
export const MOCK_DEFAULT_SUMMARY: ProjectSummary = MOCK_PROJECT_SUMMARIES[0];

/**
 * 示例项目 → Frontend Domain Model (复用 api/domain.ts toWorkspaceProject,
 * 保证 Mock 与真实 API 走同一转换链路)。
 * @param overrides 覆盖 ProjectSummary 字段 (partial)
 */
export function toMockWorkspaceProject(
  overrides?: Partial<ProjectSummary>,
): WorkspaceProject {
  return toWorkspaceProject({ ...MOCK_DEFAULT_SUMMARY, ...overrides });
}

/** 示例进度树 (ScorePocket → 开发阶段 → Backend/用户系统 → API 开发, §5.2)。 */
export const MOCK_TODO_TREE: TodoTree = {
  root: {
    id: 'phase-dev',
    title: '开发阶段',
    type: 'phase',
    status: 'running',
    statusLabel: '执行中',
    progress: 62,
    children: [
      {
        id: 'mod-backend',
        title: 'Backend',
        type: 'module',
        status: 'running',
        statusLabel: '执行中',
        progress: 80,
        children: [
          {
            id: 'task-api',
            title: 'API 开发',
            type: 'task',
            status: 'running',
            statusLabel: '执行中',
            progress: 40,
            agent: 'backend-dev',
            owner: '开发 Agent',
            startedAt: '2026-08-11T09:00:00Z',
            nextAction: '实现 /api/health 接口',
            children: [],
          },
        ],
      },
      {
        id: 'mod-user',
        title: '用户系统',
        type: 'module',
        status: 'pending',
        statusLabel: '待办',
        progress: 0,
        children: [],
      },
    ],
  },
};
