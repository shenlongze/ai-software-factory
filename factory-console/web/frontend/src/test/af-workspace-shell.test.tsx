/**
 * src/test/af-workspace-shell.test.tsx — AI OS Workspace Shell 三栏壳 (S10-014 Task 004)。
 *
 * 验证 (S10-014-plan §3.1 导航 + §4 Design System + AF-UI-Architecture §2.4 三栏):
 * - 三栏壳渲染: Header + Sidebar (7 导航项) + Main Content + Context Panel
 * - 默认 dashboard 激活态; 激活态跟随 route.page (aria-current="page")
 * - 导航点击 → window.location.hash 更新 (#/workspace/<page>)
 * - 折叠切换 → 侧栏 class 变化 (af-sidebar--collapsed) + localStorage 持久化
 * - dashboard/projects → 真实项目列表 (GET /api/dashboard, 四态)
 * - team/workflows/runtime/audit/settings → AfModulePlaceholder (禁空白)
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { AfWorkspaceShell } from '../components/af/AfWorkspaceShell';
import { sampleDashboard, sampleProject, stubFetch } from './fixtures';

function workspaceRoute(page = 'dashboard') {
  return { level: 'workspace' as const, page };
}

const NAV_LABELS = [
  'Dashboard',
  'Projects',
  'AI Team',
  'Workflow Center',
  'Runtime Monitor',
  'Audit',
  'Settings',
];

/** 本环境 window.localStorage 为 undefined (jsdom 已知坑) — 测试注入可控 Storage 桩。 */
function stubLocalStorage(initial: [string, string][] = []): Map<string, string> {
  const store = new Map<string, string>(initial);
  const storage: Storage = {
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => {
      store.set(key, String(value));
    },
    removeItem: (key) => {
      store.delete(key);
    },
    clear: () => store.clear(),
    key: () => null,
    length: 0,
  };
  Object.defineProperty(window, 'localStorage', { value: storage, configurable: true });
  return store;
}

afterEach(() => {
  window.location.hash = '';
  try {
    window.localStorage.removeItem('af.sidebar.collapsed');
  } catch {
    /* 环境无 localStorage 时忽略 */
  }
});

