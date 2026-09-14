/**
 * ds/StageCard.tsx — 阶段卡片 (Agent/Status/输入/输出/耗时/成本/查看详情)。
 * inTimeline=true 时包一层 TimelineNode (状态圆点 + 标题), 供 S10-003 Timeline 消费。
 */

import { agentMeta, formatCost, formatDuration } from '../../design/tokens';
import { AgentAvatar } from './AgentAvatar';
import { Button } from './Button';
import { StatusBadge } from './StatusBadge';
import { TimelineNode } from './Timeline';

export function StageCard({
  name,
  agent,
  status,
  input,
  output,
  durationSec,
  cost,
  onViewDetails,
  inTimeline = false,
}: {
  name: string;
  agent: string;
  status: string;
  input?: string[];
  output?: string[];
  durationSec?: number | null;
  cost?: number | null;
  onViewDetails?: () => void;
  inTimeline?: boolean;
}): JSX.Element {
  const agentName = agentMeta(agent).label;
  const card = (
    <div className="ds-stage-card" data-testid="ds-stage-card" data-status={status.toLowerCase()}>
      <div className="ds-stage-card-head">
        <AgentAvatar role={agent} />
        <div className="ds-stage-card-title">
          <span className="ds-stage-card-name">{name}</span>
          <span className="ds-stage-card-agent">{agentName}</span>
        </div>
        <StatusBadge status={status} />
      </div>
      <dl className="ds-stage-card-meta">
        {input != null && input.length > 0 ? (
          <div className="ds-stage-card-field">
            <dt>输入</dt>
            <dd>{input.join('、')}</dd>
          </div>
        ) : null}
        {output != null && output.length > 0 ? (
          <div className="ds-stage-card-field">
            <dt>输出</dt>
            <dd>{output.join('、')}</dd>
          </div>
        ) : null}
        <div className="ds-stage-card-field">
          <dt>耗时</dt>
          <dd>{formatDuration(durationSec)}</dd>
        </div>
        <div className="ds-stage-card-field">
          <dt>成本</dt>
          <dd>{formatCost(cost)}</dd>
        </div>
      </dl>
      {onViewDetails != null ? (
        <div className="ds-stage-card-actions">
          <Button variant="secondary" size="sm" onClick={onViewDetails}>
            查看详情
          </Button>
        </div>
      ) : null}
    </div>
  );

  if (!inTimeline) return card;
  return (
    <TimelineNode status={status} title={name}>
      {card}
    </TimelineNode>
  );
}
