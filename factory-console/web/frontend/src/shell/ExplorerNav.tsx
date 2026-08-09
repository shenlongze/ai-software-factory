/**
 * shell/ExplorerNav.tsx — S10-001 Explorer 主导航 (8 项)。
 *
 * Home/Projects/Tasks/Agents/Skills/Templates/Artifacts/Settings,
 * 图标+文字, 点击切换 Shell 视图 (active + aria-current)。
 */

import { NAV_ITEMS } from '../mock/workspace';
import type { ExplorerViewId } from '../mock/workspace';

export function ExplorerNav({
  active,
  onSelect,
}: {
  active: ExplorerViewId;
  onSelect: (view: ExplorerViewId) => void;
}): JSX.Element {
  return (
    <nav className="ws-nav" aria-label="Factory Explorer 导航" data-testid="ws-explorer-nav">
      <div className="ws-nav-section">导航</div>
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          type="button"
          className={`ws-nav-item${active === item.id ? ' active' : ''}`}
          data-nav-id={item.id}
          aria-current={active === item.id ? 'page' : undefined}
          onClick={() => onSelect(item.id)}
        >
          <span className="ws-nav-icon" aria-hidden="true">
            {item.icon}
          </span>
          <span className="ws-nav-label">{item.label}</span>
        </button>
      ))}
    </nav>
  );
}
