/** S47-B — Review 控制面 (Acceptance/Release/Delivery) 前端测试。

 * 规则: 组件是纯投影 — 全部经 api client (backend canonical); 测试用
 * mock api (vitest spy) 返回真实形状; 断言 UI 渲染 backend truth; 按钮
 * 失败 → 保持状态 + 显示错误; 无本地 truth。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { api } from '../api/client';
import { AfReviewPage } from '../pages/project/AfReviewPage';
import type { AcceptanceReview, ReleaseTruth } from '../models/domain';

const ACC_PENDING: AcceptanceReview = {
  acceptance_id: 'ACC-pend1', project_id: 'P-a', artifact_id: 'art-x',
  version: 1, verification_id: 'ver-1', source_run_id: 'run-1',
  status: 'PENDING', verification_status: 'PASS',
};
const ACC_APPROVED: AcceptanceReview = { ...ACC_PENDING, acceptance_id: 'ACC-appr1', status: 'APPROVED', decision: { decision: 'APPROVED', comment: '可以', at: 't' } };
const REL_GATED: ReleaseTruth = {
  release_id: 'RELEASE-r1', status: 'GATED', task_run_id: 'run-1',
  artifact_ids: ['art-x'], verification_ids: ['ver-1'],
  gate: { allowed: true, missing: [] },
};
const REL_RELEASED: ReleaseTruth = { ...REL_GATED, status: 'RELEASED' };

describe('AfReviewPage (acceptance/release projection)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders PENDING acceptance with Approve + Request Changes', async () => {
    vi.spyOn(api, 'projectAcceptances').mockResolvedValue([ACC_PENDING]);
    vi.spyOn(api, 'releasesTruth').mockResolvedValue([]);
    render(<AfReviewPage projectId="P-a" />);
    expect(await screen.findByText(/Pending Review/)).toBeTruthy();
    expect(screen.getByTestId('approve-ACC-pend1')).toBeTruthy();
  });

  it('approve calls canonical API and refreshes to APPROVED', async () => {
    vi.spyOn(api, 'projectAcceptances')
      .mockResolvedValueOnce([ACC_PENDING])
      .mockResolvedValueOnce([ACC_APPROVED]);
    vi.spyOn(api, 'releasesTruth').mockResolvedValue([]);
    const approve = vi.spyOn(api, 'approveAcceptance').mockResolvedValue(ACC_APPROVED);
    render(<AfReviewPage projectId="P-a" />);
    await screen.findByText(/Pending Review/);
    fireEvent.click(screen.getByTestId('approve-ACC-pend1'));
    await waitFor(() => expect(approve).toHaveBeenCalledWith('ACC-pend1'));
    expect(await screen.findByText(/Approved/)).toBeTruthy();
  });

  it('approve failure keeps state and shows real error', async () => {
    vi.spyOn(api, 'projectAcceptances').mockResolvedValue([ACC_PENDING]);
    vi.spyOn(api, 'releasesTruth').mockResolvedValue([]);
    vi.spyOn(api, 'approveAcceptance').mockRejectedValue(new Error('ver FAIL — cannot approve'));
    render(<AfReviewPage projectId="P-a" />);
    await screen.findByText(/Pending Review/);
    fireEvent.click(screen.getByTestId('approve-ACC-pend1'));
    expect(await screen.findByText(/ver FAIL/)).toBeTruthy();
    expect(screen.getByText(/Pending Review/)).toBeTruthy(); // 未变 APPROVED
  });

  it('request change posts comment via canonical API', async () => {
    vi.spyOn(api, 'projectAcceptances')
      .mockResolvedValueOnce([ACC_APPROVED])
      .mockResolvedValueOnce([{ ...ACC_APPROVED, status: 'CHANGE_REQUESTED' }]);
    vi.spyOn(api, 'releasesTruth').mockResolvedValue([]);
    const rc = vi.spyOn(api, 'requestAcceptanceChange').mockResolvedValue(
      { ...ACC_APPROVED, status: 'CHANGE_REQUESTED' });
    render(<AfReviewPage projectId="P-a" />);
    await screen.findByText(/Approved/);
    fireEvent.click(screen.getByTestId('request-change-ACC-appr1'));
    fireEvent.change(screen.getByTestId('change-input-ACC-appr1'), { target: { value: '改深色' } });
    fireEvent.click(screen.getByText(/Submit Change Request/));
    await waitFor(() => expect(rc).toHaveBeenCalledWith('ACC-appr1', '改深色'));
    expect(await screen.findByText(/Change Requested/)).toBeTruthy();
  });

  it('renders release card with gate + Release action; executed → Delivered', async () => {
    vi.spyOn(api, 'projectAcceptances').mockResolvedValue([ACC_APPROVED]);
    vi.spyOn(api, 'releasesTruth')
      .mockResolvedValueOnce([REL_GATED])
      .mockResolvedValueOnce([REL_RELEASED]);
    const ex = vi.spyOn(api, 'executeRelease').mockResolvedValue({ release: REL_RELEASED });
    render(<AfReviewPage projectId="P-a" />);
    expect(await screen.findByText('RELEASE-r1')).toBeTruthy();
    fireEvent.click(screen.getByTestId('release-RELEASE-r1'));
    await waitFor(() => expect(ex).toHaveBeenCalledWith('RELEASE-r1'));
    expect(await screen.findByText(/Delivered/)).toBeTruthy();
  });

  it('release backend error surfaces real message (no fake released)', async () => {
    vi.spyOn(api, 'projectAcceptances').mockResolvedValue([ACC_APPROVED]);
    vi.spyOn(api, 'releasesTruth').mockResolvedValue([REL_GATED]);
    vi.spyOn(api, 'executeRelease').mockRejectedValue(new Error('gate failed: evidence_missing'));
    render(<AfReviewPage projectId="P-a" />);
    await screen.findByText('RELEASE-r1');
    fireEvent.click(screen.getByTestId('release-RELEASE-r1'));
    expect(await screen.findByText(/gate failed/)).toBeTruthy();
    expect(screen.queryByText(/Delivered/)).toBeNull();
  });

  it('project isolation: releases joined by this project run only', async () => {
    const otherRel = { ...REL_RELEASED, release_id: 'RELEASE-other', task_run_id: 'run-OTHER' };
    vi.spyOn(api, 'projectAcceptances').mockResolvedValue([ACC_APPROVED]); // run-1
    vi.spyOn(api, 'releasesTruth').mockResolvedValue([REL_RELEASED, otherRel]);
    render(<AfReviewPage projectId="P-a" />);
    await waitFor(() => {
      expect(screen.queryByText('RELEASE-other')).toBeNull();
      expect(screen.queryByTestId('rel-RELEASE-r1')).toBeTruthy();
    });
  });

  it('empty state renders no acceptance and no release', async () => {
    vi.spyOn(api, 'projectAcceptances').mockResolvedValue([]);
    vi.spyOn(api, 'releasesTruth').mockResolvedValue([]);
    render(<AfReviewPage projectId="P-empty" />);
    expect(await screen.findByText(/还没有可验收的产物/)).toBeTruthy();
  });
});