describe('AfWorkspaceShell (AI OS 三栏壳)', () => {
  it('渲染三栏壳: Header + Sidebar 7 导航项 + Main + Context Panel', () => {
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(screen.getByTestId('af-workspace-entry')).toBeInTheDocument();
    expect(screen.getByTestId('af-header')).toBeInTheDocument();
    expect(screen.getByTestId('af-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('af-main-content')).toBeInTheDocument();
    expect(screen.getByTestId('af-context-panel')).toBeInTheDocument();
    for (const label of NAV_LABELS) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toBeInTheDocument();
    }
  });

  it('默认 dashboard: Dashboard 导航项激活 (aria-current=page), 其他不激活', () => {
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(screen.getByRole('button', { name: /Dashboard/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('button', { name: /Projects/ })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('button', { name: /Settings/ })).not.toHaveAttribute('aria-current');
  });

  it('激活态跟随路由: route.page=team → AI Team 高亮, Dashboard 不高亮', () => {
    render(<AfWorkspaceShell route={workspaceRoute('team')} />);
    expect(screen.getByRole('button', { name: /AI Team/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('button', { name: /Dashboard/ })).not.toHaveAttribute('aria-current');
  });

  it('点击导航项 → 更新 window.location.hash', async () => {
    const user = userEvent.setup();
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    await user.click(screen.getByRole('button', { name: /AI Team/ }));
    expect(window.location.hash).toBe('#/workspace/team');
    await user.click(screen.getByRole('button', { name: /Workflow Center/ }));
    expect(window.location.hash).toBe('#/workspace/workflows');
    await user.click(screen.getByRole('button', { name: /Settings/ }));
    expect(window.location.hash).toBe('#/workspace/settings');
  });

  it('折叠切换 → 侧栏 class 变化 (af-sidebar--collapsed) + 再次点击恢复', async () => {
    const user = userEvent.setup();
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    const sidebar = screen.getByTestId('af-sidebar');
    expect(sidebar).not.toHaveClass('af-sidebar--collapsed');
    await user.click(screen.getByRole('button', { name: /折叠侧栏/ }));
    expect(sidebar).toHaveClass('af-sidebar--collapsed');
    await user.click(screen.getByRole('button', { name: /展开侧栏/ }));
    expect(sidebar).not.toHaveClass('af-sidebar--collapsed');
  });

  it('折叠状态持久化到 localStorage (af.sidebar.collapsed=1)', async () => {
    const user = userEvent.setup();
    const store = stubLocalStorage();
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    await user.click(screen.getByRole('button', { name: /折叠侧栏/ }));
    expect(store.get('af.sidebar.collapsed')).toBe('1');
  });

  it('折叠状态从 localStorage 恢复 (初始折叠)', () => {
    stubLocalStorage([['af.sidebar.collapsed', '1']]);
    render(<AfWorkspaceShell route={workspaceRoute('team')} />);
    expect(screen.getByTestId('af-sidebar')).toHaveClass('af-sidebar--collapsed');
  });

  it('dashboard: 渲染真实项目列表 (GET /api/dashboard)', async () => {
    stubFetch({
      '/api/dashboard': sampleDashboard({
        projects: [
          sampleProject({
            id: 'markpad',
            name: 'markpad',
            lifecycle_stage: 'development',
            progress: 0.66,
          }),
          sampleProject({ id: 'ledger-app', name: 'ledger-app', lifecycle_stage: null, status: 'idea' }),
        ],
      }),
    });
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(await screen.findByText('markpad')).toBeInTheDocument();
    expect(screen.getByText('ledger-app')).toBeInTheDocument();
    expect(screen.getByText('开发')).toBeInTheDocument();
    expect(screen.getByText('想法')).toBeInTheDocument();
    expect(screen.getByText('66%')).toBeInTheDocument();
  });

  it('projects 页复用项目列表 (真实数据) + Projects 激活', async () => {
    stubFetch({
      '/api/dashboard': sampleDashboard({
        projects: [sampleProject({ id: 'markpad', name: 'markpad' })],
      }),
    });
    render(<AfWorkspaceShell route={workspaceRoute('projects')} />);
    expect(await screen.findByText('markpad')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Projects/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it.each([
    ['team', 'AI Team module loading — 开发中'],
    ['workflows', 'Workflow Center module loading — 开发中'],
    ['runtime', 'Runtime Monitor module loading — 开发中'],
    ['audit', 'Audit module loading — 开发中'],
    ['settings', 'Settings module loading — 开发中'],
  ])('占位页 %s → AfModulePlaceholder (禁空白)', (page, expectedText) => {
    render(<AfWorkspaceShell route={workspaceRoute(page)} />);
    expect(screen.getByTestId('af-module-placeholder')).toHaveTextContent(expectedText);
  });

  it('加载中 → af-loading-state', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(screen.getByTestId('af-loading-state')).toBeInTheDocument();
  });

  it('空列表 → af-empty-state (暂无项目)', async () => {
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(await screen.findByTestId('af-empty-state')).toHaveTextContent(
      '暂无项目 — 输入想法创建一个',
    );
  });

  it('API 失败 → af-error-state', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))));
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(await screen.findByTestId('af-error-state')).toHaveTextContent('network down');
  });

  it('Header: AI Factory 品牌 + 子页标签 + LLM 状态点 + 开发者控制台 链接', () => {
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceShell route={workspaceRoute('audit')} />);
    expect(screen.getByText('AI Factory')).toBeInTheDocument();
    expect(screen.getByText('审计')).toBeInTheDocument();
    expect(screen.getByTestId('af-llm-status')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /开发者控制台/ })).toBeInTheDocument();
  });
});
