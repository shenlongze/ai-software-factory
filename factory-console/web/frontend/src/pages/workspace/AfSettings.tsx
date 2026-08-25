/**
 * pages/workspace/AfSettings.tsx — 设置页 (WebUI #3, Founder 2026-08-26)。
 *
 * Tabs: LLM/模型 · Agent · Skill · MCP · 插件(占位)
 * 数据: GET /api/providers · /api/agents · /api/skills · /api/mcp/connections · /api/mcp/tools
 * 只读展示 (管理动作 add/remove 待后端 API, 后续补)。
 */

import { useEffect, useState } from 'react';

interface ProviderItem {
  id?: string;
  name?: string;
  type?: string;
  status?: string;
  models?: string[];
  capabilities?: string[];
}

interface AgentItem {
  id?: string;
  name?: string;
  role?: string;
  skills?: string[];
  status?: string;
}

interface SkillItem {
  id?: string;
  name?: string;
  category?: string;
  version?: string;
}

interface MCPConn {
  id?: string;
  name?: string;
  server_url?: string;
  transport?: string;
  enabled?: boolean;
}

const TABS = [
  { id: 'llm', label: '🤖 LLM / 模型' },
  { id: 'agent', label: '👤 Agent' },
  { id: 'skill', label: '🧩 Skill' },
  { id: 'mcp', label: '🔌 MCP' },
  { id: 'plugin', label: '📦 插件' },
] as const;

type TabId = (typeof TABS)[number]['id'];

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

export function AfSettings(): JSX.Element {
  const [tab, setTab] = useState<TabId>('llm');
  const [providers, setProviders] = useState<ProviderItem[]>([]);
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [mcps, setMcps] = useState<MCPConn[]>([]);
  const [mcpTools, setMcpTools] = useState<unknown[]>([]);
  const [msg] = useState<string>('');

  useEffect(() => {
    getJson<ProviderItem[]>('/api/providers').then(setProviders).catch(() => setProviders([]));
    getJson<{ agents: AgentItem[] }>('/api/agents')
      .then((d) => setAgents(d.agents ?? []))
      .catch(() => setAgents([]));
    getJson<{ skills: SkillItem[] }>('/api/skills')
      .then((d) => setSkills(d.skills ?? []))
      .catch(() => setSkills([]));
    getJson<{ connections: MCPConn[] }>('/api/mcp/connections')
      .then((d) => setMcps(d.connections ?? []))
      .catch(() => setMcps([]));
    getJson<{ tools: unknown[] }>('/api/mcp/tools')
      .then((d) => setMcpTools(d.tools ?? []))
      .catch(() => setMcpTools([]));
  }, []);

  const table = (cols: string[], rows: string[][]) => (
    <table className="af-manage-table">
      <thead>
        <tr>
          {cols.map((c) => (
            <th key={c}>{c}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td colSpan={cols.length} className="af-home-note">
              （暂无数据）
            </td>
          </tr>
        ) : (
          rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j}>{c}</td>
              ))}
            </tr>
          ))
        )}
      </tbody>
    </table>
  );

  return (
    <div className="af-settings" data-testid="af-settings">
      <h2 className="af-detail-name">设置</h2>
      <div className="af-settings-tabs" role="tablist" aria-label="设置分类">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`af-settings-tab${tab === t.id ? ' active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {msg ? <p className="af-composer-msg">{msg}</p> : null}

      <div className="af-settings-body" data-testid={`af-settings-${tab}`}>
        {tab === 'llm' && (
          <section>
            <h3 className="af-settings-h3">🤖 LLM / 模型 Provider</h3>
            {table(
              ['ID', '名称', '类型', '状态', '模型'],
              providers.map((p) => [p.id ?? '', p.name ?? '', p.type ?? '', p.status ?? '', (p.models ?? []).join(', ')]),
            )}
            <p className="af-home-note">API Key 配置走 CLI: factory config / factory doctor（不在此页存明文 key）</p>
          </section>
        )}
        {tab === 'agent' && (
          <section>
            <h3 className="af-settings-h3">👤 Agent（{agents.length}）</h3>
            {table(
              ['ID', '名称', '角色', 'Skills', '状态'],
              agents.map((a) => [a.id ?? '', a.name ?? '', a.role ?? '', (a.skills ?? []).join(', '), a.status ?? '']),
            )}
            <p className="af-home-note">管理动作（add/remove）走 CLI: factory agent；Web 管理待后端 API 后续补</p>
          </section>
        )}
        {tab === 'skill' && (
          <section>
            <h3 className="af-settings-h3">🧩 Skill（{skills.length}）</h3>
            {table(
              ['ID', '名称', '分类', '版本'],
              skills.map((s) => [s.id ?? '', s.name ?? '', s.category ?? '', s.version ?? '']),
            )}
          </section>
        )}
        {tab === 'mcp' && (
          <section>
            <h3 className="af-settings-h3">🔌 MCP 连接（{mcps.length}）· Tool（{mcpTools.length}）</h3>
            {table(
              ['ID', '名称', '地址', '传输', '启用'],
              mcps.map((m) => [m.id ?? '', m.name ?? '', m.server_url ?? '', m.transport ?? '', m.enabled ? '✅' : '—']),
            )}
            <p className="af-home-note">MCP 管理走 CLI: factory mcp list/connect/remove</p>
          </section>
        )}
        {tab === 'plugin' && (
          <section>
            <h3 className="af-settings-h3">📦 插件</h3>
            <p className="af-home-note">插件体系规划中（外部 skill/agent/mcp 接入 + 模板/市场）— 见战役规划 K-10 / 远期</p>
          </section>
        )}
      </div>
    </div>
  );
}
