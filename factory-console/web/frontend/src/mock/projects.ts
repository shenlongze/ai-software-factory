/**
 * mock/projects.ts — AI Factory 示例项目 Mock 数据骨架 (S10-014-plan §6.3-4)。
 *
 * 结构 = Frontend Domain Model (models/domain.ts); 开发期示例数据 (ScorePocket);
 * 后端可用后由真实 API + Domain Adapter 替换 (Mock 先行原则 §6.3-4)。
 * S10-014 Task 008 扩展: todoTree.ts / workflow.ts / runtimeActivity.ts。
 */

import type { TodoTree, WorkspaceProject } from '../models/domain';

/** 示例项目列表 (Workspace Dashboard / Projects 页)。 */
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
