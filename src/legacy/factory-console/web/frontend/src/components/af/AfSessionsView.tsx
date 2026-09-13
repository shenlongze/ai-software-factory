/**
 * components/af/AfSessionsView.tsx — 会话管理视图 (S35-UI)。
 *
 * 数据源: GET /api/sessions (统一后端 — console_sessions SSOT)。
 * 操作: 切换 (点行 → 激活会话) / 重命名 (PATCH) / 归档-恢复 (PATCH status)
 *       / 删除 (DELETE /api/sessions/{id})。
 * 原则: 纯 Projection — 不前端伪造会话; 后端不可达 → 空态不崩。
 */

import { useEffect, useMemo, useState } from 'react';
import { useConversation } from './ConversationContext';
import './af.css';

interface SessionRow {
  id: string;
  title?: string;
  status?: string;
  scope?: string;
  project_id?: string | null;
  created_at?: string;
  updated_at?: string;
  task_title?: string | null;
}

export function AfSessionsView(): JSX.Element {
  const ctx = useConversation();
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  const load = () => {
    fetch('/api/sessions', { headers: { Accept: 'application/json' } })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: { items?: SessionRow[] }) => {
        setSessions(d.items ?? []);
        setError('');
      })
      .catch((err) => setError(`加载失败: ${String(err)}`))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const q = query.trim().toLowerCase();
  const visible = useMemo(() => {
    return sessions
      .filter((s) => (showArchived ? s.status === 'archived' : s.status !== 'archived'))
      .filter((s) => !q || String(s.title ?? s.id).toLowerCase().includes(q))
      .sort((a, b) => String(b.updated_at ?? '').localeCompare(String(a.updated_at ?? '')));
  }, [sessions, q, showArchived]);

  const rename = (s: SessionRow) => {
    const next = window.prompt('会话标题:', s.title || '');
    if (!next || !next.trim()) return;
    fetch(`/api/sessions/${encodeURIComponent(s.id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: next.trim() }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(() => load())
      .catch((err) => window.alert(`重命名失败: ${String(err)}`));
  };

  const archive = (s: SessionRow) => {
    const to = s.status === 'archived' ? 'active' : 'archived';
    fetch(`/api/sessions/${encodeURIComponent(s.id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: to }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(() => load())
      .catch((err) => window.alert(`操作失败: ${String(err)}`));
  };

  const remove = (s: SessionRow) => {
    if (!window.confirm(`删除会话「${s.title || s.id}」? 不可恢复。`)) return;
    fetch(`/api/sessions/${encodeURIComponent(s.id)}`, { method: 'DELETE' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(() => load())
      .catch((err) => window.alert(`删除失败: ${String(err)}`));
  };

  const openSession = (s: SessionRow) => {
    ctx.selectSession(s.id);
    window.location.hash = '#/workspace';
  };

  if (loading) return <div className="af-sessions-view af-sessions-empty">加载会话…</div>;

  return (
    <div className="af-sessions-view" data-testid="af-sessions-view">
      <div className="af-sessions-head">
        <h3>💬 会话管理</h3>
        <span className="af-sessions-count">{visible.length} 个会话</span>
      </div>
      <input
        className="af-sessions-search"
        placeholder="搜索会话…"
        aria-label="搜索会话"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <button type="button" className="af-sessions-toggle" onClick={() => setShowArchived((v) => !v)}>
        {showArchived ? '显示活跃会话' : `查看归档 (${sessions.filter((s) => s.status === 'archived').length})`}
      </button>
      {error ? <p className="af-sessions-note">{error}</p> : null}
      {visible.length === 0 ? (
        <p className="af-sessions-note">
          {error ? '（后端不可达）' : showArchived ? '暂无归档会话' : '暂无会话 — 在中栏说一句"我想做…"开始'}
        </p>
      ) : (
        <div className="af-sessions-list">
          {visible.map((s) => (
            <div key={s.id} className={`af-session-row${ctx.activeId === s.id ? ' active' : ''}`}>
              <button type="button" className="af-session-main" onClick={() => openSession(s)}>
                <span className="af-session-title">{s.title || `Session ${s.id.slice(-6)}`}</span>
                <span className="af-session-meta">
                  <code>{s.id}</code>
                  {s.scope ? ` · ${s.scope}` : ''}
                  {s.project_id ? ` · ${s.project_id}` : ''}
                  {s.task_title ? ` · ${s.task_title}` : ''}
                  {s.updated_at ? ` · ${new Date(s.updated_at).toLocaleString()}` : ''}
                </span>
              </button>
              <div className="af-session-ops">
                <button type="button" className="af-session-op" title="重命名" onClick={() => rename(s)}>
                  ✎
                </button>
                <button type="button" className="af-session-op" title={s.status === 'archived' ? '恢复' : '归档'} onClick={() => archive(s)}>
                  {s.status === 'archived' ? '↩' : '⎋'}
                </button>
                <button type="button" className="af-session-op af-session-op--danger" title="删除" onClick={() => remove(s)}>
                  🗑
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
