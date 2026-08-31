/**
 * components/af/AfHeader.tsx — AI Enterprise Workbench Global Header (V2).
 *
 * 56px 极简 Header (设计文档 §3):
 *   左:  Logo ◆ + AI Factory + 面包屑 (Project / Context)
 *   右:  ● System Healthy + 🔔 + ❓ + 👤
 *   不塞按钮 — AI Factory 自动决定执行策略, Header 只显示定位信息。
 *
 * 保持 collapsed/onToggleSidebar 签名 (AfWorkspaceFrame 要求) 但不作为主要交互。
 */

import { useEffect, useState } from 'react';
import { useConversation } from './ConversationContext';
import { AfLangSwitch } from '../../i18n';

export interface AfHeaderProps {
  /** 当前子页人话标签 (如 "工作台" / "ScorePocket · Development")。 */
  pageLabel: string;
  /** 侧栏折叠态 (保留签名, V2 不以折叠为主要交互)。 */
  collapsed: boolean;
  /** 点击折叠按钮 → 切换侧栏折叠态 (保留签名)。 */
  onToggleSidebar: () => void;
}

interface HealthInfo {
  llm: boolean;
  agents: boolean;
  connected: boolean;
}

export function AfHeader({ pageLabel, collapsed, onToggleSidebar }: AfHeaderProps): JSX.Element {
  const [health, setHealth] = useState<HealthInfo>({ llm: false, agents: false, connected: false });
  const [runLabel, setRunLabel] = useState('');
  const ctx = useConversation();

  useEffect(() => {
    // 轻量健康探测 (失败不冒充)
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/providers', { headers: { Accept: 'application/json' } });
        if (!cancelled && res.ok) {
          setHealth((h) => ({ ...h, llm: true, connected: true }));
        } else if (!cancelled) {
          setHealth((h) => ({ ...h, connected: true }));
        }
      } catch {
        /* 离线 → 健康数据不变 */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    // 从 context 推导 run 信息 (会话活跃 = 有 Run)
    const activeRun = ctx.sending ? 'Running…' : ctx.activeId ? 'Ready' : 'Idle';
    setRunLabel(activeRun);
  }, [ctx.sending, ctx.activeId]);

  const healthy = health.connected && health.llm;

  return (
    <header className="af-header af-header--v2" data-testid="af-header" role="banner">
      {/* 左: Logo + 品牌 */}
      <div className="af-h-left">
        <span className="af-h-logo" aria-hidden="true">◆</span>
        <span className="af-h-brand">AI Factory</span>
        <span className="af-h-sep" aria-hidden="true">/</span>
        <nav className="af-h-breadcrumb" aria-label="上下文导航">
          <span className="af-h-crumb">{pageLabel}</span>
        </nav>
      </div>

      {/* 中: 空着 — 保持极简 */}
      <div className="af-h-spacer" />

      {/* 右: 系统状态 + 用户 */}
      <div className="af-h-right">
        <button
          type="button"
          className={`af-h-health${healthy ? ' af-h-health--ok' : ' af-h-health--warn'}`}
          title={healthy ? 'System Healthy' : 'System Degraded'}
        >
          <span className={`af-h-dot${healthy ? '' : ' af-h-dot--warn'}`} aria-hidden="true" />
          <span className="af-health-label">{healthy ? 'Healthy' : 'Degraded'}</span>
          <span className="af-h-sep" aria-hidden="true">·</span>
          <span className="af-h-run">{runLabel}</span>
        </button>

        <button type="button" className="af-h-icon-btn" title="Notifications (0)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 1 0-12 0v3.2a2 2 0 0 1-.6 1.4L4 17h5m6 0a3 3 0 1 1-6 0" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        <button type="button" className="af-h-icon-btn" title="Help">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8"/>
            <path d="M9 9a3 3 0 1 1 5.5 1.5c-.8.6-1.5 1-1.5 2v1M12 17h.01" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
          </svg>
        </button>

        {/* 语言切换 — 保持 i18n 测试兼容 */}
        <AfLangSwitch compact />

        {/* 开发者控制台链接 — 保留 (K7a 单入口壳要求) */}
        <a
          href="#/ops"
          className="af-h-icon-btn af-h-dev-console"
          title="开发者控制台 (开发/运维)"
          aria-label="开发者控制台 (开发/运维)"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 4h16v4H4zM4 10h10v10H4zM16 10h4v10h-4z" stroke="currentColor" strokeWidth="1.5"/>
          </svg>
        </a>

        <div className="af-h-user" title="用户菜单">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="8" r="4" fill="#8b949e"/>
            <path d="M4 21c0-4 4-6 8-6s8 2 8 6" fill="#8b949e"/>
          </svg>
        </div>

        {/* 保留折叠按钮 (AfWorkspaceFrame 签名要求), 但移到最右 */}
        <button
          type="button"
          className="af-h-collapse"
          aria-label={collapsed ? '展开侧栏' : '折叠侧栏'}
          onClick={onToggleSidebar}
          title={collapsed ? '展开侧栏' : '折叠侧栏'}
        >
          {collapsed ? '»' : '«'}
        </button>
      </div>
    </header>
  );
}
