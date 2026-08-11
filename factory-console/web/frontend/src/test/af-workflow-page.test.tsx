/**
 * src/test/af-workflow-page.test.tsx — AfWorkflowPage (S10-015 Task 004)。
 *
 * 验证 (用户 Task 004 设计约束):
 * - 真实数据流: GET /api/projects/{id}/workflow + GET /api/projects/{id}/timeline
 *   并行 (Promise.all) → toWorkflowPipeline + toRuntimeActivity → AfWorkflowViewer
 *   (禁止 mock 冒充: 页面数据必须来自真实后端桩)
 * - 四态: Loading (AfLoadingState) / Success (Viewer) / Empty (AfEmptyState) /
 *   Error (AfErrorState + [重试] 重新拉取)
 * - is_mock=true 透传 → Viewer 显示演示数据警告 (降级不冒充)
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { AfWorkflowPage } from '../pages/project/AfWorkflowPage';
import {
  sampleWorkflowInstance,
  sampleWorkflowInstanceMock,
  sampleWorkflowTimeline,
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

describe('AfWorkflowPage (Workflow 页面 — 真实 workflow+timeline 驱动)', () => {
  it('加载中 → AfLoadingState', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    render(<AfWorkflowPage projectId="demo" projectName="演示项目" />);
    expect(screen.getByTestId('af-loading-state')).toBeInTheDocument();
    expect(screen.getByTestId('af-loading-state')).toHaveTextContent('流程');
  });

  it('成功: workflow + timeline 并行拉取 → toWorkflowPipeline → Viewer 渲染 (真实数据流)', async () => {
    const fn = stubFetch({
      [WORKFLOW_PATH]: sampleWorkflowInstance(),
      [TIMELINE_PATH]: sampleWorkflowTimeline(),
    });
    render(<AfWorkflowPage projectId="demo" projectName="演示项目" />);
    expect(await screen.findByTestId('af-workflow-viewer')).toBeInTheDocument();
    // 真实实例内容: 人话 Agent 名 + 状态 + timeline 历史
    expect(screen.getByText('产品经理 Agent')).toBeInTheDocument();
    expect(screen.getByText('UI 设计师 Agent')).toBeInTheDocument();
    expect(screen.getAllByText('执行中').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('阻塞: 等待前置阶段完成: UI 设计师')).toBeInTheDocument();
    expect(screen.getAllByTestId('af-timeline-item')).toHaveLength(7);
    // 两个请求并行发出 (workflow + timeline)
    const calledPaths = fn.mock.calls.map((c) => String(c[0]));
    expect(calledPaths).toContain(WORKFLOW_PATH);
    expect(calledPaths).toContain(TIMELINE_PATH);
    // 非 mock: 无演示警告
    expect(screen.queryByTestId('af-wf-mock-badge')).not.toBeInTheDocument();
  });

  it('is_mock=true workflow → Viewer 渲染 + 演示数据警告 (降级不冒充)', async () => {
    stubFetch({
      [WORKFLOW_PATH]: sampleWorkflowInstanceMock(),
      [TIMELINE_PATH]: sampleWorkflowTimeline(),
    });
    render(<AfWorkflowPage projectId="demo" projectName="演示项目" />);
    expect(await screen.findByTestId('af-wf-mock-badge')).toHaveTextContent('演示数据');
    expect(screen.getByText('发布工程师 Agent')).toBeInTheDocument();
  });

  it('空 (stages=[]) → AfEmptyState (四态: Empty)', async () => {
    stubFetch({
      [WORKFLOW_PATH]: sampleWorkflowInstance({ stages: [] }),
      [TIMELINE_PATH]: [],
    });
    render(<AfWorkflowPage projectId="demo" projectName="演示项目" />);
    expect(await screen.findByTestId('af-empty-state')).toBeInTheDocument();
    expect(screen.getByText('暂无流程运行')).toBeInTheDocument();
  });

  it('失败 (HTTP 500) → AfErrorState + 明确文案; 点 [重试] → 重新拉取成功', async () => {
    const fn = fetchFailThen(
      { [WORKFLOW_PATH]: sampleWorkflowInstance(), [TIMELINE_PATH]: sampleWorkflowTimeline() },
      1,
    );
    const user = userEvent.setup();
    render(<AfWorkflowPage projectId="demo" projectName="演示项目" />);
    const errorState = await screen.findByTestId('af-error-state');
    expect(errorState).toHaveTextContent(/流程加载失败/);
    expect(errorState).toHaveTextContent(/500/);
    await user.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByTestId('af-workflow-viewer')).toBeInTheDocument();
    expect(screen.getByText('产品经理 Agent')).toBeInTheDocument();
    expect(fn).toHaveBeenCalledTimes(4); // 首次 2 请求 + 重试 2 请求
  });

  it('网络异常 (fetch reject) → AfErrorState + 重试按钮存在', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))));
    render(<AfWorkflowPage projectId="demo" projectName="演示项目" />);
    const errorState = await screen.findByTestId('af-error-state');
    expect(errorState).toHaveTextContent('network down');
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
  });
});
