/**
 * src/test/af-workspace-entry.test.tsx — AI Factory 工作台真实入口 (K9 Human Workspace)。
 *
 * 验证 (#/workspace 渲染 K9 三栏):
 * - 左栏 Context 导航 / 中栏 Conversation / 右栏 Workspace
 * - 中栏默认提示"和公司说话"
 * - 右栏 Workspace Tab 齐全
 */

import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { AfWorkspaceEntry } from '../pages/workspace/AfWorkspaceEntry';
import { stubFetch } from './fixtures';

function workspaceRoute(page = 'conversation') {
  return { level: 'workspace' as const, page };
}

function stubs() {
  return {
    '/api/projects': [],
    '/api/approvals?pending_only=true': [],
    '/api/conversations': { items: [], count: 0 },
    '/api/projects-os': { items: [], count: 0 },
    '/api/sessions': { items: [], count: 0 },
    '/api/ops/overview': {
      projects: { total: 0, running: 0, waiting: 0, blocked: 0, approval: 0, failed: 0 },
      workforce: { running: 0, waiting: 0, blocked: 0, error: 0, idle: 0 },
      recent_activity: [],
      calculated_at: 'now',
    },
  };
}

afterEach(() => {
  window.location.hash = '';
});

describe('AfWorkspaceEntry (K9 Human Workspace 真实入口)', () => {
  it('渲染 K9 三栏: Context 左栏 + Conversation 中栏 + Workspace 右栏', async () => {
    stubFetch(stubs());
    render(<AfWorkspaceEntry route={workspaceRoute()} />);
    expect(await screen.findByTestId('af-workspace-entry')).toBeInTheDocument();
    expect(screen.getByTestId('af-context-nav')).toBeInTheDocument();
    expect(screen.getByTestId('af-conv-center')).toBeInTheDocument();
    expect(screen.getByTestId('af-workspace')).toBeInTheDocument();
  });

  it('中栏 Conversation = 默认主入口 (和公司说话)', async () => {
    stubFetch(stubs());
    render(<AfWorkspaceEntry route={workspaceRoute()} />);
    expect(await screen.findByText(/和公司说话/)).toBeInTheDocument();
  });

  it('右栏 Workspace Tab 齐全 (任务/代码/预览/Diff/证据)', async () => {
    stubFetch(stubs());
    render(<AfWorkspaceEntry route={workspaceRoute()} />);
    expect(screen.getByRole('tab', { name: /任务/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /代码/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /预览/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Diff/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /证据/ })).toBeInTheDocument();
  });
});
