/**
 * src/test/af-project-entry.test.tsx — AI Factory 项目入口 (S10-014 Task 002b)。
 *
 * 验证 (#/project/:id[/subpage] 读取真实 Project Entity, GET /api/projects):
 * - 加载: LoadingState
 * - 成功: name / lifecycle / status / 时间 (last_activity 或 workflow created_at) /
 *         description / workflow 状态
 * - 404 (项目不在列表): ErrorState "项目不存在或已被删除"
 * - API 失败: ErrorState
 * - 子页未实现 → 明确 placeholder ("{Page} module loading — 开发中", 禁空白)
 */

import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { AfProjectEntry } from '../pages/project/AfProjectEntry';
import { sampleProject, sampleTodoBacklog, sampleWorkflowDetail, stubFetch } from './fixtures';

function projectRoute(page = 'overview') {
  return { level: 'project' as const, page, projectId: 'demo' };
}

afterEach(() => {
  window.location.hash = '';
});

describe('AfProjectEntry (AI Factory 项目真实入口)', () => {
  it('加载中 → LoadingState', () => {
    let resolveFetch: (r: Response) => void = () => {};
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            resolveFetch = resolve;
          }),
      ),
    );
    render(<AfProjectEntry route={projectRoute()} />);
    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
    void resolveFetch;
  });

  it('成功: 渲染 Project Entity (name/lifecycle/status/description/workflow/时间)', async () => {
    stubFetch({
      '/api/projects': [
        sampleProject({
          id: 'demo',
          name: '记账 App',
          description: '个人记账工具',
          lifecycle_stage: 'discovery',
          status: 'active',
          workflow_status: 'active',
          current_stage: 'product',
          current_stage_status: 'running',
          progress: 0.5,
          last_activity: '2026-08-06T00:00:00Z',
        }),
      ],
    });

    render(<AfProjectEntry route={projectRoute()} />);

    // K-7b: overview = 项目首页 (af-project-home: 生命周期 + Todo + 运维)
    const home = await screen.findByTestId('af-project-home');
    expect(within(home).getByRole('heading', { name: '记账 App' })).toBeInTheDocument();
    expect(within(home).getByTestId('af-home-lifecycle')).toBeInTheDocument();
    expect(within(home).getByTestId('af-todo-list')).toBeInTheDocument();
  });

  it('404: 项目不存在 → ErrorState "项目不存在或已被删除"', async () => {
    stubFetch({ '/api/projects': [sampleProject({ id: 'other' })] });
    render(<AfProjectEntry route={projectRoute()} />);
    expect(await screen.findByTestId('error-state')).toHaveTextContent(
      '项目不存在或已被删除',
    );
  });

  it('API 失败 → ErrorState', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('boom'))));
    render(<AfProjectEntry route={projectRoute()} />);
    expect(await screen.findByTestId('error-state')).toHaveTextContent('boom');
  });

  it('子页 todo → 真实 Todo Tree (AfTodoTreePage, 真实 backlog 驱动)', async () => {
    stubFetch({
      '/api/projects': [sampleProject({ id: 'demo' })],
      '/api/projects/demo/backlog': sampleTodoBacklog(),
    });
    render(<AfProjectEntry route={projectRoute('todo')} />);
    expect(await screen.findByTestId('af-todo-tree')).toBeInTheDocument();
  });

  it('子页 placeholder: 其他子页 → "{Page} module loading — 开发中"', async () => {
    stubFetch({ '/api/projects': [sampleProject({ id: 'demo' })] });
    render(<AfProjectEntry route={projectRoute('sprint')} />);
    expect(
      await screen.findByText('Sprint module loading — 开发中'),
    ).toBeInTheDocument();
  });

  it('工作流时间: 项目首页渲染 (K-7b overview → af-project-home)', async () => {
    stubFetch({
      '/api/projects': [sampleProject({ id: 'demo', workflow_id: 'wf-1' })],
      '/api/projects/demo/workflow': sampleWorkflowDetail({
        created_at: '2026-08-10T09:32:45Z',
      }),
    });
    render(<AfProjectEntry route={projectRoute()} />);
    const home = await screen.findByTestId('af-project-home');
    expect(within(home).getByTestId('af-home-lifecycle')).toBeInTheDocument();
  });

  it('workflow 获取失败 → 降级不阻塞首页 (仍渲染项目名)', async () => {
    stubFetch({
      '/api/projects': [sampleProject({ id: 'demo', workflow_id: 'wf-1' })],
      // /api/projects/demo/workflow 未桩 → stubFetch 404 → 降级 null
    });
    render(<AfProjectEntry route={projectRoute()} />);
    const home = await screen.findByTestId('af-project-home');
    expect(within(home).getByRole('heading', { name: 'Demo Project' })).toBeInTheDocument();
  });
});
