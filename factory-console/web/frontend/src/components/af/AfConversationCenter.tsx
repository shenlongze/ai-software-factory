/**
 * components/af/AfConversationCenter.tsx — Command Center (V2).
 *
 * 设计文档 §7-12: Conversation 是唯一主入口, AI Factory 决定执行策略。
 *   - 用户只表达目标 (What do you want to accomplish?)
 *   - AI Factory 自动组织: Intent → Plan → Workforce → Agents → Tools → Execution
 *   - 执行状态必须可见 (Planning → Researching → Synthesizing → Verifying) — 不是 "Thinking..."
 *   - Agent 是执行者, 不是聊天角色 — UI 中显示 "AI Factory" 而不是逐个 Agent
 *
 * 复用 ConversationContext 全部 API, 仅重绘 UI 外观。
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useConversation } from './ConversationContext';
import { useI18n } from '../../i18n';
import './af.css';

// 执行阶段人话映射 (用于 "AI 正在做什么")

const SUGGESTED_PROMPTS: ReadonlyArray<string> = [
  'Build a ScorePocket app',
  'Analyze competitors and write PRD',
  'Debug failing tests',
  'Generate marketing site',
  'Write API documentation',
  'Improve onboarding UX',
];

export function AfConversationCenter(): JSX.Element {
  const { t } = useI18n();
  const ctx = useConversation();
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  const hasMessages = ctx.messages.length > 0;

  // 自动滚动到底
  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [ctx.messages]);

  // 自动选中第一个会话
  useEffect(() => {
    if (ctx.activeId == null && ctx.sessions.length > 0) {
      ctx.selectSession(ctx.sessions[0].id);
    }
  }, [ctx.activeId, ctx.sessions, ctx.selectSession]);

  // 推导当前执行阶段文案 (优先从 thinking_steps, 否则用通用 sending)
  const executionLabel = useMemo(() => {
    if (!ctx.sending) return null;
    // 通用 (真实 phase 后端没返回时用这个)
    return 'AI Factory is working…';
  }, [ctx.sending]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text) return;
    setInput('');
    if (ctx.activeId == null) {
      await ctx.createSession();
    }
    await ctx.send(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  return (
    <div className="ai-conv-center ai-conv-center--v2" data-testid="af-conv-center">
      <div className="ai-conv-messages" data-testid="af-conv-messages">
        {ctx.loadingSessions && !ctx.activeId ? (
          <div className="ai-conv-loading">Loading…</div>
        ) : !hasMessages ? (
          // ========== Welcome Hero — "What do you want to accomplish?" ==========
          <div className="ai-welcome ai-welcome--v2" data-testid="af-conv-guide">
            <div className="ai-welcome-hero ai-welcome-hero--v2">
              <div className="ai-welcome-logo--v2">◆</div>
              <h1 className="ai-welcome-title--v2">What do you want to accomplish?</h1>
              <p className="ai-welcome-sub--v2">
                你今天想做什么？Describe your goal — AI Factory will plan the work, assemble the right workforce,
                and execute end-to-end.
              </p>
            </div>

            {/* 建议提示 */}
            <div className="ai-welcome-suggestions">
              {SUGGESTED_PROMPTS.map((p) => (
                <button
                  key={p}
                  type="button"
                  className="ai-suggested-prompt"
                  onClick={() => setInput(p)}
                >
                  <span className="ai-suggested-text">{p}</span>
                  <span className="ai-suggested-arrow">→</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          // ========== 消息流 ==========
          <div className="ai-msg-stream">
            {ctx.messages.map((m, idx) => (
              <MessageBubble key={m.id ?? idx} role={m.role} content={m.content} meta={m.meta ?? undefined} />
            ))}

            {/* 发送中 — 显示具体执行状态, 不要 "Thinking..." */}
            {ctx.sending && executionLabel && (
              <div className="ai-msg ai-msg--ai" data-testid="af-execution-state">
                <div className="ai-msg-avatar ai-msg-avatar--ai" aria-hidden="true">◆</div>
                <div className="ai-msg-body">
                  <div className="ai-execution-card">
                    <div className="ai-execution-head">
                      <span className="ai-execution-title">AI Factory</span>
                      <span className="ai-execution-status">Working</span>
                    </div>
                    <div className="ai-execution-body">
                      <span className="ai-execution-text">{executionLabel}</span>
                      <span className="ai-execution-dots" aria-hidden="true">
                        <span /><span /><span />
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* ========== 底部输入区 ========== */}
      <div className="ai-input-area ai-input-area--v2">
        <div className="ai-input-wrap">
          <textarea
            className="ai-input"
            rows={1}
            placeholder={t('chat.inputPlaceholder') || '和公司说话… (讨论需求 / 开始工作 / 查询状态)'}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={ctx.sending}
          />

          {/* 内嵌工具栏 */}
          <div className="ai-input-toolbar">
            <div className="ai-tb-left">
              {/* Auto mode tag — 设计文档 §7: AI 自动决定执行策略 */}
              <span className="ai-tb-auto-tag" title="AI Factory will auto-select agents, models, and tools">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M12 2l2 7h7l-5 3.5 2 7-6-4-6 4 2-7L3 9h7z" fill="currentColor"/>
                </svg>
                Auto
              </span>
              <button type="button" className="ai-tb-btn ai-tb-btn--icon" title="Attach" aria-label="Attach">+</button>
            </div>

            <div className="ai-tb-mid" />

            <button
              type="button"
              className="ai-send-btn"
              onClick={() => void handleSend()}
              disabled={ctx.sending || !input.trim()}
              data-testid="af-conv-send"
              aria-label={t('chat.send') || '发送'}
            >
              {ctx.sending ? (
                <span className="ai-sending-spinner" aria-hidden="true" />
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M4 12L20 4l-4 16-4-6-8-2z" fill="currentColor"/>
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* 上下文 chips (仅在无消息时显示引导) */}
        {!hasMessages && (
          <div className="ai-quick-chips">
            <span className="ai-quick-chip-label">Try:</span>
            <button type="button" className="ai-quick-chip" onClick={() => setInput('Build a ScorePocket app')}>
              💼 App Development
            </button>
            <button type="button" className="ai-quick-chip" onClick={() => setInput('Analyze competitors and write PRD')}>
              📐 Product Discovery
            </button>
            <button type="button" className="ai-quick-chip" onClick={() => setInput('Debug failing tests')}>
              🐛 Debug
            </button>
            <button type="button" className="ai-quick-chip" onClick={() => setInput('Write API documentation')}>
              📝 Docs
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/** 消息气泡 — 用户右/AI Factory 左 */
interface MessageBubbleProps {
  role: string;
  content: string;
  meta?: { thinking_steps?: unknown[]; tool_calls?: unknown[] };
}

function MessageBubble({ role, content, meta }: MessageBubbleProps): JSX.Element {
  const isUser = role === 'user';

  return (
    <div className={`ai-msg ai-msg--${isUser ? 'user' : 'ai'}`}>
      <div className={`ai-msg-avatar ai-msg-avatar--${isUser ? 'user' : 'ai'}`} aria-hidden="true">
        {isUser ? '👤' : '◆'}
      </div>
      <div className="ai-msg-body">
        {/* 角色标签 — 用户: "You", AI: "AI Factory" */}
        <div className="ai-msg-role">{isUser ? 'You' : 'AI Factory'}</div>
        <div className={`ai-msg-bubble ai-msg-bubble--${isUser ? 'user' : 'ai'}`}>
          <div className="ai-msg-text">{content}</div>

          {/* AI 消息: 如果有 tool_calls, 渲染结构化执行卡片 */}
          {!isUser && meta?.tool_calls && meta.tool_calls.length > 0 && (
            <ToolCallList toolCalls={meta.tool_calls as Array<{ name?: string; tool?: string; args?: Record<string, unknown>; status?: string }>} />
          )}
        </div>
      </div>
    </div>
  );
}

function ToolCallList({ toolCalls }: { toolCalls: Array<{ name?: string; tool?: string; args?: Record<string, unknown>; status?: string }> }): JSX.Element {
  // 只显示前 4 个 (避免信息过载)
  const visible = toolCalls.slice(0, 4);
  const count = toolCalls.length;

  return (
    <div className="ai-tool-calls">
      <div className="ai-tool-calls-title">Workforce executed {count} actions</div>
      {visible.map((tc, i) => {
        const name = tc.name ?? tc.tool ?? `Tool ${i + 1}`;
        const status = tc.status ?? 'ok';
        return (
          <div key={i} className="ai-tool-call">
            <span className={`ai-tool-dot ai-tool-dot--${status}`} aria-hidden="true" />
            <span className="ai-tool-name">{name}</span>
            <span className="ai-tool-status">{status === 'ok' ? '✓' : status === 'fail' ? '✕' : '…'}</span>
          </div>
        );
      })}
      {count > 4 && <div className="ai-tool-more">+ {count - 4} more…</div>}
    </div>
  );
}
