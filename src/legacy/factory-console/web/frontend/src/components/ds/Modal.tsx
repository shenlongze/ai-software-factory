/**
 * ds/Modal.tsx — 模态框 (遮罩点击关闭 + Escape 关闭 + 可选 footer)。
 * 与 S9 State.tsx Modal 并存 (ds- 类名隔离)。
 */

import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { Button } from './Button';

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}): JSX.Element | null {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="ds-modal-overlay" data-testid="ds-modal-overlay" onClick={onClose}>
      <div
        className="ds-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        data-testid="ds-modal"
        onClick={(event) => event.stopPropagation()}
      >
        {title != null ? <h3 className="ds-modal-title">{title}</h3> : null}
        <div className="ds-modal-body">{children}</div>
        <div className="ds-modal-footer">
          {footer != null ? (
            footer
          ) : (
            <Button variant="secondary" size="sm" onClick={onClose}>
              关闭
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
