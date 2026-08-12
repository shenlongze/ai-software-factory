/**
 * src/test/af-dashboard.test.tsx — AfDashboard 组件测试 (S10-015 Task 006)。
 *
 * AI 软件公司 Control Center 6 模块 (真实数据驱动, 诚实空态):
 *   ① Active Projects        复用 AfProjectCard (真实项目 + workflow 状态)
 *   ② Running AI Employees   Agent 卡 (名称/当前任务/Workflow Stage/状态) — 无 → 诚实空态
 *   ③ Workflow Status        真实 workflow 实例阶段链 (P-806fe6e8 failed)
 *   ④ Blocked Tasks          任务名/原因/负责人/下一步 — 无 → 诚实空态
 *   ⑤ Recent Runtime Events  复用 AfTimeline (最近 N 条, 倒序) — 无 → 暂无活动
 *   ⑥ Quality Summary        Tests/Quality Gate/Build — 无数据 → Unavailable
 *
 * 数据流 (真实, 禁 mock 冒充): GET /api/dashboard + 每项目 workflow/timeline/backlog
 * → toDashboardViewModel (Adapter) → 6 模块。stubFetch 仅注入后端真实结构 (fixtures)。
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { AfDashboard } from '../components/af/AfDashboard';
import {
  sampleBacklogP806,
  sampleDashboardReal,
  sampleFailedTimeline,
  sampleFailedWorkflow,
} from './fixtures';
import { stubFetch } from './fixtures';
import type { ConsoleDashboard } from '../models/types';

/** 真实环境路由桩: dashboard 七域 + P-806fe6e8 workflow/timeline/backlog (markpad 无 workflow)。 */
function dashboardRoutes(
  dashOverrides: Partial<ConsoleDashboard> = {},
  extra: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    '/api/dashboard': sampleDashboardReal(dashOverrides),
    '/api/projects/P-806fe6e8/workflow': sampleFailedWorkflow(),
    '/api/projects/P-806fe6e8/timeline?limit=50': sampleFailedTimeline(),
    '/api/projects/P-806fe6e8/backlog': sampleBacklogP806(),
    '/api/projects/markpad/timeline?limit=50': [],
    '/api/projects/markpad/backlog': sampleBacklogP806({ project_id: 'markpad' }),
    ...extra,
  };
}

afterEach(() => {
  window.location.hash = '';
});

