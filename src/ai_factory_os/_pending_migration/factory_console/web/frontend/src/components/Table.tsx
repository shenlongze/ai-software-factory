import type { ReactNode } from 'react';

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
}

/** 轻量表格 (列定义驱动; 空数据 → 空态提示)。 */
export function Table<T>({
  columns,
  rows,
  rowKey,
  empty = '暂无数据',
  onRowClick,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  empty?: string;
  onRowClick?: (row: T) => void;
}): JSX.Element {
  if (rows.length === 0) {
    return <div className="empty-state">{empty}</div>;
  }
  return (
    <table className="data-table">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.key}>{c.header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={rowKey(row)}
            className={onRowClick ? 'clickable' : undefined}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
          >
            {columns.map((c) => (
              <td key={c.key}>{c.render(row)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
