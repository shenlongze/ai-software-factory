/**
 * src/test/router-app.test.tsx — App.tsx 挂载 AI Factory 真实入口 (S10-014 Task 002b)。
 *
 * 验证:
 * - 空 hash → AI Factory 工作台 (K-7a 单入口)
 * - #/workspace (精确) 与 #/workspace/<subpage> → AI Factory 工作台 (真实项目列表)
 * - #/project/:id/... → AI Factory 项目入口 (真实 Project Entity + 子页 placeholder)
 * - #/workspace?project=id 直链 → AI Factory 项目入口 (parseHash 兼容)
 * - K-7a: 普通模式/双模式已砍, 仅 workspace/project 两级
 */

import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import App from '../App';
import { sampleDashboard, sampleProject, sampleTodoBacklog, stubFetch } from './fixtures';

function stubConsoleApis() {
  const emptyDashboard = sampleDashboard({
    projects: [],
    approvals: [],
    agents: [],
    decisions: [],
    activity: [],
  });
  stubFetch({
    '/api/dashboard': emptyDashboard,
    '/api/projects': [],
    '/api/approvals': [],
    '/api/approval-gates': [],
    '/api/workflows': [],
    '/api/artifacts': [],
    '/api/experience?limit=20': [],
    '/api/providers': [],
    '/api/recommendations?limit=20': [],
  });
}

afterEach(() => {
  window.location.hash = '';
});

describe('AI Factory 真实入口挂载 (App.tsx)', () => {
  it('空 hash → AI Factory 工作台 (K-7a 单入口, 无普通模式导航)', async () => {
    stubConsoleApis();
    render(<App />);
    expect(await screen.findByTestId('af-workspace-entry')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '普通模式' })).toBeNull();
    expect(screen.queryByRole('button', { name: '专业模式' })).toBeNull();
    expect(screen.queryByText('Human Console')).toBeNull();
  });

  it('#/workspace → AI Factory 工作台 (真实项目列表, 非占位)', async () => {
    stubConsoleApis();
    stubFetch({
      '/api/dashboard': sampleDashboard({
        projects: [sampleProject({ id: 'markpad', name: 'markpad' })],
      }),
    });
    window.location.hash = '#/workspace';
    render(<App />);
    expect(await screen.findByTestId('af-workspace-entry')).toBeInTheDocument();
    expect(await screen.findByText('markpad')).toBeInTheDocument();
    expect(screen.getByText('AI Factory')).toBeInTheDocument();
    expect(screen.queryByText('Human Console')).toBeNull();
  });

  it('#/workspace/projects → AI Factory 工作台 (workspace 子页)', async () => {
    stubConsoleApis();
    stubFetch({
      '/api/dashboard': sampleDashboard({
        projects: [sampleProject({ id: 'markpad', name: 'markpad' })],
      }),
    });
    window.location.hash = '#/workspace/projects';
    render(<App />);
    expect(await screen.findByTestId('af-workspace-entry')).toBeInTheDocument();
    expect(await screen.findByText('markpad')).toBeInTheDocument();
  });

  it('#/project/markpad/todo → AI Factory 项目入口 (Project Entity + 真实 Todo Tree)', async () => {
    stubConsoleApis();
    stubFetch({
      '/api/projects': [sampleProject({ id: 'markpad', name: 'markpad' })],
      '/api/projects/markpad/backlog': sampleTodoBacklog(),
    });
    window.location.hash = '#/project/markpad/todo';
    render(<App />);
    expect(await screen.findByTestId('af-project-entry')).toBeInTheDocument();
    expect(
      await screen.findByRole('heading', { name: 'markpad' }),
    ).toBeInTheDocument();
    expect(await screen.findByTestId('af-todo-tree')).toBeInTheDocument();
  });

  it('#/workspace?project=ledger-app 直链 → AI Factory 项目入口 (S10-003 兼容)', async () => {
    stubConsoleApis();
    stubFetch({
      '/api/projects': [sampleProject({ id: 'ledger-app', name: 'ledger-app' })],
    });
    window.location.hash = '#/workspace?project=ledger-app';
    render(<App />);
    expect(await screen.findByTestId('af-project-entry')).toBeInTheDocument();
    expect(
      await screen.findByRole('heading', { name: 'ledger-app' }),
    ).toBeInTheDocument();
  });

  it('K-7a: 普通模式已砍 — 无 ModeToggle/工作台按钮', async () => {
    stubConsoleApis();
    render(<App />);
    expect(screen.queryByRole('button', { name: '普通模式' })).toBeNull();
    expect(screen.queryByRole('button', { name: '工作台' })).toBeNull();
  });

  it('#/project/markpad (不存在项目) → ErrorState 项目不存在', async () => {
    stubConsoleApis();
    stubFetch({ '/api/projects': [] });
    window.location.hash = '#/project/ghost';
    render(<App />);
    expect(await screen.findByTestId('error-state')).toHaveTextContent(
      '项目不存在或已被删除',
    );
  });
});
