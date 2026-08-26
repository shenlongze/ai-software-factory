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
import type { RegistryTool } from '../../models/types';
import { AfLangSwitch, useI18n } from '../../i18n';
import { useTheme } from '../../theme';
import type { LlmProviderConfig } from '../../models/types';
import {
  agentRoleInfo,
  agentStatusLabel,
  skillCategoryLabel,
  skillLabel,
} from '../../components/af/afLabels';

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
  { id: 'llm', label: 'llm' },
  { id: 'agent', label: 'agent' },
  { id: 'skill', label: 'skill' },
  { id: 'mcp', label: 'mcp' },
  { id: 'tools', label: '工具' },
  { id: 'plugin', label: 'plugin' },
  { id: 'appearance', label: 'appearance' },
] as const;
type TabId = (typeof TABS)[number]['id'];

/** U-5 工具页: 统一注册表 (39 内置工具, 按阶段分组 + 详情 + 可执行)。 */
function ToolsTab(): JSX.Element {
  const [tools, setTools] = useState<RegistryTool[]>([]);
  const [summary, setSummary] = useState<{ total: number; by_status: Record<string, number> } | null>(null);
  const [selected, setSelected] = useState<RegistryTool | null>(null);
  const [result, setResult] = useState<string>('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .registryTools()
      .then((d) => {
        if (cancelled) return;
        setTools(d.tools ?? []);
        setSummary(d.summary ?? null);
      })
      .catch(() => {
        if (!cancelled) setTools([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const stages = ['设计', '开发', '测试', '部署', '运维'];
  const byStage = (s: string) => tools.filter((x) => x.stage === s);
  const statusMark = (s: string) => (s === 'implemented' ? '✅' : '⬜');

  const run = async (tool: RegistryTool) => {
    setBusy(true);
    setResult('');
    try {
      const input: Record<string, unknown> = {};
      if (tool.id === 'code_search') input.keyword = 'registry';
      if (tool.id === 'list_tasks') input.priority = 'P0';
      if (tool.id === 'read_doc') input.name = 'README.md';
      const r = await api.registryExecute(tool.id, input, { project_id: 'ai-factory-self' });
      setResult(r.success ? `✅ ${JSON.stringify(r.output).slice(0, 300)}` : `❌ ${r.error}`);
    } catch (e) {
      setResult(`❌ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section data-testid="af-tools-panel">
      <div className="af-settings-head-row">
        <div className="af-doc-group">
          内置工具注册表（{summary?.total ?? tools.length}）· 已实现 {summary?.by_status?.implemented ?? 0}
        </div>
        <span className="af-home-note">U-1/U-2: 39 工具统一注册 + 统一执行链（CLI factory tools / API / 会话同源）</span>
      </div>
      {stages.map((s) => {
        const rows = byStage(s);
        if (rows.length === 0) return null;
        return (
          <div key={s}>
            <div className="af-doc-group">[{s} · {rows.length}]</div>
            <table className="af-manage-table">
              <tbody>
                {rows.map((tool) => (
                  <tr key={tool.id}>
                    <td className="af-doc-item-label">{statusMark(tool.status)} {tool.name}</td>
                    <td><code>{tool.id}</code></td>
                    <td className="af-doc-item-meta">{tool.status}</td>
                    <td>
                      <button type="button" className="af-btn" onClick={() => setSelected(selected?.id === tool.id ? null : tool)}>
                        {selected?.id === tool.id ? '收起' : '详情'}
                      </button>
                      {tool.status === 'implemented' && ['code_search', 'list_tasks', 'monitor', 'quality_score', 'backup', 'scan', 'read_doc'].includes(tool.id) ? (
                        <button type="button" className="af-btn" disabled={busy} onClick={() => void run(tool)}>
                          执行
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {selected != null && rows.some((x) => x.id === selected.id) ? (
              <div className="af-settings-card" data-testid={`af-tool-detail-${selected.id}`}>
                <p><strong>{selected.name}</strong> · {selected.desc}</p>
                <p>关键词: {selected.keywords?.join('、') ?? '—'} · CLI: {selected.cli ?? '—'} · API: {selected.api ?? '—'}</p>
              </div>
            ) : null}
          </div>
        );
      })}
      {result ? <p className="af-composer-msg" data-testid="af-tool-result">{result}</p> : null}
    </section>
  );
}

export function AfSettings(): JSX.Element {
  const { t } = useI18n();
  const { theme, setTheme, bg, setBackgroundImage, setBackgroundOpacity, setBackgroundBlur, clearBackground } = useTheme();
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
  // U-6 (v1.1.188): 扫描本机 AI (codex/claude/hermes) → 幂等注册为 Agent
  const scanLocalAi = useCallback(async () => {
    try {
      const r = await api.registerLocalAi();
      flash(
        r.count > 0
          ? `本机 AI 已注册 ${r.count} 个: ${r.registered.map((a) => a.id).join(', ')}`
          : '未发现本机 AI CLI（PATH 里没有 codex/claude/hermes）',
      );
      loadAgents();
    } catch (err) {
      flash(`本机 AI 扫描失败: ${String(err)}`);
    }
  }, [flash, loadAgents]);
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
      <h2 className="af-detail-name">{t('settings.title')}</h2>
      <div className="af-settings-tabs" role="tablist" aria-label="设置分类">
        {TABS.map((tb) => (
          <button
            key={tb.id}
            type="button"
            role="tab"
            aria-selected={tab === tb.id}
            className={`af-settings-tab${tab === tb.id ? ' active' : ''}`}
            onClick={() => setTab(tb.id)}
          >
            {t(`settings.tab.${tb.id}`)}
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
            <h3 className="af-settings-h3">👤 AI 员工（{agents.length}）</h3>
            <p className="af-home-note">
              AI 员工 = 可调度的 AI 角色，各负责软件生产的一类工作（产品/研发/质量…）。名称与职责一目了然，内部代号见提示。
            </p>
            <div className="af-settings-form">
              <input className="af-settings-input" placeholder="内部代号 (如 backend-1)" aria-label="Agent id" value={agentForm.id} onChange={(e) => setAgentForm((f) => ({ ...f, id: e.target.value }))} />
              <input className="af-settings-input" placeholder="角色 (如 产品经理 / backend-developer)" aria-label="Agent role" value={agentForm.role} onChange={(e) => setAgentForm((f) => ({ ...f, role: e.target.value }))} />
              <input className="af-settings-input af-settings-input--wide" placeholder="技能 逗号分隔 (如 需求分析, 测试)" aria-label="Agent skills" value={agentForm.skills} onChange={(e) => setAgentForm((f) => ({ ...f, skills: e.target.value }))} />
              <button type="button" className="af-settings-action af-settings-action--primary" onClick={submitAgent}>＋ 注册 AI 员工</button>
              <button
                type="button"
                className="af-settings-action"
                data-testid="af-settings-scan-local-ai"
                title="扫描本机安装的 codex/claude/hermes 并注册为 AI 员工"
                onClick={() => void scanLocalAi()}
              >
                🔍 扫描本机 AI
              </button>
            </div>
            {table(
              ['名称', '角色', '职责', '技能', '状态', '操作'],
              agents.map((a) => {
                const info = agentRoleInfo(a.role);
                return [
                  <span key="n" title={`代号: ${a.id ?? ''}`}>{a.name ?? a.id ?? ''}</span>,
                  `${info.label}${info.group !== '其他' ? `（${info.group}线）` : ''}`,
                  info.desc,
                  (a.skills ?? []).map(skillLabel).join('、') || '—',
                  agentStatusLabel(a.status),
                  <button key="d" type="button" className="af-settings-action af-settings-action--danger" onClick={() => removeAgent(a.id ?? '')}>移除</button>,
                ];
              }),
            )}
          </section>
        )}

        {tab === 'skill' && (
          <section>
            <h3 className="af-settings-h3">🧩 技能（{skills.length}）</h3>
            <p className="af-home-note">技能 = AI 员工能干的某类活（后端开发 / 测试 / 需求分析…）。</p>
            <div className="af-settings-form">
              <input className="af-settings-input" placeholder="内部代号 (如 python-api)" aria-label="Skill id" value={skillForm.id} onChange={(e) => setSkillForm((f) => ({ ...f, id: e.target.value }))} />
              <input className="af-settings-input" placeholder="名称 (如 Python 接口开发)" aria-label="Skill name" value={skillForm.name} onChange={(e) => setSkillForm((f) => ({ ...f, name: e.target.value }))} />
              <input className="af-settings-input" placeholder="分类 (后端/前端/测试/通用)" aria-label="Skill category" value={skillForm.category} onChange={(e) => setSkillForm((f) => ({ ...f, category: e.target.value }))} />
              <button type="button" className="af-settings-action af-settings-action--primary" onClick={submitSkill}>＋ 注册技能</button>
            </div>
            {table(
              ['名称', '技能', '分类', '版本', '操作'],
              skills.map((sk) => [
                <span key="n" title={`代号: ${sk.id ?? ''}`}>{sk.name ?? sk.id ?? ''}</span>,
                skillLabel(sk.id ?? ''),
                skillCategoryLabel(sk.category ?? ''),
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

        {tab === 'appearance' && (
          <section>
            <h3 className="af-settings-h3">{t('settings.tab.appearance')}</h3>
            <div className="af-settings-form">
              <span className="af-home-note">{t('settings.theme.label')}</span>
              <select
                className="af-lang-switch"
                aria-label="主题 / Theme"
                value={theme}
                onChange={(e) => setTheme(e.target.value as 'dark' | 'light')}
              >
                <option value="dark">🌙 深色 / Dark</option>
                <option value="light">☀️ 浅色 / Light</option>
              </select>
            </div>
            <h4 className="af-settings-h4">{t('settings.background.title')}</h4>
            <div className="af-settings-form">
              <label className="af-settings-action" style={{ cursor: 'pointer' }}>
                🖼 {t('settings.background.choose')}
                <input
                  type="file"
                  accept="image/*"
                  style={{ display: 'none' }}
                  data-testid="af-bg-file"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    if (f.size > 3 * 1024 * 1024) {
                      flash('图片过大（>3MB）— 建议用 URL 或压缩后重试');
                      return;
                    }
                    const reader = new FileReader();
                    reader.onload = () => setBackgroundImage(String(reader.result ?? ''));
                    reader.readAsDataURL(f);
                  }}
                />
              </label>
              <input
                className="af-settings-input af-settings-input--wide"
                placeholder="或粘贴图片 URL"
                aria-label="背景图片 URL"
                data-testid="af-bg-url"
                defaultValue={bg.image && !bg.image.startsWith('data:') ? bg.image : ''}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && e.currentTarget.value.trim()) {
                    setBackgroundImage(e.currentTarget.value.trim());
                  }
                }}
              />
              <button type="button" className="af-settings-action" onClick={() => setBackgroundImage('')}>
                应用 URL
              </button>
              <button type="button" className="af-settings-action af-settings-action--danger" onClick={clearBackground}>
                清除背景
              </button>
            </div>
            <div className="af-settings-form">
              <span className="af-home-note">{t('settings.background.opacity')}: {bg.opacity}%</span>
              <input
                type="range" min={5} max={90} value={bg.opacity} aria-label="背景不透明度"
                onChange={(e) => setBackgroundOpacity(Number(e.target.value))}
              />
              <span className="af-home-note">{t('settings.background.blur')}: {bg.blur}px</span>
              <input
                type="range" min={0} max={30} value={bg.blur} aria-label="背景模糊"
                onChange={(e) => setBackgroundBlur(Number(e.target.value))}
              />
            </div>
            <div className="af-settings-form">
              <span className="af-home-note">{t('settings.lang.label')}</span>
              <AfLangSwitch />
            </div>
          </section>
        )}

        {tab === 'tools' && <ToolsTab />}
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
