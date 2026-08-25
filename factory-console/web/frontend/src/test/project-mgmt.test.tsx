/**
 * src/test/project-mgmt.test.tsx — S10-006.5 收尾: 项目管理前端测试。
 *
 * 覆盖 Home 列表 ⋯ 菜单 (重命名/删除) + 重命名 Modal (PATCH → 列表/树/Header
 * 同步) + 删除二次确认 Modal (DELETE → 移除; 409 运行中提示) + 失败路径。
 * 唯一 basename, 不与 workspace-shell.test.tsx 冲突 (S10-001 壳测试另立文件)。
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '../design/theme';
import { AppStateProvider } from '../state/AppState';
import { WorkspaceShell } from '../shell/WorkspaceShell';
import { stubFetch } from './fixtures';

/** jsdom EventSource 桩 (选中项目后 AgentTimeline 订阅 SSE 用)。 */
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

const PROJECT = { id: 'ledger-app', name: '记账 App', status: 'active', description: 'mock 项目' };

/** PATCH/DELETE 共用路径的响应 (测试按需覆盖)。 */
const UPDATED = {
  project_id: 'ledger-app',
  name: '记账本',
  idea: '开发一个记账 App',
  status: 'active',
};

/**
 * 渲染 Workspace Shell (AppState + Theme 双 Provider, 与 main.tsx 一致)。
 * 返回 fetch 桩 (断言 PATCH/DELETE 调用)。GET 列表 / PATCH+DELETE 同路径。
 */
function renderShell(overrides?: Record<string, unknown>): ReturnType<typeof vi.fn> {
  try {
    window.localStorage.clear();
  } catch {
    /* 忽略 */
  }
  document.documentElement.dataset.theme = 'light';
  const fetchMock = stubFetch({
    '/api/projects': [PROJECT],
    '/api/projects/ledger-app': UPDATED,
    ...overrides,
  });
  render(
    <AppStateProvider>
      <ThemeProvider>
        <WorkspaceShell />
      </ThemeProvider>
    </AppStateProvider>,
  );
  return fetchMock;
}

/** 打开 ledger-app 的 ⋯ 菜单 (等待列表渲染后点击)。 */
async function openMenu(): Promise<void> {
  const user = userEvent.setup();
  await screen.findByTestId('ws-recent-ledger-app');
  await user.click(screen.getByTestId('ws-recent-menu-ledger-app'));
  expect(screen.getByTestId('ws-recent-pop-ledger-app')).toBeInTheDocument();
}

describe('项目管理 — Home 列表 ⋯ 菜单', () => {
  it('每项渲染 ⋯ 按钮, 菜单默认隐藏', async () => {
    renderShell();
    await screen.findByTestId('ws-recent-ledger-app');
    expect(screen.getByTestId('ws-recent-menu-ledger-app')).toBeInTheDocument();
    expect(screen.queryByTestId('ws-recent-pop-ledger-app')).toBeNull();
  });

  it('点击 ⋯ → 弹出菜单 (重命名/删除)', async () => {
    renderShell();
    await openMenu();
    expect(screen.getByTestId('ws-recent-rename-ledger-app')).toHaveTextContent('重命名');
    expect(screen.getByTestId('ws-recent-delete-ledger-app')).toHaveTextContent('删除');
  });

  it('再次点击 ⋯ 关闭菜单 (toggle)', async () => {
    const user = userEvent.setup();
    renderShell();
    await screen.findByTestId('ws-recent-ledger-app');
    await user.click(screen.getByTestId('ws-recent-menu-ledger-app'));
    expect(screen.getByTestId('ws-recent-pop-ledger-app')).toBeInTheDocument();
    await user.click(screen.getByTestId('ws-recent-menu-ledger-app'));
    expect(screen.queryByTestId('ws-recent-pop-ledger-app')).toBeNull();
  });
});

