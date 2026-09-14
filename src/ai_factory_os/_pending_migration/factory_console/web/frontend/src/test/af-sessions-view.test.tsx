/**
 * src/test/af-sessions-view.test.tsx — 会话管理视图 (S35-UI)。
 *
 * 验证 AfSessionsView 从统一后端渲染真实会话 (GET /api/sessions):
 * - 会话列表 (标题/ID/作用域/时间)
 * - 搜索过滤
 * - 归档切换
 * - 删除调用 DELETE /api/sessions/{id}
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AfSessionsView } from '../components/af/AfSessionsView';
import { stubFetch } from './fixtures';
import { ConversationProvider } from '../components/af/ConversationContext';

afterEach(() => {
  vi.unstubAllGlobals();
});

const SESSIONS = [
  { id: 'sess-1', title: '飞机大战', status: 'active', scope: 'company', updated_at: '2026-09-01T02:00:00+00:00' },
  { id: 'sess-2', title: '番茄钟', status: 'active', scope: 'project', project_id: 'P-5be3a04a', updated_at: '2026-09-01T01:00:00+00:00' },
  { id: 'sess-3', title: '旧会话', status: 'archived', scope: 'company', updated_at: '2026-08-31T00:00:00+00:00' },
];

function renderView() {
  return render(
    <ConversationProvider initialProjectId={null}>
      <AfSessionsView />
    </ConversationProvider>,
  );
}

describe('AfSessionsView 会话管理 (S35-UI)', () => {
  it('渲染真实会话列表 (活跃会话)', async () => {
    stubFetch({ '/api/sessions': SESSIONS });
    renderView();
    expect(await screen.findByText('飞机大战')).toBeInTheDocument();
    expect(screen.getByText('番茄钟')).toBeInTheDocument();
    // 归档会话默认隐藏
    expect(screen.queryByText('旧会话')).not.toBeInTheDocument();
  });

  it('查看归档切换显示归档会话', async () => {
    stubFetch({ '/api/sessions': SESSIONS });
    renderView();
    await screen.findByText('飞机大战');
    fireEvent.click(screen.getByText(/查看归档/));
    expect(await screen.findByText('旧会话')).toBeInTheDocument();
    expect(screen.queryByText('飞机大战')).not.toBeInTheDocument();
  });

  it('搜索过滤', async () => {
    stubFetch({ '/api/sessions': SESSIONS });
    renderView();
    await screen.findByText('飞机大战');
    fireEvent.change(screen.getByLabelText('搜索会话'), { target: { value: '番茄' } });
    expect(screen.getByText('番茄钟')).toBeInTheDocument();
    expect(screen.queryByText('飞机大战')).not.toBeInTheDocument();
  });

  it('删除调用 DELETE API', async () => {
    const fetchMock = stubFetch({ '/api/sessions': SESSIONS });
    window.confirm = vi.fn(() => true);
    window.alert = vi.fn();
    renderView();
    await screen.findByText('飞机大战');
    fireEvent.click(screen.getAllByTitle('删除')[0]);
    await waitFor(() => {
      const del = fetchMock.mock.calls.find((c) => String(c[0]).includes('/api/sessions/sess-1') && String(c[1]?.method) === 'DELETE');
      expect(del).toBeTruthy();
    });
  });
});
