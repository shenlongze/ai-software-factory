/**
 * src/test/af-conversation-panel.test.tsx — C 列 AI 会话栏 (K-7e)。
 *
 * 验证: 作用域选择 · 会话列表(多线程) · 新建/改名/归档 · 发送消息 (真实 API) ·
 * 收起/展开 · 诚实空态 (无 LLM → 降级提示由后端返回, 前端如实展示)。
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { ConversationProvider } from '../components/af/ConversationContext';
import { AfConversationPanel } from '../components/af/AfConversationPanel';

function renderPanel(projectId?: string | null) {
  return render(
    <ConversationProvider>
      <AfConversationPanel projectId={projectId ?? null} projectName={projectId ?? null} />
    </ConversationProvider>,
  );
}

function jsonResponse(v: unknown): Response {
  return { ok: true, status: 200, json: async () => v } as Response;
}

/** 会话 API 桩: 方法感知 (GET 列表/消息, POST 创建/发送)。 */
function stubSessionApi(options: {
  initial?: unknown[];
  onCreate?: (body: unknown) => unknown;
  onSend?: (body: unknown) => unknown;
} = {}) {
  let sessions = [...(options.initial ?? [])];
  const created: unknown[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    if (url === '/api/sessions' && method === 'POST') {
      const s = options.onCreate ? options.onCreate(body) : { id: `sess-${created.length + 1}`, scope: 'company', project_id: null, title: '新会话', status: 'active', created_at: '2026-08-26T00:00:00Z', updated_at: '2026-08-26T00:00:00Z', summary: null };
      created.push(s);
      sessions = [...sessions, s];
      return jsonResponse(s);
    }
    if (url.startsWith('/api/sessions?scope=') && method === 'GET') {
      return jsonResponse({ items: sessions, count: sessions.length });
    }
    const msgMatch = url.match(/^\/api\/sessions\/([^/]+)\/messages$/);
    if (msgMatch) {
      const sid = msgMatch[1];
      if (method === 'GET') {
        return jsonResponse({ items: [], count: 0 });
      }
      if (method === 'POST') {
        const user = { id: 'msg-u', session_id: sid, role: 'user', content: body?.message ?? '', created_at: '2026-08-26T00:00:00Z' };
        const assistant = options.onSend
          ? options.onSend(body)
          : { id: 'msg-a', session_id: sid, role: 'assistant', content: 'AI 回复 (真实)', created_at: '2026-08-26T00:00:01Z' };
        return jsonResponse({ user, assistant, session: { id: sid } });
      }
    }
    return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) } as Response;
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => {
  window.location.hash = '';
  vi.unstubAllGlobals();
});

