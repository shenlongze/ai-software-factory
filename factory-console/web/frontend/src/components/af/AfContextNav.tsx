/**
 * components/af/AfContextNav.tsx — AI Enterprise Workbench Context Navigator (V2).
 *
 * 设计文档 §4-6: 区分 Global 与 Project 两种上下文 — 不混成一棵树。
 *
 * Global 模式 (无当前项目):
 *   ◆ AI Factory
 *   ⌂ Home
 *   ▣ Projects
 *   — INTELLIGENCE —
 *   ◎ Agents   ◎ Workforce   ◎ Skills   ◎ Models
 *   — GOVERNANCE —
 *   ◌ Approvals   ◌ Policies   ◌ Audit
 *   — SYSTEM —
 *   ⚙ Settings
 *
 * Project 模式 (有当前项目 ScorePocket):
 *   ← Projects
 *   ScorePocket  Development  ● Running
 *   Overview · Conversation · Tasks · Artifacts · Runs · Agents · Files · Settings
 *
 * 底部: 用户信息 + 当前工作会话列表 (来自 ConversationContext)。
 *
 * 数据来源: 真实 ConversationContext (不伪造) — sessions 列表显示当前活跃会话。
 */

import { useEffect, useMemo, useState } from 'react';
import { useConversation } from './ConversationContext';
import './af.css';

export type NavMode = 'global' | 'project';

interface NavItem {
  id: string;
  label: string;
  icon: string;
  section?: string;
  badge?: string;
}

interface ContextNavProps {
  collapsed: boolean;
  /** 当前 project id — 有值时自动进入 Project 模式。 */
  projectId?: string | null;
  /** 当前激活的 nav item (父组件驱动)。 */
  activeNav?: string;
  onSelectNav?: (id: string) => void;
  onSelectConversation?: (id: string) => void;
  onSelectProject?: (id: string) => void;
}

const GLOBAL_NAV: NavItem[] = [
  { id: 'home', label: 'Home', icon: '⌂' },
  { id: 'projects', label: 'Projects', icon: '▣' },
  // INTELLIGENCE
  { id: 'agents', label: 'Agents', icon: '◎', section: '智能体' },
  { id: 'workforce', label: 'Workforce', icon: '⊞', section: '智能体' },
  { id: 'skills', label: 'Skills', icon: '◈', section: '智能体' },
  { id: 'models', label: 'Models', icon: '⚡', section: '智能体' },
  // GOVERNANCE
  { id: 'approvals', label: '待审批', icon: '◌', section: '治理', badge: '1' },
  { id: 'policies', label: 'Policies', icon: '⬡', section: '治理' },
  { id: 'audit', label: 'Audit', icon: '⎔', section: '治理' },
  // SYSTEM
  { id: 'settings', label: 'Settings', icon: '⚙', section: '系统' },
];

interface ProjectInfo {
  id: string;
  name: string;
  env?: string;
  status?: string;
}

