/**
 * F-01-FRONTEND-STOP 回归测试 (P1):
 * Stop 后绝不进入 fallback 重新执行 — 第二次 execution 禁止。
 *
 * Test 1: Stop → AbortError → 不调用 sendSessionMessage (fallback=0)
 * Test 3: Stop 后不重新执行 (无第二次 stream/sync POST)
 * Test 5: Stop A 后 Send B 正常 (cancelledRef 不污染下一次)
 * Test 7: 多次 Stop 不产生 send
 */
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationProvider } from '../components/af/ConversationContext';
import { AfConversationCenter } from '../components/af/AfConversationCenter';

// 调用计数
let cancelCalls = 0;
let syncSendCalls = 0;
let streamCalls = 0;

function mockApi() {
  cancelCalls = 0;
  syncSendCalls = 0;
  streamCalls = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url);
    const method = (init?.method ?? 'GET').toUpperCase();
    // 会话列表
    if (u.includes('/api/sessions') && u.includes('/messages') && method === 'GET') {
      return { ok: true, json: async () => ({ items: [] }) };
    }
    if (u.includes('/api/sessions') && u.includes('/messages') && u.includes('stream=1')) {
      streamCalls += 1;
      // stream 挂起; signal abort → AbortError (模拟用户停止)
      return new Promise((_resolve, reject) => {
        const sig = init?.signal as AbortSignal | undefined;
        sig?.addEventListener('abort', () => {
          const e = new Error('The user aborted a request.');
          e.name = 'AbortError';
          reject(e);
        });
      });
    }
    if (u.includes('/api/sessions') && u.includes('/messages') && method === 'POST') {
      syncSendCalls += 1;  // 同步 fallback — Stop 后必须为 0
      return { ok: true, json: async () => ({
        user: { id: 'u1', session_id: 'conv_1', role: 'user', content: 'x', created_at: 't' },
        assistant: { id: 'a1', session_id: 'conv_1', role: 'assistant', content: 'sync', created_at: 't' },
      }) };
    }
    if (u.includes('/cancel')) {
      cancelCalls += 1;
      return { ok: true, json: async () => ({ ok: true, status: 'CANCELLING' }) };
    }
    if (u.includes('/api/sessions')) {
      return { ok: true, json: async () => ({ items: [{ id: 'conv_1', scope: 'company', project_id: null, title: '测试', status: 'active', created_at: 't0', updated_at: 't1', summary: null, run_ids: [] }], count: 1 }) };
    }
    return { ok: true, json: async () => ({}) };
  }));
}

function wrap(node: React.ReactNode) {
  return render(<ConversationProvider>{node}</ConversationProvider>);
}

async function sendText(text: string) {
  const input = await screen.findByPlaceholderText(/和公司说话/);
  fireEvent.change(input, { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: /发送/i }));
}

beforeEach(() => mockApi());

describe('F-01-FRONTEND-STOP (P1 回归)', () => {
  it('Test 1: Stop → AbortError → 绝不 fallback 同步发送', async () => {
    wrap(<AfConversationCenter />);
    await screen.findByPlaceholderText(/和公司说话/);
    await sendText('执行任务');
    // 等待 sending (停止按钮出现)
    await waitFor(() => expect(screen.getByRole('button', { name: /停止生成/i })).toBeTruthy());
    // 点击停止
    fireEvent.click(screen.getByRole('button', { name: /停止生成/i }));
    // cancel API 必须被调用
    await waitFor(() => expect(cancelCalls).toBeGreaterThanOrEqual(1));
    // 核心断言: 同步 fallback = 0 (绝不第二次 execution)
    await new Promise((r) => setTimeout(r, 50));
    expect(syncSendCalls).toBe(0);
    expect(streamCalls).toBe(1);  // 只有一次 stream execution
  });

  it('Test 3: Stop 后不产生第二次 stream/sync execution', async () => {
    wrap(<AfConversationCenter />);
    await screen.findByPlaceholderText(/和公司说话/);
    await sendText('任务A');
    await waitFor(() => expect(screen.getByRole('button', { name: /停止生成/i })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /停止生成/i }));
    await waitFor(() => expect(cancelCalls).toBeGreaterThanOrEqual(1));
    await new Promise((r) => setTimeout(r, 50));
    expect(streamCalls).toBe(1);   // 无第二次 stream
    expect(syncSendCalls).toBe(0); // 无同步 fallback
  });

  it('Test 5: Stop A 后 Send B 正常执行 (cancelledRef 不污染下一次)', async () => {
    wrap(<AfConversationCenter />);
    await screen.findByPlaceholderText(/和公司说话/);
    // Send A → Stop A
    await sendText('任务A');
    await waitFor(() => expect(screen.getByRole('button', { name: /停止生成/i })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /停止生成/i }));
    await waitFor(() => expect(cancelCalls).toBe(1));
    // 等 A 结束 (sending false → 停止按钮消失)
    await waitFor(() => expect(screen.queryByRole('button', { name: /停止生成/i })).toBeFalsy());
    // Send B → 正常进入 sending (stream 第二次 execution)
    await sendText('任务B');
    await waitFor(() => expect(screen.getByRole('button', { name: /停止生成/i })).toBeTruthy());
    expect(streamCalls).toBe(2);  // B 正常产生 execution
    fireEvent.click(screen.getByRole('button', { name: /停止生成/i }));
    await waitFor(() => expect(cancelCalls).toBe(2));  // B 自己的 cancel
    expect(syncSendCalls).toBe(0);
  });

  it('Test 7: 多次点击 Stop 不产生 send', async () => {
    wrap(<AfConversationCenter />);
    await screen.findByPlaceholderText(/和公司说话/);
    await sendText('任务C');
    await waitFor(() => expect(screen.getByRole('button', { name: /停止生成/i })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /停止生成/i }));
    fireEvent.click(screen.getByRole('button', { name: /停止生成/i }));
    fireEvent.click(screen.getByRole('button', { name: /停止生成/i }));
    await waitFor(() => expect(cancelCalls).toBeGreaterThanOrEqual(1));
    await new Promise((r) => setTimeout(r, 50));
    expect(syncSendCalls).toBe(0);
    expect(streamCalls).toBe(1);  // 仍只有一次 execution
  });
});
