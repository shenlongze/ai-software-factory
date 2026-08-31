/**
 * components/af/AfWorkspace.tsx — Dynamic Workspace / Workbench (V2).
 *
 * 设计文档 §13-18: Tab 不固定 — 由当前任务类型驱动。
 *   PRD → Artifact / Files
 *   Coding → Code / Files / Terminal / Diff
 *   Debug → Code / Logs / Terminal / Diff
 *   QA → Test / Logs / Report
 *   Default (空闲) → Files / Code / Preview / Diff
 *
 * 保留所有现有 Panel 实现 (TaskPanel/CodePanel/PreviewPanel/DiffPanel/EvidencePanel),
 * 仅重写 Tab 选择逻辑和外壳布局。
 * Approval 内联显示 (不单独页面) — 如果 ConversationContext 有 approval 状态,
 * ApprovalCard 会出现在顶部。
 */

import { useEffect, useMemo, useState } from 'react';
import { useConversation } from './ConversationContext';
import { api } from '../../api/client';
import type { OsProjectStatus } from '../../models/types';
import './af.css';

// ===== Tab 定义 =====
export interface WsTabDef {
  id: string;
  label: string;
  icon: string;
}

// 所有可用 Tab (profile 中引用)
const ALL_TABS: WsTabDef[] = [
  { id: 'files', label: 'Files', icon: '📁' },
  { id: 'artifact', label: 'Artifact', icon: '◈' },
  { id: 'code', label: '代码', icon: '💻' },
  { id: 'terminal', label: 'Terminal', icon: '⌨' },
  { id: 'preview', label: '预览', icon: '🌐' },
  { id: 'diff', label: 'Diff', icon: '📝' },
  { id: 'evidence', label: '证据', icon: '✅' },
  { id: 'task', label: '任务', icon: '📊' },
];

// ===== Profile: 根据意图/sending 动态选 Tab =====
type ProfileKey = 'prd' | 'coding' | 'debug' | 'qa' | 'default';

const PROFILE_TABS: Record<ProfileKey, string[]> = {
  prd: ['artifact', 'files', 'preview'],
  coding: ['code', 'files', 'terminal', 'diff'],
  debug: ['code', 'diff', 'evidence', 'terminal'],
  qa: ['evidence', 'task', 'diff'],
  default: ['task', 'code', 'preview', 'diff', 'evidence'],
};

// 导出给 shell 用 (保持已有 API 兼容)
export const WORKSPACE_TABS = ALL_TABS.map((t) => ({ id: t.id, label: t.label, icon: t.icon }));
export type WorkspaceTabId = string;

export function tabForIntent(intent: string): WorkspaceTabId {
  switch (intent) {
    case 'EXECUTE':
    case 'APPROVE':
    case 'ASK_STATUS':
      return 'task';
    case 'DECIDE':
    case 'CLARIFY':
      return 'code';
    default:
      return 'preview';
  }
}

/** 推导 ProfileKey — 根据 sending 状态 + 最后一条用户消息内容 */
function deriveProfile(sending: boolean, lastUserMessage?: string): ProfileKey {
  if (!sending) return 'default';
  const msg = (lastUserMessage ?? '').toLowerCase();
  if (/prd|product|competitor|market|discover|需求|竞品|市场/.test(msg)) return 'prd';
  if (/debug|fix|error|bug|fail|失败|修复|排查/.test(msg)) return 'debug';
  if (/test|qa|verify|验证|测试/.test(msg)) return 'qa';
  if (/code|develop|implement|build|write|开发|写|实现/.test(msg)) return 'coding';
  return 'coding'; // 执行中默认 coding
}


