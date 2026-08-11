/**
 * components/af/AfStatusBadge.tsx — AI Factory 状态徽标 (S10-014 Task 003, §4.3)。
 *
 * 规格 (AF-UI-Architecture §9.4): 状态标签 = 色点 + 文字 (● 执行中)。
 * - 6 语义态: 完成绿 / 执行中蓝(呼吸) / 待办灰 / 阻塞紫 / 失败红 / 待审核橙 (§4.2)
 * - 色点 + 文字并存 (无障碍 §9.8: 状态不只靠颜色)
 * - 未知状态降级: 原样显示 + 中性色点; 缺失 → '—' (§6.3)
 * 纯展示组件: 不 fetch, 数据由父层传入。
 */

import { statusLabel } from './afLabels';
import { STATUS_COLORS } from './afTokens';

export interface AfStatusBadgeProps {
  /** 状态值 (DomainStatus 6 态; 未知值原样显示)。 */
  status: string | null | undefined;
  /** 人话文字覆盖 (默认走 afLabels 映射)。 */
  label?: string;
}

/** 状态 → 色点 class 后缀 (已知 6 态原样; 未知/缺失 → neutral)。 */
function toneKey(status: string | null | undefined): string {
  if (status == null || status.length === 0) return 'neutral';
  const key = status.toLowerCase();
  return key in STATUS_COLORS ? key : 'neutral';
}

export function AfStatusBadge({ status, label }: AfStatusBadgeProps): JSX.Element {
  const text = label ?? statusLabel(status);
  const tone = toneKey(status);
  return (
    <span
      className="af-status-badge"
      data-testid="af-status-badge"
      aria-label={`状态: ${text}`}
    >
      <span className={`af-status-dot af-status-dot--${tone}`} aria-hidden="true" />
      <span className="af-status-text">{text}</span>
    </span>
  );
}
