/**
 * components/af/AfModulePlaceholder.tsx — 子页未实现占位 (S10-014 Task 002b)。
 *
 * 格式: "{Page} module loading — 开发中" (如 "Todo Tree module loading — 开发中")。
 * 禁止空白页面: 未实现子页一律渲染明确占位。
 */

export function AfModulePlaceholder({ pageLabel }: { pageLabel: string }): JSX.Element {
  return (
    <div className="af-module-placeholder" data-testid="af-module-placeholder">
      {pageLabel} module loading — 开发中
    </div>
  );
}