// ===== Artifact Panel (V2 新面板 — 设计文档 §17) =====
function ArtifactPanel(): JSX.Element {
  const [artifacts, setArtifacts] = useState<Array<{ id: string; type?: string; ref?: string; status?: string; metadata?: Record<string, unknown> }>>([]);
  const [selected, setSelected] = useState<string>('');
  const [content, setContent] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .artifacts({})
      .then((list) => {
        if (cancelled) return;
        setArtifacts(list.slice(0, 10));
        if (list.length > 0) {
          setSelected(list[0].id);
          return api.artifactContent(list[0].id).then((c) => {
            if (!cancelled) setContent(c.content ?? '');
          });
        }
        return undefined;
      })
      .catch(() => { /* API 失败时静默降级显示空态 */ });
    return () => {
      cancelled = true;
    };
  }, []);


  const current = artifacts.find((a) => a.id === selected);

  return (
    <div className="ai-panel-content">
      {artifacts.length === 0 ? (
        <div className="ai-panel-empty">
          <div className="ai-panel-empty-icon">◈</div>
          <div className="ai-panel-empty-title">暂无可展示内容</div>
          <div className="ai-panel-empty-desc">
            AI Factory will produce artifacts as it works — PRDs, code, designs, docs, and more.
          </div>
        </div>
      ) : (
        <>
          {current && (
            <div className="ai-artifact-meta">
              <div className="ai-artifact-name">{current.ref ?? current.type ?? current.id}</div>
              <div className="ai-artifact-badges">
                <span className={`ai-artifact-badge ai-artifact-badge--${current.status ?? 'generated'}`}>
                  {current.status ?? 'Generated'}
                </span>
                <span className="ai-artifact-version">v1</span>
              </div>
            </div>
          )}
          <div className="ai-file-list">
            {artifacts.map((a) => (
              <button
                key={a.id}
                type="button"
                className={`ai-file-item${selected === a.id ? ' ai-file-item--active' : ''}`}
                onClick={() => {
                  setSelected(a.id);
                  void api.artifactContent(a.id).then((c) => setContent(c.content ?? ''));
                }}
              >
                <span className="ai-file-icon">{/\.md$/i.test(String(a.ref ?? '')) ? '📝' : /\.[jt]sx?$/.test(String(a.ref ?? '')) ? '⚡' : '📄'}</span>
                <span className="ai-file-name">{a.ref ?? a.type ?? a.id}</span>
                {a.status ? <span className="ai-file-status">{a.status}</span> : null}
              </button>
            ))}
          </div>
          {content && <pre className="ai-code-block">{content.slice(0, 4000)}</pre>}
        </>
      )}
    </div>
  );
}

