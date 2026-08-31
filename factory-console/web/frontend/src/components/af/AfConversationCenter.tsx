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
import { api } from '../../api/client';
import type { SessionRunSummary } from '../../models/types';
import { renderMarkdown } from './markdown';
import './af.css';

// 执行阶段人话映射 (用于 "AI 正在做什么")

// S31-004: 角色人话标签 (不暴露内部角色名给普通用户)
const ROLE_LABELS: Record<string, string> = {
  'product-manager': '产品经理',
  'uxui': 'UX/UI 设计',
  'architect': '架构设计',
  'developer': '开发',
  'tester': '测试',
  'release': '发布',
};

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
  const [runs, setRuns] = useState<SessionRunSummary[]>([]);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  // S34-001 P0-5: Run 卡默认展开但可折叠 (执行上下文, 非消息)
  const [runsCollapsed, setRunsCollapsed] = useState(false);
  // S31-006: Command Center — Active Work + Recent Results (真实 opsOverview)
  const [overview, setOverview] = useState<{ projects?: { running?: number; total?: number }; recent_activity?: Array<{ event_type?: string; timestamp?: string; trace_id?: string }> } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const hasMessages = ctx.messages.length > 0;

  // S31-006: Command Center — 加载真实运行概览 (Active Work / Recent Results)
  useEffect(() => {
    let cancelled = false;
    api
      .opsOverview()
      .then((d) => {
        if (!cancelled) setOverview(d);
      })
      .catch(() => { /* 失败静默 — 不伪造 */ });
    return () => { cancelled = true; };
  }, []);

  // S30-004 P0-2: 加载 Session 关联的真实 Run (activeId 变化时拉取, 后端 Source of Truth)
  useEffect(() => {
    let cancelled = false;
    if (ctx.activeId == null) {
      setRuns([]);
      return;
    }
    api.sessionRuns(ctx.activeId)
      .then((d) => {
        if (!cancelled) setRuns(d.runs ?? []);
      })
      .catch(() => {
        if (!cancelled) setRuns([]); // 失败静默 — 不伪造状态
      });
    return () => {
      cancelled = true;
    };
  }, [ctx.activeId, ctx.sending]);

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
    // 通用 (真实 phase 后端没返回时用这个) — S34-001 P0-3: 自然中文
    return '正在分析并执行你的请求…';
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

            {/* S31-006: Active Work — 真实运行中 (来自 opsOverview, 非前端模拟) */}
            {overview && (overview.projects?.running ?? 0) > 0 && (
              <div className="ai-cc-section" data-testid="af-active-work">
                <div className="ai-cc-section-title">正在进行</div>
                <div className="ai-cc-active">
                  <span className="ai-cc-dot ai-cc-dot--running" aria-hidden="true" />
                  <span>{overview.projects?.running ?? 0} 个任务运行中</span>
                </div>
              </div>
            )}

            {/* S31-006: Recent Results — 真实最近活动 (事件流) */}
            {overview && Array.isArray(overview.recent_activity) && overview.recent_activity.length > 0 && (
              <div className="ai-cc-section" data-testid="af-recent-results">
                <div className="ai-cc-section-title">最近</div>
                <div className="ai-cc-recent">
                  {overview.recent_activity.slice(0, 4).map((ev, i) => (
                    <div key={i} className="ai-cc-recent-item">
                      <span className="ai-cc-recent-icon">✓</span>
                      <span className="ai-cc-recent-type">{ev.event_type ?? 'event'}</span>
                      <span className="ai-cc-recent-time">
                        {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ''}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          // ========== 消息流 ==========
          <div className="ai-msg-stream">
            {ctx.messages.map((m, idx) => (
              <MessageBubble
                key={m.id ?? idx}
                role={m.role}
                content={m.content}
                meta={m.meta ?? undefined}
                runs={runs}
                expandedRunId={expandedRun}
                onToggleRun={(id) => setExpandedRun(expandedRun === id ? null : id)}
                runsCollapsed={runsCollapsed}
                onToggleRunsCollapsed={() => setRunsCollapsed(!runsCollapsed)}
              />
            ))}

            {/* 发送中 — S34-001 P0-3: 自然 Working 状态 (非永久消息) */}
            {ctx.sending && (
              <div className="ai-msg ai-msg--ai" data-testid="af-execution-state">
                <div className="ai-msg-avatar ai-msg-avatar--ai" aria-hidden="true">◆</div>
                <div className="ai-msg-body">
                  <div className="ai-execution-card">
                    <div className="ai-execution-head">
                      <span className="ai-execution-title">AI Factory</span>
                      <span className="ai-execution-status ai-execution-status--working">正在工作…</span>
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
  meta?: { thinking_steps?: unknown[]; tool_calls?: unknown[]; run_ids?: string[] };
  /** S34-002: 本会话真实 Runs (按消息 meta.run_ids 过滤归属) */
  runs?: SessionRunSummary[];
  /** S34-002: Run 展开/折叠状态 (消息级) */
  expandedRunId?: string | null;
  onToggleRun?: (id: string) => void;
  runsCollapsed?: boolean;
  onToggleRunsCollapsed?: () => void;
}

function MessageBubble({ role, content, meta, runs = [], expandedRunId, onToggleRun, runsCollapsed, onToggleRunsCollapsed }: MessageBubbleProps): JSX.Element {
  const isUser = role === 'user';
  // S34-001: 空内容 + 无工具调用 + 无 Run → 不渲染 (执行状态卡负责提示)
  if (!isUser && !content.trim() && !(meta?.tool_calls && meta.tool_calls.length > 0) && !(meta?.run_ids && meta.run_ids.length > 0)) {
    return <></>;
  }
  // S34-002: 本消息触发的 Run (真实过滤, 非全局)
  const msgRuns = (meta?.run_ids ?? []).map((rid) => runs.find((r) => r.run_id === rid)).filter((r): r is SessionRunSummary => r != null);

  return (
    <div className={`ai-msg ai-msg--${isUser ? 'user' : 'ai'}`}>
      <div className={`ai-msg-avatar ai-msg-avatar--${isUser ? 'user' : 'ai'}`} aria-hidden="true">
        {isUser ? '👤' : '◆'}
      </div>
      <div className="ai-msg-body">
        {/* 角色标签 — 用户: "You", AI: "AI Factory" */}
        <div className="ai-msg-role">{isUser ? 'You' : 'AI Factory'}</div>
        <div className={`ai-msg-bubble ai-msg-bubble--${isUser ? 'user' : 'ai'}`}>
          {/* S34-001: AI 回复 + 用户输入都支持 Markdown (安全渲染, 零依赖) */}
          {content && <div className="ai-msg-text">{renderMarkdown(content)}</div>}

          {/* AI 消息: 如果有 tool_calls, 渲染结构化执行卡片 */}
          {!isUser && meta?.tool_calls && meta.tool_calls.length > 0 && (
            <ToolCallList toolCalls={meta.tool_calls as Array<{ name?: string; tool?: string; args?: Record<string, unknown>; status?: string }>} />
          )}

          {/* S34-002: 本条回复触发的 Run — 执行证据属于这条 AI 回复, 不是全局 */}
          {!isUser && msgRuns.length > 0 && (
            <div className="ai-run-context" data-testid={`af-run-context-${msgRuns[0].run_id}`}>
              <div className="ai-run-context-head">
                <span className="ai-run-context-label">执行中 · {msgRuns.length} 个 Run</span>
                <span className="ai-run-context-toggle" role="button" aria-label="折叠/展开执行" onClick={onToggleRunsCollapsed}>
                  {runsCollapsed ? '展开 ▾' : '收起 ▴'}
                </span>
              </div>
              {!runsCollapsed && (
                <div className="ai-run-context-body">
                  {msgRuns.map((r) => (
                    <div key={r.run_id}>
                      <button
                        type="button"
                        className="ai-run-item"
                        data-testid="af-run-item"
                        onClick={() => onToggleRun?.(r.run_id)}
                      >
                        <span className={`ai-run-status ai-run-status--${r.status}`}>
                          {r.status === 'running' ? '●' : r.status === 'completed' ? '✓' : '✗'}
                        </span>
                        <span className="ai-run-id">{r.run_id}</span>
                        <span className="ai-run-state">{r.status}</span>
                        <span className="ai-run-expand">{expandedRunId === r.run_id ? '▾' : '▸'}</span>
                      </button>
                      {expandedRunId === r.run_id && (
                        <div className="ai-run-detail" data-testid="af-run-detail">
                          {Array.isArray(r.stages) && r.stages.length > 0 ? (
                            r.stages.map((s, i) => {
                              const stage = s as { role?: string; stage?: string; status?: string; latency_s?: number };
                              return (
                                <div key={i} className="ai-run-stage">
                                  <span className={`ai-run-stage-state ai-run-stage-state--${(stage.status ?? '').toLowerCase()}`}>
                                    {stage.status === 'COMPLETED' ? '✓' : stage.status === 'RUNNING' || stage.status === 'running' ? '●' : '○'}
                                  </span>
                                  <span className="ai-run-stage-role">{ROLE_LABELS[stage.role ?? ''] ?? stage.role ?? stage.stage ?? 'stage'}</span>
                                  {stage.latency_s != null && (
                                    <span className="ai-run-stage-latency">{stage.latency_s.toFixed(1)}s</span>
                                  )}
                                </div>
                              );
                            })
                          ) : (
                            <div className="ai-run-detail-empty">暂无执行阶段</div>
                          )}
                          {r.totals && Object.keys(r.totals).length > 0 && (
                            <div className="ai-run-totals-line">
                              tokens {r.totals.total_tokens ?? '-'} · cost ${(r.totals.cost_usd_est ?? 0).toFixed(4)}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ToolCallList({ toolCalls }: { toolCalls: Array<{ name?: string; tool?: string; args?: Record<string, unknown>; status?: string }> }): JSX.Element {
  // S34-001 P0-4: 默认 compact — 执行证据融入对话, 不抢占主视觉
  const [open, setOpen] = useState(false);
  const okCount = toolCalls.filter((tc) => (tc.status ?? 'ok') === 'ok').length;
  const count = toolCalls.length;
  const visible = open ? toolCalls : toolCalls.slice(0, 4);

  return (
    <div className="ai-tool-calls">
      <button type="button" className="ai-tool-calls-summary" onClick={() => setOpen(!open)}>
        <span className="ai-tool-calls-title">✓ 已完成 {okCount} 个操作</span>
        <span className="ai-tool-calls-toggle">{open ? '收起 ▴' : '展开 ▾'}</span>
      </button>
      {open && (
        <div className="ai-tool-calls-detail">
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
      )}
    </div>
  );
}
