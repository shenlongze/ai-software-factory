/**
 * components/af/AfBrandHeader.tsx — AI Factory 品牌 Header (AI OS 深色, S10-013 §9)。
 *
 * ◆ AI Factory + 子页/上下文标签 + 开发者控制台链接 (K-7a: 砍双模式, 指向 board)。
 */

import type { ReactNode } from 'react';

export interface AfBrandHeaderProps {
  /** 子页/上下文标签 (如 "工作台" / "项目 · Overview")。 */
  contextLabel?: string;
  /** 右侧自定义内容 (如项目详情返回链接)。 */
  trailing?: ReactNode;
}

export function AfBrandHeader({
  contextLabel,
  trailing,
}: AfBrandHeaderProps): JSX.Element {
  return (
    <header className="af-header" data-testid="af-brand-header">
      <span className="af-brand-mark" aria-hidden="true">
        ◆
      </span>
      <span className="af-brand-name">AI Factory</span>
      {contextLabel != null && contextLabel.length > 0 ? (
        <span className="af-subpage-label" data-testid="af-context-label">
          {contextLabel}
        </span>
      ) : null}
      <span className="af-header-spacer" />
      <a
        className="af-console-link"
        href="http://127.0.0.1:8011/api/board"
        title="打开开发者控制台 (board: 战役/员工/质量/成本/审计监控)"
      >
        🛠 开发者控制台
      </a>
      {trailing}
    </header>
  );
}
