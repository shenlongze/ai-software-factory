/**
 * pages/workspace/AfSettings.tsx — 设置页 (v1.1.102 完善: 管理面, 非只读)。
 *
 * Tabs: LLM/模型 · Agent · Skill · MCP · 插件
 * 管理动作 (真实 API):
 *   LLM   — GET/PATCH /api/config/llm (启用/停用 Provider + 默认模型)
 *   Agent — GET /api/agents + POST/DELETE /api/agents (注册/移除)
 *   Skill — GET /api/skills + POST/DELETE /api/skills (注册/移除)
 *   MCP   — GET/POST/DELETE /api/mcp/connections + GET /api/mcp/tools
 *           (连接/移除 + Tool 清单)
 * 诚实原则: key 只显示"已配置/未配置" (不存明文); 动作失败 → 明确提示。
 */

import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { LlmProviderConfig } from '../../models/types';

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

interface MCPTool {
  id?: string;
  name?: string;
  description?: string;
  server?: string;
}

const TABS = [
  { id: 'llm', label: '🤖 LLM / 模型' },
  { id: 'agent', label: '👤 Agent' },
  { id: 'skill', label: '🧩 Skill' },
  { id: 'mcp', label: '🔌 MCP' },
  { id: 'plugin', label: '📦 插件' },
] as const;

type TabId = (typeof TABS)[number]['id'];

