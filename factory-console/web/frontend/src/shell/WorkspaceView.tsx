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
import { NAV_ITEMS } from '../mock/workspace';
import type { ExplorerViewId } from '../mock/workspace';
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
function WorkspaceHome({
  onOpenProjects,
  onCreateProject,
}: {
  onOpenProjects: () => void;
  onCreateProject: (idea: string) => void;
}): JSX.Element {
  const [idea, setIdea] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (): Promise<void> => {
    const text = idea.trim();
    if (text.length === 0) {
      setError('请先输入你想开发的软件 (例如: 开发一个记账 App)');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onCreateProject(text);
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建失败, 请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="ws-empty" data-testid="ws-workspace-home">
      <div className="ws-empty-icon" aria-hidden="true">
        ✨
      </div>
      <h1 className="ws-empty-title">AI Workspace</h1>
      <p className="ws-empty-desc">
        输入一句话, 看到 AI 软件生产全过程 — 从需求分析、设计、编码到测试发布。
      </p>
      <div className="ws-create" data-testid="ws-create-form">
        <textarea
          className="ws-create-input"
          data-testid="ws-create-input"
          placeholder="我想开发一个 xxx"
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          rows={2}
        />
        <div className="ws-create-actions">
          <Button
            variant="primary"
            onClick={() => void submit()}
            disabled={submitting}
            data-testid="ws-create-submit"
          >
            {submitting ? '创建中…' : '开始生产'}
          </Button>
          <Button variant="ghost" onClick={onOpenProjects}>
            选择项目
          </Button>
        </div>
        {error != null ? (
          <p className="ws-create-error" data-testid="ws-create-error">
            {error}
          </p>
        ) : null}
      </div>
      <TimelinePlaceholder />
    </div>
  );
}

/** 选中项目后的工作台视图 (Header + Agent Timeline 实时事件流)。 */
function ProjectWorkspace({
  project,
  onViewArtifact,
}: {
  project: { id: string; name: string; status?: string | null };
  onViewArtifact?: (artifactId: string) => void;
}): JSX.Element {
  return (
    <div className="ws-project" data-testid="ws-project-workspace">
      <header className="ws-project-head">
        <h1 className="ws-project-name" data-testid="ws-project-name">
          {project.name}
        </h1>
        {project.status != null ? <StatusBadge status={project.status} label={project.status} /> : null}
      </header>
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
  onCreateProject,
}: {
  view: ExplorerViewId;
  project: { id: string; name: string; status?: string | null } | null;
  onOpenProjects: () => void;
  /** S10-004 联动: Timeline artifact 查看 → Runtime Panel (WorkspaceShell 提供)。 */
  onViewArtifact?: (artifactId: string) => void;
  /** S10-006.5: 创建项目 (WorkspaceShell 调 POST /api/projects → 选中新项目)。 */
  onCreateProject?: (idea: string) => Promise<void>;
}): JSX.Element {
  if (view === 'settings') return <SettingsView />;
  if (view !== 'home' && view !== 'projects') return <PlaceholderView view={view} />;
  if (project != null) return <ProjectWorkspace project={project} onViewArtifact={onViewArtifact} />;
  return <WorkspaceHome onOpenProjects={onOpenProjects} onCreateProject={onCreateProject ?? (async () => {})} />;
}
