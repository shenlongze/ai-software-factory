/**
 * src/test/af-workspace-shell.test.tsx — K9 Human Workspace 三栏壳。
 *
 * 验证 (K9 Human Workspace PRD §3):
 * - 三栏壳渲染: Header + Context 左栏 + Conversation 中栏 + Workspace 右栏
 * - 中栏 Conversation = 唯一主入口 (和公司说话)
 * - 右栏 Workspace Tab 齐全 (任务/代码/预览/Diff/证据)
 */

import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { AfWorkspaceShell } from '../components/af/AfWorkspaceShell';
import { stubFetch } from './fixtures';

function workspaceRoute(page = 'conversation') {
  return { level: 'workspace' as const, page };
}

/** 数据桩: 会话/项目/塔 集合。 */
function companyStubs() {
  return {
    '/api/projects': [],
    '/api/approvals?pending_only=true': [],
    '/api/conversations': { items: [], count: 0 },
    '/api/projects-os': { items: [], count: 0 },
    '/api/ops/overview': {
      projects: { total: 0, running: 0, waiting: 0, blocked: 0, approval: 0, failed: 0 },
      workforce: { running: 0, waiting: 0, blocked: 0, error: 0, idle: 0 },
      recent_activity: [],
      calculated_at: 'now',
    },
    '/api/sessions': { items: [], count: 0 },
  };
}

afterEach(() => {
  window.location.hash = '';
  try {
    window.localStorage.removeItem('af.sidebar.collapsed');
  } catch {
    /* 环境无 localStorage 时忽略 */
  }
});

describe('AfWorkspaceShell (K9 Human Workspace 三栏壳)', () => {
  it('渲染三栏: Header + Context 左栏 + Conversation 中栏 + Workspace 右栏', async () => {
    stubFetch(companyStubs());
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(screen.getByTestId('af-workspace-entry')).toBeInTheDocument();
    expect(screen.getByTestId('af-header')).toBeInTheDocument();
    expect(screen.getByTestId('af-context-nav')).toBeInTheDocument();
    expect(screen.getByTestId('af-conv-center')).toBeInTheDocument();
    expect(screen.getByTestId('af-workspace')).toBeInTheDocument();
  });

  it('中栏 Conversation = 唯一主入口 (引导式对话)', async () => {
    stubFetch(companyStubs());
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(await screen.findByText(/你今天想做什么/)).toBeInTheDocument();
  });

  it('右栏 Workspace Tab 齐全 (任务/代码/预览/Diff/证据)', async () => {
    stubFetch(companyStubs());
    render(<AfWorkspaceShell route={workspaceRoute()} />);
    expect(screen.getByRole('tab', { name: /任务/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /代码/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /预览/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Diff/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /证据/ })).toBeInTheDocument();
  });
});
