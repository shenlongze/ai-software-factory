/**
 * src/test/af-project-shell.test.tsx — AI OS Project Shell 项目层壳 (S10-014 Task 005)。
 *
 * 验证 (S10-014-plan §3.1 Project Shell 11 导航 + §2.3 路由 + AF-UI-Architecture §2.4):
 * - 项目层壳渲染: Project Header (← 返回工作台 + 项目名 + lifecycle 徽标) +
 *   Project Sidebar (11 导航项) + Main
 * - 默认 overview 激活态; 激活态跟随 route.page (aria-current="page")
 * - 导航点击 → window.location.hash 更新 (#/project/demo/<page>; overview → #/project/demo)
 * - overview → 真实 Project Entity (GET /api/projects 定位, 详情渲染)
 * - 其他 10 页 → AfModulePlaceholder (禁空白; "Todo Tree module loading — 开发中")
 * - 404 (项目不在列表) → ErrorState "项目不存在或已被删除"
 * - 加载中 → LoadingState; API 失败 → ErrorState
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { PROJECT_NAV_ITEMS } from '../components/af/AfProjectSidebar';
import { AfProjectShell } from '../components/af/AfProjectShell';
import { sampleProject, sampleTodoBacklog, sampleWorkflowInstance, sampleWorkflowTimeline, sampleFailedWorkflow, sampleFailedTimeline, stubFetch } from './fixtures';

function projectRoute(page = 'overview') {
  return { level: 'project' as const, page, projectId: 'demo' };
}


/** 侧栏内导航按钮 (K-7d: B 列页面标签页与导航同名 — 查询收窄到侧栏)。 */
function navButton(name: RegExp) {
  return within(screen.getByTestId('af-project-sidebar')).getByRole('button', { name });
}

const NAV_LABELS = ['概览', '文档', '任务', '执行', '运行时', '质量', '运维'];

afterEach(() => {
  window.location.hash = '';
});

