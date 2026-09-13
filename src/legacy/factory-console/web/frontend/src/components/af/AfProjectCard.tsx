/**
 * components/af/AfProjectCard.tsx — 工作台项目卡 (S10-014 Task 002b)。
 *
 * 展示真实 ProjectSummary 投影: name / lifecycle 人话 / workflow 状态 + 当前阶段 /
 * progress 百分比 / stage_counts 芯片; 点击 → 跳转 #/project/{id}。
 */

import type { ProjectSummary } from '../../models/types';
import {
  lifecycleLabel,
  progressPercent,
  stageCountChips,
  workflowLabel,
} from './afLabels';

export interface AfProjectCardProps {
  project: ProjectSummary;
  onOpen: (id: string) => void;
}

export function AfProjectCard({ project, onOpen }: AfProjectCardProps): JSX.Element {
  const pct = progressPercent(project.progress);
  const chips = stageCountChips(project.stage_counts);

  return (
    <button
      type="button"
      className="af-project-card"
      data-testid="af-project-card"
      onClick={() => onOpen(project.id)}
    >
      <div className="af-card-title-row">
        <span className="af-card-name">{project.name}</span>
        <span className="af-card-lifecycle">{lifecycleLabel(project)}</span>
      </div>
      {project.description != null && project.description.length > 0 ? (
        <p className="af-card-desc">{project.description}</p>
      ) : null}
      <div className="af-card-workflow">
        <span className="af-badge af-badge-blue">{workflowLabel(project.workflow_status)}</span>
        {project.current_stage != null && project.current_stage.length > 0 ? (
          <span className="af-card-stage">阶段: {project.current_stage}</span>
        ) : null}
      </div>
      <div className="af-card-progress">
        <div className="af-progress-track">
          <div className="af-progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <span className="af-progress-text">{pct}%</span>
      </div>
      {chips.length > 0 ? (
        <div className="af-card-chips">
          {chips.map((chip) => (
            <span key={chip.label} className="af-chip">
              {chip.label} {chip.count}
            </span>
          ))}
        </div>
      ) : null}
    </button>
  );
}
