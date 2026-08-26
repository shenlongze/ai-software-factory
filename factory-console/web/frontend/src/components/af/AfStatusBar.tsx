/**
 * components/af/AfStatusBar.tsx — 底部状态栏 (K-7d, VSCode 风格)。
 *
 * 模型 (GET /api/providers 首个 ACTIVE) · 作用域 · 会话消息/上下文 tokens ·
 * 版本 (GET /version)。真实数据, 失败 → 诚实占位 (—)。
 */

import { useEffect, useState } from 'react';
import { useConversation } from './ConversationContext';

export interface AfStatusBarProps {
  /** 作用域人话标签 (如 "公司 · 我的公司" / "项目 · markpad")。 */
  scopeLabel: string;
}

export function AfStatusBar({ scopeLabel }: AfStatusBarProps): JSX.Element {
  const [model, setModel] = useState<string>('');
  const [version, setVersion] = useState<string>('');
  const ctx = useConversation();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/providers', { headers: { Accept: 'application/json' } });
        if (!cancelled && res.ok) {
          const raw = (await res.json()) as { items?: { id: string; status: string; models: string[] }[] };
          const items = raw.items ?? [];
          const active = items.find((p) => p.status === 'ACTIVE' && p.models.length > 0);
          if (active) {
            const first = active.models[0];
            setModel(typeof first === 'string' ? first : String(first));
          }
        }
      } catch {
        /* 失败 → 占位 */
      }
      try {
        const res = await fetch('/version', { headers: { Accept: 'application/json' } });
        if (!cancelled && res.ok) {
          const v = (await res.json()) as { version?: string };
          if (v.version) setVersion(`v${v.version}`);
        }
      } catch {
        /* 失败 → 占位 */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const tokens = ctx.messages.reduce((acc, m) => acc + Math.ceil(m.content.length / 2), 0);

  return (
    <footer className="af-statusbar" data-testid="af-statusbar">
      <span className="af-statusbar-item" data-testid="af-statusbar-model">
        ⚡ {model || '模型 —'}
      </span>
      <span className="af-statusbar-item">📍 {scopeLabel}</span>
      <span className="af-statusbar-item">
        💬 会话 {ctx.sessions.length} · 消息 {ctx.messages.length} · ≈{tokens} tokens
      </span>
      <span className="af-statusbar-item af-statusbar-item--right" data-testid="af-statusbar-version">
        {version || 'v—'}
      </span>
    </footer>
  );
}
