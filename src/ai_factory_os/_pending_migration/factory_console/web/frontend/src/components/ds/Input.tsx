/**
 * ds/Input.tsx — 文本输入框 (label + input + 可选 hint)。
 */

import type { InputHTMLAttributes } from 'react';

export function Input({
  label,
  hint,
  className = '',
  ...rest
}: { label?: string; hint?: string; className?: string } & InputHTMLAttributes<HTMLInputElement>): JSX.Element {
  return (
    <label className={`ds-field${className ? ` ${className}` : ''}`} data-testid="ds-input-field">
      {label != null ? <span className="ds-label">{label}</span> : null}
      <input className="ds-input" data-testid="ds-input" {...rest} />
      {hint != null ? <span className="ds-hint">{hint}</span> : null}
    </label>
  );
}
