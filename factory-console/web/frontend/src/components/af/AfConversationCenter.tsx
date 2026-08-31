/**
 * components/af/AfConversationCenter.tsx — K9 Human Workspace 中栏 (Conversation)。
 *
 * 人机协作空间 (PRD §3.2): 会话列表 + 消息流 + 输入。
 * - 消息可携带结构化卡片 (MessageCardView: 分析/PRD/任务树/执行/诊断/审批)
 * - send 后根据 reply.intent 联动右栏 Workspace (tabForIntent)
 * - 数据全来自真实 API (conversations), 零业务状态。
 */

import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { useI18n } from '../../i18n';
import type { ConversationSummary, ConversationReply } from '../../models/types';
import { MessageCardView } from './AfMessageCard';
import type { MessageCardPayload } from '../../models/types';
import { useConversation } from './ConversationContext';
import { tabForIntent } from './AfWorkspace';
import './af.css';

interface UiMessage {
  content: string;
  intent: string;
  actor: string;
  card?: MessageCardPayload;
}

export function AfConversationCenter(): JSX.Element {
  const { t } = useI18n();
  const [convs, setConvs] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string>('');
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [workItems, setWorkItems] = useState<Array<{ id: string; title: string; status: string }>>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const { setWorkspaceTab } = useConversation();

  useEffect(() => {
    void load();
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const items = await api.conversations();
      setConvs(items);
      if (items.length > 0 && !activeId) {
        setActiveId(items[0].id);
        void loadConversation(items[0].id);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const loadConversation = async (id: string) => {
    setActiveId(id);
    try {
      const c = await api.getConversation(id);
      setMessages((c.messages ?? []).map((m) => ({ content: m.content, intent: m.intent, actor: m.actor })));
      setWorkItems(c.state?.work_items ?? []);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [messages]);

  const newConversation = async () => {
    try {
      const c = await api.createConversation('新会话 ' + new Date().toLocaleTimeString());
      await load();
      setActiveId(c.id);
      setMessages([]);
      setWorkItems([]);
    } catch (e) {
      setError(String(e));
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || !activeId) return;
    setInput('');
    setSending(true);
    setMessages((m) => [...m, { content: text, intent: 'user', actor: 'human' }]);
    try {
      const r: ConversationReply = await api.sendConversationMessage(activeId, text);
      setMessages((m) => [
        ...m,
        { content: r.reply.text, intent: r.intent, actor: 'system', card: r.card },
      ]);
      // K9 联动: reply intent → 右栏 Workspace Tab
      setWorkspaceTab(tabForIntent(r.intent));
      // 刷新 work 状态 (真实投影)
      const c = await api.getConversation(activeId);
      setWorkItems((c.state?.work_items ?? []).map((wi) => ({ id: wi.id, title: wi.title, status: wi.status })));
    } catch (e) {
      setError(String(e));
      setMessages((m) => [...m, { content: '⚠️ 发送失败: ' + String(e), intent: 'REPLY', actor: 'system' }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="af-conv-center" data-testid="af-conv-center">
      {/* 会话列表 */}
      <aside className="af-conv-list">
        <button className="af-btn af-btn--primary af-conv-new" onClick={() => void newConversation()}>
          + {t('chat.newSession')}
        </button>
        {convs.map((c) => (
          <div
            key={c.id}
            className={`af-conv-item${c.id === activeId ? ' af-conv-item--active' : ''}`}
            onClick={() => void loadConversation(c.id)}
          >
            <div className="af-conv-item-title">{c.metadata?.title ?? '会话'}</div>
            <div className="af-conv-item-meta">{c.id.slice(0, 12)}</div>
          </div>
        ))}
      </aside>

      {/* 消息流 */}
      <div className="af-conv-main">
        <div className="af-conv-messages" data-testid="af-conv-messages">
          {loading && <div className="af-conv-hint">加载中…</div>}
          {error && <div className="af-conv-hint af-conv-hint--error">⚠️ {error}</div>}
          {messages.length === 0 && !loading && (
            <div className="af-conv-empty">{t('chat.talkHint')}</div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`af-msg af-msg--${m.actor === 'human' ? 'human' : 'ai'}`}>
              <div className="af-msg-bubble">
                {m.card ? (
                  <MessageCardView card={m.card} />
                ) : (
                  <div className="af-msg-text">{m.content}</div>
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Work 状态内嵌 (真实投影) */}
        {workItems.length > 0 && (
          <div className="af-conv-work" data-testid="af-conv-work">
            {workItems.map((wi) => (
              <span key={wi.id} className="af-conv-work-item">
                {wi.title} · <b>{wi.status}</b>
              </span>
            ))}
          </div>
        )}

        {/* 输入区 */}
        <div className="af-conv-input-row">
          <input
            className="af-conv-input"
            value={input}
            placeholder={t('chat.inputPlaceholder')}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            disabled={sending}
          />
          <button className="af-btn af-btn--primary" onClick={() => void send()} disabled={sending || !input.trim()}>
            {sending ? t('chat.sending') : t('chat.send')}
          </button>
        </div>
      </div>
    </div>
  );
}
