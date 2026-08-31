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
import { useI18n } from '../../i18n';

/** K-7b: 默认一人公司根 (one-person company) — 项目直接挂下面; 部门仅用户显式创建时才出现。 */
export const PERSONAL_COMPANY = {
  id: 'personal-company',
  name: '我的公司',
  icon: '🏢',
};

/** Workspace 导航项 (K6 Human Console: 三一级入口)。

 * Conversation = 默认首页 (普通用户唯一主要入口)。
 * Work = Projects/Sprints/Tasks。Control Tower = 实时观察。
 * 底层能力 (dashboard/audit/settings) 保留可访问 (drill-down 兼容)。
 */
export const WORKSPACE_NAV_ITEMS: readonly { page: string; label: string; icon: string }[] = [
  { page: 'conversation', label: '对话', icon: '💬' },
  { page: 'work', label: '工作', icon: '📋' },
  { page: 'tower', label: '控制塔', icon: '🛰' },
  { page: 'dashboard', label: '我的公司', icon: '🏢' },
  { page: 'projects', label: '项目', icon: '▦' },
  { page: 'monitor', label: '监控', icon: '📊' },
  { page: 'audit', label: '审计', icon: '🔍' },
  { page: 'settings', label: '设置', icon: '⚙' },
];

/** 导航项 page → hash 路由 (conversation/dashboard 精确 #/workspace, 其余 #/workspace/<page>)。 */
export function navPathForPage(page: string): string {
  if (page === 'conversation' || page === 'dashboard') return '#/workspace';
  return `#/workspace/${page}`;
}

export interface AfSidebarProps {
  /** 当前路由 page (导航激活态依据)。 */
  activePage: string;
  /** 折叠态 (宽度 64px, 仅图标)。 */
  collapsed: boolean;
}

export function AfSidebar({ activePage, collapsed }: AfSidebarProps): JSX.Element {
  const { t } = useI18n();
  const navigate = (page: string) => {
    window.location.hash = navPathForPage(page);
  };
  // K-7a: 左栏 = 项目列表 (新建/搜索/分组, 真实 /api/projects) — Codex 任务列表形态
  const [projects, setProjects] = useState<
    { id: string; name: string; status?: string | null; starred?: boolean; archived?: boolean; last_activity?: string | null }[]
  >([]);
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const [showAll, setShowAll] = useState<boolean>(false); // 全部默认收起 (Founder 2026-08-26: 默认收起, 点开展开)

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
  const filtered = projects.filter((p) => !p.archived && p.name.toLowerCase().includes(q));
  // Founder 2026-08-26: 收藏 + 最近3 + 全部
  const starredProjects = filtered.filter((p) => p.starred);
  const recentProjects = filtered
    .filter((p) => !p.starred && p.last_activity)
    .sort((a, b) => String(b.last_activity ?? '').localeCompare(String(a.last_activity ?? '')))
    .slice(0, 3);
  const recentIds = new Set(recentProjects.map((p) => p.id));
  const starredIds = new Set(starredProjects.map((p) => p.id));
  const restProjects = filtered.filter((p) => !starredIds.has(p.id) && !recentIds.has(p.id));

  const toggleStar = (p: { id: string; starred?: boolean }) => {
    api
      .updateProject(p.id, { starred: !p.starred })
      .then(() => {
        setProjects((prev) =>
          prev.map((x) => (x.id === p.id ? { ...x, starred: !p.starred } : x)),
        );
      })
      .catch((err) => {
        // eslint-disable-next-line no-alert
        window.alert(`收藏失败: ${String(err)}`);
      });
  };

  const renderProjectRow = (p: { id: string; name: string; starred?: boolean }) => (
    <div key={p.id} className="af-project-row">
      <button type="button" className="af-project-item af-os-leaf" onClick={() => openProject(p.id)}>
        <span className="af-os-icon" aria-hidden="true">📁</span>
        <span className="af-project-name">{p.name}</span>
      </button>
      <button
        type="button"
        className={`af-star-btn${p.starred ? ' active' : ''}`}
        onClick={() => toggleStar(p)}
        aria-label={p.starred ? `取消收藏 ${p.name}` : `收藏 ${p.name}`}
        title={p.starred ? '取消收藏' : '收藏'}
      >
        {p.starred ? '★' : '☆'}
      </button>
    </div>
  );

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
          {/* Founder 2026-08-26: 收藏 + 最近3 + 全部 (OS 树) */}
          <div className="af-os-tree" data-testid="af-os-tree">
            <div className="af-os-node af-os-node--root" title="一人公司根目录 (可 rename / 复制出去)">
              <span className="af-os-icon" aria-hidden="true">{PERSONAL_COMPANY.icon}</span>
              <span className="af-os-label">{PERSONAL_COMPANY.name}</span>
            </div>
            <div className="af-os-children">
              {filtered.length === 0 && (
                <div className="af-project-empty">（暂无项目 — 点新建开始）</div>
              )}
              {starredProjects.length > 0 && (
                <>
                  <div className="af-project-group">⭐ 收藏</div>
                  {starredProjects.map(renderProjectRow)}
                </>
              )}
              {recentProjects.length > 0 && (
                <>
                  <div className="af-project-group">🕐 最近</div>
                  {recentProjects.map(renderProjectRow)}
                </>
              )}
              {restProjects.length > 0 && (
                <>
                  <div className="af-project-group af-project-group--toggle" onClick={() => setShowAll((v) => !v)}>
                    <span>{showAll ? '▾' : '▸'} 全部 ({restProjects.length})</span>
                    <button
                      type="button"
                      className="af-manage-link"
                      onClick={(e) => {
                        e.stopPropagation();
                        window.location.hash = '#/workspace/manage';
                      }}
                    >
                      ⚙ 管理
                    </button>
                  </div>
                  {showAll && restProjects.map(renderProjectRow)}
                </>
              )}
            </div>
          </div>
        </div>
      )}
      <div className="af-nav-section">{t('nav.section.workspace')}</div>
      <nav className="af-nav" aria-label="Workspace 导航">
        {WORKSPACE_NAV_ITEMS.map((item) => {
          const active = item.page === activePage;
          const label = t(`nav.workspace.${item.page}`);
          return (
            <button
              key={item.page}
              type="button"
              className={`af-nav-item${active ? ' af-nav-item--active' : ''}`}
              aria-current={active ? 'page' : undefined}
              title={collapsed ? label : undefined}
              onClick={() => navigate(item.page)}
            >
              <span className="af-nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              <span className="af-nav-label">{label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
