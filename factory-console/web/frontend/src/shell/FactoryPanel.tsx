/**
 * shell/FactoryPanel.tsx — S10-001 右侧 Factory Panel (4 Tab 框架)。
 *
 * Runtime Tab (browser): S10-004 Runtime Workspace Panel — 选中项目后渲染
 * RuntimePanel (Instances 列表 + [+] 创建 + Browser iframe + Terminal mock
 * stream + REST 轮询); 未选中项目 → 空态 (等待选择项目)。
 * Artifact Tab (artifact): S10-005 Artifact Center — 选中项目后渲染
 * ArtifactCenter (6 类产物 List + 类型过滤 + Detail Viewer 类型化渲染 +
 * Timeline 联动); 未选中项目 → 空态 (等待选择项目)。
 * Task / Review — 仍为 Empty State 占位 (S10-002 / S10-006 接入)。
 */

import { PANEL_TABS } from '../mock/workspace';
import type { PanelTabId } from '../mock/workspace';
import { ArtifactCenter } from './ArtifactCenter';
import { RuntimePanel } from './RuntimePanel';

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
  projectId,
  focusArtifactId,
  focusNonce,
  onFocusConsumed,
}: {
  activeTab: PanelTabId;
  onSelectTab: (tab: PanelTabId) => void;
  /** S10-004: 选中项目 (Runtime Panel 需要 projectId; null → 空态)。 */
  projectId?: string | null;
  /** S10-004: Timeline 联动 — 待定位 artifact_id (透传给 RuntimePanel)。 */
  focusArtifactId?: string | null;
  focusNonce?: number | null;
  onFocusConsumed?: () => void;
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
        {activeTab === 'browser' && projectId != null ? (
          <RuntimePanel
            projectId={projectId}
            focusArtifactId={focusArtifactId}
            focusNonce={focusNonce}
            onFocusConsumed={onFocusConsumed}
          />
        ) : activeTab === 'artifact' && projectId != null ? (
          <ArtifactCenter
            projectId={projectId}
            focusArtifactId={focusArtifactId}
            focusNonce={focusNonce}
            onFocusConsumed={onFocusConsumed}
          />
        ) : (
          <PanelEmpty tabId={activeTab} />
        )}
      </div>
    </div>
  );
}
