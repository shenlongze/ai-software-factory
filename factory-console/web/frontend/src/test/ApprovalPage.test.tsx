/**
 * src/test/ApprovalPage.test.tsx — 审批中心 (S9-002 操作化)。
 *
 * - 组织级审批门区: 渲染 pending 门 + 待处理计数; Approve / Reject → POST
 *   (/api/approvals/{id}/approve|reject, reviewer=console) 并刷新 — Console 唯一写路径
 * - 非 pending 门不显示操作按钮
 * - Core 9c 审批区: 只读投影 (无任何操作按钮)
 * - 普通模式隐藏 by 行, 专家模式显示
 * - 空态 / 错误态 / 备注
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AppStateProvider } from '../state/AppState';
import { ApprovalPage } from '../pages/ApprovalPage';
import { ModeToggle } from '../components/ModeToggle';
import {
  sampleApproval,
  sampleApprovalDecision,
  sampleApprovalGate,
  stubFetch,
} from './fixtures';

function renderApprovals({
  gates = [sampleApprovalGate()],
  core = [sampleApproval()],
  extra = {},
}: {
  gates?: unknown[];
  core?: unknown[];
  extra?: Record<string, unknown>;
} = {}) {
  const fetchMock = stubFetch({ '/api/approval-gates': gates, '/api/approvals': core, ...extra });
  const view = render(
    <AppStateProvider>
      <ApprovalPage />
    </AppStateProvider>,
  );
  return { fetchMock, ...view };
}

describe('ApprovalPage', () => {
  it('渲染组织级门卡片与待处理计数; Core 区只读投影', async () => {
    renderApprovals({
      gates: [
        sampleApprovalGate(),
        sampleApprovalGate({ id: 'gate-2', stage_id: 'release', status: 'approved' }),
      ],
    });
    expect(await screen.findByText('审批中心')).toBeInTheDocument();
    expect(screen.getByText(/当前 1 个待处理门 \(共 2 个\)/)).toBeInTheDocument();
    expect(screen.getByText('门 design')).toBeInTheDocument();
    expect(screen.getByText('门 release')).toBeInTheDocument();
    // Core 只读区保持既有语义
    expect(screen.getAllByText('design · v3').length).toBeGreaterThan(0);
    expect(screen.getByText('门 design_gate · req-1')).toBeInTheDocument();
    expect(screen.getAllByText('3 条证据').length).toBeGreaterThan(0);
  });

  it('pending 门显示 Approve / Reject 按钮 (Console 写路径, 无 Request Change)', async () => {
    renderApprovals();
    expect(await screen.findByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Request Change' })).toBeNull();
  });

  it('非 pending 门不显示操作按钮; Core 区无任何操作按钮', async () => {
    renderApprovals({
      gates: [sampleApprovalGate({ status: 'approved' })],
    });
    await screen.findByText('审批中心');
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
  });

  it('点击 Approve → POST /api/approvals/{id}/approve (reviewer=console) 并刷新', async () => {
    const { fetchMock } = renderApprovals({
      extra: { '/api/approvals/gate-1/approve': sampleApprovalDecision({ action: 'approved' }) },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Approve' }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
      );
      expect(post).toBeDefined();
      expect(String(post![0])).toBe('/api/approvals/gate-1/approve');
      expect(JSON.parse(String((post![1] as RequestInit).body))).toEqual({
        reviewer: 'console',
      });
    });
    // 决定成功后刷新: 门列表被重新拉取 (初始 1 次 + 刷新 1 次)
    await waitFor(() => {
      const gateGets = fetchMock.mock.calls.filter(
        (c) => String(c[0]) === '/api/approval-gates' && (c[1] as RequestInit | undefined)?.method !== 'POST',
      );
      expect(gateGets.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('点击 Reject → POST /api/approvals/{id}/reject', async () => {
    const { fetchMock } = renderApprovals({
      extra: { '/api/approvals/gate-1/reject': sampleApprovalDecision({ action: 'rejected' }) },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Reject' }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
      );
      expect(post).toBeDefined();
      expect(String(post![0])).toBe('/api/approvals/gate-1/reject');
    });
  });

  it('普通模式隐藏 by 行; 专家模式显示', async () => {
    stubFetch({
      '/api/approval-gates': [sampleApprovalGate()],
      '/api/approvals': [sampleApproval()],
    });
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

  it('有备注时渲染备注 (门 + Core)', async () => {
    renderApprovals({
      gates: [sampleApprovalGate({ comment: '设计需补充' })],
      core: [sampleApproval({ comment: '补充测试' })],
    });
    expect(await screen.findByText(/备注: 设计需补充/)).toBeInTheDocument();
    expect(screen.getByText(/备注: 补充测试/)).toBeInTheDocument();
  });

  it('空门 + 空 Core → 双空态', async () => {
    renderApprovals({ gates: [], core: [] });
    expect(await screen.findByText('暂无组织级审批门')).toBeInTheDocument();
    expect(screen.getByText('暂无 Core 审批请求')).toBeInTheDocument();
    expect(screen.getByText(/当前 0 个待处理门 \(共 0 个\)/)).toBeInTheDocument();
  });

  it('API 错误 → 门与 Core 各一 ErrorState', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) }) as Response),
    );
    render(
      <AppStateProvider>
        <ApprovalPage />
      </AppStateProvider>,
    );
    const errors = await screen.findAllByTestId('error-state');
    expect(errors.length).toBe(2);
    errors.forEach((el) => expect(el).toHaveTextContent(/503/));
  });
});
