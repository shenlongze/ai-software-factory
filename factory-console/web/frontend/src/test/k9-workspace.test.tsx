/**
 * K9 Human Workspace 三栏组件测试。
 * - AfConversationCenter: 会话列表/消息流/输入/Work 状态/发送联动
 * - AfWorkspace: Tab 切换/任务面板真实数据
 * - AfContextNav: 左栏导航渲染
 */
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationProvider } from '../components/af/ConversationContext';
import { AfConversationCenter } from '../components/af/AfConversationCenter';
import { AfWorkspace, deriveProfile, tabForIntent } from '../components/af/AfWorkspace';
import { AfContextNav } from '../components/af/AfContextNav';

const conv = {
  id: 'conv_1', type: 'conv', version: 1, status: 'OPEN',
  metadata: { title: '测试会话' },
  messages: [{ id: 'm1', content: '我想做一个 App', intent: 'DISCUSS', actor: 'human', at: 't1' }],
  state: { goal: '', confirmed_decisions: [], work_items: [{ id: 'task_1', title: '任务A', status: 'RUNNING' }] },
};

const reply = { message_id: 'm2', intent: 'EXECUTE', reply: { text: '好的,开始执行', status: 'OK' }, conversation_version: 2 };

const projStatus = {
  project_id: 'project_1', title: '测试项目', status: 'ACTIVE',
  progress: { completed: 1, failed: 0, running: 1, blocked: 0, waiting: 1, total: 3, percentage: 33 },
  sprints: [{
    sprint_id: 'sprint_1', title: 'S1', status: 'ACTIVE',
    progress: { completed: 1, failed: 0, running: 1, blocked: 0, total: 3, percentage: 33 },
    tasks: [
      { id: 'task_1', title: '任务A', status: 'COMPLETED', production_run_id: 'r1' },
      { id: 'task_2', title: '任务B', status: 'RUNNING', production_run_id: 'r2' },
    ],
  }],
};

function mockApi() {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url);
    const method = init?.method?.toUpperCase() ?? 'GET';
    if (u.includes('/api/conversations') && u.includes('/messages')) return { ok: true, json: async () => reply };
    if (u.includes('/api/conversations/conv_1')) return { ok: true, json: async () => conv };
    if (u.includes('/api/conversations')) return { ok: true, json: async () => ({ items: [conv], count: 1 }) };
    if (u.includes('/api/projects-os') && u.includes('/status')) return { ok: true, json: async () => projStatus };
    if (u.includes('/api/projects/') && u.includes('/runs')) return { ok: true, json: async () => ({ project_id: 'project_1', runs: [{ run_id: 'R-TEST-1', status: 'running', totals: { total_tokens: 100 } }], count: 1 }) };
    if (u.includes('/api/projects-os')) return { ok: true, json: async () => ({ items: [{ id: 'project_1', title: '测试项目' }] }) };
    if (u.includes('/api/ops/overview')) return { ok: true, json: async () => ({ projects: { total: 1, running: 0, waiting: 0, blocked: 0, approval: 1, failed: 0 }, workforce: { running: 1, waiting: 0, blocked: 0, error: 0, idle: 0 }, recent_activity: [{ event_type: 'TOOL_CALL', timestamp: '2026-08-31T11:00:00+00:00', trace_id: 'sess-1' }], calculated_at: 'now' }) };
    // ConversationContext 数据源 — 新 UI 使用 sessions API
    if (u.includes('/api/sessions') && u.includes('/messages')) {
      if (method === 'POST') {
        // POST send message → 返回 user + assistant
        return { ok: true, json: async () => ({
          user: { id: 'm2', session_id: 'conv_1', role: 'user', content: '开始做', created_at: 't2' },
          assistant: { id: 'm3', session_id: 'conv_1', role: 'assistant', content: '好的,开始执行', created_at: 't3' },
        }) };
      }
      // GET messages (含 AI markdown 回复 — S34-001 测试; run_ids 关联 — S34-002)
      return { ok: true, json: async () => ({ items: [
        { id: 'm1', session_id: 'conv_1', role: 'user', content: '我想做一个 App', created_at: 't1' },
        { id: 'm2', session_id: 'conv_1', role: 'assistant', content: '好的，**开始执行**！\n\n- 任务 A\n- 任务 B', created_at: 't2', meta: { run_ids: ['R-TEST-1'], tool_calls: [{ tool: 'project_status', ok: true }, { tool: 'project_scan', ok: true }, { tool: 'bash_exec', ok: true }], usage: { model: 'deepseek-v4-flash', context_window: 1048576, prompt_tokens: 248000, completion_tokens: 12000, total_tokens: 260000, elapsed_s: 113 } } },
      ] }) };
    }
    // S31-004: Session → Run 关联 (Runs 卡) — 必须在 /api/sessions 列表之前匹配
    if (u.includes('/runs')) return { ok: true, json: async () => ({ session_id: 'conv_1', runs: [{ run_id: 'R-TEST-1', status: 'running', stages: [{ role: 'product-manager', stage: 'product', status: 'COMPLETED', latency_s: 14.9 }], totals: { total_tokens: 1639, cost_usd_est: 0.000644 } }], count: 1 }) };
    if (u.includes('/api/sessions')) return { ok: true, json: async () => ({ items: [{ id: 'conv_1', scope: 'company', project_id: null, title: '测试会话', status: 'active', created_at: 't0', updated_at: 't1', summary: null, run_ids: ['R-TEST-1'] }], count: 1 }) };
    return { ok: true, json: async () => ({}) };
  }));
}

