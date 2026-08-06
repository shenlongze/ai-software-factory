import type { ReactNode } from 'react';

/** 通用卡片容器 (标题 + 可选副标题 + 内容)。 */
export function Card({
  title,
  subtitle,
  children,
  className = '',
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <section className={`card ${className}`} data-testid={`card-${title}`}>
      <header className="card-header">
        <h3 className="card-title">{title}</h3>
        {subtitle ? <span className="card-subtitle">{subtitle}</span> : null}
      </header>
      <div className="card-body">{children}</div>
    </section>
  );
}
