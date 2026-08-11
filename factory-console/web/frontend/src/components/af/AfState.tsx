/**
 * components/af/AfState.tsx — AI Factory 四态组件之三 (S10-014 Task 003)。
 *
 * AI OS 深色风格独立版 (console 的 components/State.tsx 不动):
 * - AfEmptyState: 空态 (暂无数据 + 可选引导 hint)
 * - AfLoadingState: 加载态 (label + 转圈动画)
 * - AfErrorState: 错误态 (message + 可选重试按钮)
 * 纯展示组件: 不 fetch, 数据/回调由父层传入。
 */

export interface AfEmptyStateProps {
  message?: string;
  hint?: string;
}

export interface AfLoadingStateProps {
  label?: string;
}

export interface AfErrorStateProps {
  message: string;
  onRetry?: () => void;
}

/** 空态 (无数据时的友好提示)。 */
export function AfEmptyState({ message = '暂无数据', hint }: AfEmptyStateProps): JSX.Element {
  return (
    <div className="af-empty-state" data-testid="af-empty-state">
      <div className="af-empty-message">{message}</div>
      {hint != null && hint.length > 0 ? <div className="af-empty-hint">{hint}</div> : null}
    </div>
  );
}

/** 加载态。 */
export function AfLoadingState({ label = '加载中…' }: AfLoadingStateProps): JSX.Element {
  return (
    <div className="af-loading-state" data-testid="af-loading-state" role="status">
      <span className="af-loading-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

/** 错误态 (失败安全展示 + 可选重试)。 */
export function AfErrorState({ message, onRetry }: AfErrorStateProps): JSX.Element {
  return (
    <div className="af-error-state" data-testid="af-error-state" role="alert">
      <span className="af-error-icon" aria-hidden="true">
        ⚠
      </span>
      <span className="af-error-message">{message}</span>
      {onRetry != null ? (
        <button type="button" className="af-btn af-btn-secondary" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </div>
  );
}
