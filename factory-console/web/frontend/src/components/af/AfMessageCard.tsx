/**
 * components/af/AfMessageCard.tsx — K9 消息卡片渲染 (PRD §4, 6 种)。
 *
 * 中栏 Conversation 消息可携带结构化卡片, 普通用户直接看到"分析/PRD/任务/审批",
 * 按钮触发真实操作 (查看→右栏 Tab / 批准→Governance / 修复→Self-Healing)。
 * 无卡片 → 纯文本。数据来自消息 payload (后端真实回复), 不伪造。
 */

import type { ReactNode } from 'react';
import { useState } from 'react';
import { useConversation } from './ConversationContext';
import { api } from '../../api/client';
import type { MessageCardPayload } from '../../models/types';
import './af.css';

export type CardType = MessageCardPayload['type'];

export type MessageCard = MessageCardPayload;

function CardShell({ icon, title, children }: { icon: string; title: string; children: ReactNode }): JSX.Element {
  return (
    <div className="af-msg-card" data-testid={`af-msg-card-${title}`}>
      <div className="af-msg-card-head">
        <span className="af-msg-card-icon" aria-hidden="true">
          {icon}
        </span>
        <span className="af-msg-card-title">{title}</span>
      </div>
      <div className="af-msg-card-body">{children}</div>
    </div>
  );
}

function ActionButton({ label, onClick, kind = 'primary' }: { label: string; onClick: () => void; kind?: string }): JSX.Element {
  return (
    <button type="button" className={`af-btn af-btn--${kind} af-msg-card-btn`} onClick={onClick}>
      {label}
    </button>
  );
}

export function MessageCardView({ card }: { card: MessageCard }): JSX.Element {
  const { setWorkspaceTab } = useConversation();
  const [approvalState, setApprovalState] = useState<string>('');

  const viewTab = (tab: string) => () => setWorkspaceTab(tab);
  const approve = async () => {
    if (!card.refId) return;
    try {
      await api.osDecideApproval(card.refId, 'approve');
      setApprovalState('已批准 ✅');
    } catch {
      setApprovalState('操作失败');
    }
  };
  const reject = async () => {
    if (!card.refId) return;
    try {
      await api.osDecideApproval(card.refId, 'reject');
      setApprovalState('已拒绝');
    } catch {
      setApprovalState('操作失败');
    }
  };

  switch (card.type) {
    case 'analysis':
      return (
        <CardShell icon="📋" title="需求分析">
          {card.done?.map((d) => (
            <div key={d} className="af-msg-card-line">✓ {d}</div>
          ))}
          {card.pending?.map((p) => (
            <div key={p} className="af-msg-card-line af-msg-card-line--warn">⚠ {p}</div>
          ))}
          <div className="af-msg-card-actions">
            <ActionButton label="查看分析" onClick={viewTab('code')} />
            <ActionButton label="继续讨论" kind="ghost" onClick={() => {}} />
          </div>
        </CardShell>
      );

    case 'prd':
      return (
        <CardShell icon="📄" title="Product Requirement">
          {card.summary && <div className="af-msg-card-line">{card.summary}</div>}
          <div className="af-msg-card-actions">
            <ActionButton label="查看 PRD" onClick={viewTab('code')} />
            <ActionButton label="确认需求" kind="ghost" onClick={() => {}} />
          </div>
        </CardShell>
      );

    case 'task_tree':
      return (
        <CardShell icon="📊" title="任务树">
          {card.summary && <div className="af-msg-card-line">{card.summary}</div>}
          <div className="af-msg-card-actions">
            <ActionButton label="查看任务" onClick={viewTab('task')} />
          </div>
        </CardShell>
      );

    case 'execution':
      return (
        <CardShell icon="⚙️" title="执行中">
          {card.summary && <div className="af-msg-card-line">{card.summary}</div>}
          <div className="af-msg-card-actions">
            <ActionButton label="查看详情" onClick={viewTab('code')} />
          </div>
        </CardShell>
      );

    case 'diagnosis':
      return (
        <CardShell icon="🐛" title="执行遇到问题">
          {card.summary && <div className="af-msg-card-line">{card.summary}</div>}
          <div className="af-msg-card-actions">
            <ActionButton label="查看诊断" onClick={viewTab('code')} />
            <ActionButton label="修复" kind="ghost" onClick={() => {}} />
          </div>
        </CardShell>
      );

    case 'approval':
      return (
        <CardShell icon="🔐" title="需要你的批准">
          {card.summary && <div className="af-msg-card-line">{card.summary}</div>}
          {card.risk && <div className="af-msg-card-line af-msg-card-line--warn">风险: {card.risk}</div>}
          {approvalState ? (
            <div className="af-msg-card-line">{approvalState}</div>
          ) : (
            <div className="af-msg-card-actions">
              <ActionButton label="批准" onClick={approve} />
              <ActionButton label="拒绝" kind="danger" onClick={reject} />
            </div>
          )}
        </CardShell>
      );

    default:
      return <div className="af-msg-card">{card.summary ?? ''}</div>;
  }
}