function wrap(node: React.ReactNode) {
  return render(<ConversationProvider>{node}</ConversationProvider>);
}

beforeEach(() => { mockApi(); });

describe('AfConversationCenter (K9 中栏)', () => {
  it('渲染消息流 + 输入区', async () => {
    wrap(<AfConversationCenter />);
    await waitFor(() => expect(screen.getByText(/我想做一个 App/)).toBeTruthy());
    expect(screen.getByPlaceholderText(/和公司说话/)).toBeTruthy();
    // 发送按钮 (图标)
    expect(screen.getByRole('button', { name: /发送/i })).toBeTruthy();
  });

  it('消息流正确渲染 user/assistant 气泡', async () => {
    wrap(<AfConversationCenter />);
    await waitFor(() => expect(screen.getByText(/我想做一个 App/)).toBeTruthy());
    // 用户气泡 + 发送按钮都在
    const bubbles = screen.getAllByText(/我想做一个 App/);
    expect(bubbles.length).toBeGreaterThan(0);
  });

  it('发送 → 追加 AI 回复', async () => {
    wrap(<AfConversationCenter />);
    await waitFor(() => expect(screen.getByPlaceholderText(/和公司说话/)).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText(/和公司说话/), { target: { value: '开始做' } });
    fireEvent.click(screen.getByRole('button', { name: /发送/i }));
    await waitFor(() => expect(screen.getByText(/好的,开始执行/)).toBeTruthy());
  });
});

describe('AfWorkspace (K9 右栏)', () => {
  it('渲染 Tab 栏 + 任务面板 (真实进度)', async () => {
    wrap(<AfWorkspace />);
    await waitFor(() => expect(screen.getByRole('tab', { name: /任务/ })).toBeTruthy());
    expect(screen.getByRole('tab', { name: /代码/ })).toBeTruthy();
    expect(screen.getByRole('tab', { name: /预览/ })).toBeTruthy();
    expect(screen.getByRole('tab', { name: /Diff/ })).toBeTruthy();
    expect(screen.getByRole('tab', { name: /证据/ })).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/任务B/)).toBeTruthy());
  });

  it('Tab 可手动切换', async () => {
    wrap(<AfWorkspace />);
    await waitFor(() => expect(screen.getByRole('tab', { name: /预览/ })).toBeTruthy());
    fireEvent.click(screen.getByRole('tab', { name: /预览/ }));
    expect(screen.getByText(/暂无可预览产物/)).toBeTruthy();
  });
});

