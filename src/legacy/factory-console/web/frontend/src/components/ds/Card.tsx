/**
 * ds/Card.tsx — 卡片容器 (surface/边框/圆角 + 可选标题/副标题/操作区)。
 * 与 S9 src/components/Card.tsx 并存 (ds- 类名隔离, 互不影响)。
 */

import type { ReactNode } from 'react';

export function Card({
  title,
  subtitle,
  actions,
  children,
  className = '',
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}): JSX.Element {
  const hasHeader = title != null || subtitle != null || actions != null;
  return (
    <section className={`ds-card${className ? ` ${className}` : ''}`} data-testid="ds-card">
      {hasHeader ? (
        <header className="ds-card-header">
          <div className="ds-card-heading">
            {title != null ? <h3 className="ds-card-title">{title}</h3> : null}
            {subtitle != null ? <span className="ds-card-subtitle">{subtitle}</span> : null}
          </div>
          {actions != null ? <div className="ds-card-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="ds-card-body">{children}</div>
    </section>
  );
}
