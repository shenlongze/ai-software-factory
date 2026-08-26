/**
 * src/test/af-monitor.test.tsx — 📊 监控页 (M4: 自身/外部两 Tab)。
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AfMonitorPage } from '../pages/workspace/AfMonitorPage';

function jsonResponse(v: unknown): Response {
  return { ok: true, status: 200, json: async () => v } as Response;
}

function stubApi() {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === '/api/agents') return jsonResponse({ agents: [
      { id: 'backend-1', name: 'backend-1', role: 'backend-developer' },
      { id: 'claude.architecture-examiner', name: '架构审查', role: 'architect', source: 'claude' },
    ] });
    if (url === '/api/skills') return jsonResponse({ skills: [{ id: 's1' }, { id: 's2' }] });
    if (url === '/api/runtime-sessions?status=running') return jsonResponse({ items: [{ id: 'rs1', agent_id: 'backend-1', task_id: 'T1', status: 'RUNNING' }] });
    if (url === '/api/monitor?limit=5&offset=0') return jsonResponse({ version: 'v1.1.194', frontend: { up: true }, backend: { up: true } });
    if (url === '/api/external-ai') return jsonResponse({ adapters: [
      { id: 'codex', name: '本机 Codex', found: true, builtin: true, path: '/usr/bin/codex' },
    ] });
    if (url === '/api/external-ai/monitor') return jsonResponse({
      executors: [{ executor_id: 'codex', total: 5, success: 4, failed: 1, success_rate: 0.8, first_pass_rate: 0.8, verify_pass_rate: 1.0, verified: 2, avg_duration_ms: 2000, rework_total: 0, last_run_at: '2026-08-27T00:00:00Z' }],
      alerts: [{ severity: 'high', executor_id: 'codex', type: 'consecutive_failures', detail: '连续失败 3 次' }],
    });
    return jsonResponse({});
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => { vi.unstubAllGlobals(); });

describe('AfMonitorPage (📊 监控)', () => {
  it('自身能力 tab: 概览卡 + AI 员工(内部/外部) + 执行中', async () => {
    stubApi();
    render(<AfMonitorPage />);
    // 概览卡
    expect(await screen.findByText('AI 员工（内部 1）')).toBeInTheDocument();
    expect(screen.getByText('技能')).toBeInTheDocument();
    expect(screen.getAllByText('执行中任务').length).toBeGreaterThan(0);
    // 员工列表
    expect(screen.getByText('backend-1')).toBeInTheDocument();
    expect(screen.getByText(/架构审查/)).toBeInTheDocument();  // 外部 agent 带源
  });

  it('外部能力 tab: 指标表 + 告警', async () => {
    const user = userEvent.setup();
    stubApi();
    render(<AfMonitorPage />);
    await user.click(screen.getByRole('tab', { name: '外部能力' }));
    const table = await screen.findByTestId('af-monitor-table');
    expect(within(table).getByText('codex')).toBeInTheDocument();
    expect(within(table).getAllByText('80%').length).toBeGreaterThan(0);  // success_rate/first_pass
    // 告警
    expect(await screen.findByText(/连续失败 3 次/)).toBeInTheDocument();
  });
});
