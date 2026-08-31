/**
 * K6 Human Console 页面测试。
 * - ConversationPage: 默认首页, 会话列表/消息流/发送/Work 状态
 * - ControlTowerPage: 全局视图/谁在工作/项目钻取
 * - WorkPage: 项目→Sprint→Task + Approval
 */
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationPage } from '../pages/ConversationPage';
import { ControlTowerPage } from '../pages/ControlTowerPage';
import { WorkPage } from '../pages/WorkPage';

const conv = {
  id: 'conv_abc', type: 'conv', version: 3, status: 'OPEN',
  metadata: { title: '记账 App' },
  messages: [
    { id: 'm1', content: '我想做一个记账 App', intent: 'DISCUSS', actor: 'human', at: 't1' },
    { id: 'm2', content: '好的,我们聊聊。目标用户是谁?', intent: 'REPLY', actor: 'system', at: 't2' },
  ],
  state: { goal: '记账 App', confirmed_decisions: ['个人用户'], work_items: [{ id: 'task_1', title: '记账', status: 'RUNNING' }] },
};

const overview = {
  projects: { total: 1, running: 1, waiting: 0, blocked: 0, approval: 0, failed: 0 },
  workforce: { running: 1, waiting: 0, blocked: 0, error: 0, idle: 1 },
  recent_activity: [{ timestamp: 't', event_type: 'TASK_RUNNING', correlation_id: 'c' }],
  calculated_at: 'now',
};

const who = {
  agents: [{ agent: 'dev', tasks: 1, state: 'RUNNING', current_work: '记账' }],
  count: 1, calculated_at: 'now',
};

const drill = {
  project: { id: 'project_1', title: '记账', status: 'ACTIVE', progress: { completed: 1, total: 2, percentage: 50 } },
  sprints: [{
    sprint: { id: 'sprint_1', title: 'S1', status: 'ACTIVE', progress: { completed: 1, total: 2, percentage: 50 } },
    tasks: [{ id: 'task_1', title: '记账', status: 'COMPLETED', operational_state: 'COMPLETED', why: 'run ok' }],
  }],
};

const projStatus = {
  project_id: 'project_1', title: '记账', status: 'ACTIVE',
  progress: { completed: 1, failed: 0, running: 0, blocked: 0, waiting: 1, total: 2, percentage: 50 },
  sprints: [{
    sprint_id: 'sprint_1', title: 'S1', status: 'ACTIVE',
    progress: { completed: 1, failed: 0, running: 0, blocked: 0, total: 2, percentage: 50 },
    tasks: [{ id: 'task_1', title: '记账', status: 'COMPLETED', production_run_id: 'prun_1' }],
  }],
};

function mockApi() {
  const fetchMock = vi.fn(async (url: string) => {
    const u = String(url);
    if (u.includes('/api/conversations/') && u.includes('/messages')) {
      return { ok: true, json: async () => ({ message_id: 'm3', intent: 'REPLY', reply: { text: '收到', status: 'OK' }, conversation_version: 4 }) };
    }
    if (u.includes('/api/conversations/conv_abc')) {
      return { ok: true, json: async () => conv };
    }
    if (u.includes('/api/conversations')) {
      return { ok: true, json: async () => ({ items: [conv] }) };
    }
    if (u.includes('/api/ops/overview')) return { ok: true, json: async () => overview };
    if (u.includes('/api/ops/who-working')) return { ok: true, json: async () => who };
    if (u.includes('/api/ops/drill/')) return { ok: true, json: async () => drill };
    if (u.includes('/api/projects-os/') && u.includes('/status')) return { ok: true, json: async () => projStatus };
    if (u.includes('/api/projects-os')) return { ok: true, json: async () => ({ items: [{ id: 'project_1', title: '记账' }] }) };
    if (u.includes('/api/tasks/') && u.includes('/approval')) return { ok: true, json: async () => ({ approval_id: 'appr_1', status: 'PENDING', task_id: 'task_1', risk: 'HIGH' }) };
    return { ok: true, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
}

beforeEach(() => { mockApi(); });

describe('ConversationPage (K6 默认首页)', () => {
  it('渲染会话列表 + 消息流', async () => {
    render(<ConversationPage />);
    await waitFor(() => expect(screen.getByText('记账 App')).toBeTruthy());
    expect(screen.getByText(/我想做一个记账 App/)).toBeTruthy();
  });

  it('Work 状态内嵌 (真实投影)', async () => {
    render(<ConversationPage />);
    await waitFor(() => expect(screen.getByText('记账')).toBeTruthy());
    expect(screen.getByText('RUNNING')).toBeTruthy();
  });
});

describe('ControlTowerPage (K6 实时视图)', () => {
  it('全局视图 + 谁在工作', async () => {
    render(<ControlTowerPage />);
    await waitFor(() => expect(screen.getByText(/Control Tower/)).toBeTruthy(), { timeout: 3000 });
    expect(screen.getByText('运行中')).toBeTruthy();
    expect(screen.getByText('RUNNING')).toBeTruthy();
  });

  it('项目钻取 (task→why)', async () => {
    render(<ControlTowerPage />);
    await waitFor(() => expect(screen.getAllByRole('button').length).toBeGreaterThan(0), { timeout: 3000 });
    const btn = screen.getAllByRole('button').find((b) => b.textContent?.includes('记账'));
    expect(btn).toBeTruthy();
    fireEvent.click(btn!);
    await waitFor(() => expect(screen.getByText(/run ok/)).toBeTruthy(), { timeout: 3000 });
  });
});

describe('WorkPage (K6 Work 视图)', () => {
  it('项目→Sprint→Task', async () => {
    render(<WorkPage />);
    await waitFor(() => expect(screen.getAllByText('记账').length).toBeGreaterThan(0), { timeout: 3000 });
    fireEvent.click(screen.getAllByText('记账')[0]);
    await waitFor(() => expect(screen.getByText(/S1/)).toBeTruthy(), { timeout: 3000 });
    expect(screen.getAllByText(/50%/).length).toBeGreaterThan(0);
  });

  it('Approval 按钮 → 审批请求', async () => {
    render(<WorkPage />);
    await waitFor(() => expect(screen.getAllByText('记账').length).toBeGreaterThan(0), { timeout: 3000 });
    fireEvent.click(screen.getAllByText('记账')[0]);
    await waitFor(() => expect(screen.getAllByText('审批').length).toBeGreaterThan(0), { timeout: 3000 });
    fireEvent.click(screen.getAllByText('审批')[0]);
    await waitFor(() => expect(screen.getByText(/PENDING/)).toBeTruthy(), { timeout: 3000 });
  });
});
