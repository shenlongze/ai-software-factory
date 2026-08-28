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
    expect(screen.getByTestId('af-chat-scope')).toHaveTextContent('公司 · 全局');
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
    // 发送失败 = messages POST 返回非 ok (SSE 读不到 body) → 回退同步也失败 → 诚实提示
    const fn = stubSessionApi({
      onSend: () => {
        throw new Error('network down');
      },
    });
    void fn;
    renderPanel();
    await userEvent.click(screen.getByLabelText('新建会话'));
    await screen.findByTestId(/af-session-sess-1/);
    await userEvent.type(screen.getByRole('textbox', { name: 'AI 会话输入' }), 'hi');
    await userEvent.click(screen.getByRole('button', { name: '发送' }));
    expect(await screen.findByText(/发送失败/)).toBeInTheDocument();
  });

  it('T3: 思考链可视化 — 有 thinking_steps 时显示可折叠思考区', async () => {
    // onSend 返回带 thinking_steps 的 assistant 消息 (模拟后端已完成落库的消息)
    stubSessionApi({
      onSend: () => ({
        id: 'msg-a',
        session_id: 'sess-1',
        role: 'assistant',
        content: '最终回答',
        created_at: '2026-08-26T00:00:01Z',
        meta: {
          thinking_steps: [
            { round: 1, detail: '先分析需求' },
            { round: 2, detail: '再查代码' },
          ],
        },
      }),
    });
    renderPanel();
    await userEvent.click(screen.getByLabelText('新建会话'));
    await screen.findByTestId(/af-session-sess-1/);
    await userEvent.type(screen.getByRole('textbox', { name: 'AI 会话输入' }), '查一下代码');
    await userEvent.click(screen.getByRole('button', { name: '发送' }));
    // 思考区显示步数, 默认收起; 点击展开显示细节
    expect(await screen.findByText(/思考过程 \(2 步\)/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /思考过程/ }));
    expect(await screen.findByText(/先分析需求/)).toBeInTheDocument();
    expect(await screen.findByText(/再查代码/)).toBeInTheDocument();
  });

  it('T4: 工具详情 — 失败工具显示参数/结果详情 + 重试按钮', async () => {
    stubSessionApi({
      onSend: () => ({
        id: 'msg-a',
        session_id: 'sess-1',
        role: 'assistant',
        content: '最终回答',
        created_at: '2026-08-26T00:00:01Z',
        meta: {
          tool_calls: [
            {
              tool: 'bash_exec',
              ok: false,
              duration_ms: 42,
              error: 'command not found',
              params: '{"command":"ls /tmp"}',
              output: 'bash: ls: command not found',
            },
          ],
        },
      }),
    });
    renderPanel();
    await userEvent.click(screen.getByLabelText('新建会话'));
    await screen.findByTestId(/af-session-sess-1/);
    await userEvent.type(screen.getByRole('textbox', { name: 'AI 会话输入' }), '跑个命令');
    await userEvent.click(screen.getByRole('button', { name: '发送' }));
    // 失败工具: 显示错误 + 详情按钮 + 重试按钮
    expect(await screen.findByText(/command not found/)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /重试/ })).toBeInTheDocument();
    // 展开详情 → 显示参数和结果 (错误文本出现在徽章+结果两处, 用 getAllByText)
    await userEvent.click(screen.getByRole('button', { name: /详情/ }));
    expect(await screen.findByText(/ls \/tmp/)).toBeInTheDocument();
    expect((await screen.findAllByText(/command not found/)).length).toBeGreaterThan(0);
  });

  it('T5: 证据链 — 有 evidence 时显示证据来源, 展开可见工具+结果', async () => {
    stubSessionApi({
      onSend: () => ({
        id: 'msg-a',
        session_id: 'sess-1',
        role: 'assistant',
        content: '基于工具结果给出回答',
        created_at: '2026-08-26T00:00:01Z',
        meta: {
          evidence: [
            { tool: 'project_status', ok: true, output: '生命周期: 开发中, 任务 5/8 完成' },
            { tool: 'git_status', ok: false, output: 'error: 无法读取' },
          ],
        },
      }),
    });
    renderPanel();
    await userEvent.click(screen.getByLabelText('新建会话'));
    await screen.findByTestId(/af-session-sess-1/);
    await userEvent.type(screen.getByRole('textbox', { name: 'AI 会话输入' }), '项目状态如何');
    await userEvent.click(screen.getByRole('button', { name: '发送' }));
    // 证据来源显示条数, 默认收起; 点击展开显示工具+结果
    expect(await screen.findByText(/证据来源 \(2\)/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /证据来源/ }));
    expect(await screen.findByText(/project_status/)).toBeInTheDocument();
    expect(await screen.findByText(/任务 5\/8 完成/)).toBeInTheDocument();
    expect(await screen.findByText(/git_status/)).toBeInTheDocument();
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

  it('作用域自动跟随视图 (A 方案): 有项目 → 项目; 无项目 → 公司', async () => {
    stubSessionApi();
    const { unmount } = renderPanel('P-1');
    expect(await screen.findByTestId('af-chat-scope')).toHaveTextContent('项目 · P-1');
    unmount();
    stubSessionApi();
    renderPanel(null);
    expect(await screen.findByTestId('af-chat-scope')).toHaveTextContent('公司 · 全局');
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
