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
import { AfWorkspace } from '../components/af/AfWorkspace';
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
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const u = String(url);
    if (u.includes('/api/conversations') && u.includes('/messages')) return { ok: true, json: async () => reply };
    if (u.includes('/api/conversations/conv_1')) return { ok: true, json: async () => conv };
    if (u.includes('/api/conversations')) return { ok: true, json: async () => ({ items: [conv], count: 1 }) };
    if (u.includes('/api/projects-os') && u.includes('/status')) return { ok: true, json: async () => projStatus };
    if (u.includes('/api/projects-os')) return { ok: true, json: async () => ({ items: [{ id: 'project_1', title: '测试项目' }] }) };
    if (u.includes('/api/ops/overview')) return { ok: true, json: async () => ({ projects: { total: 1, running: 0, waiting: 0, blocked: 0, approval: 1, failed: 0 }, workforce: { running: 1, waiting: 0, blocked: 0, error: 0, idle: 0 }, recent_activity: [], calculated_at: 'now' }) };
    if (u.includes('/api/sessions')) return { ok: true, json: async () => ({ items: [], count: 0 }) };
    return { ok: true, json: async () => ({}) };
  }));
}

function wrap(node: React.ReactNode) {
  return render(<ConversationProvider>{node}</ConversationProvider>);
}

beforeEach(() => { mockApi(); });

describe('AfConversationCenter (K9 中栏)', () => {
  it('渲染会话列表 + 消息流 + 输入区', async () => {
    wrap(<AfConversationCenter />);
    await waitFor(() => expect(screen.getByText('测试会话')).toBeTruthy());
    expect(screen.getByText(/我想做一个 App/)).toBeTruthy();
    expect(screen.getByPlaceholderText(/和公司说话/)).toBeTruthy();
  });

  it('Work 状态内嵌 (真实投影)', async () => {
    wrap(<AfConversationCenter />);
    await waitFor(() => expect(screen.getByText(/任务A/)).toBeTruthy());
    expect(screen.getByText('RUNNING')).toBeTruthy();
  });

  it('发送 → 追加 AI 回复', async () => {
    wrap(<AfConversationCenter />);
    await waitFor(() => expect(screen.getByPlaceholderText(/和公司说话/)).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText(/和公司说话/), { target: { value: '开始做' } });
    fireEvent.click(screen.getByText('发送'));
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
    expect(screen.getByText(/产物预览会在这里显示/)).toBeTruthy();
  });
});

describe('AfContextNav (K9 左栏)', () => {
  it('渲染 Context 导航 (品牌/对话/项目/运行/审批)', async () => {
    wrap(<AfContextNav collapsed={false} />);
    await waitFor(() => expect(screen.getByText('AI Factory')).toBeTruthy());
    expect(screen.getByText(/我的工作/)).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/测试项目/)).toBeTruthy());
    expect(screen.getByText(/待审批/)).toBeTruthy();
  });
});
