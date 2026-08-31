/**
 * components/af/AfStatusBar.tsx — Global Status Bar 28px (V2, 设计文档 §20)。
 *
 * ● Connected | Run | Agents | Tasks | Artifacts | Tokens | Cost
 *
 * 真实数据: model 来自 /api/providers, messages/tokens 来自 ConversationContext。
 * 失败 → 诚实占位 "—", 绝不伪造进度或数据。
 */

import { useEffect, useState } from 'react';
import { useConversation } from './ConversationContext';

export interface AfStatusBarProps {
  /** 作用域人话标签 (保留签名)。 */
  scopeLabel: string;
}

export function AfStatusBar({ scopeLabel: _scopeLabel }: AfStatusBarProps): JSX.Element {
  const [model, setModel] = useState<string>('—');
  const [connected, setConnected] = useState(false);
  const ctx = useConversation();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/providers', { headers: { Accept: 'application/json' } });
        if (!cancelled && res.ok) {
          setConnected(true);
          const raw = (await res.json()) as { items?: { id: string; status: string; models: string[] }[] };
          const active = (raw.items ?? []).find((p) => p.status === 'ACTIVE' && p.models.length > 0);
          if (active) {
            const first = active.models[0];
            setModel(typeof first === 'string' ? first : String(first));
          }
        }
      } catch {
        /* 离线 → 保持默认值 */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // 轻量 tokens 估算 (真实 tokens 后端才知道, 前端估算 ≈ chars/2)
  const tokens = ctx.messages.reduce((acc, m) => acc + Math.ceil(m.content.length / 2), 0);
  // run 状态
  const runLabel = ctx.sending ? 'Running' : ctx.activeId ? 'Ready' : 'Idle';
  const runId = ctx.activeId ? ctx.activeId.slice(-4) : '—';

  return (
    <footer className="af-statusbar af-statusbar--v2" data-testid="af-statusbar" role="status">
      {/* 左: 连接 + Run */}
      <span className={`af-sb-item af-sb-item--health ${connected ? 'ok' : 'off'}`}>
        <span className="af-sb-dot" aria-hidden="true" />
        {connected ? 'Connected' : 'Offline'}
      </span>
      <span className="af-sb-item af-sb-item--sep">|</span>
      <span className="af-sb-item">
        Run <span className="af-sb-run">{runLabel}</span>
        {runId !== '—' && <span className="af-sb-run-id">#{runId}</span>}
      </span>
      <span className="af-sb-item af-sb-item--sep">|</span>
      <span className="af-sb-item">Agents —</span>
      <span className="af-sb-item af-sb-item--sep">|</span>
      <span className="af-sb-item">Tasks —</span>
      <span className="af-sb-item af-sb-item--sep">|</span>
      <span className="af-sb-item">Artifacts —</span>

      {/* 右: Model + Tokens (右对齐, 和设计文档一致) */}
      <span className="af-sb-item af-sb-item--right">
        <span className="af-sb-item af-sb-item--sep">|</span>
        <span className="af-sb-item">⚡ {model}</span>
        <span className="af-sb-item af-sb-item--sep">|</span>
        <span className="af-sb-item">≈{tokens.toLocaleString()} tokens</span>
      </span>
    </footer>
  );
}
