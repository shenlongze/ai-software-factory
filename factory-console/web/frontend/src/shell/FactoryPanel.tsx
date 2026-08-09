/**
 * shell/FactoryPanel.tsx — S10-001 右侧 Factory Panel (4 Tab 框架)。
 *
 * Browser / Task / Artifact / Review — 每个 Tab 均为 Empty State 占位,
 * 具体内容由 S10-004 / S10-002 / S10-005 / S10-006 接入。
 */

import { PANEL_TABS } from '../mock/workspace';
import type { PanelTabId } from '../mock/workspace';

function PanelEmpty({ tabId }: { tabId: PanelTabId }): JSX.Element {
  const tab = PANEL_TABS.find((meta) => meta.id === tabId) ?? PANEL_TABS[0];
  return (
    <div className="ws-empty" data-testid={`ws-panel-${tabId}`}>
      <div className="ws-empty-icon" aria-hidden="true">
        {tab.icon}
      </div>
      <h2 className="ws-empty-title" style={{ fontSize: 'var(--ds-font-lg)' }}>
        {tab.emptyTitle}
      </h2>
      <p className="ws-empty-desc">{tab.emptyDescription}</p>
      <p className="ws-empty-hint">{tab.futureTask}</p>
    </div>
  );
}

export function FactoryPanel({
  activeTab,
  onSelectTab,
}: {
  activeTab: PanelTabId;
  onSelectTab: (tab: PanelTabId) => void;
}): JSX.Element {
  return (
    <div className="ws-panel" data-testid="ws-factory-panel">
      <div className="ws-panel-tabs" role="tablist" aria-label="Factory Panel">
        {PANEL_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`ws-panel-tab-${tab.id}`}
            className={`ws-panel-tab${activeTab === tab.id ? ' active' : ''}`}
            data-tab-id={tab.id}
            aria-selected={activeTab === tab.id}
            aria-controls={`ws-panel-${tab.id}`}
            onClick={() => onSelectTab(tab.id)}
          >
            <span aria-hidden="true">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>
      <div
        className="ws-panel-body"
        role="tabpanel"
        id={`ws-panel-${activeTab}`}
        aria-labelledby={`ws-panel-tab-${activeTab}`}
        data-testid="ws-panel-body"
      >
        <PanelEmpty tabId={activeTab} />
      </div>
    </div>
  );
}
