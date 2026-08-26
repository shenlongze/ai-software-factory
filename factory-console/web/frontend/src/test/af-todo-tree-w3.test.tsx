/**
 * src/test/af-todo-tree-w3.test.tsx — W-3 (v1.1.142): Todo 编辑/优先级/归档/审计溯源。
 *
 * Founder: "todo list 一定要支持编辑, 并且有优先级, 完成的任务一定要支持归档, 审计, 溯源等"。
 * 覆盖:
 * - AfTodoTree 归档: done(completed) 不进主树; [已归档 (N)] 默认收起; 点开显示 done 任务;
 *   点击归档任务 → onSelectTask (审计入口)
 * - AfTaskDetailPanel 操作区 (onUpdate 提供时): 开始/完成按钮按受控状态机路径回调
 *   (todo→[ready,in_progress] / in_progress→[review,done] / blocked→重新开始→[in_progress]);
 *   优先级选择回调; 内联编辑标题/描述保存回调; 错误展示; 无 onUpdate → 不渲染操作区
 * - 审计溯源: 详情面板展示 exec_ref / exec_result
 * - AfTodoTreePage 集成: 点完成 → PATCH 逐布调用 + 刷新 (真实 fetch 桩)
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AfTodoTree, type TaskMeta } from '../components/af/AfTodoTree';
import { AfTaskDetailPanel, statusPathTo } from '../components/af/AfTaskDetailPanel';
import { AfTodoTreePage } from '../pages/project/AfTodoTreePage';
import { toTodoTree } from '../api/domain';
import type { TaskDetail } from '../models/domain';
import { sampleTodoBacklog, stubFetch } from './fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

// ------------------------------------------------------------------ statusPathTo (状态机合法路径)

describe('statusPathTo (W-3 受控状态机路径)', () => {
  it('todo → in_progress: [ready, in_progress]', () => {
    expect(statusPathTo('todo', 'in_progress')).toEqual(['ready', 'in_progress']);
  });
  it('ready → in_progress: [in_progress]', () => {
    expect(statusPathTo('ready', 'in_progress')).toEqual(['in_progress']);
  });
  it('blocked → in_progress (重新开始): [in_progress]', () => {
    expect(statusPathTo('blocked', 'in_progress')).toEqual(['in_progress']);
  });
  it('in_progress → done: [review, done]', () => {
    expect(statusPathTo('in_progress', 'done')).toEqual(['review', 'done']);
  });
  it('review → done: [done]', () => {
    expect(statusPathTo('review', 'done')).toEqual(['done']);
  });
  it('done → 无路径 (终态)', () => {
    expect(statusPathTo('done', 'in_progress')).toEqual([]);
    expect(statusPathTo('done', 'done')).toEqual([]);
  });
});

// ------------------------------------------------------------------ AfTodoTree 归档

describe('AfTodoTree 归档 (W-3)', () => {
  function renderTree(overrides: Parameters<typeof sampleTodoBacklog>[0] = {}) {
    const backlog = sampleTodoBacklog(overrides);
    const meta: Record<string, TaskMeta> = {};
    for (const t of backlog.tasks ?? []) {
      meta[t.id] = { priority: t.priority ?? undefined, owner: t.assignee ?? undefined };
    }
    return { meta };
  }

  it('done 任务不进主树 (待办视角); 工具栏 [已归档 (N)] 默认收起', () => {
    const { meta } = renderTree();
    render(<AfTodoTree tree={toTodoTree(sampleTodoBacklog(), '演示项目')} taskMeta={meta} />);
    // done 任务 (t-reg-db 用户数据模型) 不在主树
    expect(screen.queryByText('用户数据模型')).not.toBeInTheDocument();
    // 归档开关存在且默认收起
    const toggle = screen.getByTestId('af-tree-archive-toggle');
    expect(toggle).toHaveTextContent('已归档 (1)');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('af-tree-archive')).not.toBeInTheDocument();
  });

  it('点 [已归档] → 展开归档区, 显示 done 任务; 点击 → onSelectTask', async () => {
    const user = userEvent.setup();
    const { meta } = renderTree();
    const onSelect = vi.fn();
    render(<AfTodoTree tree={toTodoTree(sampleTodoBacklog(), '演示项目')} taskMeta={meta} onSelectTask={onSelect} />);
    await user.click(screen.getByTestId('af-tree-archive-toggle'));
    const archive = screen.getByTestId('af-tree-archive');
    expect(archive).toBeInTheDocument();
    expect(within(archive).getByText('用户数据模型')).toBeInTheDocument();
    await user.click(within(archive).getByRole('button', { name: /已归档任务: 用户数据模型/ }));
    expect(onSelect).toHaveBeenCalledWith('t-reg-db');
  });

  it('全部任务已完成 → "所有任务已完成 🎉" (不再是"暂无任务")', async () => {
    const backlog = sampleTodoBacklog({
      tasks: (sampleTodoBacklog().tasks ?? []).map((t) => ({ ...t, status: 'done' })),
    });
    render(<AfTodoTree tree={toTodoTree(backlog, '演示项目')} />);
    expect(screen.getByText(/所有任务已完成/)).toBeInTheDocument();
    expect(screen.getByTestId('af-tree-archive-toggle')).toHaveTextContent('已归档 (6)');
  });
});

// ------------------------------------------------------------------ AfTaskDetailPanel 操作区

/** running 任务 (含 rawStatus) — 完成按钮路径测试。 */
function runningTask(overrides: Partial<TaskDetail> = {}): TaskDetail {
  return {
    id: 'TASK-run',
    title: '实现注册 API',
    status: 'running',
    statusLabel: '执行中',
    rawStatus: 'in_progress',
    priority: 'P1',
    description: 'POST /api/register',
    execRef: 'EXR-1',
    execResult: 'EXS-1',
    history: [],
    artifacts: [],
    ...overrides,
  };
}

