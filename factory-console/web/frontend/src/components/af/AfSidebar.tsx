/**
 * components/af/AfSidebar.tsx — AI OS 左侧导航栏 (S10-014 Task 004)。
 *
 * §3.1 两级导航 (Workspace 级): Dashboard/Projects/AI Team/Workflow Center/
 * Runtime Monitor/Audit/Settings — 图标+文字, 激活态主色左边框 (§4.3 Navigation)。
 * 240px 可折叠 (64px 仅图标); 点击 → hash 路由 (#/workspace/<page>, dashboard → #/workspace)。
 *
 * 纯展示 + hash 导航: 不持有路由状态, 激活态由 activePage 传入 (App hashchange 驱动)。
 */

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

  return (
    <aside
      className={`af-sidebar${collapsed ? ' af-sidebar--collapsed' : ''}`}
      data-testid="af-sidebar"
      aria-label="工作台导航"
    >
      <div className="af-sidebar-brand" title="AI Factory" aria-label="AI Factory">
        <span className="af-brand-mark" aria-hidden="true">
          ◆
        </span>
      </div>
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
