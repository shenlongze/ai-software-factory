/**
 * ds/StatusBadge.tsx — 阶段状态徽章 (8 状态: pending/running/waiting_review/
 * approved/completed/failed/rejected/rework → 语义色 + 中文标签)。
 */

import { statusLabel, statusTone } from '../../design/tokens';

export function StatusBadge({ status, label }: { status: string; label?: string }): JSX.Element {
  const tone = statusTone(status);
  return (
    <span
      className={`ds-badge ds-badge-${tone}`}
      data-status={status.toLowerCase()}
      data-tone={tone}
    >
      <span className="ds-badge-dot" aria-hidden="true" />
      {label ?? statusLabel(status)}
    </span>
  );
}
