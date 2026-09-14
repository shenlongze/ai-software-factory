/**
 * components/af/AfTimeline.tsx — AI Factory 垂直时间线 (S10-014 Task 003, §4.3)。
 *
 * 规格 (AF-UI-Architecture §9.5): 左侧时间戳 (灰) + 状态色圆点 8px + 连接线 2px
 * + 右侧内容 (执行者/动作/结果徽标)。
 * - status 缺省 → 中性圆点; running → 呼吸动画 (§4.4)
 * - 空数组 → 空态提示 (不渲染空列表)
 * 纯展示组件: 不 fetch, 事件由父层传入。
 */

import type { DomainStatus } from '../../models/domain';
import { formatTime } from './afLabels';

export interface AfTimelineItem {
  time: string;
  actor: string;
  action: string;
  result: string;
  status?: DomainStatus;
}

export interface AfTimelineProps {
  items: AfTimelineItem[];
}

export function AfTimeline({ items }: AfTimelineProps): JSX.Element {
  if (items.length === 0) {
    return (
      <div className="af-timeline-empty" data-testid="af-timeline-empty">
        暂无活动
      </div>
    );
  }
  return (
    <div className="af-timeline" data-testid="af-timeline">
      {items.map((item, idx) => {
        const tone = item.status ?? 'neutral';
        const isLast = idx === items.length - 1;
        return (
          <div className="af-timeline-item" data-testid="af-timeline-item" key={`${item.time}-${idx}`}>
            <div className="af-timeline-time" data-testid="af-timeline-time">
              {formatTime(item.time)}
            </div>
            <div className="af-timeline-rail">
              <span
                className={`af-timeline-dot af-timeline-dot--${tone}`}
                data-testid="af-timeline-dot"
                aria-hidden="true"
              />
              {!isLast ? <span className="af-timeline-line" aria-hidden="true" /> : null}
            </div>
            <div className="af-timeline-body">
              <span className="af-timeline-actor">{item.actor}</span>
              <span className="af-timeline-action">{item.action}</span>
              {item.result != null && item.result.length > 0 ? (
                <span className="af-timeline-result">{item.result}</span>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
