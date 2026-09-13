/**
 * ds/ArtifactCard.tsx — 产物卡片 (图标/类型/名称/CreatedBy/Input/Output/Status)。
 * 6 类产物链 (product/ux_ui/architecture/code/test/release + idea/prd/design/bug_report)。
 */

import type { ReactNode } from 'react';
import { agentMeta } from '../../design/tokens';
import { StatusBadge } from './StatusBadge';

const ARTIFACT_ICONS: Record<string, string> = {
  idea: '💡',
  product: '📄',
  prd: '📄',
  ux_ui: '🎨',
  design: '🎨',
  architecture: '🏗️',
  code: '💻',
  test: '🧪',
  bug_report: '🐞',
  release: '📦',
};

const ARTIFACT_LABELS_CN: Record<string, string> = {
  idea: '想法',
  product: '产品',
  prd: 'PRD 文档',
  ux_ui: 'UX/UI 设计',
  design: '设计',
  architecture: '架构',
  code: '代码',
  test: '测试',
  bug_report: '缺陷报告',
  release: '发布包',
};

export function ArtifactCard({
  type,
  name,
  createdBy,
  input,
  output,
  status,
  extra,
}: {
  type: string;
  name: string;
  createdBy?: string | null;
  input?: string;
  output?: string;
  status?: string;
  extra?: ReactNode;
}): JSX.Element {
  const typeKey = type.toLowerCase();
  return (
    <div className="ds-artifact-card" data-testid="ds-artifact-card" data-type={typeKey}>
      <span className="ds-artifact-icon" aria-hidden="true">
        {ARTIFACT_ICONS[typeKey] ?? '📄'}
      </span>
      <div className="ds-artifact-main">
        <div className="ds-artifact-head">
          <span className="ds-artifact-type">{ARTIFACT_LABELS_CN[typeKey] ?? type}</span>
          <span className="ds-artifact-name">{name}</span>
          {status != null ? <StatusBadge status={status} /> : null}
        </div>
        <div className="ds-artifact-meta">
          {createdBy != null ? <span className="ds-artifact-by">创建: {agentMeta(createdBy).label}</span> : null}
          {input != null && input !== '' ? <span className="ds-artifact-field">输入: {input}</span> : null}
          {output != null && output !== '' ? <span className="ds-artifact-field">输出: {output}</span> : null}
        </div>
        {extra != null ? <div className="ds-artifact-extra">{extra}</div> : null}
      </div>
    </div>
  );
}
