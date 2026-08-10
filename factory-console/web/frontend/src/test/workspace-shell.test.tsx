/**
 * src/test/workspace-shell.test.tsx — S10-001 Workspace Shell 测试。
 *
 * 覆盖: 三栏 Layout (尺寸/折叠)、Header (品牌/项目选择/LLM 状态/主题/用户菜单)、
 * Explorer 导航 (8 项/切换)、Project Tree (mock 项目 + 6 阶段状态色点)、
 * Workspace 空态 + Timeline 预留、Panel 4 Tab (切换/空态)、
 * App 集成 (控制台 → 工作台) + pageFromHash。
 * 唯一 basename, 不与 S9/S10-000 测试冲突。
 */

import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { ThemeProvider } from '../design/theme';
import { pageFromHash } from '../state/AppState';
import { AppStateProvider, useAppState } from '../state/AppState';
import { WorkspaceShell } from '../shell/WorkspaceShell';
import { NAV_ITEMS, PANEL_TABS } from '../mock/workspace';
import { stubFetch } from './fixtures';

/** jsdom EventSource 桩 (S10-003: 选中项目后 AgentTimeline 订阅 SSE 用)。 */
class FakeEventSource {
  static instances: FakeEventSource[] = [];

  url: string;
  listeners: Record<string, Array<(ev: MessageEvent<string>) => void>> = {};
  onerror: ((ev: Event) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, cb: (ev: MessageEvent<string>) => void): void {
    (this.listeners[name] ??= []).push(cb);
  }

  close(): void {
    this.closed = true;
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});

/** Timeline 事件流桩 (S10-003 AgentTimeline 初始历史; 选中项目后渲染)。 */
const STUB_TIMELINE_EVENTS = [
  { id: 'evt-1', seq: 1, project_id: 'ledger-app', type: 'user', event_type: '', stage_id: null, agent_id: null, artifact_id: null, gate_id: null, message: '项目创建: 记账 App', status: 'OK', payload: {}, created_at: null },
  { id: 'evt-2', seq: 2, project_id: 'ledger-app', type: 'stage', event_type: 'org.workflow.stage_started', stage_id: 'mock-product', agent_id: 'pm', artifact_id: null, gate_id: null, message: '阶段开始: PM', status: 'OK', payload: { name: 'PM' }, created_at: null },
];

/** 渲染 Workspace Shell (AppState + Theme 双 Provider, 与 main.tsx 一致)。 */
function renderShell() {
  // jsdom 无 localStorage (theme.tsx 内部已 try/catch 降级 light)
  try {
    window.localStorage.clear();
  } catch {
    /* 忽略 */
  }
  document.documentElement.dataset.theme = 'light';
  stubFetch({
    '/api/projects/ledger-app/timeline?limit=200': STUB_TIMELINE_EVENTS,
  });
  return render(
    <AppStateProvider>
      <ThemeProvider>
        <WorkspaceShell />
      </ThemeProvider>
    </AppStateProvider>,
  );
}

/** 页面探针 (验证 navigate 生效)。 */
function PageProbe(): JSX.Element {
  const { page } = useAppState();
  return <span data-testid="probe-page">{page.name}</span>;
}

function renderShellWithProbe() {
  try {
    window.localStorage.clear();
  } catch {
    /* 忽略 */
  }
  document.documentElement.dataset.theme = 'light';
  return render(
    <AppStateProvider>
      <ThemeProvider>
        <WorkspaceShell />
        <PageProbe />
      </ThemeProvider>
    </AppStateProvider>,
  );
}

