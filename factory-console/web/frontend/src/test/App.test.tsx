/**
 * src/test/App.test.tsx — 应用外壳 (Shell)。
 *
 * - 品牌/导航/页脚渲染
 * - 普通模式隐藏 Providers 导航, 专业模式显示 (Expert 专属)
 * - 导航切换页面 (Dashboard 默认)
 * - Simple ↔ Expert 切换
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
    '/api/experience?limit=20': [],
    '/api/providers': [],
    '/api/recommendations?limit=20': [],
  });
  return render(<App />);
}

describe('App Shell', () => {
  it('渲染品牌与导航 (Dashboard/项目/审批/决策/智能)', async () => {
    renderApp();
    expect(screen.getByText('AI Software Factory')).toBeInTheDocument();
    expect(screen.getByText('Human Console')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '项目' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '审批' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '决策' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '智能' })).toBeInTheDocument();
  });

  it('普通模式: Providers 导航隐藏; 专业模式显示', async () => {
    const user = userEvent.setup();
    renderApp();
    expect(screen.queryByRole('button', { name: 'Providers' })).toBeNull();
    await user.click(screen.getByRole('button', { name: '专业模式' }));
    expect(screen.getByRole('button', { name: 'Providers' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '普通模式' }));
    expect(screen.queryByRole('button', { name: 'Providers' })).toBeNull();
  });

  it('默认页为 Dashboard', async () => {
    renderApp();
    expect(await screen.findByText('正在管理 0 个项目')).toBeInTheDocument();
  });

  it('导航切换页面', async () => {
    const user = userEvent.setup();
    renderApp();
    await user.click(screen.getByRole('button', { name: '项目' }));
    expect(await screen.findByText(/点击项目查看其 AI 工作区/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '审批' }));
    expect(await screen.findByText('暂无审批请求')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '决策' }));
    expect(await screen.findByText('暂无 AI 决策')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '智能' }));
    expect(await screen.findByText('暂无经验记录')).toBeInTheDocument();
  });

  it('页脚渲染只读声明', () => {
    renderApp();
    expect(screen.getByText(/只读控制台 \(执行权永远在人工一侧\)/)).toBeInTheDocument();
  });
});
