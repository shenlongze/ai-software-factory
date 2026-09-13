/** 评分条 (0..1 → 百分比宽度; value 可能为 null = 无数据不臆造)。 */
export function ScoreBar({
  label,
  value,
  max = 1,
}: {
  label: string;
  value: number | null;
  max?: number;
}): JSX.Element {
  const pct = value === null ? 0 : Math.round((Math.min(Math.max(value, 0), max) / max) * 100);
  return (
    <div className="score-bar" data-testid={`score-${label}`}>
      <span className="score-label">{label}</span>
      <div className="score-track">
        <div className="score-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="score-value">{value === null ? '—' : `${pct}%`}</span>
    </div>
  );
}
