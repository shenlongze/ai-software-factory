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
import { sampleProject, stubFetch } from './fixtures';

function projectRoute(page = 'overview') {
  return { level: 'project' as const, page, projectId: 'demo' };
}

const NAV_LABELS = [
  'Overview',
  'Vision',
  'Discovery',
  'PRD',
  'Roadmap',
  'Backlog',
  'Sprint',
  'Todo Tree',
  'Workflow',
  'Runtime',
  'Logs',
];

afterEach(() => {
  window.location.hash = '';
});

describe('AfProjectShell (AI OS 项目层壳)', () => {
  it('渲染项目层壳: Project Header + Sidebar 11 导航项 + Main', () => {
    stubFetch({ '/api/projects': [sampleProject({ id: 'demo' })] });
    render(<AfProjectShell route={projectRoute()} />);
    expect(screen.getByTestId('af-project-entry')).toBeInTheDocument();
    expect(screen.getByTestId('af-project-header')).toBeInTheDocument();
    expect(screen.getByTestId('af-project-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('af-main-content')).toBeInTheDocument();
    for (const label of NAV_LABELS) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toBeInTheDocument();
    }
  });

  it('PROJECT_NAV_ITEMS 与路由表对齐: 11 项, overview 在前', () => {
    expect(PROJECT_NAV_ITEMS.map((item) => item.page)).toEqual([
      'overview',
      'vision',
      'discovery',
      'prd',
      'roadmap',
      'backlog',
      'sprint',
      'todo',
      'workflow',
      'runtime',
      'logs',
    ]);
  });

  it('默认 overview: Overview 导航项激活 (aria-current=page), 其他不激活', () => {
    stubFetch({ '/api/projects': [sampleProject({ id: 'demo' })] });
    render(<AfProjectShell route={projectRoute()} />);
    expect(screen.getByRole('button', { name: /Overview/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('button', { name: /Todo Tree/ })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('button', { name: /Logs/ })).not.toHaveAttribute('aria-current');
  });

  it('激活态跟随路由: route.page=todo → Todo Tree 高亮, Overview 不高亮', () => {
    stubFetch({ '/api/projects': [sampleProject({ id: 'demo' })] });
    render(<AfProjectShell route={projectRoute('todo')} />);
    expect(screen.getByRole('button', { name: /Todo Tree/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('button', { name: /Overview/ })).not.toHaveAttribute('aria-current');
  });

  it('点击导航项 → 更新 window.location.hash (overview → #/project/demo, 其余 → #/project/demo/<page>)', async () => {
    const user = userEvent.setup();
    stubFetch({ '/api/projects': [sampleProject({ id: 'demo' })] });
    render(<AfProjectShell route={projectRoute()} />);
    await user.click(screen.getByRole('button', { name: /Todo Tree/ }));
    expect(window.location.hash).toBe('#/project/demo/todo');
    await user.click(screen.getByRole('button', { name: /Backlog/ }));
    expect(window.location.hash).toBe('#/project/demo/backlog');
    await user.click(screen.getByRole('button', { name: /Vision/ }));
    expect(window.location.hash).toBe('#/project/demo/vision');
    await user.click(screen.getByRole('button', { name: /Overview/ }));
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

  it('overview: 渲染真实 Project Entity (GET /api/projects 定位 → 详情)', async () => {
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
    const detail = await screen.findByTestId('af-project-detail');
    expect(within(detail).getByRole('heading', { name: '记账 App' })).toBeInTheDocument();
    expect(within(detail).getByText('demo')).toBeInTheDocument();
    expect(within(detail).getByText('探索')).toBeInTheDocument(); // lifecycle 人话标签
    expect(within(detail).getByText('活跃')).toBeInTheDocument(); // status 人话标签
    expect(within(detail).getByText('个人记账工具')).toBeInTheDocument();
    expect(within(detail).getByText('执行中')).toBeInTheDocument(); // workflow 状态
    expect(within(detail).getByText('50%')).toBeInTheDocument();
  });

  it.each([
    ['todo', 'Todo Tree module loading — 开发中'],
    ['vision', 'Vision module loading — 开发中'],
    ['sprint', 'Sprint module loading — 开发中'],
    ['logs', 'Logs module loading — 开发中'],
    ['workflow', 'Workflow module loading — 开发中'],
  ])('占位页 %s → AfModulePlaceholder (禁空白)', async (page, expectedText) => {
    stubFetch({ '/api/projects': [sampleProject({ id: 'demo' })] });
    render(<AfProjectShell route={projectRoute(page)} />);
    expect(await screen.findByTestId('af-module-placeholder')).toHaveTextContent(expectedText);
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
