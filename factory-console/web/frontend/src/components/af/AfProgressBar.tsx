/**
 * components/af/AfProgressBar.tsx — AI Factory 进度条 (S10-014 Task 003, §4.3)。
 *
 * 规格 (AF-UI-Architecture §9.4): 细 4px + 圆角 + 状态色填充 + 百分比文字。
 * - value 语义: 0..100 百分比 (0/100 边界; NaN/越界 → 夹取, 不崩溃)
 * - status: 6 态语义色填充 (默认主色蓝)
 * 纯展示组件: 不 fetch, 数据由父层传入。
 */

import type { DomainStatus } from '../../models/domain';

export interface AfProgressBarProps {
  /** 进度 0..100 (百分比); 非法值夹取。 */
  value: number;
  /** 状态 (决定填充色; 缺省主色蓝)。 */
  status?: DomainStatus;
}

/** 0..100 夹取 (NaN → 0; 负 → 0; >100 → 100)。 */
export function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function AfProgressBar({ value, status }: AfProgressBarProps): JSX.Element {
  const pct = clampPercent(value);
  const fillClass = status != null ? `af-progress-fill af-progress-fill--${status}` : 'af-progress-fill';
  return (
    <div
      className="af-progress-bar"
      data-testid="af-progress-bar"
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`进度 ${pct}%`}
    >
      <div className="af-progress-track">
        <div className={fillClass} data-testid="af-progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="af-progress-text">{pct}%</span>
    </div>
  );
}
