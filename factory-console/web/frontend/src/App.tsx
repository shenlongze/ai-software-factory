import { AppStateProvider, useAppState } from './state/AppState';
import type { Page } from './state/AppState';
import { ModeToggle } from './components/ModeToggle';
import { parseHash, type ParsedRoute } from './router';
import { DashboardPage } from './pages/DashboardPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { LifecyclePage } from './pages/LifecyclePage';
import { ApprovalPage } from './pages/ApprovalPage';
import { DecisionsPage } from './pages/DecisionsPage';
import { IntelligencePage } from './pages/IntelligencePage';
import { ProvidersPage } from './pages/ProvidersPage';
import { WorkflowPage } from './pages/WorkflowPage';
import { ArtifactsPage } from './pages/ArtifactsPage';
import { ReviewPage } from './pages/ReviewPage';
import { WorkspaceShell } from './shell/WorkspaceShell';

/** 导航项 (普通模式隐藏 Providers — Expert 专属)。 */
function NavLink({ label, page, target }: { label: string; page: Page; target: Page }): JSX.Element {
  const { navigate } = useAppState();
  const active = page.name === target.name;
  return (
    <button
      type="button"
      className={`nav-link${active ? ' active' : ''}`}
      aria-current={active ? 'page' : undefined}
      onClick={() => navigate(target)}
    >
      {label}
    </button>
  );
}

/**
 * S10-014 Task 002: AI Factory 路由入口占位 (独立于 Human Console)。
 * 只渲染当前两级路由解析结果 — Workspace/Project Shell 与页面由 Task 004/005 实现。
 */
function AiFactoryEntry({ route }: { route: ParsedRoute }): JSX.Element {
  return (
    <div className="af-entry" data-testid="af-entry">
      <header className="af-entry-header">
        <span className="brand-mark">◆</span>
        <span className="af-entry-title">AI Factory</span>
        <span className="af-entry-level">{route.level === 'project' ? '项目' : '工作台'}</span>
      </header>
      <main className="af-entry-main" data-testid="af-entry-main">
        <p data-testid="af-route-level">{route.level}</p>
        <p data-testid="af-route-page">{route.page}</p>
        {route.projectId != null ? <p data-testid="af-route-project">{route.projectId}</p> : null}
      </main>
    </div>
  );
}

function Shell(): JSX.Element {
  const { mode, page } = useAppState();

  // S10-014 Task 002: AI Factory 两级路由入口 (hash 路由, 独立层, 不破坏 Human Console):
  //   #/workspace/<subpage> + #/project/:id[/<subpage>] + #/workspace?project=id 直链
  //   → AI Factory 入口; '#/workspace' 精确 → 保留 S10-001 Workspace Shell (console 工作台)。
  const route = parseHash(window.location.hash);
  const isAiFactoryRoute =
    route.level === 'project' || (route.level === 'workspace' && route.page !== 'dashboard');
  if (isAiFactoryRoute) {
    return <AiFactoryEntry route={route} />;
  }

  // S10-001: Workspace Shell 全屏三栏 (独立于 Human Console, 无 console 头/脚)
  // S10-003: hash 项目直链 (#/workspace?project=id) → 初始选中项目 (Agent Timeline)
  if (page.name === 'workspace') {
    return <WorkspaceShell initialProjectId={page.projectId ?? null} />;
  }

  return (
    <div className="console-shell">
      <header className="console-header">
        <div className="brand">
          <span className="brand-mark">◆</span>
          <span className="brand-name">AI Software Factory</span>
          <span className="brand-sub">Human Console</span>
        </div>
        <nav className="console-nav" aria-label="主导航">
          <NavLink label="Dashboard" page={page} target={{ name: 'dashboard' }} />
          <NavLink label="项目" page={page} target={{ name: 'projects' }} />
          <NavLink label="工作流" page={page} target={{ name: 'workflow', workflowId: '' }} />
          <NavLink label="产物" page={page} target={{ name: 'artifacts' }} />
          <NavLink label="审批" page={page} target={{ name: 'approvals' }} />
          <NavLink label="决策" page={page} target={{ name: 'decisions' }} />
          <NavLink label="智能" page={page} target={{ name: 'intelligence' }} />
          <NavLink label="工作台" page={page} target={{ name: 'workspace' }} />
          {mode === 'expert' ? <NavLink label="Providers" page={page} target={{ name: 'providers' }} /> : null}
        </nav>
        <ModeToggle />
      </header>
      <main className="console-main">
        {page.name === 'dashboard' ? <DashboardPage /> : null}
        {page.name === 'projects' ? <ProjectsPage /> : null}
        {page.name === 'lifecycle' ? <LifecyclePage /> : null}
        {page.name === 'workflow' ? <WorkflowPage /> : null}
        {page.name === 'artifacts' ? <ArtifactsPage /> : null}
        {page.name === 'review' ? <ReviewPage /> : null}
        {page.name === 'approvals' ? <ApprovalPage /> : null}
        {page.name === 'decisions' ? <DecisionsPage /> : null}
        {page.name === 'intelligence' ? <IntelligencePage /> : null}
        {page.name === 'providers' ? <ProvidersPage /> : null}
      </main>
      <footer className="console-footer">
        Human Console — 只读控制台 (执行权永远在人工一侧) · Phase 11B · ADR-0035
      </footer>
    </div>
  );
}

export default function App(): JSX.Element {
  return (
    <AppStateProvider>
      <Shell />
    </AppStateProvider>
  );
}
