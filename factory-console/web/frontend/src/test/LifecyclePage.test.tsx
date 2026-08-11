/**
 * src/test/LifecyclePage.test.tsx — 项目工作区 (生命周期快照)。
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { AppStateProvider, useAppState } from '../state/AppState';
import { LifecyclePage } from '../pages/LifecyclePage';
import { sampleLifecycle, stubFetch } from './fixtures';

function renderLifecycle(lifecycle = sampleLifecycle()) {
  stubFetch({ '/api/projects/demo/lifecycle': lifecycle });
  return render(
    <AppStateProvider>
      <NavToLifecycle />
    </AppStateProvider>,
  );
}

/** 先导航到 lifecycle (projectId=demo) 再挂载页面。 */
function NavToLifecycle(): JSX.Element {
  const { navigate, page } = useAppState();
  const [ready, setReady] = React.useState(false);
  React.useEffect(() => {
    navigate({ name: 'lifecycle', projectId: 'demo' });
    setReady(true);
  }, [navigate]);
  if (!ready || page.name !== 'lifecycle') {
    return <span data-testid="nav-pending" />;
  }
  return <LifecyclePage />;
}

describe('LifecyclePage', () => {
  it('渲染项目工作区 (阶段/下一步/已完成/待审批)', async () => {
    renderLifecycle();
    expect(await screen.findByText('demo')).toBeInTheDocument();
    expect(screen.getByText('当前阶段')).toBeInTheDocument();
    expect(screen.getByText('build')).toBeInTheDocument();
    expect(screen.getByText('完成 build 阶段')).toBeInTheDocument();
    expect(screen.getByText('planning')).toBeInTheDocument();
    expect(screen.getByText(/design · 门 design_gate/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '去审批中心处理' })).toBeInTheDocument();
  });

  it('返回项目按钮 → 导航回 projects', async () => {
    const user = userEvent.setup();
    stubFetch({ '/api/projects/demo/lifecycle': sampleLifecycle() });
    render(
      <AppStateProvider>
        <NavToLifecycle />
        <ProbePage />
      </AppStateProvider>,
    );
    await user.click(await screen.findByRole('button', { name: /返回项目/ }));
    expect(screen.getByTestId('probe-page')).toHaveTextContent('projects');
  });

  it('无生命周期数据 → 空态', async () => {
    stubFetch({ '/api/projects/demo/lifecycle': null });
    render(
      <AppStateProvider>
        <NavToLifecycle />
      </AppStateProvider>,
    );
    expect(await screen.findByText(/暂无生命周期记录/)).toBeInTheDocument();
  });

  it('无下一步/无已完成阶段/无待审批 → 各自空态', async () => {
    renderLifecycle(
      sampleLifecycle({ next_actions: [], completed_stages: [], pending_approval: null }),
    );
    expect(await screen.findByText('暂无下一步建议')).toBeInTheDocument();
    expect(screen.getByText('暂无已完成阶段')).toBeInTheDocument();
    expect(screen.queryByText('待人工审批')).toBeNull();
  });

  it('API 404 (项目无生命周期记录) → 空态而非错误', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }) as Response),
    );
    render(
      <AppStateProvider>
        <NavToLifecycle />
      </AppStateProvider>,
    );
    // 404 视为"暂无记录", 不暴露 HTTP 状态码 (S10-015 修复)
    expect(await screen.findByText(/暂无生命周期记录/)).toBeInTheDocument();
    expect(screen.queryByTestId('error-state')).toBeNull();
  });

  it('API 错误 → ErrorState', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response),
    );
    render(
      <AppStateProvider>
        <NavToLifecycle />
      </AppStateProvider>,
    );
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/500/);
  });
});

function ProbePage(): JSX.Element {
  const { page } = useAppState();
  return <span data-testid="probe-page">{page.name}</span>;
}
