/**
 * shell/WorkspaceView.tsx — S10-001 中间 Workspace 区。
 *
 * - 空态页 "AI Workspace" (无选中项目时) + Timeline 预留容器 (S10-003 接入)
 * - 项目工作台 (选中项目: 项目名/状态/进度 + Timeline 预留)
 * - 其余导航视图 (Tasks/Agents/...) 与 Settings 的空态占位
 * 不实现 Timeline/Browser/Artifact/Review 内容 (S10-001 只做 Shell)。
 */

import { useEffect, useState } from 'react';
import { Button, Input, Modal, StatusBadge } from '../components/ds';
import { api, ApiError } from '../api/client';
import { NAV_ITEMS } from '../mock/workspace';
import type { ExplorerViewId } from '../mock/workspace';
import type { IdeaSuggestion } from '../models/types';
import { AgentTimeline } from './AgentTimeline';
import { ArtifactCenter } from './ArtifactCenter';
import { RunStatusBar } from './RunStatusBar';

/** S10-007 阶段三: Welcome 示例 chips (点击填入输入框; 有项目时不挡已有列表)。 */
export const EXAMPLE_IDEAS = ['一个记账 App', '一个待办清单 App', '一个博客网站'] as const;

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
  projects,
  onSelectProject,
  onRenameProject,
  onDeleteProject,
}: {
  onOpenProjects: () => void;
  /** S10-007 收尾: 确认创建 (name 可选 — 用户编辑后的名称; 无 → 旧直接创建兼容)。 */
  onCreateProject: (idea: string, name?: string) => void;
  /** S10-006.5: 已有项目列表 (默认视图直接可见, 点击进入工作台)。 */
  projects: { id: string; name: string }[];
  onSelectProject: (projectId: string) => void;
  /** S10-006.5 收尾: 重命名/删除 (PATCH/DELETE → Shell 同步列表+树; 失败抛回展示)。 */
  onRenameProject: (projectId: string, name: string) => Promise<void>;
  onDeleteProject: (projectId: string) => Promise<void>;
}): JSX.Element {
  const [idea, setIdea] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // S10-007 收尾: 想法确认对话 — 两阶段 (分析需求 → AI 理解卡片 → 确认创建)
  const [suggesting, setSuggesting] = useState(false);
  const [suggestion, setSuggestion] = useState<IdeaSuggestion | null>(null);
  const [editedName, setEditedName] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  // S10-006.5 收尾: 每项 ⋯ 菜单 (openMenuId) + 重命名/删除 Modal (action) + 请求态
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [action, setAction] = useState<{ type: 'rename' | 'delete'; project: { id: string; name: string } } | null>(null);
  const [busy, setBusy] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');

  // 菜单打开时: 点击菜单外任意处关闭 (mousedown 早于 click, 菜单项 onClick 已先执行;
  // ⋯ 按钮/弹出菜单内部不拦截 — 按钮自身 onClick 负责切换)
  useEffect(() => {
    if (openMenuId == null) return undefined;
    const close = (event: MouseEvent): void => {
      const target = event.target;
      if (target instanceof Element && target.closest('.ws-recent-menu-wrap') != null) return;
      setOpenMenuId(null);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [openMenuId]);

  const openRename = (project: { id: string; name: string }): void => {
    setRenameValue(project.name);
    setModalError(null);
    setAction({ type: 'rename', project });
    setOpenMenuId(null);
  };

  const openDelete = (project: { id: string; name: string }): void => {
    setModalError(null);
    setAction({ type: 'delete', project });
    setOpenMenuId(null);
  };

  const closeModal = (): void => {
    if (busy) return; // 请求中禁止关闭 (防误触)
    setAction(null);
    setModalError(null);
  };

  const confirmRename = async (): Promise<void> => {
    if (action == null || action.type !== 'rename') return;
    const name = renameValue.trim();
    if (name.length === 0) {
      setModalError('项目名不能为空');
      return;
    }
    setBusy(true);
    setModalError(null);
    try {
      await onRenameProject(action.project.id, name);
      setAction(null);
    } catch (err) {
      setModalError(err instanceof Error ? err.message : '重命名失败, 请稍后重试');
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async (): Promise<void> => {
    if (action == null || action.type !== 'delete') return;
    setBusy(true);
    setModalError(null);
    try {
      await onDeleteProject(action.project.id);
      setAction(null);
    } catch (err) {
      // 409 运行中保护 (后端诚实拒绝) → 明确提示; 其余透传 ApiError 消息
      setModalError(
        err instanceof ApiError && err.status === 409
          ? '项目正在开发中, 无法删除'
          : err instanceof Error
            ? err.message
            : '删除失败, 请稍后重试',
      );
    } finally {
      setBusy(false);
    }
  };

  /** S10-007 收尾: 阶段一「分析需求」— POST /api/projects/suggest (真实 LLM +
   * 诚实 fallback; 失败 → 错误提示可重试, 不假装)。 */
  const analyze = async (): Promise<void> => {
    const text = idea.trim();
    if (text.length === 0) {
      setError('请先输入你想开发的软件 (例如: 开发一个记账 App)');
      return;
    }
    setSuggesting(true);
    setError(null);
    setConfirmError(null);
    try {
      const result = await api.suggestProject(text);
      setSuggestion(result);
      setEditedName(result.suggested_name);
    } catch (err) {
      setError(err instanceof Error ? err.message : '分析失败, 请稍后重试');
    } finally {
      setSuggesting(false);
    }
  };

  /** S10-007 收尾: 阶段二「确认创建」— 用户编辑后的名称显式传给 Shell
   * (POST /api/projects {idea, name}); 成功 → Shell 选中新项目 → 工作台。 */
  const confirmCreate = async (): Promise<void> => {
    if (suggestion == null) return;
    const name = editedName.trim();
    setConfirming(true);
    setConfirmError(null);
    try {
      await onCreateProject(suggestion.idea, name.length > 0 ? name : undefined);
      setSuggestion(null); // 防卸载前闪回 (Shell 选中项目后本组件卸载)
    } catch (err) {
      setConfirmError(err instanceof Error ? err.message : '创建失败, 请稍后重试');
    } finally {
      setConfirming(false);
    }
  };

  /** 「重新分析」— 收起卡片回输入态 (想法保留, 可修改后再次分析)。 */
  const reanalyze = (): void => {
    setSuggestion(null);
    setConfirmError(null);
    setError(null);
  };

  /** 旧直接创建兼容 (无 name — 规则 slug 兜底; 保留给跳过分析的快速用户)。 */
  const submitDirect = async (): Promise<void> => {
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
      {/* S10-007 阶段三: Welcome 首屏 (首次进入引导, 不把 Workspace 做成管理台) */}
      <h1 className="ws-empty-title" data-testid="ws-welcome-title">
        你想创建什么软件?
      </h1>
      <p className="ws-empty-desc" data-testid="ws-welcome-subtitle">
        输入一句话, AI 团队为你开发 — 从需求分析、设计、编码到测试发布全程自动。
      </p>
      <div className="ws-example-chips" data-testid="ws-example-chips">
        {EXAMPLE_IDEAS.map((example, index) => (
          <button
            key={example}
            type="button"
            className="ws-example-chip"
            data-testid={`ws-example-chip-${index}`}
            onClick={() => setIdea(example)}
          >
            {example}
          </button>
        ))}
      </div>
      {/* S10-007 收尾: 两阶段创建 — 阶段一: 输入想法 → [分析需求] (loading);
          阶段二: AI 理解卡片 (名称可编辑+摘要+澄清问题) → [确认创建] */}
      {suggestion == null ? (
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
              onClick={() => void analyze()}
              disabled={suggesting || submitting}
              loading={suggesting}
              data-testid="ws-suggest-submit"
            >
              {suggesting ? '分析中…' : '分析需求'}
            </Button>
            <Button
              variant="ghost"
              onClick={() => void submitDirect()}
              disabled={submitting || suggesting}
              loading={submitting}
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
      ) : (
        <div className="ws-suggest-card" data-testid="ws-suggest-card">
          <div className="ws-suggest-head">
            <span className="ws-suggest-title">AI 理解</span>
            {!suggestion.ai_generated ? (
              <span className="ws-suggest-quick" data-testid="ws-suggest-quick">
                快速模式
              </span>
            ) : null}
          </div>
          <p className="ws-suggest-idea" data-testid="ws-suggest-idea">
            想法: {suggestion.idea}
          </p>
          <Input
            label="项目名称 (可编辑)"
            data-testid="ws-suggest-name"
            value={editedName}
            onChange={(e) => setEditedName(e.target.value)}
            disabled={confirming}
          />
          <p className="ws-suggest-slug" data-testid="ws-suggest-slug">
            slug: {suggestion.slug}
          </p>
          <p className="ws-suggest-summary" data-testid="ws-suggest-summary">
            {suggestion.summary}
          </p>
          {suggestion.questions.length > 0 ? (
            <div className="ws-suggest-questions" data-testid="ws-suggest-questions">
              <p className="ws-suggest-questions-title">需要确认的问题:</p>
              <ul>
                {suggestion.questions.map((question, index) => (
                  <li key={index} data-testid={`ws-suggest-question-${index}`}>
                    {question}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="ws-suggest-actions">
            <Button
              variant="primary"
              onClick={() => void confirmCreate()}
              disabled={confirming}
              loading={confirming}
              data-testid="ws-suggest-confirm"
            >
              {confirming ? '创建中…' : '确认创建'}
            </Button>
            <Button
              variant="ghost"
              onClick={reanalyze}
              disabled={confirming}
              data-testid="ws-suggest-reanalyze"
            >
              重新分析
            </Button>
          </div>
          {confirmError != null ? (
            <p className="ws-create-error" data-testid="ws-suggest-confirm-error">
              {confirmError}
            </p>
          ) : null}
        </div>
      )}
      {projects.length > 0 ? (
        <div className="ws-recent" data-testid="ws-recent-projects">
          <h3 className="ws-recent-title">已有项目</h3>
          <div className="ws-recent-list">
            {projects.map((project) => (
              <div
                key={project.id}
                className="ws-recent-item"
                data-testid={`ws-recent-row-${project.id}`}
              >
                <button
                  type="button"
                  className="ws-recent-main"
                  data-testid={`ws-recent-${project.id}`}
                  onClick={() => onSelectProject(project.id)}
                >
                  <span className="ws-recent-name">{project.name}</span>
                  <span className="ws-recent-arrow" aria-hidden="true">
                    →
                  </span>
                </button>
                <div className="ws-recent-menu-wrap">
                  <button
                    type="button"
                    className="ws-recent-menu-btn"
                    aria-label={`${project.name} 操作`}
                    aria-haspopup="menu"
                    aria-expanded={openMenuId === project.id}
                    data-testid={`ws-recent-menu-${project.id}`}
                    onClick={() => setOpenMenuId((cur) => (cur === project.id ? null : project.id))}
                  >
                    ⋯
                  </button>
                  {openMenuId === project.id ? (
                    <div
                      className="ws-recent-pop"
                      role="menu"
                      data-testid={`ws-recent-pop-${project.id}`}
                    >
                      <button
                        type="button"
                        role="menuitem"
                        className="ws-recent-pop-item"
                        data-testid={`ws-recent-rename-${project.id}`}
                        onClick={() => openRename(project)}
                      >
                        重命名
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        className="ws-recent-pop-item danger"
                        data-testid={`ws-recent-delete-${project.id}`}
                        onClick={() => openDelete(project)}
                      >
                        删除
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* S10-006.5 收尾: 重命名 Modal (PATCH → 列表/树同步) */}
      <Modal
        open={action?.type === 'rename'}
        title="重命名项目"
        onClose={closeModal}
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={closeModal} disabled={busy}>
              取消
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => void confirmRename()}
              disabled={busy}
              loading={busy}
              data-testid="pm-rename-save"
            >
              保存
            </Button>
          </>
        }
      >
        <div className="pm-modal-body" data-testid="pm-rename-modal">
          <p className="pm-modal-desc">输入项目新名称 (保存后列表与项目树同步更新)。</p>
          <Input
            label="项目名称"
            data-testid="pm-rename-input"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void confirmRename();
            }}
            autoFocus
          />
          {modalError != null ? (
            <p className="pm-modal-error" data-testid="pm-modal-error">
              {modalError}
            </p>
          ) : null}
        </div>
      </Modal>

      {/* S10-006.5 收尾: 删除二次确认 Modal (DELETE → 列表/树移除; 运行中 409 提示) */}
      <Modal
        open={action?.type === 'delete'}
        title="删除项目"
        onClose={closeModal}
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={closeModal} disabled={busy}>
              取消
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={() => void confirmDelete()}
              disabled={busy}
              loading={busy}
              data-testid="pm-delete-confirm"
            >
              删除
            </Button>
          </>
        }
      >
        <div className="pm-modal-body" data-testid="pm-delete-modal">
          <p className="pm-modal-desc">
            确定删除「{action?.type === 'delete' ? action.project.name : ''}」吗? 删除后不可恢复。
          </p>
          {modalError != null ? (
            <p className="pm-modal-error" data-testid="pm-modal-error">
              {modalError}
            </p>
          ) : null}
        </div>
      </Modal>

      <TimelinePlaceholder />
    </div>
  );
}

/** 选中项目后的工作台视图 (Run 状态条 + Header + Agent Timeline 实时事件流)。 */
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
      {/* S10-007 阶段三: 开始开发入口 + run 状态条 (Timeline 顶部) */}
      <RunStatusBar projectId={project.id} />
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
  projects,
  onOpenProjects,
  onViewArtifact,
  onCreateProject,
  onRenameProject,
  onDeleteProject,
  onSelectProject,
}: {
  view: ExplorerViewId;
  project: { id: string; name: string; status?: string | null } | null;
  /** S10-006.5: 已有项目列表 (Home 默认视图展示)。 */
  projects: { id: string; name: string }[];
  onOpenProjects: () => void;
  /** S10-004 联动: Timeline artifact 查看 → Runtime Panel (WorkspaceShell 提供)。 */
  onViewArtifact?: (artifactId: string) => void;
  /** S10-006.5: 创建项目 (WorkspaceShell 调 POST /api/projects → 选中新项目)。
   * S10-007 收尾: name 可选 — 用户确认的名称 (suggest 卡片编辑后显式传)。 */
  onCreateProject?: (idea: string, name?: string) => Promise<void>;
  /** S10-006.5 收尾: 重命名/删除 (Home 列表 ⋯ 菜单 → Modal → Shell 同步)。 */
  onRenameProject?: (projectId: string, name: string) => Promise<void>;
  onDeleteProject?: (projectId: string) => Promise<void>;
  /** S10-006.5: 选择已有项目 (Home 列表点击)。 */
  onSelectProject?: (projectId: string) => void;
}): JSX.Element {
  if (view === 'settings') return <SettingsView />;
  if (view === 'artifacts') {
    // S10-007: 全局产物库 (所有项目) — 真实 /api/artifacts
    return (
      <div className="ws-artifacts-view" data-testid="ws-artifacts-view">
        <ArtifactCenter />
      </div>
    );
  }
  if (view !== 'home' && view !== 'projects') return <PlaceholderView view={view} />;
  if (project != null) return <ProjectWorkspace project={project} onViewArtifact={onViewArtifact} />;
  return (
    <WorkspaceHome
      onOpenProjects={onOpenProjects}
      onCreateProject={onCreateProject ?? (async () => {})}
      projects={projects}
      onSelectProject={onSelectProject ?? (() => {})}
      onRenameProject={onRenameProject ?? (async () => {})}
      onDeleteProject={onDeleteProject ?? (async () => {})}
    />
  );
}
