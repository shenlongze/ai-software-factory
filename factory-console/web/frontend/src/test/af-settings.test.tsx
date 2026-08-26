/**
 * src/test/af-settings.test.tsx — 设置管理面 (v1.1.102)。
 *
 * 验证: LLM 管理 (启用/停用/默认模型) · Agent/Skill 注册移除 · MCP 连接/移除。
 * 方法感知 fetch 桩 (GET/POST/PATCH/DELETE 同路径不同响应)。
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { AfSettings } from '../pages/workspace/AfSettings';

function jsonResponse(v: unknown): Response {
  return { ok: true, status: 200, json: async () => v } as Response;
}

function stubApi(overrides: Record<string, unknown> = {}) {
  const calls: { method: string; url: string; body?: unknown }[] = [];
  const state: { agents: unknown[]; skills: unknown[]; mcpConnections: unknown[] } = {
    agents: [],
    skills: [],
    mcpConnections: [],
  };
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ method, url, body });
    const key = `${method} ${url}`;
    if (key in overrides) return jsonResponse((overrides as Record<string, unknown>)[key]);
    if (method === 'GET') {
      if (url.includes('/config/llm')) return jsonResponse({ providers: [], selected: { provider_id: null, model: null } });
      if (url.includes('/agents')) return jsonResponse({ agents: state.agents, count: state.agents.length });
      if (url.includes('/skills')) return jsonResponse({ skills: state.skills, count: state.skills.length });
      if (url.includes('/mcp/connections')) return jsonResponse({ connections: state.mcpConnections, count: state.mcpConnections.length });
      if (url.includes('/mcp/tools')) return jsonResponse({ tools: [], count: 0 });
    }
    if (method === 'POST' && url === '/api/agents') {
      const rec = { id: body?.id, name: body?.id, role: body?.role, skills: body?.skills ?? [] };
      state.agents.push(rec);
      return jsonResponse(rec);
    }
    if (method === 'POST' && url === '/api/skills') {
      const rec = { id: body?.id, name: body?.name ?? body?.id, category: body?.category ?? 'general', version: '1.0' };
      state.skills.push(rec);
      return jsonResponse(rec);
    }
    if (method === 'POST' && url === '/api/mcp/connections') {
      const rec = { id: 'mcp-1', name: body?.name, server_url: body?.server_url, transport: 'mock', enabled: true, tools: [] };
      state.mcpConnections.push(rec);
      return jsonResponse(rec);
    }
    if (method === 'DELETE' && url === '/api/mcp/connections/mcp-1') {
      state.mcpConnections = [];
      return jsonResponse({ deleted: true });
    }
    return jsonResponse({ ok: true });
  });
  vi.stubGlobal('fetch', fn);
  return { fn, calls };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AfSettings (设置管理面)', () => {
  it('LLM tab: 渲染 Provider 卡片 + 停用动作调 PATCH /api/config/llm', async () => {
    const { calls } = stubApi({
      'GET /api/config/llm': {
        providers: [
          { id: 'deepseek', enabled: true, models: ['deepseek-chat', 'deepseek-reasoner'], key_configured: true, default_model: 'deepseek-chat' },
        ],
        selected: { provider_id: 'deepseek', model: 'deepseek-chat' },
      },
    });
    render(<AfSettings />);
    const card = await screen.findByTestId('af-llm-deepseek');
    expect(within(card).getByText('已启用')).toBeInTheDocument();
    expect(within(card).getByText(/Key 已配置/)).toBeInTheDocument();
    await userEvent.click(within(card).getByRole('button', { name: '停用' }));
    expect(calls.some((c) => c.method === 'PATCH' && c.url === '/api/config/llm' && (c.body as { enabled?: boolean })?.enabled === false)).toBe(true);
  });

  it('Agent tab: 注册 → POST /api/agents + 列表刷新', async () => {
    const { calls } = stubApi();
    render(<AfSettings />);
    await userEvent.click(screen.getByRole('tab', { name: '👤 Agent' }));
    await userEvent.type(screen.getByLabelText('Agent id'), 'pm-1');
    await userEvent.type(screen.getByLabelText('Agent role'), 'product_manager');
    await userEvent.type(screen.getByLabelText('Agent skills'), 'prd, discovery');
    await userEvent.click(screen.getByRole('button', { name: '＋ 注册 Agent' }));
    expect(calls.some((c) => c.method === 'POST' && c.url === '/api/agents')).toBe(true);
    const posted = calls.find((c) => c.method === 'POST' && c.url === '/api/agents')?.body as { id: string; skills: string[] };
    expect(posted.id).toBe('pm-1');
    expect(posted.skills).toEqual(['prd', 'discovery']);
  });

  it('Skill tab: 注册 → POST /api/skills', async () => {
    const { calls } = stubApi();
    render(<AfSettings />);
    await userEvent.click(screen.getByRole('tab', { name: '🧩 Skill' }));
    await userEvent.type(screen.getByLabelText('Skill id'), 'python-api');
    await userEvent.type(screen.getByLabelText('Skill name'), 'Python API');
    await userEvent.click(screen.getByRole('button', { name: '＋ 注册 Skill' }));
    expect(calls.some((c) => c.method === 'POST' && c.url === '/api/skills')).toBe(true);
  });

  it('MCP tab: 连接 → POST /api/mcp/connections + 移除 → DELETE', async () => {
    const { calls } = stubApi();
    render(<AfSettings />);
    await userEvent.click(screen.getByRole('tab', { name: '🔌 MCP' }));
    await userEvent.type(screen.getByLabelText('MCP 名称'), 'weather');
    await userEvent.type(screen.getByLabelText('MCP 地址'), 'https://mock.example/tools');
    await userEvent.click(screen.getByRole('button', { name: '＋ 连接' }));
    expect(calls.some((c) => c.method === 'POST' && c.url === '/api/mcp/connections')).toBe(true);
    // 连接后列表出现 → 移除 → DELETE
    const card = await screen.findByTestId('af-mcp-mcp-1');
    await userEvent.click(within(card).getByRole('button', { name: '移除' }));
    expect(calls.some((c) => c.method === 'DELETE' && c.url === '/api/mcp/connections/mcp-1')).toBe(true);
  });
});