describe('AfProjectShell (AI OS 项目层壳)', () => {
  it('渲染项目层壳: Project Header + Sidebar 7 导航项 + Main', () => {
    stubFetch({ '/api/projects': [sampleProject({ id: 'demo' })] });
    render(<AfProjectShell route={projectRoute()} />);
    expect(screen.getByTestId('af-project-entry')).toBeInTheDocument();
    expect(screen.getByTestId('af-project-header')).toBeInTheDocument();
    expect(screen.getByTestId('af-project-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('af-main-content')).toBeInTheDocument();
    for (const label of NAV_LABELS) {
      expect(navButton(new RegExp(label))).toBeInTheDocument();
    }
  });

  it('PROJECT_NAV_ITEMS 与路由表对齐: 7 项 (Founder 精简 + 运维)', () => {
    expect(PROJECT_NAV_ITEMS.map((item) => item.page)).toEqual([
      'overview',
      'docs',
      'todo',
      'workflow',
      'runtime',
      'quality',
      'ops',
    ]);
  });

  it('默认 overview: 概览 导航项激活 (aria-current=page), 其他不激活', () => {
    stubFetch({ '/api/projects': [sampleProject({ id: 'demo' })] });
    render(<AfProjectShell route={projectRoute()} />);
    expect(navButton(/概览/)).toHaveAttribute('aria-current', 'page');
    expect(navButton(/任务/)).not.toHaveAttribute('aria-current');
    expect(navButton(/质量/)).not.toHaveAttribute('aria-current');
  });

  it('激活态跟随路由: route.page=todo → 任务 高亮, 概览 不高亮', () => {
    stubFetch({ '/api/projects': [sampleProject({ id: 'demo' })] });
    render(<AfProjectShell route={projectRoute('todo')} />);
    expect(navButton(/任务/)).toHaveAttribute('aria-current', 'page');
    expect(navButton(/概览/)).not.toHaveAttribute('aria-current');
  });

  it('点击导航项 → 更新 window.location.hash (overview → #/project/demo, 其余 → #/project/demo/<page>)', async () => {
    const user = userEvent.setup();
    stubFetch({ '/api/projects': [sampleProject({ id: 'demo' })] });
    render(<AfProjectShell route={projectRoute()} />);
    await user.click(navButton(/任务/));
    expect(window.location.hash).toBe('#/project/demo/todo');
    await user.click(navButton(/执行/));
    expect(window.location.hash).toBe('#/project/demo/workflow');
    await user.click(navButton(/质量/));
    expect(window.location.hash).toBe('#/project/demo/quality');
    await user.click(navButton(/概览/));
    expect(window.location.hash).toBe('#/project/demo');
  });

  it('Project Header: ← 返回工作台 (href=#/workspace) + 项目名 + lifecycle 徽标', async () => {
    stubFetch({
      '/api/projects': [
        sampleProject({ id: 'demo', name: '记账 App', lifecycle_stage: 'discovery' }),
      ],
    });
    render(<AfProjectShell route={projectRoute()} />);
    expect(await screen.findByTestId('af-project-header-name')).toHaveTextContent('记账 App');
    expect(screen.getByTestId('af-project-header-lifecycle')).toHaveTextContent('探索');
    expect(screen.getByRole('link', { name: /返回工作台/ })).toHaveAttribute('href', '#/workspace');
  });

  it('overview: 渲染项目首页 (K-7b: 生命周期 + Todo)', async () => {
    stubFetch({
      '/api/projects': [
        sampleProject({
          id: 'demo',
          name: '记账 App',
          description: '个人记账工具',
          lifecycle_stage: 'discovery',
          status: 'active',
          workflow_status: 'active',
          current_stage: 'product',
          progress: 0.5,
          last_activity: '2026-08-06T00:00:00Z',
        }),
      ],
    });
    render(<AfProjectShell route={projectRoute()} />);
    const home = await screen.findByTestId('af-project-home');
    expect(within(home).getByRole('heading', { name: '记账 App' })).toBeInTheDocument();
    expect(within(home).getByTestId('af-home-lifecycle')).toBeInTheDocument();
    expect(within(home).getByTestId('af-home-todo-summary')).toBeInTheDocument();
  });

  it('workflow 页 → 真实 Workflow Viewer (AfWorkflowPage, workflow+timeline 驱动)', async () => {
    stubFetch({
      '/api/projects': [sampleProject({ id: 'demo' })],
      '/api/projects/demo/workflow': sampleWorkflowInstance(),
      '/api/projects/demo/timeline?limit=200': sampleWorkflowTimeline(),
    });
    render(<AfProjectShell route={projectRoute('workflow')} />);
    expect(await screen.findByTestId('af-workflow-viewer')).toBeInTheDocument();
    // 真实流水线内容: 人话 Agent 名 + 阻塞原因 + 三层 (Instance/Template/Timeline)
    expect(screen.getAllByText('产品经理 Agent').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('阻塞: 等待前置阶段完成: UI 设计师')).toBeInTheDocument();
    expect(screen.getByTestId('af-wf-instance')).toBeInTheDocument();
    expect(screen.getByTestId('af-wf-template')).toBeInTheDocument();
    expect(screen.getByTestId('af-wf-timeline')).toBeInTheDocument();
  });

  it('todo 页 → 真实 Todo Tree (AfTodoTreePage, backlog 驱动)', async () => {
    stubFetch({
      '/api/projects': [sampleProject({ id: 'demo' })],
      '/api/projects/demo/backlog': sampleTodoBacklog(),
    });
    render(<AfProjectShell route={projectRoute('todo')} />);
    expect(await screen.findByTestId('af-todo-tree')).toBeInTheDocument();
  });

  it('runtime 页 → 真实 Runtime Timeline (AfRuntimePage, workflow+timeline 驱动, 失败展示)', async () => {
    stubFetch({
      '/api/projects': [sampleProject({ id: 'demo' })],
      '/api/projects/demo/workflow': sampleFailedWorkflow(),
      '/api/projects/demo/timeline?limit=200': sampleFailedTimeline(),
    });
    render(<AfProjectShell route={projectRoute('runtime')} />);
    expect(await screen.findByTestId('af-runtime-timeline')).toBeInTheDocument();
    // 真实失败展示: failed_reason 全文 + 当前 Agent + 事件流
    expect(screen.getByTestId('af-runtime-failed')).toHaveTextContent(
      'DeveloperError: provider response contains no parseable patch or operations (after 1 retry)',
    );
    expect(screen.getByTestId('af-runtime-agent')).toHaveTextContent('开发工程师 Agent');
    expect(screen.getAllByTestId('af-timeline-item').length).toBeGreaterThanOrEqual(1);
  });

  it('404: 项目不存在 → ErrorState "项目不存在或已被删除"', async () => {
    stubFetch({ '/api/projects': [sampleProject({ id: 'other' })] });
    render(<AfProjectShell route={projectRoute()} />);
    expect(await screen.findByTestId('error-state')).toHaveTextContent(
      '项目不存在或已被删除',
    );
  });

  it('加载中 → LoadingState', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    render(<AfProjectShell route={projectRoute()} />);
    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
  });

  it('API 失败 → ErrorState', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('boom'))));
    render(<AfProjectShell route={projectRoute()} />);
    expect(await screen.findByTestId('error-state')).toHaveTextContent('boom');
  });
});
