/**
 * src/test/af-todo-tree-page.test.tsx — AfTodoTreePage (S10-015 Task 003)。
 *
 * 验证 (S10-015-architecture-review §3 + 任务四态要求):
 * - 真实数据流: GET /api/projects/{id}/backlog → toTodoTree → AfTodoTree (非 mock 冒充)
 * - 四态: Loading (AfLoadingState) / Success (树) / Empty (AfEmptyState) /
 *   Error (AfErrorState + [重试] 重新拉取)
 * - 优先级标签来自真实 backlog.tasks 字段 (页面级 taskMeta 投影)
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { AfTodoTreePage } from '../pages/project/AfTodoTreePage';
import { sampleTodoBacklog, stubFetch } from './fixtures';

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

const BACKLOG_PATH = '/api/projects/demo/backlog';

describe('AfTodoTreePage (Todo Tree 页面 — 真实 backlog 驱动)', () => {
  it('加载中 → AfLoadingState', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    render(<AfTodoTreePage projectId="demo" projectName="演示项目" />);
    expect(screen.getByTestId('af-loading-state')).toBeInTheDocument();
    expect(screen.getByTestId('af-loading-state')).toHaveTextContent('任务树');
  });

  it('成功: GET /api/projects/demo/backlog → toTodoTree → 树渲染 (真实数据流)', async () => {
    const fn = stubFetch({ [BACKLOG_PATH]: sampleTodoBacklog() });
    render(<AfTodoTreePage projectId="demo" projectName="演示项目" />);
    expect(await screen.findByTestId('af-todo-tree')).toBeInTheDocument();
    // 项目头 + 真实层级
    expect(screen.getByText('演示项目')).toBeInTheDocument();
    expect(screen.getByText('开发阶段')).toBeInTheDocument();
    expect(screen.getByText('用户系统')).toBeInTheDocument();
    expect(screen.getByText('用户注册')).toBeInTheDocument();
    expect(screen.getByText('实现注册 API')).toBeInTheDocument();
    // 真实请求: 正确的 path + Accept JSON
    expect(fn).toHaveBeenCalledWith(BACKLOG_PATH, expect.objectContaining({ headers: expect.anything() }));
    // 优先级标签来自真实 backlog.tasks (P0 唯一 / P1 ×2)
    expect(screen.getByText('P0')).toBeInTheDocument();
    expect(screen.getAllByText('P1')).toHaveLength(2);
    // 6 态状态徽标 (fixture 中 todo 状态 task ×2 — 其余为 in_progress/blocked/review/done)
    expect(screen.getAllByText('待办').length).toBeGreaterThanOrEqual(2);
  });

  it('空 backlog (无 epics) → AfEmptyState "暂无任务" (四态: Empty)', async () => {
    stubFetch({
      [BACKLOG_PATH]: { project_id: 'demo', epics: [], features: [], stories: [], tasks: [] },
    });
    render(<AfTodoTreePage projectId="demo" projectName="演示项目" />);
    expect(await screen.findByTestId('af-empty-state')).toBeInTheDocument();
    expect(screen.getByText('暂无任务 — AI 正在规划')).toBeInTheDocument();
  });

  it('失败 (HTTP 500) → AfErrorState + 明确文案; 点 [重试] → 重新拉取成功', async () => {
    const fn = fetchFailThen({ [BACKLOG_PATH]: sampleTodoBacklog() }, 1);
    const user = userEvent.setup();
    render(<AfTodoTreePage projectId="demo" projectName="演示项目" />);
    const errorState = await screen.findByTestId('af-error-state');
    expect(errorState).toHaveTextContent(/任务树加载失败/);
    expect(errorState).toHaveTextContent(/500/);
    await user.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByTestId('af-todo-tree')).toBeInTheDocument();
    expect(screen.getByText('实现注册 API')).toBeInTheDocument();
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('网络异常 (fetch reject) → AfErrorState + 重试按钮存在', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))));
    render(<AfTodoTreePage projectId="demo" projectName="演示项目" />);
    const errorState = await screen.findByTestId('af-error-state');
    expect(errorState).toHaveTextContent('network down');
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
  });

  it('404 (项目不存在) → AfErrorState 含 404 文案', async () => {
    stubFetch({}); // 未注册 → 404
    render(<AfTodoTreePage projectId="ghost" projectName="幽灵项目" />);
    const errorState = await screen.findByTestId('af-error-state');
    expect(errorState).toHaveTextContent(/404/);
  });
});