describe('项目管理 — 重命名 (PATCH)', () => {
  it('重命名 Modal 打开并预填当前项目名', async () => {
    const user = userEvent.setup();
    renderShell();
    await openMenu();
    await user.click(screen.getByTestId('ws-recent-rename-ledger-app'));
    expect(screen.getByTestId('pm-rename-modal')).toBeInTheDocument();
    expect(screen.getByTestId('pm-rename-input')).toHaveValue('记账 App');
  });

  it('保存 → PATCH /api/projects/{id} {name} → 列表/项目树同步更新', async () => {
    const user = userEvent.setup();
    const fetchMock = renderShell();
    await openMenu();
    await user.click(screen.getByTestId('ws-recent-rename-ledger-app'));
    fireEvent.change(screen.getByTestId('pm-rename-input'), { target: { value: '记账本' } });
    await user.click(screen.getByTestId('pm-rename-save'));

    // PATCH 调用形状 (method + body + 路径)
    const patchCall = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === 'PATCH',
    );
    expect(patchCall).toBeDefined();
    const [path, init] = patchCall as unknown as [string, RequestInit];
    expect(path).toBe('/api/projects/ledger-app');
    expect(JSON.parse(String(init.body))).toEqual({ name: '记账本' });

    // 列表同步 (Home recent 项新名) + Modal 关闭
    expect(await screen.findByText('记账本', { selector: '.ws-recent-name' })).toBeInTheDocument();
    expect(screen.queryByTestId('pm-rename-modal')).toBeNull();

    // 项目树同步 (Projects 视图树节点新名)
    await user.click(screen.getByRole('button', { name: 'Projects' }));
    const tree = await screen.findByTestId('ws-project-tree');
    expect(within(tree).getByRole('button', { name: /记账本/ })).toBeInTheDocument();
    expect(within(tree).queryByRole('button', { name: /记账 App/ })).toBeNull();
  });

  it('空名 → 错误提示 + 不发 PATCH', async () => {
    const user = userEvent.setup();
    const fetchMock = renderShell();
    await openMenu();
    await user.click(screen.getByTestId('ws-recent-rename-ledger-app'));
    fireEvent.change(screen.getByTestId('pm-rename-input'), { target: { value: '   ' } });
    await user.click(screen.getByTestId('pm-rename-save'));

    expect(await screen.findByTestId('pm-modal-error')).toHaveTextContent('项目名不能为空');
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === 'PATCH')).toBe(false);
  });

  it('后端 400 拒绝 → 错误提示 (Modal 停留, 可重试)', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === '/api/projects') {
        return { ok: true, status: 200, json: async () => ({ items: [PROJECT], count: 1 }) } as Response;
      }
      if (path === '/api/projects/ledger-app' && init?.method === 'PATCH') {
        return { ok: false, status: 400, json: async () => ({ detail: 'empty name' }) } as Response;
      }
      return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    render(
      <AppStateProvider>
        <ThemeProvider>
          <WorkspaceShell />
        </ThemeProvider>
      </AppStateProvider>,
    );

    await openMenu();
    await user.click(screen.getByTestId('ws-recent-rename-ledger-app'));
    fireEvent.change(screen.getByTestId('pm-rename-input'), { target: { value: 'x' } });
    await user.click(screen.getByTestId('pm-rename-save'));

    expect(await screen.findByTestId('pm-modal-error')).toHaveTextContent('HTTP 400');
    expect(screen.getByTestId('pm-rename-modal')).toBeInTheDocument(); // Modal 停留
  });

  it('重命名后 Header 项目选择器选项同步新名', async () => {
    const user = userEvent.setup();
    renderShell();
    await openMenu();
    await user.click(screen.getByTestId('ws-recent-rename-ledger-app'));
    fireEvent.change(screen.getByTestId('pm-rename-input'), { target: { value: '记账本' } });
    await user.click(screen.getByTestId('pm-rename-save'));
    await screen.findByText('记账本', { selector: '.ws-recent-name' });

    const options = within(screen.getByTestId('ds-select') as HTMLElement).getAllByRole('option');
    expect(options.map((option) => option.textContent)).toContain('记账本');
    expect(options.map((option) => option.textContent)).not.toContain('记账 App');
  });
});

describe('项目管理 — 删除 (DELETE)', () => {
  it('删除 → 二次确认 Modal (删除后不可恢复)', async () => {
    const user = userEvent.setup();
    renderShell();
    await openMenu();
    await user.click(screen.getByTestId('ws-recent-delete-ledger-app'));
    expect(screen.getByTestId('pm-delete-modal')).toBeInTheDocument();
    expect(screen.getByText(/删除后不可恢复/)).toBeInTheDocument();
  });

  it('确认 → DELETE /api/projects/{id} → 列表/项目树移除', async () => {
    const user = userEvent.setup();
    const fetchMock = renderShell();
    await openMenu();
    await user.click(screen.getByTestId('ws-recent-delete-ledger-app'));
    await user.click(screen.getByTestId('pm-delete-confirm'));

    // DELETE 调用形状
    const deleteCall = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === 'DELETE',
    );
    expect(deleteCall).toBeDefined();
    const [path] = deleteCall as unknown as [string, RequestInit];
    expect(path).toBe('/api/projects/ledger-app');

    // 列表移除 (Home recent 区消失) + Modal 关闭
    await waitFor(() => {
      expect(screen.queryByTestId('pm-delete-modal')).toBeNull();
    });
    expect(screen.queryByTestId('ws-recent-ledger-app')).toBeNull();
    expect(screen.queryByTestId('ws-recent-projects')).toBeNull();

    // 项目树移除 (Projects 视图空态)
    await user.click(screen.getByRole('button', { name: 'Projects' }));
    expect(await screen.findByTestId('ws-tree-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('ws-tree-project-ledger-app')).toBeNull();
  });

  it('取消 → 不发 DELETE, Modal 关闭', async () => {
    const user = userEvent.setup();
    const fetchMock = renderShell();
    await openMenu();
    await user.click(screen.getByTestId('ws-recent-delete-ledger-app'));
    await user.click(screen.getByRole('button', { name: '取消' }));

    expect(screen.queryByTestId('pm-delete-modal')).toBeNull();
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === 'DELETE')).toBe(false);
    expect(screen.getByTestId('ws-recent-row-ledger-app')).toBeInTheDocument(); // 列表保留
  });

  it('409 运行中 → 提示"项目正在开发中, 无法删除", 列表保留', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === '/api/projects') {
        return { ok: true, status: 200, json: async () => ({ items: [PROJECT], count: 1 }) } as Response;
      }
      if (path === '/api/projects/ledger-app' && init?.method === 'DELETE') {
        return { ok: false, status: 409, json: async () => ({ detail: 'project is running' }) } as Response;
      }
      return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    render(
      <AppStateProvider>
        <ThemeProvider>
          <WorkspaceShell />
        </ThemeProvider>
      </AppStateProvider>,
    );

    await openMenu();
    await user.click(screen.getByTestId('ws-recent-delete-ledger-app'));
    await user.click(screen.getByTestId('pm-delete-confirm'));

    expect(await screen.findByText('项目正在开发中, 无法删除')).toBeInTheDocument();
    expect(screen.getByTestId('pm-delete-modal')).toBeInTheDocument(); // Modal 停留
    expect(screen.getByTestId('ws-recent-row-ledger-app')).toBeInTheDocument(); // 列表保留
  });
});
