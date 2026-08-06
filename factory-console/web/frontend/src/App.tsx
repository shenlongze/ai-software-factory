import { AppStateProvider, useAppState } from './state/AppState';
import type { Page } from './state/AppState';
import { ModeToggle } from './components/ModeToggle';
import { DashboardPage } from './pages/DashboardPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { LifecyclePage } from './pages/LifecyclePage';
import { ApprovalPage } from './pages/ApprovalPage';
import { DecisionsPage } from './pages/DecisionsPage';
import { IntelligencePage } from './pages/IntelligencePage';
import { ProvidersPage } from './pages/ProvidersPage';

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

function Shell(): JSX.Element {
  const { mode, page } = useAppState();

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
          <NavLink label="审批" page={page} target={{ name: 'approvals' }} />
          <NavLink label="决策" page={page} target={{ name: 'decisions' }} />
          <NavLink label="智能" page={page} target={{ name: 'intelligence' }} />
          {mode === 'expert' ? <NavLink label="Providers" page={page} target={{ name: 'providers' }} /> : null}
        </nav>
        <ModeToggle />
      </header>
      <main className="console-main">
        {page.name === 'dashboard' ? <DashboardPage /> : null}
        {page.name === 'projects' ? <ProjectsPage /> : null}
        {page.name === 'lifecycle' ? <LifecyclePage /> : null}
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
