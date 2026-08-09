/**
 * ds/Button.tsx — 按钮 (primary/secondary/danger/ghost + loading)。
 * 消费 design.css --ds-* 令牌; 与 S9 全局 button 样式隔离 (ds- 前缀)。
 */

import type { ButtonHTMLAttributes, ReactNode } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md';

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  children,
  className = '',
  ...rest
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: ReactNode;
  className?: string;
} & ButtonHTMLAttributes<HTMLButtonElement>): JSX.Element {
  const classes = ['ds-btn', `ds-btn-${variant}`, `ds-btn-${size}`, loading ? 'is-loading' : '', className]
    .filter(Boolean)
    .join(' ');
  return (
    <button
      type="button"
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      data-variant={variant}
      {...rest}
    >
      {loading ? <span className="ds-btn-spinner" aria-hidden="true" /> : null}
      <span>{children}</span>
    </button>
  );
}
