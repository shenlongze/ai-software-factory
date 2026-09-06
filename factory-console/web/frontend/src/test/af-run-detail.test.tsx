/** S47-C2 — AfRunDetail (Run/Stage/Call/Repair drill-down) 测试。

 * 纯投影: 数据来自 api.projectRunDetail (真实 progress+report)。断言渲染
 * 真实形状 (stages/repair 标记/calls usage/errors/totals); 不 mock 生产
 * 事实; 展开交互; 无 active run 状态由父层 runs 决定 (ActiveRuntimePanel
 * latest-run 入口)。
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { api } from '../api/client';
import { runtimeClient } from '../api/runtimeClient';
import { AfRunDetail } from '../components/af/AfRunDetail';
import { ActiveRuntimePanel } from '../components/af/ActiveRuntimePanel';
import type { RunDetail } from '../models/domain';

const RUN_DETAIL: RunDetail = {
  project_id: 'P-a',
  run_id: 'R-1789',
  status: 'completed',
  stages: [
    { workflow: 'WF-DESIGN', stage: 'product', role: 'product-manager', calls: [0], cost_usd_est: 0.0006, latency_s: 10.7, status: 'COMPLETED' },
    { workflow: 'WF-APP', stage: 'development', role: 'developer', calls: [1, 2], cost_usd_est: 0.01, latency_s: 80.2, status: 'COMPLETED' },
    { workflow: 'WF-APP', stage: 'repair 1', role: 'developer', calls: [3], cost_usd_est: 0.002, latency_s: 15.0, status: 'COMPLETED' },
    { workflow: 'WF-APP', stage: 'retest 1', role: 'tester', calls: [4], status: 'COMPLETED' },
  ],
  calls: [
    { model: 'deepseek-v4-pro', usage: { total_tokens: 1506 }, latency_s: 5.2, ok: true },
    { model: 'deepseek-v4-pro', usage: { total_tokens: 8000 }, latency_s: 40.1, ok: true },
    { model: 'deepseek-v4-pro', usage: { total_tokens: 900 }, latency_s: 3.0, ok: false, error: 'timeout' },
  ],
  errors: [],
  totals: { calls: 3, total_tokens: 10406, cost_usd_est: 0.0126, wall_s: 120.5 },
};

afterEach(() => vi.restoreAllMocks());

describe('AfRunDetail (drill-down projection)', () => {
  it('renders run header + totals + all stages (repair labelled)', async () => {
    vi.spyOn(api, 'projectRunDetail').mockResolvedValue(RUN_DETAIL);
    render(<AfRunDetail projectId="P-a" runId="R-1789" />);
    expect(await screen.findByTestId('af-run-detail')).toBeTruthy();
    expect(screen.getByText(/R-1789/)).toBeTruthy();
    expect(screen.getByTestId('af-run-totals').textContent).toContain('3 LLM calls');
    expect(screen.getByTestId('af-run-stages').textContent).toContain('产品设计');
    expect(screen.getByText('问题修复 (AI Repair)')).toBeTruthy(); // repair 人话
    expect(screen.getByText('复测 (Retest)')).toBeTruthy();
  });

  it('stage expand shows role/status/note details', async () => {
    vi.spyOn(api, 'projectRunDetail').mockResolvedValue({
      ...RUN_DETAIL,
      stages: [{ ...RUN_DETAIL.stages[0], note: 'artifact=art-1' }],
    });
    render(<AfRunDetail projectId="P-a" runId="R-1789" />);
    await screen.findByTestId('af-run-stages');
    fireEvent.click(screen.getByText('产品设计'));
    expect(await screen.findByText(/art-1/)).toBeTruthy();
    // 展开详情区出现 (stage 原始 id + note)
    expect(screen.getByText('product')).toBeTruthy();
  });

  it('renders calls usage metadata (no secret fields rendered)', async () => {
    vi.spyOn(api, 'projectRunDetail').mockResolvedValue(RUN_DETAIL);
    render(<AfRunDetail projectId="P-a" runId="R-1789" />);
    await screen.findByTestId('af-run-calls');
    const table = screen.getByTestId('af-run-calls').textContent ?? '';
    expect(table).toContain('deepseek-v4-pro');
    expect(table).toContain('timeout');
    expect(table).not.toContain('sk-');
    expect(table).not.toContain('api_key');
    expect(table).not.toContain('Bearer');
  });

  it('renders errors block when run failed', async () => {
    vi.spyOn(api, 'projectRunDetail').mockResolvedValue({
      ...RUN_DETAIL,
      status: 'failed',
      errors: [{ where: 'dev/development', message: 'no parseable patch' }],
    });
    render(<AfRunDetail projectId="P-a" runId="R-1789" />);
    expect(await screen.findByTestId('af-run-errors')).toBeTruthy();
    expect(screen.getByText(/no parseable patch/)).toBeTruthy();
  });

  it('backend error → real error, no fake data', async () => {
    vi.spyOn(api, 'projectRunDetail').mockRejectedValue(new Error('404: Run 不存在'));
    render(<AfRunDetail projectId="P-a" runId="NOPE" />);
    expect(await screen.findByRole('alert')).toBeTruthy();
  });

  it('close button calls onClose', async () => {
    vi.spyOn(api, 'projectRunDetail').mockResolvedValue(RUN_DETAIL);
    const onClose = vi.fn();
    render(<AfRunDetail projectId="P-a" runId="R-1789" onClose={onClose} />);
    await screen.findByText(/R-1789/);
    fireEvent.click(screen.getByText('关闭'));
    expect(onClose).toHaveBeenCalled();
  });
});

describe('ActiveRuntimePanel latest-run entry (no active run)', () => {
  it('no running run → latest completed run shown with detail entry', async () => {
    vi.spyOn(runtimeClient, 'subscribeEvents').mockReturnValue({
      close: vi.fn(), isMock: () => false,
    } as never);
    const onSelect = vi.fn();
    render(
      <ActiveRuntimePanel
        projectId="P-a"
        runs={[{ run_id: 'R-1', status: 'completed' }]}
        onSelectRun={onSelect}
      />,
    );
    expect(await screen.findByTestId('af-latest-run-id')).toBeTruthy();
    fireEvent.click(screen.getByTestId('af-open-latest-detail'));
    expect(onSelect).toHaveBeenCalledWith('R-1');
  });
});
