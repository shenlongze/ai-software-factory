/**
 * shell/WorkspaceHeader.tsx — S10-001 Header 栏。
 *
 * 品牌 (AI Factory) / 项目选择 (mock) / LLM 状态 / 主题切换 (ThemeToggle,
 * S10-000) / 用户菜单 (设置 + 返回控制台)。全部样式消费 --ds-* 令牌。
 */

import { useState } from 'react';
import { Select } from '../components/ds';
import { ThemeToggle } from '../design/theme';
import { CURRENT_USER, LLM_STATUS, MOCK_PROJECTS } from '../mock/workspace';
import { useAppState } from '../state/AppState';

export function WorkspaceHeader({
  projectId,
  onSelectProject,
  onOpenSettings,
}: {
  projectId: string | null;
  onSelectProject: (projectId: string | null) => void;
  onOpenSettings: () => void;
}): JSX.Element {
  const { navigate } = useAppState();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="ws-header" data-testid="ws-header">
      <div className="ws-brand">
        <span className="ws-brand-mark" aria-hidden="true">
          ◆
        </span>
        <div>
          <div className="ws-brand-name">AI Factory</div>
          <div className="ws-brand-sub">Workspace</div>
        </div>
      </div>

      <div className="ws-header-center">
        <Select
          label="项目"
          placeholder="选择项目…"
          value={projectId ?? ''}
          onChange={(value) => onSelectProject(value === '' ? null : value)}
          options={MOCK_PROJECTS.map((project) => ({ value: project.id, label: project.name }))}
        />
      </div>

      <div className="ws-header-right">
        <span className="ds-badge ds-badge-success ws-llm-status" data-testid="ws-llm-status">
          <span className="ds-badge-dot" aria-hidden="true" />
          LLM 已连接 · {LLM_STATUS.provider} {LLM_STATUS.model}
        </span>
        <ThemeToggle />
        <div className="ws-user">
          <button
            type="button"
            className="ws-user-btn"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            data-testid="ws-user-btn"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="ws-user-avatar" aria-hidden="true">
              {CURRENT_USER.initials}
            </span>
            {CURRENT_USER.name}
          </button>
          {menuOpen ? (
            <div className="ws-user-menu" role="menu" data-testid="ws-user-menu">
              <button
                type="button"
                role="menuitem"
                className="ws-user-menu-item"
                data-testid="ws-user-menu-settings"
                onClick={() => {
                  setMenuOpen(false);
                  onOpenSettings();
                }}
              >
                ⚙️ 设置
              </button>
              <button
                type="button"
                role="menuitem"
                className="ws-user-menu-item"
                data-testid="ws-user-menu-console"
                onClick={() => {
                  setMenuOpen(false);
                  navigate({ name: 'dashboard' });
                }}
              >
                ↩ 返回控制台
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
