/**
 * components/af/AfHeader.tsx — AI OS Workspace Header (S10-014 Task 004)。
 *
 * 组合 AfBrandHeader (◆ AI Factory + 子页标签 + [进入 Human Console], §4.3 Header)
 * + LLM 状态点 (中性灰占位 — Task 005+ 接入真实探测, 不冒充连接态)
 * + 侧栏折叠按钮 (切换 Sidebar 折叠态)。
 */

import { AfBrandHeader } from './AfBrandHeader';

export interface AfHeaderProps {
  /** 当前子页人话标签 (如 "工作台" / "项目")。 */
  pageLabel: string;
  /** 侧栏折叠态 (按钮图标/aria-label 依据)。 */
  collapsed: boolean;
  /** 点击折叠按钮 → 切换侧栏折叠态。 */
  onToggleSidebar: () => void;
}

export function AfHeader({ pageLabel, collapsed, onToggleSidebar }: AfHeaderProps): JSX.Element {
  return (
    <div data-testid="af-header">
      <AfBrandHeader
        contextLabel={pageLabel}
        trailing={
          <>
            <span
              className="af-llm-status"
              data-testid="af-llm-status"
              title="LLM 状态 — Task 005+ 接入真实探测"
            >
              <span className="af-llm-dot" aria-hidden="true" />
              LLM
            </span>
            <button
              type="button"
              className="af-collapse-btn"
              aria-label={collapsed ? '展开侧栏' : '折叠侧栏'}
              onClick={onToggleSidebar}
            >
              {collapsed ? '»' : '«'}
            </button>
          </>
        }
      />
    </div>
  );
}
