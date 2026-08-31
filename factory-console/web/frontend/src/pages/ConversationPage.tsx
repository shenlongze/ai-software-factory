/**
 * pages/ConversationPage.tsx — K6 Human Console 默认首页 (Conversation OS)。
 *
 * 普通用户唯一主要入口: 和公司说话。
 * - 会话列表 + 消息流 + 输入框 (真实 /api/conversations)
 * - 多轮对话: sendMessage → Intent → 回复 (自然讨论, 非命令)
 * - Work 状态内嵌: work_items 状态行 (真实投影)
 * - drill-down: 任务行 → Work/Task (链接)
 * - 讨论 ≠ 执行: 仅展示, 不自动创建 Work (后端控制)
 */
import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { ConversationSummary, ConversationReply } from '../models/types';

const INTENT_LABEL: Record<string, string> = {
  DISCUSS: '💬 讨论', DECIDE: '✅ 决策', APPROVE: '👍 确认',
  EXECUTE: '🚀 执行', ASK_STATUS: '📊 状态', CLARIFY: '❓ 澄清', REPLY: '🤖',
};

export function ConversationPage(): JSX.Element {
  const [convs, setConvs] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string>('');
  const [messages, setMessages] = useState<Array<{ content: string; intent: string; actor: string }>>([]);
  const [workItems, setWorkItems] = useState<Array<{ id: string; title: string; status: string }>>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { void load(); }, []);

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
      setMessages((m) => [...m, { content: r.reply.text, intent: r.intent, actor: 'system' }]);
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

  const openTask = (taskId: string) => {
    window.location.hash = `#/workspace/work?task=${encodeURIComponent(taskId)}`;
  };

  return (
    <div style={{ display: 'flex', height: '100%', gap: 12 }}>
      {/* 会话列表 */}
      <aside style={{ width: 220, borderRight: '1px solid rgba(255,255,255,0.1)', paddingRight: 12, overflowY: 'auto' }}>
        <button
          onClick={() => void newConversation()}
          style={{ width: '100%', marginBottom: 8, padding: 8, borderRadius: 8,
                   background: '#0071e3', color: '#fff', border: 'none', cursor: 'pointer' }}
        >
          + 新对话
        </button>
        {convs.map((c) => (
          <div
            key={c.id}
            onClick={() => void loadConversation(c.id)}
            style={{ padding: '8px 10px', borderRadius: 8, cursor: 'pointer', marginBottom: 4,
                     background: c.id === activeId ? 'rgba(0,113,227,0.25)' : 'transparent',
                     border: '1px solid rgba(255,255,255,0.06)' }}
          >
            <div style={{ fontSize: 13, fontWeight: 600 }}>{c.metadata?.title ?? '会话'}</div>
            <div style={{ fontSize: 11, opacity: 0.6 }}>{c.id.slice(0, 16)} · v{c.version ?? 1}</div>
          </div>
        ))}
      </aside>

      {/* 消息流 */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {error && <div style={{ color: '#ff453a', fontSize: 12, marginBottom: 4 }}>{error}</div>}

        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {loading && <div style={{ opacity: 0.6 }}>加载中…</div>}
          {messages.length === 0 && !loading && (
            <div style={{ opacity: 0.7, textAlign: 'center', marginTop: 60 }}>
              <div style={{ fontSize: 22, marginBottom: 8 }}>🏢</div>
              <div>和公司说话，开始你的工作</div>
              <div style={{ fontSize: 12, opacity: 0.6, marginTop: 4 }}>
                例如：我想开发一个新的记账 App
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              style={{ alignSelf: m.actor === 'human' ? 'flex-end' : 'flex-start', maxWidth: '78%',
                       padding: '8px 12px', borderRadius: 12, whiteSpace: 'pre-wrap',
                       background: m.actor === 'human' ? '#0071e3' : 'rgba(255,255,255,0.08)',
                       color: m.actor === 'human' ? '#fff' : 'inherit' }}
            >
              <div style={{ fontSize: 10, opacity: 0.7, marginBottom: 2 }}>
                {m.actor === 'human' ? '你' : (INTENT_LABEL[m.intent] ?? m.intent)}
              </div>
              {m.content}
            </div>
          ))}
          {sending && <div style={{ opacity: 0.6, fontSize: 12 }}>思考中…</div>}
          <div ref={bottomRef} />
        </div>

        {/* Work 状态内嵌 (真实投影) */}
        {workItems.length > 0 && (
          <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', padding: '8px 4px' }}>
            <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 4 }}>当前工作</div>
            {workItems.slice(-4).map((wi) => (
              <div
                key={wi.id}
                onClick={() => wi.id && openTask(wi.id)}
                style={{ fontSize: 12, display: 'flex', gap: 8, alignItems: 'center',
                         cursor: wi.id ? 'pointer' : 'default', padding: '2px 4px' }}
              >
                <span>{wi.status === 'COMPLETED' ? '✅' : wi.status === 'FAILED' ? '❌' : wi.status === 'RECOVERED' ? '🔧' : '🔄'}</span>
                <span>{wi.title}</span>
                <span style={{ opacity: 0.6, fontSize: 10 }}>{wi.status}</span>
              </div>
            ))}
          </div>
        )}

        {/* 输入 */}
        <div style={{ display: 'flex', gap: 8, padding: '8px 4px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void send(); }}
            placeholder={activeId ? '和公司说话…' : '先选择或新建一个对话'}
            disabled={!activeId || sending}
            style={{ flex: 1, padding: '10px 12px', borderRadius: 10, border: '1px solid rgba(255,255,255,0.15)',
                     background: 'rgba(255,255,255,0.05)', color: 'inherit' }}
          />
          <button
            onClick={() => void send()}
            disabled={!activeId || sending || !input.trim()}
            style={{ padding: '0 18px', borderRadius: 10, border: 'none', cursor: 'pointer',
                     background: '#0071e3', color: '#fff' }}
          >
            发送
          </button>
        </div>
      </main>
    </div>
  );
}
