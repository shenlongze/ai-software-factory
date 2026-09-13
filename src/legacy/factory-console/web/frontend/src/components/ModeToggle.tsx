import { useAppState } from '../state/AppState';
import type { Mode } from '../state/AppState';

/** 普通模式 ↔ 专业模式切换 (segmented control; 普通模式默认)。 */
export function ModeToggle(): JSX.Element {
  const { mode, setMode } = useAppState();

  const option = (value: Mode, label: string) => (
    <button
      type="button"
      className={`mode-option${mode === value ? ' active' : ''}`}
      aria-pressed={mode === value}
      data-mode={value}
      onClick={() => setMode(value)}
    >
      {label}
    </button>
  );

  return (
    <div className="mode-toggle" role="group" aria-label="模式切换">
      {option('simple', '普通模式')}
      {option('expert', '专业模式')}
    </div>
  );
}
