import type { ReactNode } from 'react';

/** 空态 (无数据时的友好提示)。 */
export function EmptyState({ message }: { message: string }): JSX.Element {
  return (
    <div className="empty-state" data-testid="empty-state">
      {message}
    </div>
  );
}

/** 加载态。 */
export function LoadingState({ label = '加载中…' }: { label?: string }): JSX.Element {
  return (
    <div className="loading-state" data-testid="loading-state">
      {label}
    </div>
  );
}

/** 错误态 (API 失败, 失败安全展示)。 */
export function ErrorState({ message }: { message: string }): JSX.Element {
  return (
    <div className="error-state" data-testid="error-state">
      {message}
    </div>
  );
}

/** 只读提示弹层 (Permission Boundary: 写动作的唯一呈现 — 说明决策通道, 不写)。 */
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}): JSX.Element {
  return (
    <div className="modal-overlay" data-testid="modal" onClick={onClose}>
      <div className="modal" role="dialog" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <h3 className="modal-title">{title}</h3>
        <div className="modal-body">{children}</div>
        <button type="button" className="modal-close" onClick={onClose}>
          关闭
        </button>
      </div>
    </div>
  );
}
