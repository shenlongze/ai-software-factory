/**
 * src/test/run-status-bar.test.tsx — S10-007 阶段三 RunStatusBar 测试。
 * 唯一 basename。覆盖: 开始开发按钮 (none)/点击 POST start/轮询状态条
 * (running 进度/完成 totals/失败+重试)/503 key 缺失引导。
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RunStatusBar } from '../shell/RunStatusBar';

function okResponse(data: unknown): Response {
  return { ok: true, status: 200, json: async () => data } as Response;
}

const PROJECT = 'ledger-app';

function stubFetch(map: Record<string, unknown>): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      for (const [k, v] of Object.entries(map).sort((a, b) => b[0].length - a[0].length)) {
        if (url.includes(k)) return okResponse(v);
      }
      return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) } as Response;
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('RunStatusBar — 开始开发按钮 (none)', () => {
  it('run-status none → 显示 🚀 开始开发按钮', async () => {
    stubFetch({ [`/api/projects/${PROJECT}/run-status`]: { status: 'none', runs: [] } });
    render(<RunStatusBar projectId={PROJECT} />);
    expect(await screen.findByTestId('ws-start-dev')).toBeInTheDocument();
    expect(screen.getByText(/开始开发/)).toBeInTheDocument();
  });

  it('点击开始开发 → POST /start', async () => {
    let startCalled = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/start')) {
        startCalled = true;
        return okResponse({ status: 'started', run_id: 'R1' });
      }
      // 初始 run-status → none (显示开始开发按钮); start 后 → running
      return okResponse(
        startCalled
          ? { status: 'running', runs: [{ run_id: 'R1', status: 'running', stages: [], totals: {} }] }
          : { status: 'none', runs: [] },
      );
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<RunStatusBar projectId={PROJECT} />);
    await screen.findByTestId('ws-start-dev');
    await userEvent.setup().click(screen.getByTestId('ws-start-dev'));
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(calls.some((u) => u.includes('/start'))).toBe(true);
    });
  });

  it('503 (key 缺失) → 引导文案', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/start')) {
        return { ok: false, status: 503, json: async () => ({ detail: 'LLM API key unavailable' }) } as Response;
      }
      return okResponse({ status: 'none', runs: [] });
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<RunStatusBar projectId={PROJECT} />);
    await screen.findByTestId('ws-start-dev');
    await userEvent.setup().click(screen.getByTestId('ws-start-dev'));
    expect(await screen.findByText(/LLM API Key/)).toBeInTheDocument();
  });
});

describe('RunStatusBar — 运行状态条', () => {
  it('running → 显示开发中 + 阶段进度', async () => {
    stubFetch({
      [`/api/projects/${PROJECT}/run-status`]: {
        status: 'running',
        runs: [
          {
            run_id: 'R1',
            status: 'running',
            stages: [
              { stage: 'product', status: 'COMPLETED' },
              { stage: 'ux_ui', status: 'RUNNING' },
            ],
            totals: { calls: 1 },
          },
        ],
      },
    });
    render(<RunStatusBar projectId={PROJECT} />);
    expect(await screen.findByText(/开发中/)).toBeInTheDocument();
    expect(screen.getByText(/ux_ui/)).toBeInTheDocument();
  });

  it('completed → 显示完成 + totals', async () => {
    stubFetch({
      [`/api/projects/${PROJECT}/run-status`]: {
        status: 'completed',
        runs: [
          {
            run_id: 'R1',
            status: 'completed',
            stages: [{ stage: 'release', status: 'COMPLETED' }],
            totals: { calls: 7, total_tokens: 69728, cost_usd_est: 0.026 },
          },
        ],
      },
    });
    render(<RunStatusBar projectId={PROJECT} />);
    expect(await screen.findByText(/完成/)).toBeInTheDocument();
    expect(screen.getByText(/7/)).toBeInTheDocument();
  });

  it('failed → 显示失败原因 + 重试按钮', async () => {
    stubFetch({
      [`/api/projects/${PROJECT}/run-status`]: {
        status: 'failed',
        runs: [
          {
            run_id: 'R1',
            status: 'failed',
            stages: [],
            totals: {},
            errors: [{ message: 'LLM 调用失败', stage: 'ux_ui' }],
          },
        ],
      },
    });
    render(<RunStatusBar projectId={PROJECT} />);
    expect(await screen.findByTestId('ws-run-status')).toHaveAttribute('data-status', 'failed');
    expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument();
  });
});
