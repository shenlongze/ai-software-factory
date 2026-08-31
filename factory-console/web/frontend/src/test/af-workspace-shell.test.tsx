/**
 * src/test/af-workspace-shell.test.tsx — AI OS Workspace Shell 三栏壳 (S10-014 Task 004)。
 *
 * 验证 (S10-014-plan §3.1 导航 + §4 Design System + AF-UI-Architecture §2.4 三栏):
 * - 三栏壳渲染: Header + Sidebar (3 导航项) + Main Content + 预览标签页 (K-7d)
 * - 默认 dashboard 激活态; 激活态跟随 route.page (aria-current="page")
 * - 导航点击 → window.location.hash 更新 (#/workspace/<page>)
 * - 折叠切换 → 侧栏 class 变化 (af-sidebar--collapsed) + localStorage 持久化
 * - 方案 A (Founder 2026-08-26): 导航 3 项 = 我的公司/项目/设置
 *   (AI Team/Workflow Center/Runtime Monitor/Audit 移 board)
 */

import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { AfWorkspaceShell } from '../components/af/AfWorkspaceShell';
import { sampleDashboard, sampleProject, stubFetch } from './fixtures';

function workspaceRoute(page = 'conversation') {
  return { level: 'workspace' as const, page };
}

/** 公司首页 (AfCompanyHome) 数据桩: GET /api/projects + /api/approvals?pending_only=true。 */
function companyStubs(projects: unknown[] = [], approvals: unknown[] = []) {
  return {
    '/api/projects': projects,
    '/api/approvals?pending_only=true': approvals,
  };
}

const NAV_LABELS = ['nav.workspace.conversation', 'nav.workspace.work', 'nav.workspace.tower'];

/** 侧栏导航按钮 (K-7d: B 列页面标签页与导航可能同名 — 查询收窄到导航区)。 */
function navButton(name: RegExp) {
  return within(screen.getByRole('navigation', { name: 'Workspace 导航' })).getByRole('button', {
    name,
  });
}

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
  it('渲染三栏壳: Header + Sidebar 8 导航项 + Main (K6 三入口)', async () => {
    stubFetch(companyStubs());
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(screen.getByTestId('af-workspace-entry')).toBeInTheDocument();
    expect(screen.getByTestId('af-header')).toBeInTheDocument();
    expect(screen.getByTestId('af-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('af-main-content')).toBeInTheDocument();
    // AI 会话栏 (C 列)
    expect(screen.getByTestId('af-conversation-panel')).toBeInTheDocument();
    for (const label of NAV_LABELS) {
      expect(navButton(new RegExp(label))).toBeInTheDocument();
    }
  });

  it('默认 conversation: 对话 导航项激活 (aria-current=page), 其他不激活', () => {
    stubFetch(companyStubs());
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(navButton(/nav.workspace.conversation/)).toHaveAttribute('aria-current', 'page');
    expect(navButton(/nav.workspace.work/)).not.toHaveAttribute('aria-current');
    expect(navButton(/nav.workspace.tower/)).not.toHaveAttribute('aria-current');
  });

  it('激活态跟随路由: route.page=work → 工作 高亮, 对话 不高亮', () => {
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceShell route={workspaceRoute('work')} />);
    expect(navButton(/nav.workspace.work/)).toHaveAttribute('aria-current', 'page');
    expect(navButton(/nav.workspace.conversation/)).not.toHaveAttribute('aria-current');
  });

  it('点击导航项 → 更新 window.location.hash', async () => {
    const user = userEvent.setup();
    stubFetch(companyStubs());
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    await user.click(navButton(/nav.workspace.work/));
    expect(window.location.hash).toBe('#/workspace/work');
    await user.click(navButton(/nav.workspace.tower/));
    expect(window.location.hash).toBe('#/workspace/tower');
    await user.click(navButton(/nav.workspace.conversation/));
    expect(window.location.hash).toBe('#/workspace');
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
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceShell route={workspaceRoute('projects')} />);
    expect(screen.getByTestId('af-sidebar')).toHaveClass('af-sidebar--collapsed');
  });

  it('dashboard (我的公司): 关注项目 (收藏必显示) + 待办聚合 (真实 API)', async () => {
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
    // 关注项目: 收藏必显示 (有更新排前; 旧收藏也显示 — Founder 严重同步问题); 未收藏不占位
    expect(screen.getByTestId('af-focused-p-recent')).toBeInTheDocument();
    expect(screen.getByTestId('af-focused-p-old')).toBeInTheDocument();
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
    expect(navButton(/项目/)).toHaveAttribute('aria-current', 'page');
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
    expect(screen.getByRole('tab', { name: '👤 AI 员工' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '🧩 技能' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '🔌 MCP' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '🎨 外观' })).toBeInTheDocument();
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
    render(<AfWorkspaceShell route={workspaceRoute('projects')} />);
    expect(screen.getByText('AI Factory')).toBeInTheDocument();
    expect(screen.getAllByText('项目').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId('af-llm-status')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /开发者控制台/ })).toBeInTheDocument();
  });
});


describe('AfWorkspaceFrame 分隔条拖拽 (Founder: 中间可调整大小)', () => {
  it('拖左分隔条 → 侧栏宽度变化; 拖右分隔条 → 会话栏宽度变化', async () => {
    const { container } = render(<AfWorkspaceShell route={workspaceRoute()} />);
    await screen.findByTestId('af-workspace-entry');
    const leftResizer = screen.getByTestId('af-resizer-left');
    const rightResizer = screen.getByTestId('af-resizer-right');
    const sidebar = container.querySelector('.af-col-a') as HTMLElement;
    const chat = container.querySelector('.af-col-c') as HTMLElement;
    // 拖左条 +80px (从侧栏右边界往右拖)
    await fireEvent.mouseDown(leftResizer, { clientX: 300 });
    await fireEvent.mouseMove(window, { clientX: 380 });
    await fireEvent.mouseUp(window);
    const afterSidebar = parseFloat(sidebar.style.width || '240');
    expect(afterSidebar).toBeGreaterThan(300);
    expect(afterSidebar).toBeLessThanOrEqual(420); // clamp max

    // 拖右条往左 +60px 会话栏宽
    await fireEvent.mouseDown(rightResizer, { clientX: 900 });
    await fireEvent.mouseMove(window, { clientX: 840 });
    await fireEvent.mouseUp(window);
    const afterChat = parseFloat(chat.style.width || '340');
    expect(afterChat).toBeGreaterThan(380);
    expect(afterChat).toBeLessThanOrEqual(560); // clamp max
  });

  it('双击分隔条 → 恢复默认宽度', async () => {
    const { container } = render(<AfWorkspaceShell route={workspaceRoute()} />);
    await screen.findByTestId('af-workspace-entry');
    const leftResizer = screen.getByTestId('af-resizer-left');
    const sidebar = container.querySelector('.af-col-a') as HTMLElement;
    await fireEvent.doubleClick(leftResizer);
    expect(parseFloat(sidebar.style.width || '0')).toBe(240);
  });
});
