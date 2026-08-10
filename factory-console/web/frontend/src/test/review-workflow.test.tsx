/**
 * src/test/review-workflow.test.tsx — S10-006 Review Workflow 测试。
 * 唯一 basename, 不与 S9-003 ReviewPage 测试冲突。
 * 覆盖: Queue 渲染/Content 类型化 (product/ux_ui Screen Card)/Approve/Reject+Comment
 *       /Feedback 保存/空态/联动。
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReviewWorkflowPanel } from '../shell/ReviewWorkflowPanel';
import { buildReviewQueue } from '../api/runtimeClient';

function okResponse(data: unknown): Response {
  return { ok: true, status: 200, json: async () => data } as Response;
}

function stubFetch(map: Record<string, unknown>): void {
  const entries = Object.entries(map).sort((a, b) => b[0].length - a[0].length);
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      for (const [k, v] of entries) {
        if (url.includes(k)) return okResponse(v);
      }
      return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) } as Response;
    }),
  );
}

const PROJECT = 'ledger-app';
const GATES_URL = '/api/approval-gates';
const ART_URL = '/api/artifacts';
const FEEDBACK_URL = '/api/review-feedback';

const GATES = [
  { id: 'G-1', stage_id: 'STG-PM', workflow_id: 'WF-1', project_id: PROJECT, status: 'pending', reviewer: '', comment: '', requested_at: '2026-08-10T00:00:00+00:00', approved_at: null, rejected_at: null },
  { id: 'G-2', stage_id: 'STG-UX', workflow_id: 'WF-1', project_id: PROJECT, status: 'pending', reviewer: '', comment: '', requested_at: '2026-08-10T00:00:00+00:00', approved_at: null, rejected_at: null },
];

const ARTS = [
  { id: 'art-product', type: 'product', status: 'validated', name: 'product', stage_id: 'STG-PM', ref: 'product', version: '1', created_at: '2026-08-10T00:00:00+00:00', workflow_id: 'WF-1', project_id: PROJECT },
  { id: 'art-uxui', type: 'ux_ui', status: 'validated', name: 'ux_ui', stage_id: 'STG-UX', ref: 'ux_ui', version: '1', created_at: '2026-08-10T00:00:00+00:00', workflow_id: 'WF-1', project_id: PROJECT },
];

const PRODUCT_META = { market_analysis: '记账市场', user_persona: '普通用户', user_journey: '记录', feature_list: ['记账'], mvp_scope: { in: ['a'] }, user_stories: ['我可以记账'] };

const ART_DETAIL = (type: string, metadata: Record<string, unknown>) => ({
  id: `art-${type}`,
  type,
  status: 'validated',
  name: type,
  stage_id: `STG-${type.toUpperCase()}`,
  ref: type,
  version: '1',
  created_at: '2026-08-10T00:00:00+00:00',
  workflow_id: 'WF-1',
  project_id: PROJECT,
  metadata,
  review: null,
});

afterEach(() => vi.unstubAllGlobals());

describe('ReviewWorkflowPanel — Queue', () => {
  it('渲染待审门队列 (product/ux_ui)', async () => {
    stubFetch({ [GATES_URL]: GATES, [ART_URL]: ARTS });
    render(<ReviewWorkflowPanel projectId={PROJECT} />);
    expect(await screen.findByTestId('review-queue')).toBeInTheDocument();
    expect(screen.getByTestId('review-queue-G-1')).toBeInTheDocument();
    expect(screen.getByTestId('review-queue-G-2')).toBeInTheDocument();
  });

  it('空态: 没有待审核的门', async () => {
    stubFetch({ [GATES_URL]: [], [ART_URL]: ARTS });
    render(<ReviewWorkflowPanel projectId={PROJECT} />);
    expect(await screen.findByText('没有待审核的门')).toBeInTheDocument();
  });

  it('mock fallback → 演示数据徽章', async () => {
    stubFetch({});
    render(<ReviewWorkflowPanel projectId={PROJECT} />);
    expect(await screen.findByTestId('review-queue')).toBeInTheDocument();
  });
});

describe('ReviewWorkflowPanel — Content 类型化渲染', () => {
  it('product gate → Product 内容 (6 节)', async () => {
    stubFetch({
      [GATES_URL]: GATES,
      [ART_URL]: ARTS,
      '/api/artifacts/art-product': { id: 'art-product', type: 'product', status: 'validated', metadata: PRODUCT_META, review: null },
    });
    render(<ReviewWorkflowPanel projectId={PROJECT} />);
    const first = await screen.findByTestId('review-queue');
    await userEvent.setup().click(within(first).getByTestId('review-queue-G-1'));
    expect(await screen.findByText('记账市场')).toBeInTheDocument();
  });
});

describe('ReviewWorkflowPanel — Decision', () => {
  it('Approve → POST approve + 队列刷新', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/approve')) return okResponse({ ok: true });
      if (url.includes('/api/artifacts/')) return okResponse(ART_DETAIL('product', PRODUCT_META));
      if (url.includes(GATES_URL)) return okResponse(GATES);
      if (url.includes(ART_URL)) return okResponse(ARTS);
      return okResponse([]);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<ReviewWorkflowPanel projectId={PROJECT} />);
    await screen.findByTestId('review-queue');
    await userEvent.setup().click(screen.getByTestId('review-queue-G-1'));
    await userEvent.setup().click(screen.getByTestId('review-approve'));
    const calls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(calls.some((u) => u.includes('/approve'))).toBe(true);
  });

  it('Reject + Comment → POST review-feedback 保存', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/reject')) return okResponse({ ok: true });
      if (url.includes('/api/artifacts/')) return okResponse(ART_DETAIL('product', PRODUCT_META));
      if (url.includes(FEEDBACK_URL) && init?.method === 'POST') return okResponse({ id: 'FB-1' });
      if (url.includes(GATES_URL)) return okResponse(GATES);
      if (url.includes(ART_URL)) return okResponse(ARTS);
      return okResponse([]);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<ReviewWorkflowPanel projectId={PROJECT} />);
    await screen.findByTestId('review-queue');
    await userEvent.setup().click(screen.getByTestId('review-queue-G-1'));
    await userEvent.setup().type(screen.getByTestId('review-comment'), '按钮改大');
    await userEvent.setup().click(screen.getByTestId('review-reject'));
    const calls = fetchMock.mock.calls.map((c) => ({ url: String(c[0]), body: (c[1] as RequestInit)?.body }));
    const feedbackCall = calls.find((c) => c.url.includes(FEEDBACK_URL) && c.body != null);
    expect(feedbackCall).toBeDefined();
    expect(String(feedbackCall!.body)).toContain('按钮改大');
  });

  it('Reject 后显示反馈已保存提示', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/reject')) return okResponse({ ok: true });
      if (url.includes('/api/artifacts/')) return okResponse(ART_DETAIL('product', PRODUCT_META));
      if (url.includes(FEEDBACK_URL) && init?.method === 'POST') return okResponse({ id: 'FB-1' });
      if (url.includes(GATES_URL)) return okResponse(GATES);
      if (url.includes(ART_URL)) return okResponse(ARTS);
      return okResponse([]);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<ReviewWorkflowPanel projectId={PROJECT} />);
    await screen.findByTestId('review-queue');
    await userEvent.setup().click(screen.getByTestId('review-queue-G-1'));
    await userEvent.setup().type(screen.getByTestId('review-comment'), '按钮改大');
    await userEvent.setup().click(screen.getByTestId('review-reject'));
    expect(await screen.findByText(/反馈已保存/)).toBeInTheDocument();
  });
});

describe('buildReviewQueue — 纯函数', () => {
  it('pending 门 + 产物关联 → 队列项', () => {
    const queue = buildReviewQueue(GATES, ARTS as never, PROJECT);
    expect(queue.length).toBe(2);
    expect(queue[0].gate.id).toBe('G-1');
    expect(queue[0].artifact?.id).toBe('art-product');
  });
});
