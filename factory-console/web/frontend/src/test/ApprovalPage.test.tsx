/**
 * src/test/ApprovalPage.test.tsx — 审批中心。
 *
 * - 清单渲染 (卡片/状态/风险/置信度/证据)
 * - pending 计数
 * - Approve / Request Change / Reject 交互 → 只读 Modal (不发起写请求)
 * - 非 pending 审批不显示操作按钮
 * - 普通模式隐藏 by 行, 专家模式显示
 * - 空态 / 错误态
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AppStateProvider } from '../state/AppState';
import { ApprovalPage } from '../pages/ApprovalPage';
import { ModeToggle } from '../components/ModeToggle';
import { sampleApproval, stubFetch } from './fixtures';

function renderApprovals(approvals = [sampleApproval()]) {
  stubFetch({ '/api/approvals': approvals });
  return render(
    <AppStateProvider>
      <ApprovalPage />
    </AppStateProvider>,
  );
}

describe('ApprovalPage', () => {
  it('渲染审批卡片与待处理计数', async () => {
    renderApprovals([sampleApproval(), sampleApproval({ id: 'req-2', status: 'approved' })]);
    expect(await screen.findByText('审批中心')).toBeInTheDocument();
    expect(screen.getByText(/个待处理请求 \(共/)).toBeInTheDocument();
    expect(screen.getAllByText('design · v3').length).toBeGreaterThan(0);
    expect(screen.getByText('门 design_gate · req-1')).toBeInTheDocument();
    expect(screen.getAllByText('3 条证据').length).toBeGreaterThan(0);
  });

  it('pending 审批显示 Approve / Request Change / Reject 按钮', async () => {
    renderApprovals();
    expect(await screen.findByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Request Change' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
  });

  it('非 pending 审批不显示操作按钮', async () => {
    renderApprovals([sampleApproval({ status: 'approved' })]);
    await screen.findByText('审批中心');
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
  });

  it('点击 Approve → 只读指引 Modal (无写请求)', async () => {
    const fetchMock = stubFetch({ '/api/approvals': [sampleApproval()] });
    const user = userEvent.setup();
    renderApprovals();
    await user.click(await screen.findByRole('button', { name: 'Approve' }));
    const dialog = screen.getByRole('dialog', { name: /Approve — design req-1/ });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText(/Human Console 只读/)).toBeInTheDocument();
    expect(screen.getByText(/不向系统写入任何状态/)).toBeInTheDocument();
    // Permission Boundary: 交互全程零写请求
    expect(fetchMock.mock.calls.every((call) => String(call[0]) === '/api/approvals')).toBe(true);
    await user.click(screen.getByRole('button', { name: '关闭' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('Request Change / Reject 同样只弹指引', async () => {
    const user = userEvent.setup();
    renderApprovals();
    await user.click(await screen.findByRole('button', { name: 'Request Change' }));
    expect(screen.getByRole('dialog', { name: /Request Change/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '关闭' }));
    await user.click(screen.getByRole('button', { name: 'Reject' }));
    expect(screen.getByRole('dialog', { name: /Reject/ })).toBeInTheDocument();
  });

  it('普通模式隐藏 by 行; 专家模式显示', async () => {
    stubFetch({ '/api/approvals': [sampleApproval()] });
    const user = userEvent.setup();
    render(
      <AppStateProvider>
        <ModeToggle />
        <ApprovalPage />
      </AppStateProvider>,
    );
    await screen.findByText('审批中心');
    expect(screen.queryByText(/by planner/)).toBeNull();
    await user.click(screen.getByRole('button', { name: '专业模式' }));
    expect(screen.getByText(/by planner/)).toBeInTheDocument();
  });

  it('有备注时渲染备注', async () => {
    renderApprovals([sampleApproval({ comment: '补充测试' })]);
    expect(await screen.findByText(/备注: 补充测试/)).toBeInTheDocument();
  });

  it('空清单 → 空态', async () => {
    renderApprovals([]);
    expect(await screen.findByText('暂无审批请求')).toBeInTheDocument();
    expect(screen.getByText(/个待处理请求/)).toBeInTheDocument();
  });

  it('API 错误 → ErrorState', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) }) as Response),
    );
    render(
      <AppStateProvider>
        <ApprovalPage />
      </AppStateProvider>,
    );
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/503/);
  });
});