describe('AfTaskDetailPanel 操作区 (W-3)', () => {
  it('无 onUpdate → 不渲染操作区', () => {
    render(<AfTaskDetailPanel task={runningTask()} />);
    expect(screen.queryByTestId('af-task-detail-ops')).not.toBeInTheDocument();
  });

  it('审计溯源: 展示 exec_ref / exec_result', () => {
    render(<AfTaskDetailPanel task={runningTask()} />);
    expect(screen.getByTestId('af-task-detail-exec-ref')).toHaveTextContent('EXR-1');
    expect(screen.getByTestId('af-task-detail-exec-result')).toHaveTextContent('EXS-1');
  });

  it('running(in_progress) → [完成] 按钮回调 statusPath=[review, done]', async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn(async () => {});
    render(<AfTaskDetailPanel task={runningTask()} onUpdate={onUpdate} />);
    await user.click(screen.getByTestId('af-task-detail-finish'));
    expect(onUpdate).toHaveBeenCalledWith({ statusPath: ['review', 'done'] }, 'TASK-run');
  });

  it('pending(todo) → [开始] 按钮回调 statusPath=[ready, in_progress]', async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn(async () => {});
    render(
      <AfTaskDetailPanel
        task={runningTask({ id: 'TASK-todo', status: 'pending', statusLabel: '待办', rawStatus: 'todo', execRef: undefined, execResult: undefined })}
        onUpdate={onUpdate}
      />,
    );
    await user.click(screen.getByTestId('af-task-detail-start'));
    expect(onUpdate).toHaveBeenCalledWith({ statusPath: ['ready', 'in_progress'] }, 'TASK-todo');
  });

  it('blocked → [重新开始] 回调 statusPath=[in_progress]', async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn(async () => {});
    render(
      <AfTaskDetailPanel
        task={runningTask({ id: 'TASK-b', status: 'blocked', statusLabel: '阻塞', rawStatus: 'blocked' })}
        onUpdate={onUpdate}
      />,
    );
    await user.click(screen.getByTestId('af-task-detail-start'));
    expect(onUpdate).toHaveBeenCalledWith({ statusPath: ['in_progress'] }, 'TASK-b');
  });

  it('优先级选择 → 回调 {priority}', async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn(async () => {});
    render(<AfTaskDetailPanel task={runningTask()} onUpdate={onUpdate} />);
    await user.selectOptions(screen.getByTestId('af-task-detail-priority-select'), 'P0');
    expect(onUpdate).toHaveBeenCalledWith({ priority: 'P0' }, 'TASK-run');
  });

  it('编辑标题/描述 → 保存回调 {title, description}', async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn(async () => {});
    render(<AfTaskDetailPanel task={runningTask()} onUpdate={onUpdate} />);
    await user.click(screen.getByTestId('af-task-detail-edit'));
    const title = screen.getByTestId('af-task-detail-edit-title');
    await user.clear(title);
    await user.type(title, '新标题');
    await user.click(screen.getByTestId('af-task-detail-edit-save'));
    expect(onUpdate).toHaveBeenCalledWith({ title: '新标题' }, 'TASK-run');
  });

  it('onUpdate 失败 → 展示错误文案 (不崩溃)', async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn(async () => {
      throw new Error('API /backlog/task 请求失败 (HTTP 409)');
    });
    render(<AfTaskDetailPanel task={runningTask()} onUpdate={onUpdate} />);
    await user.click(screen.getByTestId('af-task-detail-finish'));
    expect(await screen.findByTestId('af-task-detail-error')).toHaveTextContent('HTTP 409');
  });
});