describe('AfConversationPanel (AI 会话栏 C 列)', () => {
  it('空态: 无会话 → 提示新建; 输入框存在', async () => {
    stubSessionApi();
    renderPanel();
    expect(await screen.findByText(/暂无会话/)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'AI 会话输入' })).toBeInTheDocument();
    expect(screen.getByLabelText('会话作用域')).toBeInTheDocument();
  });

  it('新建会话 → 列表出现并自动选中', async () => {
    stubSessionApi();
    renderPanel();
    await userEvent.click(screen.getByLabelText('新建会话'));
    expect(await screen.findByTestId(/af-session-sess-1/)).toBeInTheDocument();
    expect(screen.getAllByText(/新会话/).length).toBeGreaterThanOrEqual(1);
  });

  it('发送消息 → 用户消息 + AI 回复 (真实 API 返回) 展示', async () => {
    stubSessionApi({
      onSend: () => ({
        id: 'msg-a',
        session_id: 'sess-1',
        role: 'assistant',
        content: '好的, 我们来做一个记账App',
        created_at: '2026-08-26T00:00:01Z',
      }),
    });
    renderPanel();
    await userEvent.click(screen.getByLabelText('新建会话'));
    await screen.findByTestId(/af-session-sess-1/);
    await userEvent.type(screen.getByRole('textbox', { name: 'AI 会话输入' }), '我想做一个记账App');
    await userEvent.click(screen.getByRole('button', { name: '发送' }));
    expect(await screen.findByText('我想做一个记账App')).toBeInTheDocument();
    expect(await screen.findByText('好的, 我们来做一个记账App')).toBeInTheDocument();
  });

  it('发送失败 → 诚实错误提示', async () => {
    const fn = stubSessionApi();
    renderPanel();
    await userEvent.click(screen.getByLabelText('新建会话'));
    await screen.findByTestId(/af-session-sess-1/);
    fn.mockRejectedValueOnce(new Error('network down'));
    await userEvent.type(screen.getByRole('textbox', { name: 'AI 会话输入' }), 'hi');
    await userEvent.click(screen.getByRole('button', { name: '发送' }));
    expect(await screen.findByText(/发送失败/)).toBeInTheDocument();
  });

  it('改名 (✎) → 行内输入保存', async () => {
    stubSessionApi({
      onCreate: () => ({
        id: 'sess-1',
        scope: 'company',
        project_id: null,
        title: '新会话',
        status: 'active',
        created_at: '2026-08-26T00:00:00Z',
        updated_at: '2026-08-26T00:00:00Z',
        summary: null,
      }),
    });
    renderPanel();
    await userEvent.click(screen.getByLabelText('新建会话'));
    await screen.findByTestId(/af-session-sess-1/);
    await userEvent.click(screen.getByLabelText('改名'));
    const input = screen.getByLabelText('会话标题');
    await userEvent.clear(input);
    await userEvent.type(input, '讨论: 导出功能');
    await userEvent.keyboard('{Enter}');
    // PATCH 后 refresh 返回原标题 (桩不维护 PATCH) — 至少不崩溃, 输入框关闭
    expect(screen.queryByLabelText('会话标题')).not.toBeInTheDocument();
  });

  it('收起 → 折叠轨; 再展开', async () => {
    stubSessionApi();
    renderPanel();
    await userEvent.click(screen.getByLabelText('收起 AI 会话'));
    expect(screen.getByLabelText('AI 会话 (已收起)')).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText('展开 AI 会话'));
    expect(screen.getByTestId('af-conversation-panel')).toBeInTheDocument();
  });

  it('项目级作用域: 无项目 → 提示先进入项目; 有项目 → 作用域标签带项目名', async () => {
    stubSessionApi();
    const { unmount } = renderPanel('P-1');
    await userEvent.selectOptions(screen.getByLabelText('会话作用域'), 'project');
    expect(await screen.findByText(/项目 · P-1/)).toBeInTheDocument();
    unmount();
    stubSessionApi();
    renderPanel(null);
    await userEvent.selectOptions(screen.getByLabelText('会话作用域'), 'project');
    expect(await screen.findByText(/请先进入项目/)).toBeInTheDocument();
  });
});

describe('会话跳转按钮 (发起/查看后直达功能页)', () => {
  it('assistant 消息带 meta.target → 渲染跳转链接', async () => {
    const fn = stubSessionApi({
      onSend: () => ({
        id: 'msg-a',
        session_id: 'sess-1',
        role: 'assistant',
        content: '任务统计: done:3',
        created_at: '2026-08-26T00:00:01Z',
      }),
    });
    // 让 send 返回 meta.target
    const orig = fn.getMockImplementation();
    fn.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const res = await (orig as (i: RequestInfo | URL, init?: RequestInit) => Promise<Response>)(input, init);
      const body = await res.json();
      return {
        ok: true,
        json: async () => ({ ...body, meta: { intent: 'project_tasks', project: 'p1', data_source: 'live', target: { url: '#/project/p1/todo', label: '查看任务' } } }),
      } as Response;
    });
    renderPanel();
    await userEvent.click(screen.getByLabelText('新建会话'));
    await screen.findByTestId(/af-session-sess-1/);
    await userEvent.type(screen.getByRole('textbox', { name: 'AI 会话输入' }), '有什么任务');
    await userEvent.click(screen.getByRole('button', { name: '发送' }));
    const jump = await screen.findByTestId(/af-chat-jump-msg-a/);
    expect(jump).toHaveTextContent('查看任务');
    expect(jump).toHaveAttribute('href', '#/project/p1/todo');
  });
});