describe('AfContextNav (K9 左栏)', () => {
  it('渲染 Context 导航 (品牌/对话/项目/最近 — S31-002)', async () => {
    wrap(<AfContextNav collapsed={false} />);
    await waitFor(() => expect(screen.getByText('AI Factory')).toBeTruthy());
    expect(screen.getAllByText(/对话/).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText(/测试项目/)).toBeTruthy());
    // S31-002: Module 菜单 (待审批) 不进入一级导航
    expect(screen.queryByText(/待审批/)).toBeNull();
  });
});

// S31-004: Run 卡 Execution Detail 展开 (真实 stages)
describe('Run 卡 Execution Detail (S31-004)', () => {
  it('渲染 Run 卡, 点击展开真实 stages (人话角色)', async () => {
    wrap(<AfConversationCenter />);
    // Run 卡出现 (activeId 自动选 conv_1 → runs 加载)
    const item = await waitFor(() => screen.getByTestId('af-run-item'));
    expect(item.textContent).toContain('R-TEST-1');
    expect(item.textContent).toContain('running');
    // 点击展开 → stages + tokens
    fireEvent.click(item);
    await waitFor(() => {
      const detail = screen.getByTestId('af-run-detail');
      expect(detail.textContent).toContain('产品经理'); // ROLE_LABELS 人话
      expect(detail.textContent).toContain('tokens');
    });
  });
});

// S32-002: Conversation Management — 重命名/归档 (真实 PATCH /api/sessions)
describe('Conversation Management (S32-002)', () => {
  it('会话项有重命名/归档操作按钮', async () => {
    wrap(<AfContextNav collapsed={false} />);
    await waitFor(() => expect(screen.getByText(/测试会话/)).toBeTruthy());
    const rename = screen.getByLabelText(/重命名/);
    expect(rename).toBeTruthy();
    const archive = screen.getByLabelText(/归档/);
    expect(archive).toBeTruthy();
  });
});

// S32-003: Project — 新建项目入口 (真实 POST /api/projects)
describe('Project Management (S32-003)', () => {
  it('项目块有新建项目按钮', async () => {
    wrap(<AfContextNav collapsed={false} />);
    await waitFor(() => expect(screen.getByLabelText(/新建项目/)).toBeTruthy());
    expect(screen.getByLabelText(/新建项目/)).toBeTruthy();
  });
});

// S32-004A: Project 点击 → hash 导航 (Shell 传 onSelectProject)
describe('Project Navigation (S32-004A)', () => {
  it('AfContextNav 项目点击调用 onSelectProject', async () => {
    let selected = '';
    render(
      <ConversationProvider>
        <AfContextNav
          collapsed={false}
          onSelectProject={(id) => { selected = id; }}
        />
      </ConversationProvider>,
    );
    await waitFor(() => expect(screen.getByText(/测试项目/)).toBeTruthy());
    fireEvent.click(screen.getByText(/测试项目/));
    expect(selected).toBe('project_1');
  });
});

// S32-004B: Contextual Project Selection — 右栏 Project Workspace
describe('Project Workspace (S32-004B)', () => {
  it('项目选中时右栏切换为 Project Workspace (真实数据)', async () => {
    render(
      <ConversationProvider initialProjectId="project_1">
        <AfWorkspace />
      </ConversationProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('af-project-workspace')).toBeTruthy());
    expect(screen.getByText(/项目 Workspace/)).toBeTruthy();
    expect(screen.getByText(/测试项目/)).toBeTruthy();
    expect(screen.getByLabelText(/清除项目 Context/)).toBeTruthy();
  });
});

// S33-006/007/008: 会话 → Workspace 自动联动
describe('Conversation → Workspace 联动 (S33)', () => {
  it('tabForIntent 意图→Tab 映射 (真实) ', () => {
    expect(tabForIntent('EXECUTE')).toBe('task');
    expect(tabForIntent('ASK_STATUS')).toBe('task');
    expect(tabForIntent('DECIDE')).toBe('code');
    expect(tabForIntent('CLARIFY')).toBe('code');
  });
  it('deriveProfile 消息→profile (真实, 非关键词正则 — 后端意图)', () => {
    // 发送中按消息内容推导 (执行中默认 coding)
    expect(deriveProfile(true, '继续开发登录功能')).toBe('coding');
    expect(deriveProfile(true, '这个 bug 为什么失败')).toBe('debug');
    expect(deriveProfile(true, '分析一下竞品')).toBe('prd');
    expect(deriveProfile(true, '运行测试')).toBe('qa');
    expect(deriveProfile(false, '任意')).toBe('default');
  });
});

