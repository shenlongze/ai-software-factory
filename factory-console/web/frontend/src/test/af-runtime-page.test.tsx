/**
 * src/test/af-runtime-page.test.tsx — AfRuntimePage (S10-015 Task 005b)。
 *
 * 验证 (用户 Task 005 设计约束 — 禁止 mock 冒充/前端自行生成状态):
 * - 真实数据流: GET /api/projects/{id}/workflow + GET /api/projects/{id}/timeline
 *   并行 (Promise.all, 真实后端 fetch + ApiError 语义) → toWorkflowPipeline +
 *   toRuntimeActivity → AfRuntimeTimeline
 * - 四态: Loading (AfLoadingState) / Success (Runtime Timeline) / Empty
 *   (AfEmptyState) / Error (AfErrorState + [重试] 重新拉取)
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { AfRuntimePage } from '../pages/project/AfRuntimePage';
import {
  sampleFailedTimeline,
  sampleFailedWorkflow,
  stubFetch,
} from './fixtures';

/** 自定义 fetch 桩 (先失败 N 次, 后成功) — 重试路径用。 */
function fetchFailThen(routes: Record<string, unknown>, failCount = 1) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (fn.mock.calls.length - 1 < failCount) {
      return { ok: false, status: 500, json: async () => ({ detail: 'boom' }) } as Response;
    }
    if (path in routes) {
      return { ok: true, status: 200, json: async () => routes[path] } as Response;
    }
    return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) } as Response;
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const WORKFLOW_PATH = '/api/projects/demo/workflow';
const TIMELINE_PATH = '/api/projects/demo/timeline?limit=200';

describe('AfRuntimePage (Runtime 页面 — 真实 workflow+timeline 并行驱动)', () => {
  it('加载中 → AfLoadingState', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    render(<AfRuntimePage projectId="demo" projectName="ScorePocket" />);
    expect(screen.getByTestId('af-loading-state')).toBeInTheDocument();
    expect(screen.getByTestId('af-loading-state')).toHaveTextContent(/运行/);
  });

  it('成功: workflow + timeline 并行拉取 → Runtime Timeline (真实失败展示)', async () => {
    const fn = stubFetch({
      [WORKFLOW_PATH]: sampleFailedWorkflow(),
      [TIMELINE_PATH]: sampleFailedTimeline(),
    });
    render(<AfRuntimePage projectId="demo" projectName="ScorePocket" />);
    expect(await screen.findByTestId('af-runtime-timeline')).toBeInTheDocument();
    // 真实失败展示: failed_reason 全文 + 当前 Agent + 下一步
    expect(screen.getByTestId('af-runtime-failed')).toHaveTextContent(
      'DeveloperError: provider response contains no parseable patch or operations (after 1 retry)',
    );
    expect(screen.getByTestId('af-runtime-agent')).toHaveTextContent('开发工程师 Agent');
    expect(screen.getByTestId('af-runtime-next')).toHaveTextContent('等待 测试工程师 开始「测试」');
    // 真实事件流 4 条
    expect(screen.getAllByTestId('af-timeline-item')).toHaveLength(4);
    // 两个请求并行发出 (workflow + timeline)
    const calledPaths = fn.mock.calls.map((c) => String(c[0]));
    expect(calledPaths).toContain(WORKFLOW_PATH);
    expect(calledPaths).toContain(TIMELINE_PATH);
  });

  it('空 (workflow 无 stages + 无事件) → AfEmptyState (四态: Empty)', async () => {
    stubFetch({
      [WORKFLOW_PATH]: sampleFailedWorkflow({ stages: [] }),
      [TIMELINE_PATH]: [],
    });
    render(<AfRuntimePage projectId="demo" projectName="ScorePocket" />);
    expect(await screen.findByTestId('af-empty-state')).toBeInTheDocument();
    expect(screen.getByText(/暂无运行活动/)).toBeInTheDocument();
  });

  it('失败 (HTTP 500) → AfErrorState + 明确文案; 点 [重试] → 重新拉取成功', async () => {
    const fn = fetchFailThen(
      { [WORKFLOW_PATH]: sampleFailedWorkflow(), [TIMELINE_PATH]: sampleFailedTimeline() },
      1,
    );
    const user = userEvent.setup();
    render(<AfRuntimePage projectId="demo" projectName="ScorePocket" />);
    const errorState = await screen.findByTestId('af-error-state');
    expect(errorState).toHaveTextContent(/运行状态加载失败/);
    expect(errorState).toHaveTextContent(/500/);
    await user.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByTestId('af-runtime-timeline')).toBeInTheDocument();
    expect(screen.getByTestId('af-runtime-failed')).toHaveTextContent(
      'DeveloperError: provider response contains no parseable patch or operations (after 1 retry)',
    );
    expect(fn).toHaveBeenCalledTimes(4); // 首次 2 请求 + 重试 2 请求
  });

  it('网络异常 (fetch reject) → AfErrorState + 重试按钮存在', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))));
    render(<AfRuntimePage projectId="demo" projectName="ScorePocket" />);
    const errorState = await screen.findByTestId('af-error-state');
    expect(errorState).toHaveTextContent('network down');
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
  });
});
