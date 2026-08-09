/**
 * shell/ProjectTree.tsx — S10-001 Project Tree (mock)。
 *
 * Ledger App ├ Product ├ UX/UI ├ Architecture ├ Code ├ Test └ Release,
 * 每阶段状态色点 (待办/运行/待审/完成/失败) + 中文状态标签。
 * S10-005 Artifact Center 接入后, 点击阶段跳对应产物。
 */

import { statusLabel, statusTone } from '../design/tokens';
import { MOCK_PROJECTS } from '../mock/workspace';
import type { MockProject } from '../mock/workspace';

export function ProjectTree({
  project,
  onSelectProject,
}: {
  project: MockProject | null;
  onSelectProject: (projectId: string) => void;
}): JSX.Element {
  return (
    <section className="ws-tree" aria-label="项目阶段树" data-testid="ws-project-tree">
      <div className="ws-tree-header">项目</div>
      {MOCK_PROJECTS.map((mockProject) => {
        const selected = project?.id === mockProject.id;
        return (
          <button
            key={mockProject.id}
            type="button"
            className={`ws-tree-project${selected ? ' selected' : ''}`}
            data-project-id={mockProject.id}
            aria-pressed={selected}
            onClick={() => onSelectProject(mockProject.id)}
          >
            <span className="ws-tree-caret" aria-hidden="true">
              {selected ? '▾' : '▸'}
            </span>
            {mockProject.name}
          </button>
        );
      })}
      {project != null ? (
        <ul className="ws-tree-stages" data-testid="ws-project-tree-stages">
          {project.stages.map((stage) => {
            const tone = statusTone(stage.status);
            return (
              <li key={stage.id} className="ws-tree-stage" data-stage-id={stage.id}>
                <span
                  className={`ws-tree-dot ws-dot-${tone}`}
                  data-status={stage.status}
                  aria-hidden="true"
                />
                <span className="ws-tree-stage-name">{stage.name}</span>
                <span className="ws-tree-stage-status">{statusLabel(stage.status)}</span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