// ------------------------------------------------------------------ Layout 三栏
describe('Workspace Shell 三栏布局', () => {
  it('渲染 Header + Explorer + Workspace + Panel', () => {
    renderShell();
    expect(screen.getByTestId('ws-shell')).toBeInTheDocument();
    expect(screen.getByTestId('ws-header')).toBeInTheDocument();
    expect(screen.getByTestId('ds-layout')).toBeInTheDocument();
    expect(screen.getByTestId('ds-explorer')).toBeInTheDocument();
    expect(screen.getByTestId('ds-workspace')).toBeInTheDocument();
    expect(screen.getByTestId('ds-panel')).toBeInTheDocument();
  });

  it('Explorer 默认 220px / Panel 默认 360px', () => {
    renderShell();
    expect(screen.getByTestId('ds-explorer').getAttribute('style')).toContain('width: 220px');
    expect(screen.getByTestId('ds-panel').getAttribute('style')).toContain('width: 360px');
  });

  it('Explorer 折叠隐藏导航内容, 再次展开恢复', async () => {
    const user = userEvent.setup();
    renderShell();
    expect(screen.getByTestId('ws-explorer-nav')).toBeInTheDocument();
    await user.click(screen.getByTestId('ds-explorer-toggle'));
    expect(screen.queryByTestId('ws-explorer-nav')).toBeNull();
    await user.click(screen.getByTestId('ds-explorer-toggle'));
    expect(screen.getByTestId('ws-explorer-nav')).toBeInTheDocument();
  });

  it('Panel 折叠隐藏 Tab 内容, 再次展开恢复', async () => {
    const user = userEvent.setup();
    renderShell();
    expect(screen.getByTestId('ws-factory-panel')).toBeInTheDocument();
    await user.click(screen.getByTestId('ds-panel-toggle'));
    expect(screen.queryByTestId('ws-factory-panel')).toBeNull();
    await user.click(screen.getByTestId('ds-panel-toggle'));
    expect(screen.getByTestId('ws-factory-panel')).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ Header
describe('Workspace Header', () => {
  it('品牌 AI Factory + Workspace 副标', () => {
    renderShell();
    expect(screen.getByText('AI Factory')).toBeInTheDocument();
    expect(screen.getByText('Workspace')).toBeInTheDocument();
  });

  it('项目选择渲染 mock 项目选项 (记账 App)', () => {
    renderShell();
    const select = screen.getByTestId('ds-select');
    const options = within(select as HTMLElement).getAllByRole('option');
    expect(options.map((option) => option.textContent)).toContain('记账 App');
  });

  it('切换项目选择 → Workspace 显示选中项目 + Agent Timeline', async () => {
    renderShell();
    fireEvent.change(screen.getByTestId('ds-select'), { target: { value: 'ledger-app' } });
    expect(screen.getByTestId('ws-project-workspace')).toBeInTheDocument();
    expect(screen.getByTestId('ws-project-name')).toHaveTextContent('记账 App');
    // S10-003: Agent Timeline 接入 (初始历史事件渲染)
    expect(screen.getByTestId('agent-timeline')).toBeInTheDocument();
    expect(await screen.findByText('项目创建: 记账 App')).toBeInTheDocument();
  });

  it('LLM 状态 pill 显示已连接 + Provider/模型 (mock)', () => {
    renderShell();
    expect(screen.getByTestId('ws-llm-status')).toHaveTextContent('LLM 已连接');
    expect(screen.getByTestId('ws-llm-status')).toHaveTextContent('DeepSeek');
  });

  it('主题切换: 点击 ThemeToggle → html data-theme 亮/暗切换', async () => {
    const user = userEvent.setup();
    renderShell();
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(screen.getByRole('button', { name: '切换到暗色主题' })).toBeInTheDocument();
    await user.click(screen.getByTestId('ds-theme-toggle'));
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(screen.getByRole('button', { name: '切换到亮色主题' })).toBeInTheDocument();
    await user.click(screen.getByTestId('ds-theme-toggle'));
    expect(document.documentElement.dataset.theme).toBe('light');
  });
});

// ------------------------------------------------------------------ Explorer 导航
describe('Explorer 导航', () => {
  it('渲染 8 项导航 (Home/Projects/Tasks/Agents/Skills/Templates/Artifacts/Settings)', () => {
    renderShell();
    const nav = within(screen.getByTestId('ws-explorer-nav'));
    expect(NAV_ITEMS).toHaveLength(8);
    for (const item of NAV_ITEMS) {
      expect(nav.getByRole('button', { name: item.label })).toBeInTheDocument();
    }
  });

  it('默认 Home 高亮 (aria-current=page), 点击切换高亮', async () => {
    const user = userEvent.setup();
    renderShell();
    const nav = within(screen.getByTestId('ws-explorer-nav'));
    expect(nav.getByRole('button', { name: 'Home' })).toHaveAttribute('aria-current', 'page');
    await user.click(nav.getByRole('button', { name: 'Projects' }));
    expect(nav.getByRole('button', { name: 'Projects' })).toHaveAttribute('aria-current', 'page');
    expect(nav.getByRole('button', { name: 'Home' })).not.toHaveAttribute('aria-current');
  });

  it('点击 Projects → Project Tree 显示', async () => {
    const user = userEvent.setup();
    renderShell();
    expect(screen.queryByTestId('ws-project-tree')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Projects' }));
    expect(screen.getByTestId('ws-project-tree')).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ Project Tree
describe('Project Tree (mock)', () => {
  async function openTree() {
    const user = userEvent.setup();
    renderShell();
    await user.click(screen.getByRole('button', { name: 'Projects' }));
    await user.click(screen.getByRole('button', { name: /记账 App/ }));
    return user;
  }

  it('渲染项目 "记账 App" + 6 阶段 (Product→Release)', async () => {
    await openTree();
    expect(screen.getByRole('button', { name: /记账 App/ })).toBeInTheDocument();
    const stages = screen.getByTestId('ws-project-tree-stages');
    for (const name of ['Product', 'UX/UI', 'Architecture', 'Code', 'Test', 'Release']) {
      expect(within(stages).getByText(name)).toBeInTheDocument();
    }
  });

  it('阶段状态色点 data-status 正确 (完成/待审/待办)', async () => {
    await openTree();
    const stages = screen.getByTestId('ws-project-tree-stages');
    expect(stages.querySelector('[data-stage-id="product"] [data-status]')).toHaveAttribute(
      'data-status',
      'completed',
    );
    expect(stages.querySelector('[data-stage-id="architecture"] [data-status]')).toHaveAttribute(
      'data-status',
      'waiting_review',
    );
    expect(stages.querySelector('[data-stage-id="code"] [data-status]')).toHaveAttribute(
      'data-status',
      'pending',
    );
    expect(within(stages).getByText('待审核')).toBeInTheDocument();
    expect(within(stages).getAllByText('待执行')).toHaveLength(3);
  });

  it('点击项目 → Workspace 显示项目工作台 + Agent Timeline (S10-003)', async () => {
    const user = await openTree();
    await user.click(screen.getByRole('button', { name: /记账 App/ }));
    expect(screen.getByTestId('ws-project-workspace')).toBeInTheDocument();
    expect(screen.getByTestId('ws-project-name')).toHaveTextContent('记账 App');
    expect(screen.getByText('进行中')).toBeInTheDocument(); // StatusBadge (active)
    // Timeline 预留已替换为 AgentTimeline (事件流渲染)
    expect(screen.queryByTestId('timeline-placeholder')).toBeNull();
    expect(screen.getByTestId('agent-timeline')).toBeInTheDocument();
    expect(await screen.findByText('PM')).toBeInTheDocument(); // StageCard name (mock stage 节点)
  });
});

// ------------------------------------------------------------------ Panel 4 Tab
describe('Factory Panel 4 Tab', () => {
  it('渲染 4 个 Tab (Browser/Task/Artifact/Review), Browser 默认激活', () => {
    renderShell();
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(4);
    expect(PANEL_TABS.map((tab) => tab.label)).toEqual(['Browser', 'Task', 'Artifact', 'Review']);
    expect(screen.getByRole('tab', { name: 'Browser' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Task' })).toHaveAttribute('aria-selected', 'false');
  });

  it('Browser Tab 空态文案 (默认)', () => {
    renderShell();
    expect(screen.getByTestId('ws-panel-browser')).toBeInTheDocument();
    expect(screen.getByText('浏览器预览')).toBeInTheDocument();
  });

  it('切换 Tab → Task 空态 / Artifact 空态 / Review 空态', async () => {
    const user = userEvent.setup();
    renderShell();
    await user.click(screen.getByRole('tab', { name: 'Task' }));
    expect(screen.getByTestId('ws-panel-task')).toBeInTheDocument();
    expect(screen.queryByTestId('ws-panel-browser')).toBeNull();
    expect(screen.getByText('任务状态')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Artifact' }));
    expect(screen.getByTestId('ws-panel-artifact')).toBeInTheDocument();
    expect(screen.getByText('产物中心')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Review' }));
    expect(screen.getByTestId('ws-panel-review')).toBeInTheDocument();
    expect(screen.getByText('审核清单')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Review' })).toHaveAttribute('aria-selected', 'true');
  });
});

// ------------------------------------------------------------------ Workspace 空态 / 视图
describe('Workspace 视图', () => {
  it('空态页 "AI Workspace" + Timeline 预留容器 (S10-003)', () => {
    renderShell();
    expect(screen.getByTestId('ws-workspace-home')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'AI Workspace' })).toBeInTheDocument();
    expect(screen.getByTestId('timeline-placeholder')).toBeInTheDocument();
  });

  it('新建项目按钮 → 提示 S10-002 接入 (点击有反馈)', async () => {
    const user = userEvent.setup();
    renderShell();
    expect(screen.queryByTestId('ws-new-project-hint')).toBeNull();
    await user.click(screen.getByRole('button', { name: /新建项目/ }));
    expect(screen.getByTestId('ws-new-project-hint')).toHaveTextContent('S10-002 Runtime API');
  });

  it('导航 Settings → 设置空态视图', async () => {
    const user = userEvent.setup();
    renderShell();
    await user.click(screen.getByRole('button', { name: 'Settings' }));
    expect(screen.getByTestId('ws-view-settings')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '设置' })).toBeInTheDocument();
  });

  it('导航 Tasks → 通用占位视图 (后续 Sprint 接入)', async () => {
    const user = userEvent.setup();
    renderShell();
    await user.click(screen.getByRole('button', { name: 'Tasks' }));
    expect(screen.getByTestId('ws-view-tasks')).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ 用户菜单
describe('用户菜单', () => {
  it('打开菜单 → 设置项进入 Settings 视图', async () => {
    const user = userEvent.setup();
    renderShell();
    await user.click(screen.getByTestId('ws-user-btn'));
    expect(screen.getByTestId('ws-user-menu')).toBeInTheDocument();
    await user.click(screen.getByTestId('ws-user-menu-settings'));
    expect(screen.getByTestId('ws-view-settings')).toBeInTheDocument();
    expect(screen.queryByTestId('ws-user-menu')).toBeNull();
  });

  it('返回控制台 → navigate dashboard (AppState 生效)', async () => {
    const user = userEvent.setup();
    renderShellWithProbe();
    await user.click(screen.getByTestId('ws-user-btn'));
    await user.click(screen.getByTestId('ws-user-menu-console'));
    expect(screen.getByTestId('probe-page')).toHaveTextContent('dashboard');
  });
});

// ------------------------------------------------------------------ App 集成 / 路由入口
describe('App 集成与入口', () => {
  it('Human Console 导航 "工作台" → Workspace Shell 全屏渲染', async () => {
    const user = userEvent.setup();
    const emptyDashboard = {
      projects: [],
      approvals: [],
      agents: [],
      decisions: [],
      activity: [],
    };
    stubFetch({
      '/api/dashboard': emptyDashboard,
      '/api/projects': [],
      '/api/approvals': [],
      '/api/approval-gates': [],
      '/api/workflows': [],
      '/api/artifacts': [],
      '/api/experience?limit=20': [],
      '/api/providers': [],
      '/api/recommendations?limit=20': [],
    });
    render(
      <ThemeProvider>
        <App />
      </ThemeProvider>,
    );
    await user.click(screen.getByRole('button', { name: '工作台' }));
    expect(screen.getByTestId('ws-shell')).toBeInTheDocument();
    expect(screen.getByTestId('ws-header')).toBeInTheDocument();
    // 全屏 shell 不渲染 Human Console 页脚
    expect(screen.queryByText(/只读控制台/)).toBeNull();
  });

  it('pageFromHash: #/workspace → workspace; 其他 → null', () => {
    expect(pageFromHash('#/workspace')).toEqual({ name: 'workspace' });
    expect(pageFromHash('#/projects/ledger-app')).toBeNull();
    expect(pageFromHash('')).toBeNull();
  });
});
