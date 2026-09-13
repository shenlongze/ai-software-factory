/**
 * ds/Select.tsx — 下拉选择 (label + select + 可选 placeholder)。
 */

export interface SelectOption {
  value: string;
  label: string;
}

export function Select({
  label,
  options,
  value,
  onChange,
  placeholder,
  disabled = false,
  className = '',
}: {
  label?: string;
  options: readonly SelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}): JSX.Element {
  return (
    <label className={`ds-field${className ? ` ${className}` : ''}`} data-testid="ds-select-field">
      {label != null ? <span className="ds-label">{label}</span> : null}
      <select
        className="ds-select"
        data-testid="ds-select"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        {placeholder != null ? <option value="">{placeholder}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