export function AfSettings(): JSX.Element {
  const [tab, setTab] = useState<TabId>('llm');
  const [msg, setMsg] = useState<string>('');

  // LLM
  const [providers, setProviders] = useState<LlmProviderConfig[]>([]);
  const [selected, setSelected] = useState<{ provider_id: string | null; model: string | null }>({
    provider_id: null,
    model: null,
  });
  // Agent / Skill
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [skills, setSkills] = useState<SkillItem[]>([]);
  // MCP
  const [mcps, setMcps] = useState<MCPConn[]>([]);
  const [mcpTools, setMcpTools] = useState<MCPTool[]>([]);

  const flash = (text: string) => {
    setMsg(text);
    window.setTimeout(() => setMsg(''), 4000);
  };

  const loadLlm = useCallback(() => {
    api
      .llmConfig()
      .then((d) => {
        setProviders(d.providers ?? []);
        setSelected(d.selected ?? { provider_id: null, model: null });
      })
      .catch(() => setProviders([]));
  }, []);

  const loadAgents = useCallback(() => {
    api
      .agents()
      .then(setAgents)
      .catch(() => setAgents([]));
  }, []);

  const loadSkills = useCallback(() => {
    api
      .skills()
      .then((d) => setSkills(d.skills ?? []))
      .catch(() => setSkills([]));
  }, []);

  const loadMcp = useCallback(() => {
    api
      .mcpConnections()
      .then((d) => setMcps(d.connections ?? []))
      .catch(() => setMcps([]));
    api
      .mcpTools()
      .then((d) => setMcpTools(d.tools ?? []))
      .catch(() => setMcpTools([]));
  }, []);

  useEffect(() => {
    loadLlm();
    loadAgents();
    loadSkills();
    loadMcp();
  }, [loadLlm, loadAgents, loadSkills, loadMcp]);

  // ---------------------------------------------------------------- LLM 动作
  const toggleProvider = (p: LlmProviderConfig) => {
    api
      .updateLlmConfig(p.id, { enabled: !p.enabled })
      .then((updated) => {
        setProviders((prev) => prev.map((x) => (x.id === p.id ? updated : x)));
        loadLlm();
      })
      .catch((err) => flash(`操作失败: ${String(err)}`));
  };

  const setDefaultModel = (p: LlmProviderConfig, model: string) => {
    api
      .updateLlmConfig(p.id, { default_model: model })
      .then(() => {
        flash(`已设置默认模型: ${p.id} → ${model}`);
        loadLlm();
      })
      .catch((err) => flash(`操作失败: ${String(err)}`));
  };

  // ---------------------------------------------------------------- Agent 表单
  const [agentForm, setAgentForm] = useState({ id: '', role: '', skills: '' });
  const submitAgent = () => {
    const id = agentForm.id.trim();
    const role = agentForm.role.trim();
    if (!id || !role) {
      flash('Agent 注册必填 id 与 role');
      return;
    }
    const skills = agentForm.skills.split(/[,，]/).map((x) => x.trim()).filter(Boolean);
    api
      .createAgent(id, role, skills)
      .then(() => {
        setAgentForm({ id: '', role: '', skills: '' });
        loadAgents();
        flash(`Agent 已注册: ${id}`);
      })
      .catch((err) => flash(`注册失败: ${String(err)}`));
  };
  const removeAgent = (id: string) => {
    api
      .deleteAgent(id)
      .then(() => {
        loadAgents();
        flash(`Agent 已移除: ${id}`);
      })
      .catch((err) => flash(`移除失败: ${String(err)}`));
  };

  // ---------------------------------------------------------------- Skill 表单
  const [skillForm, setSkillForm] = useState({ id: '', name: '', category: '' });
  const submitSkill = () => {
    const id = skillForm.id.trim();
    if (!id) {
      flash('Skill 注册必填 id');
      return;
    }
    api
      .createSkill(id, skillForm.name.trim() || undefined, skillForm.category.trim() || undefined)
      .then(() => {
        setSkillForm({ id: '', name: '', category: '' });
        loadSkills();
        flash(`Skill 已注册: ${id}`);
      })
      .catch((err) => flash(`注册失败: ${String(err)}`));
  };
  const removeSkill = (id: string) => {
    api
      .deleteSkill(id)
      .then(() => {
        loadSkills();
        flash(`Skill 已移除: ${id}`);
      })
      .catch((err) => flash(`移除失败: ${String(err)}`));
  };

  // ---------------------------------------------------------------- MCP 表单
  const [mcpForm, setMcpForm] = useState({ name: '', server_url: '' });
  const submitMcp = () => {
    const name = mcpForm.name.trim();
    const serverUrl = mcpForm.server_url.trim();
    if (!name || !serverUrl) {
      flash('MCP 连接必填名称与地址');
      return;
    }
    api
      .createMCPConnection(name, serverUrl, 'mock')
      .then(() => {
        setMcpForm({ name: '', server_url: '' });
        loadMcp();
        flash(`MCP 已连接: ${name}`);
      })
      .catch((err) => flash(`连接失败: ${String(err)}`));
  };
  const removeMcp = (id: string) => {
    api
      .deleteMCPConnection(id)
      .then(() => {
        loadMcp();
        flash(`MCP 已移除: ${id}`);
      })
      .catch((err) => flash(`移除失败: ${String(err)}`));
  };

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
      {msg ? (
        <p className="af-composer-msg" data-testid="af-settings-msg">
          {msg}
        </p>
      ) : null}

      <div className="af-settings-body" data-testid={`af-settings-${tab}`}>
        {tab === 'llm' && (
          <section>
            <h3 className="af-settings-h3">🤖 LLM / 模型 Provider（{providers.length}）</h3>
            <p className="af-home-note">
              当前生效: {selected.provider_id ?? '—'}
              {selected.model ? ` / ${selected.model}` : ''} · API Key 只显示已配置态，不存明文
            </p>
            {providers.length === 0 ? (
              <p className="af-home-note">（暂无 Provider — 运行 factory init / factory config 配置）</p>
            ) : (
              <div className="af-settings-cards">
                {providers.map((p) => (
                  <div key={p.id} className="af-settings-card" data-testid={`af-llm-${p.id}`}>
                    <div className="af-settings-card-head">
                      <span className="af-settings-card-name">{p.id}</span>
                      <span className={`af-badge ${p.enabled ? 'af-badge-green' : 'af-badge-gray'}`}>
                        {p.enabled ? '已启用' : '已停用'}
                      </span>
                    </div>
                    <div className="af-settings-card-body">
                      <span className="af-settings-chip">🔑 {p.key_configured ? 'Key 已配置' : 'Key 未配置'}</span>
                      <span className="af-settings-chip">
                        默认模型:{' '}
                        {p.models.length > 0 ? (
                          <select
                            className="af-settings-select"
                            aria-label={`默认模型 ${p.id}`}
                            value={p.default_model ?? ''}
                            onChange={(e) => setDefaultModel(p, e.target.value)}
                          >
                            {p.models.map((m) => (
                              <option key={m} value={m}>
                                {m}
                              </option>
                            ))}
                          </select>
                        ) : (
                          '—'
                        )}
                      </span>
                    </div>
                    <div className="af-settings-card-foot">
                      <button type="button" className="af-settings-action" onClick={() => toggleProvider(p)}>
                        {p.enabled ? '停用' : '启用'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {tab === 'agent' && (
          <section>
            <h3 className="af-settings-h3">👤 Agent（{agents.length}）</h3>
            <div className="af-settings-form">
              <input
                className="af-settings-input"
                placeholder="id (如 pm-1)"
                aria-label="Agent id"
                value={agentForm.id}
                onChange={(e) => setAgentForm((f) => ({ ...f, id: e.target.value }))}
              />
              <input
                className="af-settings-input"
                placeholder="role (如 product_manager)"
                aria-label="Agent role"
                value={agentForm.role}
                onChange={(e) => setAgentForm((f) => ({ ...f, role: e.target.value }))}
              />
              <input
                className="af-settings-input af-settings-input--wide"
                placeholder="skills 逗号分隔 (prd,discovery)"
                aria-label="Agent skills"
                value={agentForm.skills}
                onChange={(e) => setAgentForm((f) => ({ ...f, skills: e.target.value }))}
              />
              <button type="button" className="af-settings-action af-settings-action--primary" onClick={submitAgent}>
                ＋ 注册 Agent
              </button>
            </div>
            <div className="af-settings-cards">
              {agents.map((a) => (
                <div key={a.id} className="af-settings-card" data-testid={`af-agent-${a.id}`}>
                  <div className="af-settings-card-head">
                    <span className="af-settings-card-name">{a.name ?? a.id}</span>
                    <span className="af-settings-chip">{a.role ?? ''}</span>
                  </div>
                  <div className="af-settings-card-body">
                    {(a.skills ?? []).map((sk) => (
                      <span key={sk} className="af-settings-chip">
                        {sk}
                      </span>
                    ))}
                    {a.status ? <span className="af-settings-chip">{a.status}</span> : null}
                  </div>
                  <div className="af-settings-card-foot">
                    <button type="button" className="af-settings-action af-settings-action--danger" onClick={() => removeAgent(a.id ?? '')}>
                      移除
                    </button>
                  </div>
                </div>
              ))}
              {agents.length === 0 ? <p className="af-home-note">（暂无 Agent）</p> : null}
            </div>
          </section>
        )}

        {tab === 'skill' && (
          <section>
            <h3 className="af-settings-h3">🧩 Skill（{skills.length}）</h3>
            <div className="af-settings-form">
              <input
                className="af-settings-input"
                placeholder="id (如 python-api)"
                aria-label="Skill id"
                value={skillForm.id}
                onChange={(e) => setSkillForm((f) => ({ ...f, id: e.target.value }))}
              />
              <input
                className="af-settings-input"
                placeholder="名称"
                aria-label="Skill name"
                value={skillForm.name}
                onChange={(e) => setSkillForm((f) => ({ ...f, name: e.target.value }))}
              />
              <input
                className="af-settings-input"
                placeholder="分类 (backend/general)"
                aria-label="Skill category"
                value={skillForm.category}
                onChange={(e) => setSkillForm((f) => ({ ...f, category: e.target.value }))}
              />
              <button type="button" className="af-settings-action af-settings-action--primary" onClick={submitSkill}>
                ＋ 注册 Skill
              </button>
            </div>
            <div className="af-settings-cards">
              {skills.map((sk) => (
                <div key={sk.id} className="af-settings-card" data-testid={`af-skill-${sk.id}`}>
                  <div className="af-settings-card-head">
                    <span className="af-settings-card-name">{sk.name ?? sk.id}</span>
                    <span className="af-settings-chip">{sk.category ?? ''}</span>
                  </div>
                  <div className="af-settings-card-body">
                    <span className="af-settings-chip">v{sk.version ?? '—'}</span>
                  </div>
                  <div className="af-settings-card-foot">
                    <button type="button" className="af-settings-action af-settings-action--danger" onClick={() => removeSkill(sk.id ?? '')}>
                      移除
                    </button>
                  </div>
                </div>
              ))}
              {skills.length === 0 ? <p className="af-home-note">（暂无 Skill）</p> : null}
            </div>
          </section>
        )}

        {tab === 'mcp' && (
          <section>
            <h3 className="af-settings-h3">🔌 MCP 连接（{mcps.length}）· Tool（{mcpTools.length}）</h3>
            <div className="af-settings-form">
              <input
                className="af-settings-input"
                placeholder="名称 (如 weather-mcp)"
                aria-label="MCP 名称"
                value={mcpForm.name}
                onChange={(e) => setMcpForm((f) => ({ ...f, name: e.target.value }))}
              />
              <input
                className="af-settings-input af-settings-input--wide"
                placeholder="服务地址 (mock: 任意 URL)"
                aria-label="MCP 地址"
                value={mcpForm.server_url}
                onChange={(e) => setMcpForm((f) => ({ ...f, server_url: e.target.value }))}
              />
              <button type="button" className="af-settings-action af-settings-action--primary" onClick={submitMcp}>
                ＋ 连接
              </button>
            </div>
            <div className="af-settings-cards">
              {mcps.map((m) => (
                <div key={m.id} className="af-settings-card" data-testid={`af-mcp-${m.id}`}>
                  <div className="af-settings-card-head">
                    <span className="af-settings-card-name">{m.name}</span>
                    <span className={`af-badge ${m.enabled ? 'af-badge-green' : 'af-badge-gray'}`}>
                      {m.enabled ? '启用' : '停用'}
                    </span>
                  </div>
                  <div className="af-settings-card-body">
                    <span className="af-settings-chip">{m.transport}</span>
                    <span className="af-settings-chip">{m.server_url}</span>
                  </div>
                  <div className="af-settings-card-foot">
                    <button type="button" className="af-settings-action af-settings-action--danger" onClick={() => removeMcp(m.id ?? '')}>
                      移除
                    </button>
                  </div>
                </div>
              ))}
              {mcps.length === 0 ? <p className="af-home-note">（暂无 MCP 连接 — 点＋连接注册即连，Mock 不连公网）</p> : null}
            </div>
            <h4 className="af-settings-h4">已注册 Tool（{mcpTools.length}）</h4>
            <div className="af-settings-cards">
              {mcpTools.map((t) => (
                <div key={t.id} className="af-settings-card af-settings-card--slim" data-testid={`af-mcp-tool-${t.id}`}>
                  <span className="af-settings-card-name">{t.name}</span>
                  <span className="af-settings-chip">{t.server}</span>
                  <span className="af-home-note">{t.description}</span>
                </div>
              ))}
              {mcpTools.length === 0 ? <p className="af-home-note">（暂无 Tool）</p> : null}
            </div>
          </section>
        )}

        {tab === 'plugin' && (
          <section>
            <h3 className="af-settings-h3">📦 插件</h3>
            <p className="af-home-note">
              插件体系规划中（外部 skill/agent/mcp 接入 + 模板/市场）— 见战役规划 K-10 / 远期。
              当前 Agent/Skill/MCP 已支持在对应 tab 直接管理。
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
