import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { AuditPage } from '../pages/AuditPage';

/**
 * T8: 审计视图页测试 — 事件列表 / 类型计数 / 过滤 / 导出 CSV。
 * 数据源: GET /api/audit (stub fetch)。
 */
function jsonResponse(data: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => data,
  } as Response;
}

function stubAuditApi(events: unknown[] = []): ReturnType<typeof vi.fn> {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith('/api/audit')) {
      return jsonResponse({ items: events, count: events.length, counts: { TOOL_CALL: events.length } });
    }
    return jsonResponse({ items: [], count: 0, counts: {} });
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AuditPage (T8 审计视图)', () => {
  it('空态: 无事件 → 提示', async () => {
    stubAuditApi([]);
    render(<AuditPage />);
    expect(await screen.findByText(/暂无审计事件/)).toBeInTheDocument();
  });

  it('有事件 → 渲染表格行 + 类型计数', async () => {
    stubAuditApi([
      {
        event_type: 'TOOL_CALL',
        action: 'bash_exec',
        timestamp: '2026-08-28T12:00:00+00:00',
        trace_id: 'sess-abc',
        project_id: 'P-1',
        decision: 'allow',
        result: { ok: true },
      },
      {
        event_type: 'APPROVAL_REQUESTED',
        action: 'git_push',
        timestamp: '2026-08-28T12:01:00+00:00',
        trace_id: 'sess-abc',
        project_id: 'P-1',
        decision: 'pending',
        result: null,
      },
    ]);
    render(<AuditPage />);
    expect(await screen.findByTestId('audit-table')).toBeInTheDocument();
    expect(await screen.findByText('TOOL_CALL')).toBeInTheDocument();
    expect(await screen.findByText('bash_exec')).toBeInTheDocument();
    expect(await screen.findByText('git_push')).toBeInTheDocument();
    expect(await screen.findByText(/TOOL_CALL: 2/)).toBeInTheDocument();
    // 结果列: ok=true 显示 ✅
    expect(await screen.findAllByText('✅')).toHaveLength(1);
  });

  it('导出 CSV 按钮: 有事件时可用, 点击触发下载', async () => {
    stubAuditApi([
      {
        event_type: 'TOOL_CALL',
        action: 'bash_exec',
        timestamp: '2026-08-28T12:00:00+00:00',
        trace_id: 'sess-abc',
        project_id: 'P-1',
        decision: 'allow',
        result: { ok: true },
      },
    ]);
    const clickSpy = vi.fn();
    URL.createObjectURL = clickSpy as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL;
    render(<AuditPage />);
    const btn = await screen.findByRole('button', { name: /导出 CSV/ });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(clickSpy).toHaveBeenCalled();
  });

  it('过滤输入: 输入类型后触发重新请求', async () => {
    const fn = stubAuditApi([
      {
        event_type: 'TOOL_CALL',
        action: 'bash_exec',
        timestamp: '2026-08-28T12:00:00+00:00',
        trace_id: 'sess-abc',
        project_id: 'P-1',
        decision: 'allow',
        result: { ok: true },
      },
    ]);
    render(<AuditPage />);
    await screen.findByTestId('audit-table');
    const input = screen.getByLabelText('事件类型过滤');
    fireEvent.change(input, { target: { value: 'APPROVAL' } });
    // 防抖/重取后请求应带 event_type=APPROVAL
    await new Promise((r) => setTimeout(r, 50));
    const auditCalls = fn.mock.calls.filter(([u]) => String(u).includes('/api/audit'));
    expect(auditCalls.length).toBeGreaterThan(1);
    expect(String(auditCalls[auditCalls.length - 1][0])).toContain('event_type=APPROVAL');
  });
});
