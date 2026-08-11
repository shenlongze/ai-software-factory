import { useEffect, useState } from 'react';
import { AppStateProvider, useAppState } from './state/AppState';
import type { Page } from './state/AppState';
import { ModeToggle } from './components/ModeToggle';
import { parseHash } from './router';
import { AfWorkspaceEntry } from './pages/workspace/AfWorkspaceEntry';
import { AfProjectEntry } from './pages/project/AfProjectEntry';
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

function Shell(): JSX.Element {
  const { mode, page } = useAppState();

  // S10-014 Task 002b: hash 路由导航 — 点击项目卡/返回链接 → hash 变化 →
  // 重渲染 → 重新解析路由 (SPA hash 路由无需完整刷新)。
  const [, setHashTick] = useState(0);
  useEffect(() => {
    const onChange = () => setHashTick((tick) => tick + 1);
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  // S10-014 Task 002b: AI Factory 两级路由真实入口 (hash 路由, 独立层, 不破坏 Human Console):
  //   #/workspace[/<subpage>]  → AfWorkspaceEntry (真实项目列表, GET /api/dashboard)
  //   #/project/:id[/<subpage>] → AfProjectEntry (真实 Project Entity)
  //   #/workspace?project=id    → parseHash 直链重定向 project/overview → AfProjectEntry
  //   空 hash / 非 AI Factory   → Human Console (console-shell / S10-001 Workspace Shell)
  const route = parseHash(window.location.hash);
  const isAiFactoryRoute =
    route.level === 'project' || window.location.hash.startsWith('#/workspace');
  if (isAiFactoryRoute) {
    return route.level === 'project' ? (
      <AfProjectEntry route={route} />
    ) : (
      <AfWorkspaceEntry route={route} />
    );
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
