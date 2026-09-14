/**
 * ds/Layout.tsx — 三栏布局框架 (Explorer 220px / Workspace flex / Panel 360px,
 * 两侧均可折叠)。S10-001 Workspace Shell 消费。
 */

import { useState } from 'react';
import type { ReactNode } from 'react';

export function Layout({
  explorer,
  workspace,
  panel,
  explorerWidth = 220,
  panelWidth = 360,
  defaultExplorerCollapsed = false,
  defaultPanelCollapsed = false,
}: {
  explorer: ReactNode;
  workspace: ReactNode;
  panel?: ReactNode;
  explorerWidth?: number;
  panelWidth?: number;
  defaultExplorerCollapsed?: boolean;
  defaultPanelCollapsed?: boolean;
}): JSX.Element {
  const [explorerCollapsed, setExplorerCollapsed] = useState(defaultExplorerCollapsed);
  const [panelCollapsed, setPanelCollapsed] = useState(defaultPanelCollapsed);

  return (
    <div className="ds-layout" data-testid="ds-layout">
      <aside
        className={`ds-layout-pane ds-layout-explorer${explorerCollapsed ? ' is-collapsed' : ''}`}
        data-testid="ds-explorer"
        style={explorerCollapsed ? undefined : { width: explorerWidth }}
      >
        <button
          type="button"
          className="ds-layout-toggle"
          aria-label={explorerCollapsed ? '展开左侧栏' : '折叠左侧栏'}
          data-testid="ds-explorer-toggle"
          onClick={() => setExplorerCollapsed((collapsed) => !collapsed)}
        >
          {explorerCollapsed ? '»' : '«'}
        </button>
        <div className="ds-layout-pane-body">{explorerCollapsed ? null : explorer}</div>
      </aside>

      <main className="ds-layout-workspace" data-testid="ds-workspace">
        {workspace}
      </main>

      {panel != null ? (
        <aside
          className={`ds-layout-pane ds-layout-panel${panelCollapsed ? ' is-collapsed' : ''}`}
          data-testid="ds-panel"
          style={panelCollapsed ? undefined : { width: panelWidth }}
        >
          <button
            type="button"
            className="ds-layout-toggle"
            aria-label={panelCollapsed ? '展开右侧栏' : '折叠右侧栏'}
            data-testid="ds-panel-toggle"
            onClick={() => setPanelCollapsed((collapsed) => !collapsed)}
          >
            {panelCollapsed ? '«' : '»'}
          </button>
          <div className="ds-layout-pane-body">{panelCollapsed ? null : panel}</div>
        </aside>
      ) : null}
    </div>
  );
}