// ------------------------------------------------------------------ AfTodoTreePage 集成 (PATCH 真实链路)

describe('AfTodoTreePage 任务更新 (W-3 集成)', () => {
  const BACKLOG_PATH = '/api/projects/demo/backlog';

  it('点 [完成] → PATCH review → PATCH done → 重新拉取 backlog', async () => {
    const user = userEvent.setup();
    const patched: string[] = [];
    const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (init?.method === 'PATCH') {
        const body = JSON.parse(String(init.body));
        patched.push(body.status);
        return { ok: true, status: 200, json: async () => ({ id: 't-reg-api', status: body.status }) } as Response;
      }
      if (path === BACKLOG_PATH) {
        return { ok: true, status: 200, json: async () => sampleTodoBacklog() } as Response;
      }
      return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) } as Response;
    });
    vi.stubGlobal('fetch', fn);
    render(<AfTodoTreePage projectId="demo" projectName="演示项目" />);
    // 点任务 t-reg-api (in_progress) → 详情面板 → 完成
    const taskNode = await screen.findByRole('button', { name: /实现注册 API/ });
    await user.click(taskNode);
    await user.click(await screen.findByTestId('af-task-detail-finish'));
    // 两次 PATCH: review → done
    expect(patched).toEqual(['review', 'done']);
    // 完成后重新拉取 (fetch 调用次数增加)
    const backlogCalls = fn.mock.calls.filter(([p]) => String(p) === BACKLOG_PATH).length;
    expect(backlogCalls).toBeGreaterThanOrEqual(2);
  });

  it('归档任务点击 → 详情面板显示 (审计溯源入口)', async () => {
    const user = userEvent.setup();
    stubFetch({ [BACKLOG_PATH]: sampleTodoBacklog() });
    render(<AfTodoTreePage projectId="demo" projectName="演示项目" />);
    // 展开归档 → 点 done 任务 t-reg-db
    await user.click(await screen.findByTestId('af-tree-archive-toggle'));
    const item = await screen.findByTestId('af-tree-archive-item-t-reg-db');
    await user.click(item);
    const panel = await screen.findByTestId('af-todo-tree-detail');
    expect(within(panel).getByText('用户数据模型')).toBeInTheDocument();
  });
});
