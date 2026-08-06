/**
 * src/test/DashboardPage.test.tsx — 普通模式默认页。
 *
 * - 七域 dashboard 渲染 (项目数 / 待决定 / 最近决策)
 * - Simple 模式隐藏 Expert 卡片 (成本/Agent/活动)
 * - Expert 模式展开 Expert 卡片
 * - "创建新想法" → 只读 Modal (Permission Boundary)
 * - 空数据 / 错误态 / 加载态
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AppStateProvider, useAppState } from '../state/AppState';
import { DashboardPage } from '../pages/DashboardPage';
import { ModeToggle } from '../components/ModeToggle';
import { sampleDashboard, sampleProject, stubFetch } from './fixtures';

function renderDashboard(dashboard = sampleDashboard()) {
  stubFetch({ '/api/dashboard': dashboard });
  return render(
    <AppStateProvider>
      <DashboardPage />
    </AppStateProvider>,
  );
}

describe('DashboardPage', () => {
  it('渲染项目数与待决定数 (普通模式默认视图)', async () => {
    renderDashboard();
    expect(await screen.findByText('正在管理 1 个项目')).toBeInTheDocument();
    expect(screen.getByText('1', { selector: 'strong' })).toBeInTheDocument();
  });

  it('无待审批时提示 "当前没有待处理的决定"', async () => {
    renderDashboard(sampleDashboard({ approvals: [] }));
    expect(await screen.findByText('当前没有待处理的决定')).toBeInTheDocument();
  });

  it('渲染最近 AI 决策列表 (含推荐原因)', async () => {
    renderDashboard();
    expect(await screen.findByText('最近 AI 决策')).toBeInTheDocument();
    expect(screen.getByText('选择 Provider')).toBeInTheDocument();
  });

  it('普通模式: 不渲染 Expert 专属卡片', async () => {
    renderDashboard();
    await screen.findByText('正在管理 1 个项目');
    expect(screen.queryByText('成本汇总')).toBeNull();
    expect(screen.queryByText('运行中 Agent')).toBeNull();
    expect(screen.queryByText('最近活动')).toBeNull();
  });

  it('专家模式: 渲染成本/Agent/活动卡片', async () => {
    stubFetch({ '/api/dashboard': sampleDashboard() });
    render(
      <AppStateProvider>
        <ModeToggle />
        <DashboardPage />
      </AppStateProvider>,
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: '专业模式' }));
    expect(await screen.findByText('成本汇总')).toBeInTheDocument();
    expect(screen.getByText('运行中 Agent')).toBeInTheDocument();
    expect(screen.getByText('最近活动')).toBeInTheDocument();
    expect(screen.getByText(/总成本 \$1.2345/)).toBeInTheDocument();
    expect(screen.getByText('Planner')).toBeInTheDocument();
    expect(screen.getByText('task.completed')).toBeInTheDocument();
  });

  it('专家模式: 无运行 Agent → 空态; 无活动 → 空态', async () => {
    stubFetch({ '/api/dashboard': sampleDashboard({ agents: [], activity: [] }) });
    render(
      <AppStateProvider>
        <ModeToggle />
        <DashboardPage />
      </AppStateProvider>,
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: '专业模式' }));
    expect(await screen.findByText('无运行中 Agent')).toBeInTheDocument();
    expect(screen.getByText('暂无活动')).toBeInTheDocument();
  });

  it('hero 按钮: 查看项目 / 处理审批 导航', async () => {
    const user = userEvent.setup();
    stubFetch({ '/api/dashboard': sampleDashboard() });
    render(
      <AppStateProvider>
        <DashboardPage />
        <ProbePage />
      </AppStateProvider>,
    );
    await user.click(await screen.findByRole('button', { name: '查看项目' }));
    expect(screen.getByTestId('probe-page')).toHaveTextContent('projects');
    await user.click(screen.getByRole('button', { name: '处理审批' }));
    expect(screen.getByTestId('probe-page')).toHaveTextContent('approvals');
  });

  it('决策条目点击 → 导航到决策详情', async () => {
    const user = userEvent.setup();
    stubFetch({ '/api/dashboard': sampleDashboard() });
    render(
      <AppStateProvider>
        <DashboardPage />
        <ProbePage />
      </AppStateProvider>,
    );
    await user.click(await screen.findByText('选择 Provider'));
    expect(screen.getByTestId('probe-page')).toHaveTextContent('decisions');
  });

  it('创建新想法 → 只读 Modal (写路径指引, 不写)', async () => {
    const user = userEvent.setup();
    renderDashboard();
    await user.click(await screen.findByRole('button', { name: '创建新想法' }));
    expect(screen.getByRole('dialog', { name: '创建新想法' })).toBeInTheDocument();
    expect(screen.getByText(/factory idea new/)).toBeInTheDocument();
    expect(screen.getByText(/不提供写路径/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '关闭' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('加载态先出现, 数据后渲染', async () => {
    let resolveFn: (v: unknown) => void = () => {};
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise((resolve) => {
            resolveFn = resolve;
          }),
      ),
    );
    render(
      <AppStateProvider>
        <DashboardPage />
      </AppStateProvider>,
    );
    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
    resolveFn({ ok: true, status: 200, json: async () => sampleDashboard() } as Response);
    expect(await screen.findByText('正在管理 1 个项目')).toBeInTheDocument();
  });

  it('API 错误 → ErrorState', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response),
    );
    render(
      <AppStateProvider>
        <DashboardPage />
      </AppStateProvider>,
    );
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/500/);
  });

  it('空 dashboard → 暂无数据', async () => {
    renderDashboard(sampleDashboard({ projects: [sampleProject({ status: 'archived' })] }));
    expect(await screen.findByText('正在管理 0 个项目')).toBeInTheDocument();
  });
});

/** 探测当前页面 (与 App 的 page 状态联动)。 */
function ProbePage(): JSX.Element {
  const { page } = useAppState();
  return <span data-testid="probe-page">{page.name}</span>;
}