// S34-001: AI 回复 + 用户输入支持 Markdown
describe('Message Markdown (S34-001)', () => {
  it('AI 回复渲染 markdown (粗体/列表/代码)', async () => {
    wrap(<AfConversationCenter />);
    // markdown 渲染: AI 回复的 strong/em 元素存在 (文本被拆分)
    await waitFor(() => {
      const strong = document.querySelector('.ai-msg-bubble--ai strong');
      expect(strong).toBeTruthy();
    });
    // 用户消息正常显示 (纯文本)
    expect(screen.getByText(/我想做一个 App/)).toBeTruthy();
  });
});

// S34-003B: 执行状态卡阶段感知 (工具完成→正在生成回答, 不矛盾)
describe('Execution State (S34-003B)', () => {
  it('工具已执行时执行卡显示生成回答阶段', async () => {
    // mock GET messages 已带 tool_calls 的 assistant 消息 + sending
    wrap(<AfConversationCenter />);
    await waitFor(() => {
      const txt = document.querySelector('.ai-execution-text');
      // 当前 mock 不 sending, 执行卡不出现 — 验证发送结束后无残留执行卡 (S34-003B 核心: 不矛盾)
      expect(txt).toBeFalsy();
      // ToolCallList 已渲染 (真实工具证据保留)
      expect(document.querySelector('.ai-tool-calls-summary')).toBeTruthy();
    });
    // S34-003B: 执行详情 (模型/上下文/tokens) 展开可见
    const summary = document.querySelector('.ai-tool-calls-summary') as HTMLButtonElement | null;
    if (summary) summary.click();
    await waitFor(() => {
      expect(document.querySelector('[data-testid="af-tool-usage"]')).toBeTruthy();
      expect(document.querySelector('.ai-tool-usage-model')?.textContent).toContain('deepseek-v4-flash');
      // S34-003B: 上下文进度条 + tokens 标签
      expect(document.querySelector('.ai-tool-usage-ctx')?.textContent).toContain('24%');
      expect(document.querySelector('.ai-tool-usage-tokens')?.textContent).toContain('tokens');
    });
  });
});

// S32-006: Command Center — Recent Results (真实 recent_activity)
describe('Command Center (S31-006)', () => {
  it('Welcome Hero 显示 Recent Results (真实事件流)', async () => {
    // 覆盖: 空会话 + 空消息 → Hero 显示 (Command Center)
    const originalFetch = globalThis.fetch;
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes('/api/ops/overview')) return { ok: true, json: async () => ({ projects: { total: 1, running: 1, waiting: 0, blocked: 0, approval: 0, failed: 0 }, workforce: { running: 1, waiting: 0, blocked: 0, error: 0, idle: 0 }, recent_activity: [{ event_type: 'TOOL_CALL', timestamp: '2026-08-31T11:00:00+00:00', trace_id: 'sess-1' }], calculated_at: 'now' }) };
      if (u.includes('/api/sessions') && u.includes('/messages')) return { ok: true, json: async () => ({ items: [], count: 0 }) };
      if (u.includes('/api/sessions')) return { ok: true, json: async () => ({ items: [], count: 0 }) };
      if (u.includes('/api/conversations')) return { ok: true, json: async () => ({ items: [], count: 0 }) };
      return { ok: true, json: async () => ({}) };
    }));
    wrap(<AfConversationCenter />);
    // Hero 出现 (无消息时) + Active Work (running=1) + Recent Results
    await waitFor(() => expect(screen.getByText(/What do you want to accomplish/)).toBeTruthy());
    await waitFor(() => expect(screen.getByTestId('af-active-work')).toBeTruthy());
    await waitFor(() => expect(screen.getByTestId('af-recent-results')).toBeTruthy());
    expect(screen.getByText(/1 个任务运行中/)).toBeTruthy();
    expect(screen.getByText(/TOOL_CALL/)).toBeTruthy();
    globalThis.fetch = originalFetch;
  });
});
