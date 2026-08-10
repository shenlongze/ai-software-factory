/**
 * mock/workspace.ts — S10-001 Workspace Shell 的 mock 数据。
 *
 * 约束: S10-001 只做 Shell 框架, 不接真实 API; S10-002 Runtime API
 * 接入后由真实数据替换。形状对齐 docs/sprint10/api-data-model.md
 * (Project/Stage 状态机) 与 ui-information-architecture.md (Explorer 导航)。
 * S10-006.5: 项目树改读 GET /api/projects 真实投影 — MOCK_PROJECTS 仅作
 * 后端不可达时的 fallback (ProjectTree 用 is_mock 徽章诚实标注, 不冒充)。
 */

import type { AgentRole, StageStatus } from '../design/tokens';
import type { ProjectSummary } from '../models/types';

// ------------------------------------------------------------------ Explorer 导航 (8 项)
export type ExplorerViewId =
  | 'home'
  | 'projects'
  | 'tasks'
  | 'agents'
  | 'skills'
  | 'templates'
  | 'artifacts'
  | 'settings';

export interface NavItem {
  id: ExplorerViewId;
  label: string;
  icon: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { id: 'home', label: 'Home', icon: '🏠' },
  { id: 'projects', label: 'Projects', icon: '📁' },
  { id: 'tasks', label: 'Tasks', icon: '✅' },
  { id: 'agents', label: 'Agents', icon: '🤖' },
  { id: 'skills', label: 'Skills', icon: '🧩' },
  { id: 'templates', label: 'Templates', icon: '📄' },
  { id: 'artifacts', label: 'Artifacts', icon: '📦' },
  { id: 'settings', label: 'Settings', icon: '⚙️' },
];

// ------------------------------------------------------------------ Project Tree (mock)
export type ProjectStageId = 'product' | 'ux_ui' | 'architecture' | 'code' | 'test' | 'release';

export interface ProjectStage {
  id: ProjectStageId;
  name: string;
  role: AgentRole;
  status: StageStatus;
}

export type ProjectStatus = 'active' | 'paused' | 'completed' | 'failed';

export interface MockProject {
  id: string;
  name: string;
  idea: string;
  status: ProjectStatus;
  /** 阶段链 (Product → UX/UI → Architecture → Code → Test → Release)。 */
  stages: readonly ProjectStage[];
}

export const MOCK_PROJECTS: readonly MockProject[] = [
  {
    id: 'ledger-app',
    name: '记账 App',
    idea: '开发一个记账 App',
    status: 'active',
    stages: [
      { id: 'product', name: 'Product', role: 'pm', status: 'completed' },
      { id: 'ux_ui', name: 'UX/UI', role: 'ux_ui', status: 'completed' },
      { id: 'architecture', name: 'Architecture', role: 'architecture', status: 'waiting_review' },
      { id: 'code', name: 'Code', role: 'developer', status: 'pending' },
      { id: 'test', name: 'Test', role: 'tester', status: 'pending' },
      { id: 'release', name: 'Release', role: 'release', status: 'pending' },
    ],
  },
];

/** 项目状态 → StatusBadge 显示 (api-data-model: active|paused|completed|failed)。 */
export function projectStatusBadge(status: ProjectStatus): { status: StageStatus; label: string } {
  switch (status) {
    case 'active':
      return { status: 'running', label: '进行中' };
    case 'paused':
      return { status: 'pending', label: '已暂停' };
    case 'completed':
      return { status: 'completed', label: '已完成' };
    case 'failed':
      return { status: 'failed', label: '失败' };
  }
}

/** GET /api/projects 投影 → 项目树节点 (S10-006.5 真实数据适配)。

 * 诚实边界: ProjectSummary 只含生命周期状态, 不含 6 阶段链 — stages
 * 置空数组 (树不伪造阶段明细); 状态非法 → active 兜底 (宽容收窄)。
 */
export function projectSummaryToTree(project: ProjectSummary): MockProject {
  const status: ProjectStatus = ['active', 'paused', 'completed', 'failed'].includes(
    project.status,
  )
    ? (project.status as ProjectStatus)
    : 'active';
  return {
    id: project.id,
    name: project.name || project.id,
    idea: project.description || project.name || project.id,
    status,
    stages: [],
  };
}

/** POST /api/projects 创建结果 → 项目树节点 (创建后立即入树, 不刷新列表)。 */
export function createdProjectToTree(created: {
  project_id: string;
  name: string;
  idea: string;
}): MockProject {
  return {
    id: created.project_id,
    name: created.name || created.project_id,
    idea: created.idea,
    status: 'active',
    stages: [],
  };
}

// ------------------------------------------------------------------ Panel 4 Tab
export type PanelTabId = 'browser' | 'task' | 'artifact' | 'review';

export interface PanelTabMeta {
  id: PanelTabId;
  label: string;
  icon: string;
  emptyTitle: string;
  emptyDescription: string;
  futureTask: string;
}

export const PANEL_TABS: readonly PanelTabMeta[] = [
  {
    id: 'browser',
    label: 'Browser',
    icon: '🌐',
    emptyTitle: '浏览器预览',
    emptyDescription: '选择已生成代码的项目, 在这里预览 AI 生成软件的真实运行页面。',
    futureTask: 'S10-004 Browser Runtime 接入 (iframe 沙箱预览)',
  },
  {
    id: 'task',
    label: 'Task',
    icon: '📋',
    emptyTitle: '任务状态',
    emptyDescription: 'Workflow 8 阶段状态 / 进度 / 成本 / 耗时将在这里展示。',
    futureTask: 'S10-002 Monitor API 接入 (轮询或 SSE)',
  },
  {
    id: 'artifact',
    label: 'Artifact',
    icon: '📦',
    emptyTitle: '产物中心',
    emptyDescription: '6 类产物 (PRD / Design / Code / Test / Release) 资产库将在这里展示。',
    futureTask: 'S10-005 Artifact Center 接入',
  },
  {
    id: 'review',
    label: 'Review',
    icon: '✅',
    emptyTitle: '审核清单',
    emptyDescription: '需求 / 设计 / 架构 / 发布 4 道人工审核门将在这里展示。',
    futureTask: 'S10-006 Review Workflow 接入',
  },
];

// ------------------------------------------------------------------ Header (mock)
export interface LlmStatus {
  provider: string;
  model: string;
  connected: boolean;
}

export const LLM_STATUS: LlmStatus = {
  provider: 'DeepSeek',
  model: 'v4-flash',
  connected: true,
};

export interface CurrentUser {
  name: string;
  initials: string;
}

export const CURRENT_USER: CurrentUser = {
  name: '管理员',
  initials: '管',
};
