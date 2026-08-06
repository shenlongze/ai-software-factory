/**
 * src/test/IntelligencePage.test.tsx — 智能视图 (经验/Provider/Agent/推荐)。
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AppStateProvider } from '../state/AppState';
import { IntelligencePage } from '../pages/IntelligencePage';
import { ModeToggle } from '../components/ModeToggle';
import { sampleDashboard, sampleExperience, sampleProvider, sampleRecommendation, stubFetch } from './fixtures';

function renderIntelligence() {
  stubFetch({
    '/api/experience?limit=20': [sampleExperience(), sampleExperience({ id: 'exp-2', result: 'failure', score: 0.4 })],
    '/api/providers': [sampleProvider()],
    '/api/recommendations?limit=20': [sampleRecommendation()],
    '/api/dashboard': sampleDashboard(),
  });
  return render(
    <AppStateProvider>
      <IntelligencePage />
    </AppStateProvider>,
  );
}

describe('IntelligencePage', () => {
  it('渲染四张卡片 (经验/Provider/Agent/推荐)', async () => {
    renderIntelligence();
    expect(await screen.findByText('Experience Growth')).toBeInTheDocument();
    expect(screen.getByText('Provider Performance')).toBeInTheDocument();
    expect(screen.getByText('Agent Capability')).toBeInTheDocument();
    expect(screen.getByText('Recommendation Accuracy')).toBeInTheDocument();
  });

  it('经验统计: 成功率计算', async () => {
    renderIntelligence();
    expect(await screen.findByText(/共 2 条 · 成功率 50%/)).toBeInTheDocument();
    expect(screen.getAllByText('hermes').length).toBeGreaterThan(0);
  });

  it('Provider 行渲染 成本/性能/经验 评分', async () => {
    renderIntelligence();
    expect(await screen.findByText('Hermes')).toBeInTheDocument();
  });

  it('Agent 技能标签渲染', async () => {
    renderIntelligence();
    expect(await screen.findByText('Planner')).toBeInTheDocument();
    expect(screen.getByText('planning')).toBeInTheDocument();
  });

  it('推荐条目渲染候选 + 首条解释; 专家模式显示证据链', async () => {
    const user = userEvent.setup();
    stubFetch({
      '/api/experience?limit=20': [],
      '/api/providers': [sampleProvider()],
      '/api/recommendations?limit=20': [sampleRecommendation()],
      '/api/dashboard': sampleDashboard({ agents: [] }),
    });
    render(
      <AppStateProvider>
        <ModeToggle />
        <IntelligencePage />
      </AppStateProvider>,
    );
    expect(await screen.findByText('hermes')).toBeInTheDocument();
    expect(screen.getByText('经验丰富')).toBeInTheDocument();
    expect(screen.queryByText('2 条证据')).toBeNull();
    await user.click(screen.getByRole('button', { name: '专业模式' }));
    expect(screen.getByText('2 条证据')).toBeInTheDocument();
  });

  it('空数据 → 各卡片空态', async () => {
    stubFetch({
      '/api/experience?limit=20': [],
      '/api/providers': [],
      '/api/recommendations?limit=20': [],
      '/api/dashboard': sampleDashboard({ agents: [] }),
    });
    render(
      <AppStateProvider>
        <IntelligencePage />
      </AppStateProvider>,
    );
    expect(await screen.findByText('暂无经验记录')).toBeInTheDocument();
    expect(screen.getByText('暂无 Provider 数据')).toBeInTheDocument();
    expect(screen.getByText('暂无 Agent')).toBeInTheDocument();
    expect(screen.getByText('暂无推荐记录')).toBeInTheDocument();
  });

  it('任一 API 错误 → ErrorState', async () => {
    stubFetch({
      '/api/experience?limit=20': [],
      '/api/providers': undefined as never,
      '/api/recommendations?limit=20': [],
      '/api/dashboard': sampleDashboard(),
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        if (path === '/api/providers') {
          return { ok: false, status: 500, json: async () => ({}) } as Response;
        }
        return { ok: true, status: 200, json: async () => [] } as Response;
      }),
    );
    render(
      <AppStateProvider>
        <IntelligencePage />
      </AppStateProvider>,
    );
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/500/);
  });
});