describe('AfDashboard (AI 软件公司 Control Center — 6 模块)', () => {
  it('加载中 → AfLoadingState', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    render(<AfDashboard />);
    expect(screen.getByTestId('af-loading-state')).toBeInTheDocument();
  });

  it('API 失败 → AfErrorState (控制中心加载失败)', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))));
    render(<AfDashboard />);
    expect(await screen.findByTestId('af-error-state')).toHaveTextContent('network down');
  });

  it('6 模块全部渲染 (标题)', async () => {
    stubFetch(dashboardRoutes());
    render(<AfDashboard />);
    expect(await screen.findByTestId('af-dashboard')).toBeInTheDocument();
    expect(screen.getByText('Active Projects')).toBeInTheDocument();
    expect(screen.getByText('Running AI Employees')).toBeInTheDocument();
    expect(screen.getByText('Workflow Status')).toBeInTheDocument();
    expect(screen.getByText('Blocked Tasks')).toBeInTheDocument();
    expect(screen.getByText('Recent Runtime Events')).toBeInTheDocument();
    expect(screen.getByText('Quality Summary')).toBeInTheDocument();
  });

  it('① Active Projects: 复用 AfProjectCard (2 真实项目 + workflow 状态)', async () => {
    stubFetch(dashboardRoutes());
    render(<AfDashboard />);
    const section = await screen.findByTestId('af-dash-active-projects');
    expect(within(section).getAllByTestId('af-project-card')).toHaveLength(2);
    expect(await within(section).findByText('markpad')).toBeInTheDocument();
    expect(await within(section).findByText('ScorePocket')).toBeInTheDocument();
    // workflow 状态: markpad 无 workflow → 未启动; P-806fe6e8 failed → 失败 (真实徽标)
    expect(await within(section).findByText('未启动')).toBeInTheDocument();
    expect(await within(section).findByText('失败')).toBeInTheDocument();
  });

  it('② Running AI Employees: 3 Agent AVAILABLE → 诚实空态 (暂无执行中 AI 员工)', async () => {
    stubFetch(dashboardRoutes());
    render(<AfDashboard />);
    const section = await screen.findByTestId('af-dash-running-agents');
    expect(await within(section).findByText('暂无执行中 AI 员工')).toBeInTheDocument();
  });

  it('② Running AI Employees: RUNNING Agent → 卡显示名称/当前任务/Workflow Stage/状态', async () => {
    stubFetch(
      dashboardRoutes({
        agents: [
          {
            id: 'backend-1',
            name: 'backend-1',
            role: 'backend-dev',
            status: 'RUNNING',
            skills: ['python'],
            current_task: '实现登录 API',
          },
        ],
      }),
    );
    render(<AfDashboard />);
    const section = await screen.findByTestId('af-dash-running-agents');
    // 组件渲染 "🤖 {agentName}" / "任务: {currentTask}" — 正则匹配 (前缀修饰)
    expect(await within(section).findByText(/backend-1/)).toBeInTheDocument();
    expect(await within(section).findByText(/实现登录 API/)).toBeInTheDocument();
    expect(await within(section).findByText('执行中')).toBeInTheDocument();
  });

  it('③ Workflow Status: 真实实例阶段链 (P-806fe6e8 failed → 开发/测试/发布)', async () => {
    stubFetch(dashboardRoutes());
    render(<AfDashboard />);
    const section = await screen.findByTestId('af-dash-workflow-status');
    // 项目名 (组件显示 projectName — Dashboard 不重复 workflow 实例名, 避免数据重复)
    expect(await within(section).findByText('ScorePocket')).toBeInTheDocument();
    // 阶段链人话: 开发 failed → 测试 pending → 发布 pending
    expect(await within(section).findByText('开发')).toBeInTheDocument();
    expect(await within(section).findByText('测试')).toBeInTheDocument();
    expect(await within(section).findByText('发布')).toBeInTheDocument();
    // 当前阶段 (project.current_stage 真实值)
    expect(await within(section).findByText(/development/)).toBeInTheDocument();
    // 失败状态徽标 (实例 status=failed)
    expect(within(section).getAllByText('失败').length).toBeGreaterThan(0);
  });

  it('④ Blocked Tasks: backlog 无 blocked → 诚实空态 (暂无阻塞任务)', async () => {
    stubFetch(dashboardRoutes());
    render(<AfDashboard />);
    const section = await screen.findByTestId('af-dash-blocked-tasks');
    expect(await within(section).findByText('暂无阻塞任务')).toBeInTheDocument();
  });

  it('④ Blocked Tasks: blocked Task → 任务名/原因/负责人/下一步', async () => {
    const backlog = sampleBacklogP806({
      tasks: [
        {
          id: 'TASK-b1',
          title: '实现登录 API',
          description: 'POST /api/login JWT',
          priority: 'P1',
          status: 'blocked',
          assignee: 'developer',
          dependency: ['TASK-a1'],
          created_at: null,
          updated_at: null,
          history: [],
        },
        {
          id: 'TASK-a1',
          title: '实现注册 API',
          description: 'POST /api/register',
          priority: 'P1',
          status: 'completed',
          assignee: 'developer',
          dependency: [],
          created_at: null,
          updated_at: null,
          history: [],
        },
      ],
    });
    stubFetch(dashboardRoutes({}, { '/api/projects/P-806fe6e8/backlog': backlog }));
    render(<AfDashboard />);
    const section = await screen.findByTestId('af-dash-blocked-tasks');
    // 组件渲染 "⛔ {taskName}" / "原因:" / "负责人:" / "下一步:" — 正则匹配前缀
    expect(await within(section).findByText(/实现登录 API/)).toBeInTheDocument();
    expect(await within(section).findByText(/实现注册 API/)).toBeInTheDocument(); // 依赖原因含被依赖任务名
    expect(await within(section).findByText(/开发工程师/)).toBeInTheDocument();
    expect(await within(section).findByText(/解除阻塞后继续执行/)).toBeInTheDocument();
  });

  it('⑤ Recent Runtime Events: timeline 事件 → AfTimeline (倒序, 最新在前)', async () => {
    stubFetch(dashboardRoutes());
    render(<AfDashboard />);
    const section = await screen.findByTestId('af-dash-recent-events');
    expect(await within(section).findByTestId('af-timeline')).toBeInTheDocument();
    const items = within(section).getAllByTestId('af-timeline-item');
    expect(items).toHaveLength(4); // sampleFailedTimeline 4 条
    // 最新在前: evt-504 (03:45 工作流失败) → 第一条
    expect(items[0]).toHaveTextContent('工作流失败');
  });

  it('⑤ Recent Runtime Events: 无活动 → 诚实空态 (暂无活动)', async () => {
    stubFetch(
      dashboardRoutes(
        { activity: [] },
        {
          '/api/projects/P-806fe6e8/timeline?limit=50': [],
          '/api/projects/markpad/timeline?limit=50': [],
        },
      ),
    );
    render(<AfDashboard />);
    const section = await screen.findByTestId('af-dash-recent-events');
    expect(await within(section).findByText('暂无活动')).toBeInTheDocument();
  });

  it('⑥ Quality Summary: cost/approvals/experience 真实值', async () => {
    stubFetch(dashboardRoutes());
    render(<AfDashboard />);
    const section = await screen.findByTestId('af-dash-quality');
    expect(await within(section).findByText('执行 8 次 · 成功率 13%')).toBeInTheDocument();
    expect(await within(section).findByText('待审批 1 项 (PRD)')).toBeInTheDocument();
    expect(await within(section).findByText('经验 2 条 · 成功率 50%')).toBeInTheDocument();
  });

  it('⑥ Quality Summary: 无数据 → Unavailable (不编造)', async () => {
    stubFetch(
      dashboardRoutes({
        cost: {
          total_cost: 0,
          calls: 0,
          success_rate: 0,
          avg_cost: 0,
          total_tokens: 0,
          by_provider: {},
        },
        approvals: [],
        experience: { total: 0, by_domain: {}, success_rate: 0, avg_score: 0, avg_confidence: 0 },
      }),
    );
    render(<AfDashboard />);
    const section = await screen.findByTestId('af-dash-quality');
    expect(within(section).getAllByText('Unavailable')).toHaveLength(3);
  });

  it('点击项目卡 → 跳转 #/project/{id}', async () => {
    const user = userEvent.setup();
    stubFetch(dashboardRoutes());
    render(<AfDashboard />);
    const card = await screen.findByRole('button', { name: /markpad/ });
    await user.click(card);
    expect(window.location.hash).toBe('#/project/markpad');
  });

  it('点击工作流状态项 → 跳转 #/project/{id}/workflow', async () => {
    const user = userEvent.setup();
    stubFetch(dashboardRoutes());
    render(<AfDashboard />);
    const wfItem = await screen.findByTestId('af-dash-wf-item');
    await user.click(wfItem);
    expect(window.location.hash).toBe('#/project/P-806fe6e8/workflow');
  });
});
