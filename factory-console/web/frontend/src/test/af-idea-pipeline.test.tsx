/**
 * src/test/af-idea-pipeline.test.tsx — 想法→细化→待办链路 (v1.1.144)。
 *
 * Founder: "想法 → 会话中与 AI 讨论 → 细化后进待办 应该是一套逻辑"。
 * 覆盖:
 * - toTodoTree: BacklogFeature.maturity=idea → TreeNode.maturity=idea (💡)
 * - AfTodoTree: 想法模块可见 (空模块不再被隐藏) + 💡 想法 徽标 + 操作按钮
 * - [＋ 新建模块] → onCreateFeature; 💬 讨论 → onDiscussFeature(id,name);
 *   ✓ 转正式 → onRefineFeature(id)
 * - 只有想法模块的 backlog → 渲染树 (不再误报"暂无任务")
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AfTodoTree } from '../components/af/AfTodoTree';
import { toTodoTree } from '../api/domain';
import type { BacklogResponse } from '../models/domain';
import { sampleTodoBacklog } from './fixtures';

/** 在 sampleTodoBacklog 上追加一个空想法模块 (epic E-idea → feature F-idea, 无 story)。 */
function withIdeaFeature(base: BacklogResponse = sampleTodoBacklog()): BacklogResponse {
  return {
    ...base,
    epics: [...(base.epics ?? []), { id: 'E-idea', name: '想法箱', description: '', children: ['F-idea'], created_at: '2026-08-26T00:00:00Z', updated_at: '2026-08-26T00:00:00Z' }],
    features: [
      ...(base.features ?? []),
      { id: 'F-idea', name: 'AI 记账', description: '语音记账', maturity: 'idea', children: [], created_at: '2026-08-26T00:00:00Z', updated_at: '2026-08-26T00:00:00Z' },
    ],
  };
}

describe('想法→细化→待办链路 (v1.1.144)', () => {
  it('toTodoTree: maturity=idea → TreeNode.maturity=idea (💡 想法模块)', () => {
    const backlog = withIdeaFeature();
    const tree = toTodoTree(backlog, '演示项目');
    const ideaEpic = tree.root.children.find((p) => p.id === 'E-idea');
    expect(ideaEpic).toBeDefined();
    const ideaModule = ideaEpic!.children.find((m) => m.id === 'F-idea');
    expect(ideaModule?.maturity).toBe('idea');
    // 正式模块不带 maturity (默认 refined)
    const normalModule = tree.root.children.find((p) => p.id === 'epic-dev')?.children[0];
    expect(normalModule?.maturity).toBeUndefined();
  });

  it('想法模块可见 + 💡 徽标 + 操作按钮 (讨论/转正式)', () => {
    render(
      <AfTodoTree
        tree={toTodoTree(withIdeaFeature(), '演示项目')}
        onCreateFeature={() => {}}
        onDiscussFeature={() => {}}
        onRefineFeature={() => {}}
      />,
    );
    expect(screen.getByText('AI 记账')).toBeInTheDocument();
    expect(screen.getByText('想法箱')).toBeInTheDocument();
    const ideaBadge = screen.getByTestId('af-tree-idea-badge');
    expect(ideaBadge).toHaveTextContent('想法');
    expect(screen.getByTestId('af-tree-discuss-F-idea')).toBeInTheDocument();
    expect(screen.getByTestId('af-tree-refine-F-idea')).toBeInTheDocument();
  });

  it('＋ 新建模块 → onCreateFeature 回调', async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn();
    render(<AfTodoTree tree={toTodoTree(sampleTodoBacklog(), '演示项目')} onCreateFeature={onCreate} />);
    await user.click(screen.getByTestId('af-tree-create-feature'));
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  it('💬 讨论 → onDiscussFeature(featureId, featureName)', async () => {
    const user = userEvent.setup();
    const onDiscuss = vi.fn();
    render(
      <AfTodoTree
        tree={toTodoTree(withIdeaFeature(), '演示项目')}
        onDiscussFeature={onDiscuss}
      />,
    );
    await user.click(screen.getByTestId('af-tree-discuss-F-idea'));
    expect(onDiscuss).toHaveBeenCalledWith('F-idea', 'AI 记账');
  });

  it('✓ 转正式 → onRefineFeature(featureId)', async () => {
    const user = userEvent.setup();
    const onRefine = vi.fn();
    render(
      <AfTodoTree
        tree={toTodoTree(withIdeaFeature(), '演示项目')}
        onRefineFeature={onRefine}
      />,
    );
    await user.click(screen.getByTestId('af-tree-refine-F-idea'));
    expect(onRefine).toHaveBeenCalledWith('F-idea');
  });

  it('只有想法模块 (无任务) → 渲染树, 不误报"暂无任务"', () => {
    const backlog: BacklogResponse = {
      project_id: 'p-idea',
      epics: [{ id: 'E1', name: '想法箱', description: '', children: ['F1'], created_at: '2026-08-26T00:00:00Z', updated_at: '2026-08-26T00:00:00Z' }],
      features: [{ id: 'F1', name: 'AI 记账', description: '', maturity: 'idea', children: [], created_at: '2026-08-26T00:00:00Z', updated_at: '2026-08-26T00:00:00Z' }],
      stories: [],
      tasks: [],
    };
    render(<AfTodoTree tree={toTodoTree(backlog, '想法项目')} />);
    expect(screen.queryByText('暂无任务 — AI 正在规划')).not.toBeInTheDocument();
    expect(screen.getByText('AI 记账')).toBeInTheDocument();
    expect(screen.getByTestId('af-tree-idea-badge')).toBeInTheDocument();
  });

  it('想法模块可折叠展开 (子树正常渲染)', async () => {
    const user = userEvent.setup();
    render(
      <AfTodoTree
        tree={toTodoTree(withIdeaFeature(), '演示项目')}
        onDiscussFeature={() => {}}
      />,
    );
    // 想法箱阶段默认展开 → 模块可见; 折叠 → 模块消失
    expect(screen.getByText('AI 记账')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /折叠 想法箱/ }));
    expect(screen.queryByText('AI 记账')).not.toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ AfTodoTreePage 集成

import { AfTodoTreePage } from '../pages/project/AfTodoTreePage';
import { afterEach } from 'vitest';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AfTodoTreePage 想法链路集成', () => {
  const BACKLOG_PATH = '/api/projects/demo/backlog';

  it('＋ 新建模块 → prompt 模块名 → POST /backlog/feature (maturity=idea) → 重新拉取', async () => {
    const user = userEvent.setup();
    const posts: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal('prompt', () => 'AI 记账');
    const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (init?.method === 'POST' && path.includes('/backlog/feature')) {
        posts.push({ url: path, body: JSON.parse(String(init.body)) });
        return { ok: true, status: 201, json: async () => ({ id: 'FEAT-new', name: 'AI 记账', maturity: 'idea' }) } as Response;
      }
      if (path === BACKLOG_PATH) {
        return { ok: true, status: 200, json: async () => sampleTodoBacklog() } as Response;
      }
      return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) } as Response;
    });
    vi.stubGlobal('fetch', fn);
    render(<AfTodoTreePage projectId="demo" projectName="演示项目" />);
    await user.click(await screen.findByTestId('af-tree-create-feature'));
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toMatchObject({ name: 'AI 记账', maturity: 'idea' });
    expect(posts[0].url).toContain('/api/projects/demo/backlog/feature');
    // 创建后重新拉取
    const backlogCalls = fn.mock.calls.filter(([p]) => String(p) === BACKLOG_PATH).length;
    expect(backlogCalls).toBeGreaterThanOrEqual(2);
  });
});
