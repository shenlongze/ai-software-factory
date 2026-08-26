/**
 * pages/workspace/AfSettings.tsx — 设置页 (v1.1.103 完善: 表格 + LLM 增删改)。
 *
 * Tabs: LLM/模型 · Agent · Skill · MCP · 插件
 * 表格模式 (Founder 反馈: 卡片信息不全 → 表格全量展示) + 管理动作:
 *   LLM   — GET/POST/PATCH /api/config/llm (新增/编辑/启用停用/默认模型)
 *   Agent — GET /api/agents + POST/DELETE (注册/移除)
 *   Skill — GET /api/skills + POST/DELETE (注册/移除)
 *   MCP   — GET/POST/DELETE /api/mcp/connections + GET /api/mcp/tools
 * 诚实原则: key 只存 env: 引用 (明文 400 拒绝); 动作失败 → 明确提示。
 */

import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
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

  const [providers, setProviders] = useState<LlmProviderConfig[]>([]);
  const [selected, setSelected] = useState<{ provider_id: string | null; model: string | null }>({
    provider_id: null,
    model: null,
  });
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [mcps, setMcps] = useState<MCPConn[]>([]);
  const [mcpTools, setMcpTools] = useState<MCPTool[]>([]);

  // LLM 编辑/新增状态
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [llmForm, setLlmForm] = useState({
    provider_id: '',
    enabled: true,
    models: '',
    base_url: '',
    api_key_ref: '',
    default_model: '',
  });

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

  // ---------------------------------------------------------------- 表格
  const table = (cols: string[], rows: ReactNode[][]) => (
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

  // ---------------------------------------------------------------- LLM 动作
  const toggleProvider = (p: LlmProviderConfig) => {
    api
      .updateLlmConfig(p.id, { enabled: !p.enabled })
      .then(() => {
        flash(`已${!p.enabled ? '启用' : '停用'} Provider: ${p.id}`);
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
  const startEdit = (p: LlmProviderConfig) => {
    setEditingProvider(p.id);
    setLlmForm({
      provider_id: p.id,
      enabled: p.enabled,
      models: (p.models ?? []).join(', '),
      base_url: p.base_url ?? '',
      api_key_ref: p.api_key_ref ?? '',
      default_model: p.default_model ?? '',
    });
  };
  const submitLlmForm = (isCreate: boolean) => {
    const providerId = llmForm.provider_id.trim();
    if (!providerId) {
      flash('Provider id 必填');
      return;
    }
    const body = {
      enabled: llmForm.enabled,
      models: llmForm.models.split(/[,，]/).map((x) => x.trim()).filter(Boolean),
      base_url: llmForm.base_url.trim() || undefined,
      api_key_ref: llmForm.api_key_ref.trim() || undefined,
      default_model: llmForm.default_model.trim() || undefined,
    };
    const done = () => {
      setEditingProvider(null);
      setShowAddProvider(false);
      setLlmForm({ provider_id: '', enabled: true, models: '', base_url: '', api_key_ref: '', default_model: '' });
      loadLlm();
    };
    const req = isCreate
      ? api.createLlmConfig({ provider_id: providerId, ...body })
      : api.updateLlmConfig(providerId, body);
    req
      .then(() => {
        flash(`已${isCreate ? '新增' : '更新'} Provider: ${providerId}`);
        done();
      })
      .catch((err) => flash(`保存失败: ${String(err)}`));
  };

  // ---------------------------------------------------------------- Agent/Skill/MCP 表单
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

  const llmFormFields = (
    <div className="af-settings-form af-settings-form--block">
      <input
        className="af-settings-input"
        placeholder="Provider id (如 openai)"
        aria-label="Provider id"
        value={llmForm.provider_id}
        disabled={!showAddProvider}
        onChange={(e) => setLlmForm((f) => ({ ...f, provider_id: e.target.value }))}
      />
      <input
        className="af-settings-input af-settings-input--wide"
        placeholder="模型 (逗号分隔: gpt-4o,gpt-4o-mini)"
        aria-label="Provider models"
        value={llmForm.models}
        onChange={(e) => setLlmForm((f) => ({ ...f, models: e.target.value }))}
      />
      <input
        className="af-settings-input af-settings-input--wide"
        placeholder="base_url (留空用内置默认)"
        aria-label="Provider base_url"
        value={llmForm.base_url}
        onChange={(e) => setLlmForm((f) => ({ ...f, base_url: e.target.value }))}
      />
      <input
        className="af-settings-input af-settings-input--wide"
        placeholder="api_key_ref (env:OPENAI_API_KEY — 只存引用, 不存明文)"
        aria-label="Provider api_key_ref"
        value={llmForm.api_key_ref}
        onChange={(e) => setLlmForm((f) => ({ ...f, api_key_ref: e.target.value }))}
      />
      <input
        className="af-settings-input"
        placeholder="默认模型 (可选)"
        aria-label="Provider default_model"
        value={llmForm.default_model}
        onChange={(e) => setLlmForm((f) => ({ ...f, default_model: e.target.value }))}
      />
      <label className="af-settings-check">
        <input
          type="checkbox"
          checked={llmForm.enabled}
          onChange={(e) => setLlmForm((f) => ({ ...f, enabled: e.target.checked }))}
        />
        启用
      </label>
      <button
        type="button"
        className="af-settings-action af-settings-action--primary"
        onClick={() => submitLlmForm(showAddProvider)}
      >
        保存
      </button>
      <button
        type="button"
        className="af-settings-action"
        onClick={() => {
          setEditingProvider(null);
          setShowAddProvider(false);
        }}
      >
        取消
      </button>
    </div>
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
      {msg ? (
        <p className="af-composer-msg" data-testid="af-settings-msg">
          {msg}
        </p>
      ) : null}

      <div className="af-settings-body" data-testid={`af-settings-${tab}`}>
        {tab === 'llm' && (
          <section>
            <div className="af-settings-head-row">
              <h3 className="af-settings-h3">🤖 LLM / 模型 Provider（{providers.length}）</h3>
              <button type="button" className="af-settings-action af-settings-action--primary" onClick={() => { setShowAddProvider(true); setEditingProvider(null); }}>
                ＋ 新增 Provider
              </button>
            </div>
            <p className="af-home-note">
              当前生效: {selected.provider_id ?? '—'}
              {selected.model ? ` / ${selected.model}` : ''} · Key 只存 env: 引用，不存明文
            </p>
            {showAddProvider ? llmFormFields : null}
            {table(
              ['ID', '状态', '模型', '默认模型', 'Base URL', 'Key', '操作'],
              providers.map((p) => [
                p.id,
                <button key="s" type="button" className="af-settings-action" onClick={() => toggleProvider(p)}>
                  {p.enabled ? '✅ 启用' : '⏸ 停用'}
                </button>,
                (p.models ?? []).join(', ') || '—',
                p.models.length > 0 ? (
                  <select
                    key="m"
                    className="af-settings-select"
                    aria-label={`默认模型 ${p.id}`}
                    value={p.default_model ?? ''}
                    onChange={(e) => setDefaultModel(p, e.target.value)}
                  >
                    <option value="">（未选）</option>
                    {p.models.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                ) : '—',
                p.base_url ?? '（默认）',
                p.key_configured ? '🔑 已配置' : '未配置',
                <button key="e" type="button" className="af-settings-action" onClick={() => startEdit(p)}>
                  编辑
                </button>,
              ]),
            )}
            {editingProvider != null ? llmFormFields : null}
          </section>
        )}

        {tab === 'agent' && (
          <section>
            <h3 className="af-settings-h3">👤 Agent（{agents.length}）</h3>
            <div className="af-settings-form">
              <input className="af-settings-input" placeholder="id (如 pm-1)" aria-label="Agent id" value={agentForm.id} onChange={(e) => setAgentForm((f) => ({ ...f, id: e.target.value }))} />
              <input className="af-settings-input" placeholder="role (如 product_manager)" aria-label="Agent role" value={agentForm.role} onChange={(e) => setAgentForm((f) => ({ ...f, role: e.target.value }))} />
              <input className="af-settings-input af-settings-input--wide" placeholder="skills 逗号分隔 (prd,discovery)" aria-label="Agent skills" value={agentForm.skills} onChange={(e) => setAgentForm((f) => ({ ...f, skills: e.target.value }))} />
              <button type="button" className="af-settings-action af-settings-action--primary" onClick={submitAgent}>＋ 注册 Agent</button>
            </div>
            {table(
              ['ID', '名称', '角色', 'Skills', '状态', '操作'],
              agents.map((a) => [
                a.id ?? '',
                a.name ?? '',
                a.role ?? '',
                (a.skills ?? []).join(', ') || '—',
                a.status ?? '—',
                <button key="d" type="button" className="af-settings-action af-settings-action--danger" onClick={() => removeAgent(a.id ?? '')}>移除</button>,
              ]),
            )}
          </section>
        )}

        {tab === 'skill' && (
          <section>
            <h3 className="af-settings-h3">🧩 Skill（{skills.length}）</h3>
            <div className="af-settings-form">
              <input className="af-settings-input" placeholder="id (如 python-api)" aria-label="Skill id" value={skillForm.id} onChange={(e) => setSkillForm((f) => ({ ...f, id: e.target.value }))} />
              <input className="af-settings-input" placeholder="名称" aria-label="Skill name" value={skillForm.name} onChange={(e) => setSkillForm((f) => ({ ...f, name: e.target.value }))} />
              <input className="af-settings-input" placeholder="分类 (backend/general)" aria-label="Skill category" value={skillForm.category} onChange={(e) => setSkillForm((f) => ({ ...f, category: e.target.value }))} />
              <button type="button" className="af-settings-action af-settings-action--primary" onClick={submitSkill}>＋ 注册 Skill</button>
            </div>
            {table(
              ['ID', '名称', '分类', '版本', '操作'],
              skills.map((sk) => [
                sk.id ?? '',
                sk.name ?? '',
                sk.category ?? '',
                sk.version ?? '',
                <button key="d" type="button" className="af-settings-action af-settings-action--danger" onClick={() => removeSkill(sk.id ?? '')}>移除</button>,
              ]),
            )}
          </section>
        )}

        {tab === 'mcp' && (
          <section>
            <h3 className="af-settings-h3">🔌 MCP 连接（{mcps.length}）· Tool（{mcpTools.length}）</h3>
            <div className="af-settings-form">
              <input className="af-settings-input" placeholder="名称 (如 weather-mcp)" aria-label="MCP 名称" value={mcpForm.name} onChange={(e) => setMcpForm((f) => ({ ...f, name: e.target.value }))} />
              <input className="af-settings-input af-settings-input--wide" placeholder="服务地址 (mock: 任意 URL)" aria-label="MCP 地址" value={mcpForm.server_url} onChange={(e) => setMcpForm((f) => ({ ...f, server_url: e.target.value }))} />
              <button type="button" className="af-settings-action af-settings-action--primary" onClick={submitMcp}>＋ 连接</button>
            </div>
            {table(
              ['名称', '传输', '地址', '状态', '操作'],
              mcps.map((m) => [
                m.name ?? '',
                m.transport ?? '',
                m.server_url ?? '',
                m.enabled ? '✅ 启用' : '停用',
                <button key="d" type="button" className="af-settings-action af-settings-action--danger" onClick={() => removeMcp(m.id ?? '')}>移除</button>,
              ]),
            )}
            <h4 className="af-settings-h4">已注册 Tool（{mcpTools.length}）</h4>
            {table(
              ['ID', '名称', '来源', '描述'],
              mcpTools.map((t) => [t.id ?? '', t.name ?? '', t.server ?? '', t.description ?? '']),
            )}
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
