/**
 * src/test/af-monitor.test.tsx — 📊 监控中心 (M4.2: 概览/趋势/多维/记录流/告警)。
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AfMonitorPage } from '../pages/workspace/AfMonitorPage';

function jsonResponse(v: unknown): Response {
  return { ok: true, status: 200, json: async () => v } as Response;
}

const DETAIL = {
  summary: {
    external: { total: 5, success: 4, failed: 1, success_rate: 0.8, first_pass_rate: 0.8, verify_pass_rate: 1.0, verified: 2, avg_duration_ms: 2000, p90_duration_ms: 3000, total_rework: 1 },
    internal: { total: 3, success: 2, failed: 1, success_rate: 0.67, first_pass_rate: 1.0, verify_pass_rate: null, verified: 0, avg_duration_ms: 1000, p90_duration_ms: 1500, total_rework: 0 },
    combined: { total: 8, success: 6, failed: 2, success_rate: 0.75, first_pass_rate: 0.88, verify_pass_rate: 1.0, verified: 2, avg_duration_ms: 1600, p90_duration_ms: 2500, total_rework: 1 },
  },
  trend: [
    { date: '2026-08-26', count: 5, success: 4, failed: 1 },
    { date: '2026-08-27', count: 3, success: 2, failed: 1 },
  ],
  by_executor: [{ key: 'codex', total: 5, success: 4, failed: 1, success_rate: 0.8, first_pass_rate: 0.8, verify_pass_rate: 1.0, avg_duration_ms: 2000, total_rework: 1 }],
  by_agent: [
    { key: 'claude.architecture-examiner', total: 3, success: 2, failed: 1, success_rate: 0.67, first_pass_rate: 1.0, verify_pass_rate: null, avg_duration_ms: 1500, total_rework: 0 },
    { key: 'backend-1', total: 2, success: 1, failed: 1, success_rate: 0.5, first_pass_rate: 1.0, verify_pass_rate: null, avg_duration_ms: 800, total_rework: 0 },
  ],
  by_project: [{ key: '/tmp/p', total: 5, success: 4, failed: 1, success_rate: 0.8, first_pass_rate: 0.8, verify_pass_rate: 1.0, avg_duration_ms: 2000, total_rework: 1 }],
  rework_reasons: [{ reason: '测试挂了', count: 1 }],
  verify_methods: [{ method: 'pytest·pass', count: 2 }],
  recent: [
    { result_id: 'EXS-1', executor_id: 'claude', host_agent: 'architecture-examiner', task: '审查架构', result: 'success', duration_ms: 2000, timestamp: '2026-08-27T00:00:00Z', verify: { method: 'pytest', result: 'pass', score: 0.9 }, rework: { count: 0, reasons: [] }, command: 'claude -p --agent architecture-examiner' },
    { result_id: 'EXS-2', executor_id: null, agent: 'backend-1', task: '写接口', result: 'failed', duration_ms: 500, timestamp: '2026-08-26T00:00:00Z', error: 'provider 5xx' },
  ],
  alerts: [{ severity: 'high', executor_id: 'codex', type: 'consecutive_failures', detail: '连续失败 3 次' }],
};

function stubApi() {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith('/api/external-ai/monitor')) return jsonResponse(DETAIL);
    if (url === '/api/external-ai/route') return jsonResponse({ pick: 'claude.architecture-examiner', pick_kind: 'agent', work_type: 'arch', reason: '能力匹配(architect) + 历史效果分 5.5', alternatives: ['claude.architecture-examiner', 'codex.architecture-examiner'], degraded: false, tier_advice: 'medium|high' });
    if (url === '/api/external-ai/auto') return jsonResponse({ route: { pick: 'claude.architecture-examiner', work_type: 'arch', reason: '能力匹配(architect) + 历史效果分 5.5', alternatives: [] }, execution: { executor_id: 'claude', mode: 'borrowed-shell', host_agent: 'architecture-examiner', exit_code: 0, output: '审查完成', result_id: 'EXS-A1' }, verify: { method: 'pytest', result: 'pass', score: 1.0 } });
    return jsonResponse({});
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => { vi.unstubAllGlobals(); });

describe('AfMonitorPage (📊 监控中心)', () => {
  it('概览卡 + 趋势 + 多维 + 记录流 + 告警', async () => {
    stubApi();
    render(<AfMonitorPage />);
    // 概览 (combined)
    expect((await screen.findAllByText('执行次数')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('8').length).toBeGreaterThan(0); // combined total
    expect(screen.getAllByText('75%').length).toBeGreaterThan(0); // success_rate
    // 多维表: 按执行器
    expect(await screen.findByText('按执行器')).toBeInTheDocument();
    expect(screen.getByText('按 Agent / Skill')).toBeInTheDocument();
    expect(screen.getByText('claude.architecture-examiner')).toBeInTheDocument();
    expect(screen.getByTestId('af-monitor-compare')).toBeInTheDocument(); // 内部 vs 外部对比
    // 回修原因/验证方式
    expect(screen.getByText('🔄 测试挂了 ×1')).toBeInTheDocument();
    expect(screen.getByText('✅ pytest·pass ×2')).toBeInTheDocument();
    // 记录流
    expect(screen.getByText('审查架构')).toBeInTheDocument();
    // 告警
    expect(screen.getByText(/连续失败 3 次/)).toBeInTheDocument();
  });

  it('作用域切换: 自身能力只看内部记录', async () => {
    const user = userEvent.setup();
    stubApi();
    render(<AfMonitorPage />);
    await user.click(screen.getByRole('tab', { name: '自身能力' }));
    // 内部 summary total=3
    expect(screen.getAllByText('3').length).toBeGreaterThan(0);
    // 记录流只含内部 (backend-1), 不含 claude
    expect(screen.getByText('写接口')).toBeInTheDocument();
    expect(screen.queryByText('审查架构')).not.toBeInTheDocument();
  });

  it('路由测试: 输入任务 → 显示选谁/理由/候选; 一键委派', async () => {
    const user = userEvent.setup();
    stubApi();
    render(<AfMonitorPage />);
    await user.click(screen.getByRole('tab', { name: '外部能力' }));
    await user.type(screen.getByLabelText('路由任务'), '帮忙审查系统架构');
    await user.click(screen.getByRole('button', { name: '🧭 路由' }));
    const result = await screen.findByTestId('af-monitor-route-result');
    expect(result).toHaveTextContent('claude.architecture-examiner');
    expect(result).toHaveTextContent('arch');
    // 一键委派
    await user.click(screen.getByRole('button', { name: '🚀 路由+委派' }));
    const exec = await screen.findByTestId('af-monitor-route-exec');
    expect(exec).toHaveTextContent('EXS-A1');
    expect(exec).toHaveTextContent('验证 (pytest): pass');
  });

  it('记录流点击钻取: 显示命令/验证/错误', async () => {
    const user = userEvent.setup();
    stubApi();
    render(<AfMonitorPage />);
    await user.click(await screen.findByText('审查架构'));
    expect(await screen.findByText(/验证: pytest · pass/)).toBeInTheDocument();
    expect(screen.getByText('claude -p --agent architecture-examiner')).toBeInTheDocument();
  });
});
