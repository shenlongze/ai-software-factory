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

  it('左栏项目列表 (新建/搜索/分组) + 开发者控制台链接', async () => {
    window.location.hash = '';
    renderApp();
    expect(await screen.findByTestId('af-project-pane')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '＋ 新建项目' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '搜索项目' })).toBeInTheDocument();
    expect(screen.getByText('🛠 开发者控制台')).toBeInTheDocument();
  });

  it('底部 Composer 存在', async () => {
    window.location.hash = '';
    renderApp();
    expect(await screen.findByTestId('af-composer')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '对话输入' })).toBeInTheDocument();
  });
});
