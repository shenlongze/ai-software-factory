/**
 * src/test/router-app.test.tsx — App.tsx 挂载 AI Factory 路由入口 (S10-014 Task 002)。
 *
 * 验证:
 * - 空 hash → Human Console 保留 (品牌 + 导航, 不破坏)
 * - #/workspace/<subpage> 与 #/project/:id/... → AI Factory 入口 (独立层)
 * - #/workspace?project=id 直链 → AI Factory 项目入口 (parseHash 兼容)
 * - #/workspace 精确 → 保留 S10-001 Workspace Shell (console 工作台)
 */

import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import App from '../App';
import { sampleDashboard, stubFetch } from './fixtures';

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

describe('AI Factory 路由入口挂载 (App.tsx)', () => {
  it('空 hash → Human Console 保留 (品牌 + 导航)', () => {
    stubConsoleApis();
    render(<App />);
    expect(screen.getByText('AI Software Factory')).toBeInTheDocument();
    expect(screen.getByText('Human Console')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '项目' })).toBeInTheDocument();
  });

  it('#/workspace/projects → AI Factory 入口 (workspace 级)', () => {
    stubConsoleApis();
    window.location.hash = '#/workspace/projects';
    render(<App />);
    expect(screen.getByTestId('af-entry')).toBeInTheDocument();
    expect(screen.getByTestId('af-route-level')).toHaveTextContent('workspace');
    expect(screen.getByTestId('af-route-page')).toHaveTextContent('projects');
    expect(screen.queryByText('Human Console')).toBeNull();
  });

  it('#/project/markpad/todo → AI Factory 入口 (project 级 + projectId)', () => {
    stubConsoleApis();
    window.location.hash = '#/project/markpad/todo';
    render(<App />);
    expect(screen.getByTestId('af-entry')).toBeInTheDocument();
    expect(screen.getByTestId('af-route-level')).toHaveTextContent('project');
    expect(screen.getByTestId('af-route-page')).toHaveTextContent('todo');
    expect(screen.getByTestId('af-route-project')).toHaveTextContent('markpad');
  });

  it('#/workspace?project=ledger-app 直链 → AI Factory 项目入口 (S10-003 兼容)', () => {
    stubConsoleApis();
    window.location.hash = '#/workspace?project=ledger-app';
    render(<App />);
    expect(screen.getByTestId('af-entry')).toBeInTheDocument();
    expect(screen.getByTestId('af-route-level')).toHaveTextContent('project');
    expect(screen.getByTestId('af-route-page')).toHaveTextContent('overview');
    expect(screen.getByTestId('af-route-project')).toHaveTextContent('ledger-app');
  });

  it('#/workspace 精确 → 保留 S10-001 Workspace Shell (Human Console 工作台)', async () => {
    stubConsoleApis();
    stubFetch({
      '/api/projects': [
        { id: 'ledger-app', name: '记账 App', status: 'active', description: 'mock 项目' },
      ],
    });
    window.location.hash = '#/workspace';
    render(<App />);
    expect(await screen.findByTestId('ws-shell')).toBeInTheDocument();
    expect(screen.getByTestId('ws-header')).toBeInTheDocument();
  });
});
