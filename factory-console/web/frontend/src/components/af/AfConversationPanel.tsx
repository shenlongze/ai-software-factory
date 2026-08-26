/**
 * components/af/AfConversationPanel.tsx — C 列 AI 会话栏 (K-7e)。
 *
 * - 作用域选择 (公司/项目) + 多会话列表 (新建/改名/归档)
 * - 对话消息区 (user/assistant) + 输入发送 (真实 API, LLM 回复)
 * - 上下文指示器: 作用域 + 消息数 + 估算 tokens + "压缩 (K-7f)" 诚实标注
 * - 可收起/可常驻 (context 持久化, localStorage)
 */

import { useEffect, useRef, useState } from 'react';
import { useConversation } from './ConversationContext';
import { useI18n } from '../../i18n';
import { renderMarkdown } from './markdown';
import type { SessionSummary } from '../../models/types';

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '';
  return iso.slice(5, 16).replace('T', ' ');
}

export interface AfConversationPanelProps {
  /** 当前路由项目 id (项目级作用域用; 公司级可空)。 */
  projectId?: string | null;
  /** 项目名 (展示用)。 */
  projectName?: string | null;
}

export function AfConversationPanel({ projectId, projectName }: AfConversationPanelProps): JSX.Element {
  const { t } = useI18n();
  const ctx = useConversation();
  const [input, setInput] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);

  // 项目级作用域同步当前项目
  useEffect(() => {
    ctx.setProjectId(projectId ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // 自动滚动到底
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [ctx.messages.length]);

  if (ctx.collapsed) {
    return (
      <aside className="af-chat af-chat--collapsed" data-testid="af-conversation-panel" aria-label="AI 会话 (已收起)">
        <button type="button" className="af-chat-reopen" onClick={ctx.toggleCollapsed} aria-label={t('chat.reopen')}>
          💬
        </button>
      </aside>
    );
  }

  const activeSession = ctx.sessions.find((s) => s.id === ctx.activeId) ?? null;

  const submit = () => {
    const text = input.trim();
    if (!text || ctx.sending) return;
    setInput('');
    void ctx.send(text);
  };

  const startRename = (s: SessionSummary) => {
    setEditingId(s.id);
    setEditText(s.title);
  };
  const saveRename = (id: string) => {
    const t = editText.trim();
    if (t) ctx.renameSession(id, t);
    setEditingId(null);
  };

  const scopeLabel =
    ctx.scope === 'project'
      ? ctx.featureId != null && ctx.featureName != null
        ? `📁 项目 · ${projectName ?? ctx.projectId ?? '—'} · 💡 ${ctx.featureName}`
        : `📁 项目 · ${projectName ?? ctx.projectId ?? '—'}`
      : '🏢 公司 · 全局';


  const renderSessionRow = (s: SessionSummary) => (
    <div
      key={s.id}
      className={`af-chat-session${s.id === ctx.activeId ? ' af-chat-session--active' : ''}${
        s.status === 'archived' ? ' af-chat-session--archived' : ''
      }`}
      data-testid={`af-session-${s.id}`}
    >
      {editingId === s.id ? (
        <input
          className="af-chat-rename"
          aria-label="会话标题"
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') saveRename(s.id);
            if (e.key === 'Escape') setEditingId(null);
          }}
          autoFocus
        />
      ) : (
        <button
          type="button"
          className="af-chat-session-title"
          onClick={() => ctx.selectSession(s.id)}
          title={s.title}
        >
          {s.status === 'archived' ? '🗄 ' : '● '}
          {s.title}
        </button>
      )}
      {editingId !== s.id ? (
        <span className="af-chat-session-ops">
          <button type="button" className="af-chat-op" onClick={() => startRename(s)} aria-label="改名">
            ✎
          </button>
          <button
            type="button"
            className="af-chat-op"
            onClick={() => ctx.archiveSession(s.id)}
            aria-label="归档"
          >
            🗄
          </button>
        </span>
      ) : null}
    </div>
  );

  return (
    <aside
      className={`af-chat${ctx.pinned ? ' af-chat--pinned' : ''}`}
      data-testid="af-conversation-panel"
      aria-label="AI 会话栏"
    >
      <div className="af-chat-head">
        <span className="af-chat-scope-indicator" data-testid="af-chat-scope" title="作用域自动跟随当前视图">
          {scopeLabel}
        </span>
        <button type="button" className="af-chat-btn" onClick={() => void ctx.createSession()} aria-label={t('chat.newSession')}>
          +
        </button>
        <button
          type="button"
          className={`af-chat-btn${ctx.pinned ? ' af-chat-btn--on' : ''}`}
          onClick={ctx.togglePinned}
          aria-label={ctx.pinned ? t('chat.unpin') : t('chat.pin')}
          title={ctx.pinned ? t('chat.unpin') : t('chat.pin')}
        >
          📌
        </button>
        <button type="button" className="af-chat-btn" onClick={ctx.toggleCollapsed} aria-label={t('chat.collapse')}>
          »
        </button>
      </div>

      <div className="af-chat-sessions" data-testid="af-chat-sessions">
        {ctx.loadingSessions ? (
          <p className="af-chat-note">加载会话…</p>
        ) : ctx.sessions.length === 0 ? (
          <p className="af-chat-note">{t('chat.noSessions')}</p>
        ) : (
          <>
            {ctx.sessions.filter((x) => x.status !== 'archived').map((s) => renderSessionRow(s))}
            {(() => {
              const archived = ctx.sessions.filter((x) => x.status === 'archived');
              if (archived.length === 0) return null;
              return (
                <div className="af-chat-archived" data-testid="af-chat-archived">
                  <button type="button" className="af-chat-archived-toggle" onClick={() => setShowArchived((v) => !v)}>
                    {showArchived ? '▾' : '▸'} 🗄 已归档 {archived.length}
                  </button>
                  {showArchived ? archived.map(renderSessionRow) : null}
                </div>
              );
            })()}
          </>
        )}
      </div>

      <div className="af-chat-ctx" data-testid="af-chat-ctx">
        <span>{scopeLabel}</span>
        <span>消息 {ctx.messages.length}</span>
        <span className="af-chat-compress" title="上下文压缩 (K-7f 规划中)" data-testid="af-chat-compress">
          压缩 K-7f
        </span>
      </div>

      <div className="af-chat-messages" ref={listRef} data-testid="af-chat-messages">
        {activeSession == null ? (
          <p className="af-chat-note">{t('chat.selectFirst')}</p>
        ) : ctx.messages.length === 0 ? (
          <p className="af-chat-note">{t('chat.newSessionHint')}</p>
        ) : (
          ctx.messages.map((m) => (
            <div key={m.id} className={`af-chat-msg af-chat-msg--${m.role}`} data-testid={`af-chat-msg-${m.id}`}>
              <div className="af-chat-msg-meta">
                {m.role === 'user' ? '你' : 'AI'} · {fmtTime(m.created_at)}
              </div>
              <div className={`af-chat-msg-body${m.role === 'assistant' ? ' af-chat-msg-body--md' : ''}`}>
                {m.role === 'assistant' ? renderMarkdown(m.content) : m.content}
              </div>
              {m.role === 'assistant' && m.target && m.target.url ? (
                <a className="af-chat-jump" href={m.target.url} data-testid={`af-chat-jump-${m.id}`}>
                  → {m.target.label}
                </a>
              ) : null}
            </div>
          ))
        )}
        {ctx.sending ? <p className="af-chat-note">{t('chat.sending')}</p> : null}
      </div>

      <div className="af-chat-input-row">
        <input
          className="af-chat-input"
          placeholder={ctx.scope === 'project' ? t('chat.input.project') : t('chat.input.company')}
          aria-label="AI 会话输入"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit();
            if (e.key === 'Enter' && !e.shiftKey) submit();
          }}
        />
        <button type="button" className="af-chat-send" onClick={submit} disabled={ctx.sending || !input.trim()}>
          {ctx.sending ? '…' : t('chat.send')}
        </button>
      </div>
    </aside>
  );
}
