/**
 * src/test/router-app.test.tsx — App.tsx 挂载 AI Factory 真实入口 (S10-014 Task 002b)。
 *
 * 验证:
 * - 空 hash → Human Console 保留 (品牌 + 导航, 不破坏)
 * - #/workspace (精确) 与 #/workspace/<subpage> → AI Factory 工作台 (真实项目列表)
 * - #/project/:id/... → AI Factory 项目入口 (真实 Project Entity + 子页 placeholder)
 * - #/workspace?project=id 直链 → AI Factory 项目入口 (parseHash 兼容)
 * - Console 导航"工作台" (AppState) → S10-001 Workspace Shell 保留 (双模式并存)
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import App from '../App';
import { sampleDashboard, sampleProject, stubFetch } from './fixtures';

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
  it('空 hash → Human Console 保留 (品牌 + 导航)', () => {
    stubConsoleApis();
    render(<App />);
    expect(screen.getByText('AI Software Factory')).toBeInTheDocument();
    expect(screen.getByText('Human Console')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '项目' })).toBeInTheDocument();
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

  it('#/project/markpad/todo → AI Factory 项目入口 (Project Entity + 子页 placeholder)', async () => {
    stubConsoleApis();
    stubFetch({
      '/api/projects': [sampleProject({ id: 'markpad', name: 'markpad' })],
    });
    window.location.hash = '#/project/markpad/todo';
    render(<App />);
    expect(await screen.findByTestId('af-project-entry')).toBeInTheDocument();
    expect(
      await screen.findByRole('heading', { name: 'markpad' }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText('Todo Tree module loading — 开发中'),
    ).toBeInTheDocument();
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

  it('Console 导航"工作台" → S10-001 Workspace Shell 保留 (双模式并存)', async () => {
    const user = userEvent.setup();
    stubConsoleApis();
    stubFetch({
      '/api/projects': [
        { id: 'ledger-app', name: '记账 App', status: 'active', description: 'mock 项目' },
      ],
    });
    render(<App />);
    await user.click(screen.getByRole('button', { name: '工作台' }));
    expect(await screen.findByTestId('ws-shell')).toBeInTheDocument();
    expect(screen.getByTestId('ws-header')).toBeInTheDocument();
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
