/**
 * src/test/DecisionsPage.test.tsx — 决策视图。
 *
 * - 列表来自 dashboard (最近决策), 自动选中第一条 → 详情
 * - 候选与评分 / 推荐 / 原因 / 证据链
 * - 普通模式隐藏 factor 细分, 专家模式展开
 * - 空决策 / 无列表 / 404 / 错误态
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useEffect, useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { AppStateProvider, useAppState } from '../state/AppState';
import { DecisionsPage } from '../pages/DecisionsPage';
import { ModeToggle } from '../components/ModeToggle';
import { sampleDashboard, sampleDecision, stubFetch } from './fixtures';

function renderDecisions(dashboard = sampleDashboard(), detail = sampleDecision()) {
  stubFetch({
    '/api/dashboard': dashboard,
    '/api/decisions/dec-1': detail,
  });
  return render(
    <AppStateProvider>
      <DecisionsPage />
    </AppStateProvider>,
  );
}

describe('DecisionsPage', () => {
  it('自动选中第一条决策并渲染详情', async () => {
    renderDecisions();
    expect(await screen.findByText('候选与评分')).toBeInTheDocument();
    expect(screen.getAllByText('Provider A').length).toBeGreaterThan(0);
    expect(screen.getByText('Provider B')).toBeInTheDocument();
    expect(screen.getByText('推荐')).toBeInTheDocument();
    expect(screen.getByText(/综合评分 90%/)).toBeInTheDocument();
    expect(screen.getByText('综合评分最高')).toBeInTheDocument();
    expect(screen.getByText('成本可控')).toBeInTheDocument();
    expect(screen.getByText('2 条证据')).toBeInTheDocument();
    expect(screen.getByText(/需人工审批/)).toBeInTheDocument();
  });

  it('普通模式隐藏 factor 细分; 专家模式展开', async () => {
    stubFetch({
      '/api/dashboard': sampleDashboard(),
      '/api/decisions/dec-1': sampleDecision(),
    });
    const user = userEvent.setup();
    render(
      <AppStateProvider>
        <ModeToggle />
        <DecisionsPage />
      </AppStateProvider>,
    );
    await screen.findByText('候选与评分');
    expect(screen.queryByText('Capability')).toBeNull();
    await user.click(screen.getByRole('button', { name: '专业模式' }));
    expect(screen.getAllByText('Capability').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Performance').length).toBeGreaterThan(0);
  });

  it('点击列表 tab 切换决策', async () => {
    const user = userEvent.setup();
    const detail2 = sampleDecision({ id: 'dec-2', description: '第二个决策', recommendation: 'opt-b' });
    stubFetch({
      '/api/dashboard': sampleDashboard({ decisions: [sampleDecision(), sampleDecision({ id: 'dec-2', description: '第二个决策' })] }),
      '/api/decisions/dec-1': sampleDecision(),
      '/api/decisions/dec-2': detail2,
    });
    render(
      <AppStateProvider>
        <DecisionsPage />
      </AppStateProvider>,
    );
    await screen.findByText('候选与评分');
    await user.click(screen.getByRole('button', { name: '第二个决策' }));
    expect(await screen.findByText('60%', { selector: '.score-value' })).toBeInTheDocument();
  });

  it('无列表且无详情 → 空态', async () => {
    renderDecisions(sampleDashboard({ decisions: [] }));
    expect(await screen.findByText('暂无 AI 决策')).toBeInTheDocument();
  });

  it('从导航 page state 携带 decisionId 进入 → 直接渲染该决策', async () => {
    stubFetch({
      '/api/dashboard': sampleDashboard(),
      '/api/decisions/dec-1': sampleDecision(),
    });
    render(
      <AppStateProvider>
        <NavThenDecisions />
      </AppStateProvider>,
    );
    expect(await screen.findByText('候选与评分')).toBeInTheDocument();
    expect(screen.getByText(/综合评分 90%/)).toBeInTheDocument();
  });

  it('详情 404 → ErrorState (失败安全展示)', async () => {
    stubFetch({
      '/api/dashboard': sampleDashboard(),
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        if (path === '/api/dashboard') {
          return { ok: true, status: 200, json: async () => sampleDashboard() } as Response;
        }
        return { ok: false, status: 404, json: async () => ({}) } as Response;
      }),
    );
    render(
      <AppStateProvider>
        <DecisionsPage />
      </AppStateProvider>,
    );
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/404/);
  });

  it('dashboard 错误 → ErrorState', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response),
    );
    render(
      <AppStateProvider>
        <DecisionsPage />
      </AppStateProvider>,
    );
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/500/);
  });

  it('未推荐 (recommendation null) → 等待人工判断', async () => {
    renderDecisions(
      sampleDashboard(),
      sampleDecision({ recommendation: null, options: [], reasoning: [] }),
    );
    expect(await screen.findByText('未推荐 (等待人工判断)')).toBeInTheDocument();
  });

  it('详情错误 → ErrorState', async () => {
    stubFetch({ '/api/dashboard': sampleDashboard() });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        if (path === '/api/dashboard') {
          return { ok: true, status: 200, json: async () => sampleDashboard() } as Response;
        }
        return { ok: false, status: 500, json: async () => ({}) } as Response;
      }),
    );
    render(
      <AppStateProvider>
        <DecisionsPage />
      </AppStateProvider>,
    );
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/500/);
  });
});

/** 先导航到 decisions (带 decisionId) 再挂载页面 — 覆盖 page state 初值路径。 */
function NavThenDecisions(): JSX.Element {
  const { navigate, page } = useAppState();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    navigate({ name: 'decisions', decisionId: 'dec-1' });
    setReady(true);
  }, [navigate]);
  if (!ready || page.name !== 'decisions') {
    return <span data-testid="nav-pending" />;
  }
  return <DecisionsPage />;
}
