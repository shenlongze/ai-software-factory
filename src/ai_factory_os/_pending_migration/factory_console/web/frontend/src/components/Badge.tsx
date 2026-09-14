export type BadgeTone = 'ok' | 'warn' | 'danger' | 'neutral';

/** 状态/风险徽章 (tone → 颜色; 默认 neutral)。 */
export function Badge({
  text,
  tone = 'neutral',
}: {
  text: string;
  tone?: BadgeTone;
}): JSX.Element {
  return (
    <span className={`badge badge-${tone}`} data-tone={tone}>
      {text}
    </span>
  );
}

/** 状态字符串 → 徽章 (低置信度/高风险 → 警示色)。 */
export function statusBadge(status: string): JSX.Element {
  const s = status.toLowerCase();
  if (s === 'pending' || s === 'running' || s === 'active' || s === 'recommended' || s === 'open') {
    return <Badge text={status} tone="warn" />;
  }
  if (s === 'approved' || s === 'success' || s === 'completed' || s === 'available') {
    return <Badge text={status} tone="ok" />;
  }
  if (s === 'rejected' || s === 'failure' || s === 'error') {
    return <Badge text={status} tone="danger" />;
  }
  return <Badge text={status} tone="neutral" />;
}

/** 风险等级 → 徽章 (low/medium/high)。 */
export function riskBadge(risk: string | null): JSX.Element {
  const r = (risk ?? 'low').toLowerCase();
  const tone: BadgeTone = r === 'high' ? 'danger' : r === 'medium' ? 'warn' : 'ok';
  return <Badge text={risk ?? 'low'} tone={tone} />;
}
