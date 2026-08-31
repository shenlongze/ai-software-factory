/**
 * components/af/AfContextNav.tsx — K9 Human Workspace 左栏 (Context)。
 *
 * "我现在在哪里、正在做什么" — 不是传统后台菜单 (PRD §3.1):
 * 对话 / 我的工作 / 项目 / 团队 / 运行中 / 审批。
 * 数据来自真实 API (conversations / projects-os / ops), 零业务状态。
 */

import { useEffect, useState } from 'react';
import { useConversation } from './ConversationContext';
import { api } from '../../api/client';
import type { OpsOverview } from '../../models/types';
import './af.css';

interface ContextNavProps {
  collapsed: boolean;
}

export function AfContextNav({ collapsed }: ContextNavProps): JSX.Element {
  const { setWorkspaceTab, setProjectId } = useConversation();
  const [conversations, setConversations] = useState<Array<{ id: string; title: string }>>([]);
  const [projects, setProjects] = useState<Array<{ id: string; title: string }>>([]);
  const [overview, setOverview] = useState<OpsOverview | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.conversations(), api.osProjects(), api.opsOverview()])
      .then(([convs, projs, ov]) => {
        if (cancelled) return;
        setConversations(convs.map((c) => ({ id: c.id, title: c.metadata?.title ?? '会话' })));
        setProjects(projs.slice(0, 8).map((p) => ({ id: p.id, title: p.title ?? p.id })));
        setOverview(ov as OpsOverview);
      })
      .catch(() => {
        if (!cancelled) {
          setConversations([]);
          setProjects([]);
          setOverview(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const running = overview?.workforce?.running ?? 0;
  const approvals = overview?.projects?.approval ?? 0;

  return (
    <nav className="af-context-nav" data-testid="af-context-nav" aria-label="Context 导航">
      <div className="af-context-brand">AI Factory</div>

      <div className="af-context-section">💬 对话</div>
      <button type="button" className="af-context-item" onClick={() => setWorkspaceTab('task')}>
        <span>当前工作</span>
        {running > 0 && <span className="af-context-badge af-context-badge--green">{running}</span>}
      </button>

      <div className="af-context-section">我的工作</div>
      {conversations.slice(0, 5).map((c) => (
        <button key={c.id} type="button" className="af-context-item af-context-item--sub" onClick={() => setWorkspaceTab('task')}>
          <span className="af-context-ellipsis">{c.title}</span>
        </button>
      ))}

      <div className="af-context-section">项目</div>
      {projects.map((p) => (
        <button
          key={p.id}
          type="button"
          className="af-context-item af-context-item--sub"
          onClick={() => {
            setProjectId(p.id);
            setWorkspaceTab('task');
          }}
        >
          <span className="af-context-ellipsis">{p.title}</span>
        </button>
      ))}

      {!collapsed && (
        <>
          <div className="af-context-section">运行中</div>
          <div className="af-context-stat">
            🟢 {running} 个 Agent 在工作
          </div>

          <div className="af-context-section">审批</div>
          <button type="button" className="af-context-item" onClick={() => setWorkspaceTab('task')}>
            <span>待审批</span>
            {approvals > 0 && <span className="af-context-badge af-context-badge--red">{approvals}</span>}
          </button>
        </>
      )}
    </nav>
  );
}