// ===== Task Panel =====
function TaskPanel(): JSX.Element {
  const [projects, setProjects] = useState<Array<{ id: string; title: string }>>([]);
  const [status, setStatus] = useState<OsProjectStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .osProjects()
      .then((list) => {
        if (cancelled) return;
        setProjects(list.slice(0, 5));
        if (list.length > 0) {
          return api.osProjectStatus(list[0].id).then((s) => {
            if (!cancelled) setStatus(s);
          });
        }
        return undefined;
      })
      .catch(() => { /* API 失败时静默降级显示空态 */ });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!status && projects.length === 0)
    return (
      <div className="ai-panel-empty">
        <div className="ai-panel-empty-icon">📊</div>
        <div className="ai-panel-empty-title">暂无活跃任务</div>
        <div className="ai-panel-empty-desc">告诉我你的目标，AI Factory 会自动创建任务图</div>
      </div>
    );

  return (
    <div className="ai-panel-content">
      {projects.map((p) => (
        <div key={p.id} className="ai-ws-row">
          <span>{p.title}</span>
          <span className="ai-ws-muted">{p.id.slice(0, 12)}</span>
        </div>
      ))}
      {status?.sprints?.map((s) => (
        <div key={s.sprint_id} className="ai-ws-card">
          <div className="ai-ws-row">
            <span>{s.title}</span>
            <span>{s.progress.percentage}%</span>
          </div>
          <div className="ai-ws-bar">
            <div className="ai-ws-bar-fill" style={{ width: `${s.progress.percentage}%` }} />
          </div>
          {s.tasks?.map((t) => (
            <div key={t.id} className="ai-ws-row ai-ws-task">
              <span>{t.title}</span>
              <span className={`ai-ws-state ai-ws-state--${t.status.toLowerCase()}`}>{t.status}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function CodePanel(): JSX.Element {
  const [artifacts, setArtifacts] = useState<Array<{ id: string; type?: string; ref?: string; status?: string }>>([]);
  const [selected, setSelected] = useState<string>('');
  const [content, setContent] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .artifacts({})
      .then((list) => {
        if (cancelled) return;
        setArtifacts(list.slice(0, 10));
        if (list.length > 0) {
          setSelected(list[0].id);
          return api.artifactContent(list[0].id).then((c) => {
            if (!cancelled) setContent(c.content ?? '');
          });
        }
        return undefined;
      })
      .catch(() => { /* API 失败时静默降级显示空态 */ });
    return () => {
      cancelled = true;
    };
  }, []);


  return (
    <div className="ai-panel-content">
      {artifacts.length === 0 ? (
        <div className="ai-panel-empty">
          <div className="ai-panel-empty-icon">💻</div>
          <div className="ai-panel-empty-title">暂无代码产物</div>
          <div className="ai-panel-empty-desc">开始构建吧 — 代码产物会自动出现在这里</div>
        </div>
      ) : (
        <>
          <div className="ai-file-list">
            {artifacts.map((a) => (
              <button
                key={a.id}
                type="button"
                className={`ai-file-item${selected === a.id ? ' ai-file-item--active' : ''}`}
                onClick={() => {
                  setSelected(a.id);
                  void api.artifactContent(a.id).then((c) => setContent(c.content ?? ''));
                }}
              >
                <span className="ai-file-icon">{/\.tsx?$|\.jsx?$/.test(String(a.ref ?? a.type)) ? '⚡' : '📄'}</span>
                <span className="ai-file-name">{a.ref ?? a.type ?? a.id}</span>
                {a.status ? <span className="ai-file-status">{a.status}</span> : null}
              </button>
            ))}
          </div>
          {content && <pre className="ai-code-block">{content.slice(0, 4000)}</pre>}
        </>
      )}
    </div>
  );
}

function PreviewPanel(): JSX.Element {
  const [previews, setPreviews] = useState<Array<{ id: string; type?: string; ref?: string }>>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .artifacts({})
      .then((list) => {
        if (cancelled) return;
        const p = list.filter((a) => /web|markdown|html|doc/i.test(String(a.type ?? ''))).slice(0, 5);
        setPreviews(p);
      })
      .catch(() => { /* API 失败时静默降级显示空态 */ });
    return () => {
      cancelled = true;
    };
  }, []);


  return (
    <div className="ai-panel-content">
      {previews.length === 0 ? (
        <div className="ai-panel-empty">
          <div className="ai-panel-empty-icon">🌐</div>
          <div className="ai-panel-empty-title">暂无可预览产物</div>
          <div className="ai-panel-empty-desc">可预览的产物会自动出现在这里</div>
        </div>
      ) : (
        <div className="ai-preview-grid">
          {previews.map((p) => (
            <div key={p.id} className="ai-preview-card">
              <div className="ai-preview-header">
                <span>{p.ref ?? p.type ?? p.id}</span>
              </div>
              <div className="ai-preview-body">Browser preview placeholder</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DiffPanel(): JSX.Element {
  const [diffs, setDiffs] = useState<Array<{ id: string; type?: string; ref?: string; status?: string }>>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .artifacts({})
      .then((list) => {
        if (!cancelled) setDiffs(list.filter((a) => /diff|code|patch/i.test(String(a.type ?? ''))).slice(0, 10));
      })
      .catch(() => { /* API 失败时静默降级显示空态 */ });
    return () => {
      cancelled = true;
    };
  }, []);


  return (
    <div className="ai-panel-content">
      {diffs.length === 0 ? (
        <div className="ai-panel-empty">
          <div className="ai-panel-empty-icon">📝</div>
          <div className="ai-panel-empty-title">暂无变更</div>
          <div className="ai-panel-empty-desc">AI 提出的变更会出现在这里供你审阅</div>
        </div>
      ) : (
        diffs.map((d) => (
          <div key={d.id} className="ai-ws-row ai-ws-task">
            <span>{d.ref ?? d.type ?? d.id}</span>
            <span className={`ai-ws-state ai-ws-state--${String(d.status ?? '').toLowerCase()}`}>{d.status ?? ''}</span>
          </div>
        ))
      )}
    </div>
  );
}

function EvidencePanel(): JSX.Element {
  const [tasks, setTasks] = useState<Array<{ id: string; title: string; status: string }>>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .osProjects()
      .then((list) => {
        if (cancelled || list.length === 0) return;
        return api.opsDrill(list[0].id).then((drill) => {
          if (cancelled) return;
          const t = drill.sprints?.flatMap((s) => s.tasks ?? []) ?? [];
          setTasks(
            t
              .map((x) => ({
                id: x.id,
                title: x.title ?? x.id,
                status: x.status ?? x.operational_state ?? '',
              }))
              .slice(0, 10),
          );
        });
      })
      .catch(() => { /* API 失败时静默降级显示空态 */ });
    return () => {
      cancelled = true;
    };
  }, []);


  return (
    <div className="ai-panel-content">
      {tasks.length === 0 ? (
        <div className="ai-panel-empty">
          <div className="ai-panel-empty-icon">✅</div>
          <div className="ai-panel-empty-title">暂无验证记录</div>
          <div className="ai-panel-empty-desc">验证结果会自动出现在这里</div>
        </div>
      ) : (
        tasks.map((t) => (
          <div key={t.id} className="ai-ws-row ai-ws-task">
            <span>{t.title}</span>
            <span className={`ai-ws-state ai-ws-state--${t.status.toLowerCase()}`}>{t.status}</span>
          </div>
        ))
      )}
    </div>
  );
}

function TerminalPanel(): JSX.Element {
  return (
    <div className="ai-panel-content">
      <div className="ai-panel-empty">
        <div className="ai-panel-empty-icon">⌨</div>
        <div className="ai-panel-empty-title">终端</div>
        <div className="ai-panel-empty-desc">终端集成 — 即将推出</div>
      </div>
    </div>
  );
}

function FilesPanel(): JSX.Element {
  const [files, setFiles] = useState<Array<{ id: string; ref?: string; type?: string }>>([]);
  const [selected, setSelected] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .artifacts({})
      .then((list) => {
        if (cancelled) return;
        setFiles(list.slice(0, 20));
        if (list.length > 0) setSelected(list[0].id);
      })
      .catch(() => { /* 失败静默 */ });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="ai-panel-content">
      {files.length === 0 ? (
        <div className="ai-panel-empty">
          <div className="ai-panel-empty-icon">📁</div>
          <div className="ai-panel-empty-title">项目文件</div>
          <div className="ai-panel-empty-desc">文件浏览器会在有文件时自动显示</div>
        </div>
      ) : (
        <div className="ai-file-list">
          {files.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`ai-file-item${selected === f.id ? ' ai-file-item--active' : ''}`}
              onClick={() => setSelected(f.id)}
            >
              <span className="ai-file-icon">{f.type === 'code' ? '📄' : '◈'}</span>
              <span className="ai-file-name">{f.ref ?? f.type ?? f.id}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ===== Approval Card (S31-003: 真实审批数据 — 非硬编码) =====
function ApprovalCard(): JSX.Element {
  const [approvals, setApprovals] = useState<Array<{ id: string; subject_type?: string; status?: string; created_at?: string }>>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .approvals(true)
      .then((list) => {
        if (!cancelled) setApprovals(Array.isArray(list) ? list.slice(0, 3) : []);
      })
      .catch(() => { /* 失败静默 — 不伪造 */ });
    return () => { cancelled = true; };
  }, []);

  if (approvals.length === 0) return <div className="ai-approval-card ai-approval-card--empty">无待审批</div>;

  return (
    <div className="ai-approval-card">
      <div className="ai-approval-head">
        <span className="ai-approval-icon">🎯</span>
        <span className="ai-approval-title">Human Approval Required</span>
      </div>
      <div className="ai-approval-body">
        {approvals.map((a) => (
          <div key={a.id} className="ai-approval-item">
            <span className="ai-approval-label">{a.subject_type ?? 'approval'}</span>
            <span>{a.id}</span>
            <span className={`ai-approval-pass ${a.status === 'pending' ? '' : 'ai-approval-state'}`}>{a.status ?? 'pending'}</span>
          </div>
        ))}
      </div>
      <div className="ai-approval-actions">
        <button type="button" className="ai-approval-btn ai-approval-btn--approve" onClick={() => void api.osDecideApproval(approvals[0].id, 'approve')}>Approve</button>
      </div>
    </div>
  );
}

// ===== Main Export =====
export function AfWorkspace(): JSX.Element {
  const ctx = useConversation();
  const [activeTabId, setActiveTabId] = useState<string>('task');

  // 推导 Profile + 动态 Tabs
  const profile = useMemo(() => {
    const lastUser = ctx.messages.filter((m) => m.role === 'user').slice(-1)[0]?.content;
    return deriveProfile(ctx.sending, lastUser);
  }, [ctx.sending, ctx.messages]);

  const availableTabs = useMemo(() => {
    const ids = PROFILE_TABS[profile];
    return ids.map((id) => ALL_TABS.find((t) => t.id === id)!).filter(Boolean);
  }, [profile]);

  // 确保 activeTabId 在 availableTabs 中
  useEffect(() => {
    if (!availableTabs.find((t) => t.id === activeTabId)) {
      setActiveTabId(availableTabs[0]?.id ?? 'preview');
    }
  }, [availableTabs, activeTabId]);

  const isIdle = !ctx.sending && ctx.messages.length === 0;
  const showApproval = profile === 'prd' && ctx.sending; // 示意: PRD 阶段可能触发审批

  const renderTabContent = () => {
    switch (activeTabId) {
      case 'task': return <TaskPanel />;
      case 'code': return <CodePanel />;
      case 'preview': return <PreviewPanel />;
      case 'diff': return <DiffPanel />;
      case 'evidence': return <EvidencePanel />;
      case 'artifact': return <ArtifactPanel />;
      case 'terminal': return <TerminalPanel />;
      case 'files': return <FilesPanel />;
      default: return <PreviewPanel />;
    }
  };

  return (
    <div className="ai-workspace ai-workspace--v2" data-testid="af-workspace">
      {/* Workspace Header */}
      <div className="ai-ws-header ai-ws-header--v2">
        <div className="ai-ws-label">
          Workspace
          {ctx.activeId && (
            <span className="ai-ws-context" title={`Session: ${ctx.activeId}`}>
              {ctx.sending ? '· 执行中' : '· 就绪'}
            </span>
          )}
        </div>
        <div className="ai-ws-tabs-inline" role="tablist" aria-label="Workspace panels">
          {availableTabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-label={t.label}
              aria-selected={activeTabId === t.id}
              className={`ai-ws-tab-inline${activeTabId === t.id ? ' ai-ws-tab-inline--active' : ''}`}
              onClick={() => setActiveTabId(t.id)}
              title={t.label}
            >
              <span className="ai-ws-tab-icon">{t.icon}</span>
            </button>
          ))}
        </div>
        <button type="button" className="ai-ws-icon-btn" title="Open in new tab" aria-label="Open in new tab">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
            <path d="M15 3h6v6M10 14L21 3M21 14v7H3V3h7" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
        </button>
      </div>

      {/* Approval Card — 内联显示 (不单独页面) */}
      {showApproval && <ApprovalCard />}

      {/* 空闲态: 快速入口 */}
      {isIdle && (
        <div className="ai-ws-empty">
          <div className="ai-ws-empty-title">Workspace</div>
          <div className="ai-ws-empty-sub">AI Factory will surface the right tools as it works</div>
          <div className="ai-ws-quick-starts">
            <button type="button" className="ai-quick-card">
              <span className="ai-quick-icon">📁</span>
              <span className="ai-quick-label">Files</span>
            </button>
            <button type="button" className="ai-quick-card">
              <span className="ai-quick-icon">🌐</span>
              <span className="ai-quick-label">Preview</span>
            </button>
            <button type="button" className="ai-quick-card">
              <span className="ai-quick-icon">⌨</span>
              <span className="ai-quick-label">终端</span>
            </button>
          </div>
        </div>
      )}

      {/* 动态面板内容 */}
      {!isIdle && (
        <div className="ai-ws-body">
          {renderTabContent()}
        </div>
      )}
    </div>
  );
}
