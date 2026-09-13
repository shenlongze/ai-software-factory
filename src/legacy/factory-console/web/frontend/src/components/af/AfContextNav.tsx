/**
 * components/af/AfContextNav.tsx — AI Enterprise Workbench Context Navigator (V2, S31-002)。
 *
 * S31-001 Audit 结论: 后台 Module 不应变成一级菜单 (Agents/Workforce/Skills/Models
 * /Policies/Audit 全部隐藏)。左栏 = Context: 用户"现在在什么事上"。
 *
 * Global 模式 (S31-002 Conversation-first):
 *   ⌕ Search
 *   对话 (Conversations — 活跃会话, 一级)
 *   项目 (Projects — 真实列表)
 *   最近 (Recent — 最近会话)
 *   ⚙ (设置/治理收敛到开发者模式, 弱化)
 *
 * Project 模式 (有当前项目):
 *   ← Projects
 *   ScorePocket  Development  ● Running
 *   当前任务 · 进展 · 产物 · 运行 (来自 Conversation/Run 上下文)
 *
 * 数据来源: 真实 ConversationContext + API (不伪造)。
 * 后台 Module 通过 ⚙ 进入 (开发者/治理), 不进一级导航。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useConversation } from './ConversationContext';
import { api } from '../../api/client';
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

// S31-002: 一级导航只剩 Context 对象。后台 Module (Agents/Workforce/Skills/Models/
// Policies/Audit) 收敛到 ⚙ 设置/开发者 — 不暴露给普通用户。
const CONTEXT_NAV: NavItem[] = [
  { id: 'conversation', label: '对话', icon: '💬' },
  { id: 'projects', label: '项目', icon: '▣' },
  { id: 'recent', label: '最近', icon: '◷' },
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
  const [projects, setProjects] = useState<Array<{ id: string; title: string; status?: string }>>([]);
  const [creating, setCreating] = useState(false);

  const loadProjects = useCallback(() => {
    // S35-UI: org /api/projects (统一后端 — 与项目列表/详情同源, 非 os 双体系)
    fetch('/api/projects')
      .then((r) => r.json())
      .then((data: { items?: Array<{ id: string; name: string; status?: string | null }> }) => {
        if (data?.items)
          setProjects(
            data.items.slice(0, 5).map((p) => ({ id: p.id, title: p.name, status: p.status ?? undefined })),
          );
      })
      .catch(() => { /* ignore */ });
  }, []);

  useEffect(() => {
    if (mode === 'project') return;
    loadProjects();
  }, [mode, loadProjects]);

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

  // Global mode — S31-002 Conversation-first Context
  return (
    <nav className="ai-sidebar ai-sidebar--v2 ai-sidebar--global" data-testid="af-context-nav" aria-label="AI Factory Context Navigation">
      {/* Brand */}
      <div className="ai-brand-row ai-brand-row--v2">
        <span className="ai-brand-logo" aria-hidden="true">◆</span>
        <span className="ai-brand-text">AI Factory</span>
      </div>

      {/* Context 一级导航 (对话/项目/最近 — 用户任务视角, 非 Module 清单) */}
      <div className="ai-nav-list">
        {CONTEXT_NAV.map((item) => (
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

      {/* 对话 (Conversations — 一级, 活跃会话真实列表) */}
      <div className="ai-sessions-block">
        <div className="ai-section-title">对话</div>
        {currentSessions.length === 0 ? (
          <div className="ai-nav-empty">暂无会话 — 在中栏说一句"我想做…"开始</div>
        ) : (
          currentSessions.map((s) => (
            <div key={s.id} className="ai-nav-item-row">
              <button
                type="button"
                className={`ai-nav-item ai-nav-item--sub${ctx.activeId === s.id ? ' ai-nav-item--active' : ''}`}
                onClick={() => onSelectConversation?.(s.id)}
                title={s.title || s.id}
              >
                <span className="ai-nav-icon">💬</span>
                <span className="ai-nav-label">{s.title || `Session ${s.id.slice(-4)}`}</span>
              </button>
              {/* S32-002: 重命名 / 归档 (真实 PATCH /api/sessions/{id}) */}
              <button
                type="button"
                className="ai-nav-op"
                title="重命名"
                aria-label={`重命名 ${s.title || s.id}`}
                onClick={(e) => {
                  e.stopPropagation();
                  const next = window.prompt('会话标题:', s.title || '');
                  if (next && next.trim()) ctx.renameSession(s.id, next.trim());
                }}
              >
                ✎
              </button>
              <button
                type="button"
                className="ai-nav-op"
                title="归档"
                aria-label={`归档 ${s.title || s.id}`}
                onClick={(e) => {
                  e.stopPropagation();
                  ctx.archiveSession(s.id);
                }}
              >
                ⎋
              </button>
            </div>
          ))
        )}
      </div>

      {/* 项目 (Projects — 真实列表) */}
      <div className="ai-sessions-block">
        <div className="ai-section-title">
          项目
          <button
            type="button"
            className="ai-nav-op ai-nav-op--create"
            title="新建项目"
            aria-label="新建项目"
            onClick={(e) => {
              e.stopPropagation();
              const idea = window.prompt('项目想法 (idea):');
              if (idea && idea.trim()) {
                setCreating(true);
                api
                  .createProject(idea.trim())
                  .then(() => {
                    setCreating(false);
                    loadProjects();
                  })
                  .catch(() => setCreating(false));
              }
            }}
          >
            {creating ? '…' : '＋'}
          </button>
        </div>
        {projects.length === 0 ? (
          <div className="ai-nav-empty">暂无项目 — 点 ＋ 创建</div>
        ) : (
          projects.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`ai-nav-item ai-nav-item--sub${activeNav === p.id ? ' ai-nav-item--active' : ''}`}
              onClick={() => onSelectProject?.(p.id)}
              title={p.title}
            >
              <span className="ai-nav-icon">📁</span>
              <span className="ai-nav-label">{p.title}</span>
              {p.status && (
                <span className={`ai-nav-status ai-nav-status--${(p.status ?? '').toLowerCase()}`}>{p.status}</span>
              )}
            </button>
          ))
        )}
      </div>

      {/* 最近 (Recent — 最近更新会话, 简化复用列表) */}
      {currentSessions.length > 1 && (
        <div className="ai-sessions-block">
          <div className="ai-section-title">最近</div>
          {currentSessions.slice(0, 3).map((s) => (
            <button
              key={s.id}
              type="button"
              className={`ai-nav-item ai-nav-item--sub${ctx.activeId === s.id ? ' ai-nav-item--active' : ''}`}
              onClick={() => onSelectConversation?.(s.id)}
              title={s.title || s.id}
            >
              <span className="ai-nav-icon">◷</span>
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
