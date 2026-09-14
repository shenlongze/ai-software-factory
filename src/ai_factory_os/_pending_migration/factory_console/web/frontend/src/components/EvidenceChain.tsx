import { useAppState } from '../state/AppState';

/**
 * 证据链 (lineage_ref 列表, 只读展示)。
 * 普通模式: 仅显示数量 + 前 2 条; 专业模式: 展开全部 (Expert: Evidence/Lineage)。
 */
export function EvidenceChain({ evidence }: { evidence: string[] }): JSX.Element {
  const { mode } = useAppState();
  if (!evidence || evidence.length === 0) {
    return <span className="evidence-empty">无证据链</span>;
  }
  const visible = mode === 'expert' ? evidence : evidence.slice(0, 2);
  return (
    <div className="evidence-chain" data-testid="evidence-chain">
      <span className="evidence-count">{evidence.length} 条证据</span>
      <ul className="evidence-list">
        {visible.map((ref) => (
          <li key={ref} className="evidence-item">
            {ref}
          </li>
        ))}
      </ul>
      {mode === 'simple' && evidence.length > 2 ? (
        <span className="evidence-more">… 共 {evidence.length} 条 (专业模式查看全部)</span>
      ) : null}
    </div>
  );
}
