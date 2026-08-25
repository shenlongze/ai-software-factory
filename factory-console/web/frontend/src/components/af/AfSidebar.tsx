/**
 * components/af/AfSidebar.tsx — AI OS 左侧导航栏 (S10-014 Task 004)。
 *
 * §3.1 两级导航 (Workspace 级): Dashboard/Projects/AI Team/Workflow Center/
 * Runtime Monitor/Audit/Settings — 图标+文字, 激活态主色左边框 (§4.3 Navigation)。
 * 240px 可折叠 (64px 仅图标); 点击 → hash 路由 (#/workspace/<page>, dashboard → #/workspace)。
 *
 * 纯展示 + hash 导航: 不持有路由状态, 激活态由 activePage 传入 (App hashchange 驱动)。
 */

import { useEffect, useState } from 'react';
import { api } from '../../api/client';

/** 7 个 Workspace 导航项 (与 router.tsx WORKSPACE_ROUTES 对齐, 顺序 = 导航顺序)。 */
export const WORKSPACE_NAV_ITEMS: readonly { page: string; label: string; icon: string }[] = [
  { page: 'dashboard', label: 'Dashboard', icon: '◈' },
  { page: 'projects', label: 'Projects', icon: '▦' },
  { page: 'team', label: 'AI Team', icon: '◉' },
  { page: 'workflows', label: 'Workflow Center', icon: '⇄' },
  { page: 'runtime', label: 'Runtime Monitor', icon: '◎' },
  { page: 'audit', label: 'Audit', icon: '⧉' },
  { page: 'settings', label: 'Settings', icon: '⚙' },
];

/** 导航项 page → hash 路由 (dashboard 精确 #/workspace, 其余 #/workspace/<page>)。 */
export function navPathForPage(page: string): string {
  if (page === 'dashboard') return '#/workspace';
  return `#/workspace/${page}`;
}

export interface AfSidebarProps {
  /** 当前路由 page (导航激活态依据)。 */
  activePage: string;
  /** 折叠态 (宽度 64px, 仅图标)。 */
  collapsed: boolean;
}

export function AfSidebar({ activePage, collapsed }: AfSidebarProps): JSX.Element {
  const navigate = (page: string) => {
    window.location.hash = navPathForPage(page);
  };
  // K-7a: 左栏 = 项目列表 (新建/搜索/分组, 真实 /api/projects) — Codex 任务列表形态
  const [projects, setProjects] = useState<{ id: string; name: string; status?: string | null }[]>([]);
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .projects()
      .then((list) => {
        if (!cancelled) setProjects(list);
      })
      .catch(() => {
        if (!cancelled) setProjects([]); // 后端不可达 → 空列表 (创建会诚实报错)
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const q = query.trim().toLowerCase();
  const filtered = projects.filter((p) => p.name.toLowerCase().includes(q));
  const activeProjects = filtered.filter((p) => p.status !== 'delivered' && p.status !== 'completed');
  const doneProjects = filtered.filter((p) => p.status === 'delivered' || p.status === 'completed');

  const handleCreate = () => {
    const idea = window.prompt('一句话描述你的产品想法（例如: 做一个记账App）');
    if (!idea || !idea.trim()) return;
    setCreating(true);
    api
      .createProject(idea.trim())
      .then((created) => {
        window.location.hash = `#/project/${created.project_id}`;
      })
      .catch((err) => {
        window.alert(`创建失败: ${String(err)}`);
      })
      .finally(() => setCreating(false));
  };

  const openProject = (id: string) => {
    window.location.hash = `#/project/${id}`;
  };

  return (
    <aside
      className={`af-sidebar${collapsed ? ' af-sidebar--collapsed' : ''}`}
      data-testid="af-sidebar"
      aria-label="项目列表与工作台导航"
    >
      <div className="af-sidebar-brand" title="AI Factory" aria-label="AI Factory">
        <span className="af-brand-mark" aria-hidden="true">
          ◆
        </span>
      </div>
      {!collapsed && (
        <div className="af-project-pane" data-testid="af-project-pane">
          <button type="button" className="af-new-project" onClick={handleCreate} disabled={creating}>
            {creating ? '创建中…' : '＋ 新建项目'}
          </button>
          <input
            className="af-project-search"
            placeholder="搜索项目…"
            aria-label="搜索项目"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="af-project-list">
            {filtered.length === 0 && (
              <div className="af-project-empty">（暂无项目 — 点新建开始）</div>
            )}
            {activeProjects.length > 0 && (
              <>
                <div className="af-project-group">进行中</div>
                {activeProjects.map((p) => (
                  <button key={p.id} type="button" className="af-project-item" onClick={() => openProject(p.id)}>
                    {p.name}
                  </button>
                ))}
              </>
            )}
            {doneProjects.length > 0 && (
              <>
                <div className="af-project-group">已交付</div>
                {doneProjects.map((p) => (
                  <button key={p.id} type="button" className="af-project-item" onClick={() => openProject(p.id)}>
                    {p.name}
                  </button>
                ))}
              </>
            )}
          </div>
        </div>
      )}
      <div className="af-nav-section">工作区</div>
      <nav className="af-nav" aria-label="Workspace 导航">
        {WORKSPACE_NAV_ITEMS.map((item) => {
          const active = item.page === activePage;
          return (
            <button
              key={item.page}
              type="button"
              className={`af-nav-item${active ? ' af-nav-item--active' : ''}`}
              aria-current={active ? 'page' : undefined}
              title={collapsed ? item.label : undefined}
              onClick={() => navigate(item.page)}
            >
              <span className="af-nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              <span className="af-nav-label">{item.label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
