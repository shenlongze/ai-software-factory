/**
 * src/test/App.test.tsx — 应用外壳 (K-7a 单入口)。
 *
 * K-7a 砍双模式: 空 hash → AI Factory 工作台 (AfWorkspaceEntry),
 * 无普通模式导航/ModeToggle/页脚; 顶栏含开发者控制台链接。
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from '../App';
import { sampleDashboard, stubFetch } from './fixtures';

function renderApp() {
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
    '/api/conversations': { items: [], count: 0 },
    '/api/projects-os': { items: [], count: 0 },
    '/api/sessions': { items: [], count: 0 },
    '/api/ops/overview': {
      projects: { total: 0, running: 0, waiting: 0, blocked: 0, approval: 0, failed: 0 },
      workforce: { running: 0, waiting: 0, blocked: 0, error: 0, idle: 0 },
      recent_activity: [],
      calculated_at: 'now',
    },
  });
  return render(<App />);
}

describe('App Shell (K-7a 单入口)', () => {
  it('空 hash → AI Factory 工作台 (AfWorkspaceEntry), 无普通模式导航', async () => {
    window.location.hash = '';
    renderApp();
    expect(await screen.findByTestId('af-workspace-entry')).toBeInTheDocument();
    // 双模式已砍: 无普通模式 ModeToggle / Human Console 品牌
    expect(screen.queryByRole('button', { name: '普通模式' })).toBeNull();
    expect(screen.queryByRole('button', { name: '专业模式' })).toBeNull();
    expect(screen.queryByText('Human Console')).toBeNull();
  });

  it('左栏 Context 导航 (K9) + 开发者控制台链接', async () => {
    window.location.hash = '';
    renderApp();
    expect(await screen.findByTestId('af-context-nav')).toBeInTheDocument();
    expect(screen.getAllByText('AI Factory').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('🛠 开发者控制台')).toBeInTheDocument();
  });

  it('K9: 中栏 Conversation + 右栏 Workspace + 状态栏', async () => {
    window.location.hash = '';
    renderApp();
    expect(await screen.findByTestId('af-conv-center')).toBeInTheDocument();
    expect(await screen.findByTestId('af-workspace')).toBeInTheDocument();
    expect(screen.getByTestId('af-statusbar')).toBeInTheDocument();
  });
});
