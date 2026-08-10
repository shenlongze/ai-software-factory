/**
 * shell/WorkspaceView.tsx — S10-001 中间 Workspace 区。
 *
 * - 空态页 "AI Workspace" (无选中项目时) + Timeline 预留容器 (S10-003 接入)
 * - 项目工作台 (选中项目: 项目名/状态/进度 + Timeline 预留)
 * - 其余导航视图 (Tasks/Agents/...) 与 Settings 的空态占位
 * 不实现 Timeline/Browser/Artifact/Review 内容 (S10-001 只做 Shell)。
 */

import { useState } from 'react';
import { Button, StatusBadge } from '../components/ds';
import { NAV_ITEMS, projectStatusBadge } from '../mock/workspace';
import type { ExplorerViewId, MockProject } from '../mock/workspace';
import { AgentTimeline } from './AgentTimeline';

/** Timeline 空态提示 (无选中项目时 — 选择项目后渲染 AgentTimeline)。 */
export function TimelinePlaceholder({ projectName }: { projectName?: string }): JSX.Element {
  return (
    <div className="ws-timeline-placeholder" data-testid="timeline-placeholder">
      <div className="ws-timeline-placeholder-title">Agent Timeline</div>
      <div className="ws-timeline-placeholder-desc">
        {projectName != null ? `${projectName} 的 ` : '选择项目后, '}
        AI Agent 事件流 (user / stage / artifact / review / diff / error) 将在此从上到下实时展示
      </div>
    </div>
  );
}

/** 空态页 "AI Workspace" (无选中项目)。 */
function WorkspaceHome({ onOpenProjects }: { onOpenProjects: () => void }): JSX.Element {
  const [newProjectHint, setNewProjectHint] = useState(false);
  return (
    <div className="ws-empty" data-testid="ws-workspace-home">
      <div className="ws-empty-icon" aria-hidden="true">
        ✨
      </div>
      <h1 className="ws-empty-title">AI Workspace</h1>
      <p className="ws-empty-desc">
        输入一句话, 看到 AI 软件生产全过程 — 从需求分析、设计、编码到测试发布。
      </p>
      <p className="ws-empty-hint">开始: 在左侧选择项目, 或新建一个项目。</p>
      <div className="ws-empty-actions">
        <Button variant="primary" onClick={() => setNewProjectHint(true)}>
          ＋ 新建项目
        </Button>
        <Button variant="ghost" onClick={onOpenProjects}>
          选择项目
        </Button>
      </div>
      {newProjectHint ? (
        <p className="ws-empty-hint" data-testid="ws-new-project-hint">
          新建项目将在 S10-002 Runtime API (POST /api/projects) 接入后可用。
        </p>
      ) : null}
      <TimelinePlaceholder />
    </div>
  );
}

/** 选中项目后的工作台视图 (Header + Agent Timeline 实时事件流)。 */
function ProjectWorkspace({
  project,
  onViewArtifact,
}: {
  project: MockProject;
  onViewArtifact?: (artifactId: string) => void;
}): JSX.Element {
  const badge = projectStatusBadge(project.status);
  const completedStages = project.stages.filter((stage) => stage.status === 'completed').length;
  return (
    <div className="ws-project" data-testid="ws-project-workspace">
      <header className="ws-project-head">
        <h1 className="ws-project-name" data-testid="ws-project-name">
          {project.name}
        </h1>
        <StatusBadge status={badge.status} label={badge.label} />
        <span className="ws-project-progress">
          进度 {completedStages}/{project.stages.length}
        </span>
      </header>
      <p className="ws-project-idea">{project.idea}</p>
      <AgentTimeline projectId={project.id} onViewArtifact={onViewArtifact} />
    </div>
  );
}

/** 通用视图占位 (Tasks/Agents/Skills/Templates/Artifacts — 后续 Sprint 接入)。 */
function PlaceholderView({ view }: { view: ExplorerViewId }): JSX.Element {
  const item = NAV_ITEMS.find((navItem) => navItem.id === view);
  return (
    <div className="ws-empty" data-testid={`ws-view-${view}`}>
      <div className="ws-empty-icon" aria-hidden="true">
        {item?.icon ?? '📌'}
      </div>
      <h1 className="ws-empty-title">{item?.label ?? view}</h1>
      <p className="ws-empty-desc">该模块视图将在后续 Sprint 接入 (S10-002+)。</p>
    </div>
  );
}

/** Settings 视图占位 (LLM 配置 S10-002 接入; 主题切换已由 Header 提供)。 */
function SettingsView(): JSX.Element {
  return (
    <div className="ws-empty" data-testid="ws-view-settings">
      <div className="ws-empty-icon" aria-hidden="true">
        ⚙️
      </div>
      <h1 className="ws-empty-title">设置</h1>
      <p className="ws-empty-desc">
        LLM Provider / 模型 / API Key 配置将在 S10-002 Runtime API 接入后可用。
      </p>
      <p className="ws-empty-hint">主题亮/暗切换已可用 — 点击右上角主题按钮。</p>
    </div>
  );
}

export function WorkspaceView({
  view,
  project,
  onOpenProjects,
  onViewArtifact,
}: {
  view: ExplorerViewId;
  project: MockProject | null;
  onOpenProjects: () => void;
  /** S10-004 联动: Timeline artifact 查看 → Runtime Panel (WorkspaceShell 提供)。 */
  onViewArtifact?: (artifactId: string) => void;
}): JSX.Element {
  if (view === 'settings') return <SettingsView />;
  if (view !== 'home' && view !== 'projects') return <PlaceholderView view={view} />;
  if (project != null) return <ProjectWorkspace project={project} onViewArtifact={onViewArtifact} />;
  return <WorkspaceHome onOpenProjects={onOpenProjects} />;
}
