/**
 * components/af/AfProjectSidebar.tsx — AI OS 项目级左侧导航栏 (S10-014 Task 005)。
 *
 * §3.1 Project Shell 11 导航 (Overview/Vision/Discovery/PRD/Roadmap/Backlog/Sprint/
 * Todo Tree/Workflow/Runtime/Logs) — 图标+文字, 激活态主色左边框 (§4.3 Navigation),
 * 复用 af-sidebar/af-nav/af-nav-item 样式 (与 Workspace Sidebar 同骨架)。
 *
 * 导航: 点击 → hash 路由 (#/project/:id/<page>, overview → #/project/:id 精确),
 * App.tsx hashchange 重渲染驱动; 壳不持有路由状态, 激活态由 activePage 传入。
 */

import { useI18n } from '../../i18n';

/** 11 个 Project 导航项 (与 router.tsx PROJECT_ROUTES 对齐, 顺序 = 导航顺序)。 */
export const PROJECT_NAV_ITEMS: readonly { page: string; label: string; icon: string }[] = [
  { page: 'overview', label: '概览', icon: '📋' },
  { page: 'docs', label: '文档', icon: '📄' },
  { page: 'todo', label: '任务', icon: '🗂' },
  { page: 'workflow', label: '执行', icon: '⚙️' },
  { page: 'runtime', label: '运行时', icon: '📈' },
  { page: 'quality', label: '质量', icon: '✅' },
  { page: 'ops', label: '运维', icon: '🛰' },
];

/** 导航项 page → hash 路由 (overview 精确 #/project/:id, 其余 #/project/:id/<page>)。 */
export function projectNavPathForPage(projectId: string, page: string): string {
  const base = `#/project/${encodeURIComponent(projectId)}`;
  if (page === 'overview') return base;
  return `${base}/${page}`;
}

export interface AfProjectSidebarProps {
  /** 当前项目 id (导航 hash 前缀)。 */
  projectId: string;
  /** 当前路由 page (导航激活态依据)。 */
  activePage: string;
}

export function AfProjectSidebar({ projectId, activePage }: AfProjectSidebarProps): JSX.Element {
  const { t } = useI18n();
  const navigate = (page: string) => {
    window.location.hash = projectNavPathForPage(projectId, page);
  };

  return (
    <aside
      className="af-sidebar"
      data-testid="af-project-sidebar"
      aria-label="项目导航"
    >
      <nav className="af-nav" aria-label="Project 导航">
        {PROJECT_NAV_ITEMS.map((item) => {
          const active = item.page === activePage;
          const label = t(`nav.project.${item.page}`);
          return (
            <button
              key={item.page}
              type="button"
              className={`af-nav-item${active ? ' af-nav-item--active' : ''}`}
              aria-current={active ? 'page' : undefined}
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
