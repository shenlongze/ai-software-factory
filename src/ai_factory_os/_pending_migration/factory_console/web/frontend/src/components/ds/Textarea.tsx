/**
 * ds/Textarea.tsx — 多行文本域 (label + textarea + 可选 hint)。
 */

import type { TextareaHTMLAttributes } from 'react';

export function Textarea({
  label,
  hint,
  className = '',
  ...rest
}: { label?: string; hint?: string; className?: string } & TextareaHTMLAttributes<HTMLTextAreaElement>): JSX.Element {
  return (
    <label className={`ds-field${className ? ` ${className}` : ''}`} data-testid="ds-textarea-field">
      {label != null ? <span className="ds-label">{label}</span> : null}
      <textarea className="ds-textarea" data-testid="ds-textarea" {...rest} />
      {hint != null ? <span className="ds-hint">{hint}</span> : null}
    </label>
  );
}
