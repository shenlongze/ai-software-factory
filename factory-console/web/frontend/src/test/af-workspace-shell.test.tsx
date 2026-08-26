/**
 * src/test/af-workspace-shell.test.tsx — AI OS Workspace Shell 三栏壳 (S10-014 Task 004)。
 *
 * 验证 (S10-014-plan §3.1 导航 + §4 Design System + AF-UI-Architecture §2.4 三栏):
 * - 三栏壳渲染: Header + Sidebar (7 导航项) + Main Content + 预览窗口 (K-7b)
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

/** 公司首页 (AfCompanyHome) 数据桩: GET /api/projects + /api/approvals?pending_only=true。 */
function companyStubs(projects: unknown[] = [], approvals: unknown[] = []) {
  return {
    '/api/projects': projects,
    '/api/approvals?pending_only=true': approvals,
  };
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
  it('渲染三栏壳: Header + Sidebar 7 导航项 + Main + 预览标签页 (K-7d 并入 B)', async () => {
    const user = userEvent.setup();
    stubFetch(companyStubs());
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(screen.getByTestId('af-workspace-entry')).toBeInTheDocument();
    expect(screen.getByTestId('af-header')).toBeInTheDocument();
    expect(screen.getByTestId('af-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('af-main-content')).toBeInTheDocument();
    expect(screen.getByTestId('af-b-tabs')).toBeInTheDocument();
    // 预览并入 B 列: 点"预览"标签页 → 预览窗口出现在主区
    await user.click(screen.getByRole('button', { name: '预览' }));
    expect(await screen.findByTestId('af-preview-window')).toBeInTheDocument();
    // AI 会话栏 (C 列)
    expect(screen.getByTestId('af-conversation-panel')).toBeInTheDocument();
    for (const label of NAV_LABELS) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toBeInTheDocument();
    }
  });

  it('默认 dashboard: Dashboard 导航项激活 (aria-current=page), 其他不激活', () => {
    stubFetch(companyStubs());
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
    stubFetch(companyStubs());
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
    stubFetch(companyStubs());
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
    stubFetch(companyStubs());
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    await user.click(screen.getByRole('button', { name: /折叠侧栏/ }));
    expect(store.get('af.sidebar.collapsed')).toBe('1');
  });

  it('折叠状态从 localStorage 恢复 (初始折叠)', () => {
    stubLocalStorage([['af.sidebar.collapsed', '1']]);
    render(<AfWorkspaceShell route={workspaceRoute('team')} />);
    expect(screen.getByTestId('af-sidebar')).toHaveClass('af-sidebar--collapsed');
  });

  it('dashboard (我的公司): 关注项目 (收藏+近期) + 待办聚合 (真实 API)', async () => {
    const recent = new Date(Date.now() - 2 * 24 * 3600 * 1000).toISOString();
    const old = new Date(Date.now() - 30 * 24 * 3600 * 1000).toISOString();
    stubFetch(
      companyStubs(
        [
          sampleProject({ id: 'p-recent', name: '近期项目', starred: true, last_activity: recent, status: 'development' }),
          sampleProject({ id: 'p-old', name: '旧收藏', starred: true, last_activity: old }),
          sampleProject({ id: 'p-nostar', name: '未收藏', starred: false, last_activity: recent }),
        ],
        [
          { id: 'APR-1', artifact_type: 'prd', gate: 'prd', status: 'pending', project_id: 'p-recent', requested_at: recent },
        ],
      ),
    );
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(await screen.findByTestId('af-company-home')).toBeInTheDocument();
    // 关注项目: 收藏 + 近期更新 → 展示; 旧收藏/未收藏 → 不占位
    expect(screen.getByTestId('af-focused-p-recent')).toBeInTheDocument();
    expect(screen.queryByTestId('af-focused-p-old')).not.toBeInTheDocument();
    expect(screen.queryByTestId('af-focused-p-nostar')).not.toBeInTheDocument();
    // 待办: 公司级聚合展示待审批
    expect(screen.getByTestId('af-todo-APR-1')).toBeInTheDocument();
    expect(screen.getByText(/PRD · 近期项目/)).toBeInTheDocument();
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
  ])('占位页 %s → AfModulePlaceholder (禁空白)', (page, expectedText) => {
    render(<AfWorkspaceShell route={workspaceRoute(page)} />);
    expect(screen.getByTestId('af-module-placeholder')).toHaveTextContent(expectedText);
  });

  it('settings → AfSettings 设置页 (LLM/Agent/Skill/MCP)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        const stub = (v: unknown) =>
          Promise.resolve({ ok: true, json: () => Promise.resolve(v) } as Response);
        if (String(url).includes('/api/projects')) return stub({ items: [], count: 0 }); // API 规范 v1
        if (String(url).includes('/api/providers')) return stub([]);
        if (String(url).includes('/api/agents')) return stub({ agents: [] });
        if (String(url).includes('/api/skills')) return stub({ skills: [] });
        if (String(url).includes('/api/mcp')) return stub({ connections: [], tools: [] });
        return stub({});
      }),
    );
    render(<AfWorkspaceShell route={workspaceRoute('settings')} />);
    expect(await screen.findByTestId('af-settings')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '🤖 LLM / 模型' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '👤 Agent' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '🧩 Skill' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '🔌 MCP' })).toBeInTheDocument();
  });

  it('加载中 → af-loading-state (projects 列表页)', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    render(<AfWorkspaceShell route={workspaceRoute('projects')} />);
    expect(screen.getByTestId('af-loading-state')).toBeInTheDocument();
  });

  it('空列表 → af-empty-state (暂无项目, projects 列表页)', async () => {
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceShell route={workspaceRoute('projects')} />);
    expect(await screen.findByTestId('af-empty-state')).toHaveTextContent(
      '暂无项目 — 输入想法创建一个',
    );
  });

  it('API 失败 → af-error-state (projects 列表页)', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))));
    render(<AfWorkspaceShell route={workspaceRoute('projects')} />);
    expect(await screen.findByTestId('af-error-state')).toHaveTextContent('network down');
  });

  it('Header: AI Factory 品牌 + 子页标签 + LLM 状态点 + 开发者控制台 链接', () => {
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceShell route={workspaceRoute('audit')} />);
    expect(screen.getByText('AI Factory')).toBeInTheDocument();
    expect(screen.getAllByText('审计').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId('af-llm-status')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /开发者控制台/ })).toBeInTheDocument();
  });
});
