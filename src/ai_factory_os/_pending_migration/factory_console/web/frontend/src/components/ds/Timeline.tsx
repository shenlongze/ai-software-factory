/**
 * ds/Timeline.tsx — 时间线容器 + 节点 (垂直轨道 + 状态色圆点)。
 * StageCard 基础: Agent/Status/Input/Output/Duration/Cost 见 StageCard.tsx。
 */

import type { ReactNode } from 'react';
import { statusTone } from '../../design/tokens';

export function Timeline({ children, className = '' }: { children: ReactNode; className?: string }): JSX.Element {
  return (
    <ol className={`ds-timeline${className ? ` ${className}` : ''}`} data-testid="ds-timeline">
      {children}
    </ol>
  );
}

export function TimelineNode({
  status = 'pending',
  title,
  time,
  children,
}: {
  status?: string;
  title: ReactNode;
  time?: string;
  children?: ReactNode;
}): JSX.Element {
  const tone = statusTone(status);
  return (
    <li className="ds-timeline-node" data-testid="ds-timeline-node" data-status={status.toLowerCase()}>
      <span className={`ds-timeline-dot ds-dot-${tone}`} aria-hidden="true" />
      <div className="ds-timeline-content">
        <div className="ds-timeline-head">
          <span className="ds-timeline-title">{title}</span>
          {time != null ? <span className="ds-timeline-time">{time}</span> : null}
        </div>
        {children != null ? <div className="ds-timeline-body">{children}</div> : null}
      </div>
    </li>
  );
}
