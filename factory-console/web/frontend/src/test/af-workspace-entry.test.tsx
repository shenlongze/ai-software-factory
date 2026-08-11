/**
 * src/test/af-workspace-entry.test.tsx — AI Factory 工作台真实入口 (S10-014 Task 002b)。
 *
 * 验证 (#/workspace 与 #/workspace/* 渲染真实 Workspace 数据, GET /api/dashboard):
 * - 加载: LoadingState
 * - 成功: 项目列表 (name / lifecycle 人话标签 / workflow 状态 / progress / stage_counts)
 * - 空:   EmptyState ("暂无项目 — 输入想法创建一个")
 * - 错误: ErrorState (API 失败)
 * - 点击项目卡片 → hash 跳转 #/project/{id}
 * - 品牌 Header (◆ AI Factory) + 子页标签
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { AfWorkspaceEntry } from '../pages/workspace/AfWorkspaceEntry';
import { sampleDashboard, sampleProject, stubFetch } from './fixtures';

function workspaceRoute(page = 'dashboard') {
  return { level: 'workspace' as const, page };
}

afterEach(() => {
  window.location.hash = '';
});

describe('AfWorkspaceEntry (AI Factory 工作台真实入口)', () => {
  it('加载中 → LoadingState', () => {
    let resolveFetch: (r: Response) => void = () => {};
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            resolveFetch = resolve;
          }),
      ),
    );
    render(<AfWorkspaceEntry route={workspaceRoute()} />);
    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
    void resolveFetch;
  });

  it('成功: 渲染真实项目列表 (name/lifecycle/workflow/progress/stage_counts)', async () => {
    const projects = [
      sampleProject({
        id: 'markpad',
        name: 'markpad',
        lifecycle_stage: 'development',
        lifecycle_status: 'running',
        workflow_status: 'active',
        current_stage: 'design',
        progress: 0.66,
        stage_counts: { completed: 2, running: 1 },
        description: 'Markdown 编辑器',
      }),
      sampleProject({
        id: 'P-1',
        name: 'ledger-app',
        lifecycle_stage: null,
        status: 'idea',
        workflow_status: null,
        progress: 0,
        stage_counts: {},
      }),
    ];
    stubFetch({ '/api/dashboard': sampleDashboard({ projects }) });

    render(<AfWorkspaceEntry route={workspaceRoute()} />);

    expect(await screen.findByText('markpad')).toBeInTheDocument();
    expect(screen.getByText('ledger-app')).toBeInTheDocument();
    // lifecycle 人话标签: lifecycle_stage → 开发; 缺失 → status (想法)
    expect(screen.getByText('开发')).toBeInTheDocument();
    expect(screen.getByText('想法')).toBeInTheDocument();
    // workflow 状态 + 当前阶段
    expect(screen.getByText('执行中')).toBeInTheDocument();
    expect(screen.getByText(/design/)).toBeInTheDocument();
    // progress 百分比
    expect(screen.getByText('66%')).toBeInTheDocument();
    // stage_counts 芯片 (STATUS_LABELS: completed→已完成, running→执行中)
    expect(screen.getByText('已完成 2')).toBeInTheDocument();
    expect(screen.getByText('执行中 1')).toBeInTheDocument();
  });

  it('品牌 Header: ◆ AI Factory + 子页标签', async () => {
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceEntry route={workspaceRoute('projects')} />);
    expect(await screen.findByTestId('af-workspace-entry')).toBeInTheDocument();
    expect(screen.getByText('AI Factory')).toBeInTheDocument();
    expect(screen.getByText('项目')).toBeInTheDocument();
  });

  it('空列表 → EmptyState (暂无项目)', async () => {
    stubFetch({ '/api/dashboard': sampleDashboard({ projects: [] }) });
    render(<AfWorkspaceEntry route={workspaceRoute()} />);
    expect(await screen.findByTestId('empty-state')).toHaveTextContent(
      '暂无项目 — 输入想法创建一个',
    );
  });

  it('API 失败 → ErrorState', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))));
    render(<AfWorkspaceEntry route={workspaceRoute()} />);
    expect(await screen.findByTestId('error-state')).toHaveTextContent('network down');
  });

  it('点击项目卡片 → 导航到 #/project/{id}', async () => {
    const user = userEvent.setup();
    stubFetch({
      '/api/dashboard': sampleDashboard({
        projects: [sampleProject({ id: 'markpad', name: 'markpad' })],
      }),
    });
    render(<AfWorkspaceEntry route={workspaceRoute()} />);
    const card = await screen.findByRole('button', { name: /markpad/ });
    await user.click(card);
    expect(window.location.hash).toBe('#/project/markpad');
  });
});