export function AfContextNav({
  collapsed: _collapsed,
  projectId,
  activeNav = 'home',
  onSelectNav,
  onSelectConversation,
  onSelectProject,
}: ContextNavProps): JSX.Element {
  const ctx = useConversation();
  const [currentProject, setCurrentProject] = useState<ProjectInfo | null>(null);
  const mode: NavMode = projectId || currentProject ? 'project' : 'global';

  // 拉当前 project 信息 (真实 API)
  useEffect(() => {
    if (!projectId) {
      setCurrentProject(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/projects/${projectId}`, { headers: { Accept: 'application/json' } });
        if (!cancelled && res.ok) {
          const data = (await res.json()) as { id?: string; name?: string; environment?: string; status?: string };
          setCurrentProject({
            id: projectId,
            name: data.name ?? projectId,
            env: data.environment ?? 'Development',
            status: data.status ?? 'active',
          });
        }
      } catch {
        setCurrentProject({ id: projectId, name: projectId, env: 'Development', status: 'active' });
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  const projectNavItems = useMemo(
    () => [
      { id: 'overview', label: 'Overview', icon: '◉' },
      { id: 'conversation', label: 'Conversation', icon: '💬' },
      { id: 'tasks', label: 'Tasks', icon: '▤' },
      { id: 'artifacts', label: 'Artifacts', icon: '◈' },
      { id: 'runs', label: 'Runs', icon: '▶' },
      { id: 'agents', label: 'Agents', icon: '◎' },
      { id: 'files', label: 'Files', icon: '📁' },
      { id: 'settings', label: 'Settings', icon: '⚙' },
    ],
    [],
  );

  // Global 模式下拉项目列表 (展示第一个活跃项目)
  const [projects, setProjects] = useState<Array<{ id: string; title: string }>>([]);

  useEffect(() => {
    if (mode === 'project') return;
    let cancelled = false;
    fetch('/api/projects-os')
      .then((r) => r.json())
      .then((data: { items?: Array<{ id: string; title: string }> }) => {
        if (!cancelled && data?.items) setProjects(data.items.slice(0, 3));
      })
      .catch(() => { /* ignore */ });
    return () => { cancelled = true; };
  }, [mode]);

  const currentSessions = useMemo(
    () => ctx.sessions.filter((s) => s.status !== 'archived').slice(0, 8),
    [ctx.sessions],
  );

  if (mode === 'project' && currentProject) {
    return (
      <nav className="ai-sidebar ai-sidebar--v2 ai-sidebar--project" data-testid="af-context-nav" aria-label="Project Navigator">
        {/* Project Header */}
        <div className="ai-pj-header">
          <button type="button" className="ai-pj-back" onClick={() => onSelectProject?.('')} title="← Projects">
            ←
          </button>
          <div className="ai-pj-info">
            <div className="ai-pj-name" title={currentProject.name}>{currentProject.name}</div>
            <div className="ai-pj-sub">
              <span>{currentProject.env}</span>
              <span className={`ai-pj-dot ai-pj-dot--${currentProject.status ?? 'active'}`} aria-hidden="true" />
              <span>{currentProject.status === 'running' ? 'Running' : 'Active'}</span>
            </div>
          </div>
        </div>

        {/* Project Nav Items */}
        <div className="ai-nav-list">
          {projectNavItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`ai-nav-item${activeNav === item.id ? ' ai-nav-item--active' : ''}`}
              onClick={() => onSelectNav?.(item.id)}
            >
              <span className="ai-nav-icon">{item.icon}</span>
              <span className="ai-nav-label">{item.label}</span>
            </button>
          ))}
        </div>

        {/* 当前工作会话 */}
        {currentSessions.length > 0 && (
          <div className="ai-sessions-block">
            <div className="ai-section-title">Current Work</div>
            {currentSessions.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`ai-nav-item ai-nav-item--sub${ctx.activeId === s.id ? ' ai-nav-item--active' : ''}`}
                onClick={() => onSelectConversation?.(s.id)}
                title={s.title || s.id}
              >
                <span className="ai-nav-icon">💬</span>
                <span className="ai-nav-label">{s.title || `Session ${s.id.slice(-4)}`}</span>
              </button>
            ))}
          </div>
        )}

        <NavFooter />
      </nav>
    );
  }

  // Global mode
  return (
    <nav className="ai-sidebar ai-sidebar--v2 ai-sidebar--global" data-testid="af-context-nav" aria-label="AI Factory Global Navigation">
      {/* Brand */}
      <div className="ai-brand-row ai-brand-row--v2">
        <span className="ai-brand-logo" aria-hidden="true">◆</span>
        <span className="ai-brand-text">AI Factory</span>
      </div>

      {/* Nav Items (带 section 分组) */}
      <div className="ai-nav-list">
        {GLOBAL_NAV.map((item, idx) => {
          // Section header
          const prevSection = idx > 0 ? GLOBAL_NAV[idx - 1].section : undefined;
          const showSection = item.section && item.section !== prevSection;
          return (
            <div key={item.id}>
              {showSection && (
                <div className="ai-section-title">{item.section}</div>
              )}
              <button
                type="button"
                className={`ai-nav-item${activeNav === item.id ? ' ai-nav-item--active' : ''}`}
                onClick={() => onSelectNav?.(item.id)}
              >
                <span className="ai-nav-icon">{item.icon}</span>
                <span className="ai-nav-label">{item.label}</span>
                {item.badge && <span className="ai-nav-badge">{item.badge}</span>}
              </button>
            </div>
          );
        })}
      </div>

      {/* Recent / Current Work sessions */}
      {projects.length > 0 && (
        <div className="ai-sessions-block">
          <div className="ai-section-title">项目</div>
          {projects.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`ai-nav-item ai-nav-item--sub${activeNav === p.id ? ' ai-nav-item--active' : ''}`}
              onClick={() => onSelectProject?.(p.id)}
              title={p.title}
            >
              <span className="ai-nav-icon">📁</span>
              <span className="ai-nav-label">{p.title}</span>
            </button>
          ))}
        </div>
      )}
      {currentSessions.length > 0 && (
        <div className="ai-sessions-block">
          <div className="ai-section-title">我的工作</div>
          {currentSessions.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`ai-nav-item ai-nav-item--sub${ctx.activeId === s.id ? ' ai-nav-item--active' : ''}`}
              onClick={() => onSelectConversation?.(s.id)}
              title={s.title || s.id}
            >
              <span className="ai-nav-icon">💬</span>
              <span className="ai-nav-label">{s.title || `Session ${s.id.slice(-4)}`}</span>
            </button>
          ))}
        </div>
      )}

      <NavFooter />
    </nav>
  );
}

function NavFooter(): JSX.Element {
  return (
    <div className="ai-nav-footer">
      <div className="ai-user-row">
        <span className="ai-user-avatar-sm">👤</span>
        <span className="ai-user-label">User</span>
        <span className="ai-user-plan">Free</span>
      </div>
    </div>
  );
}
