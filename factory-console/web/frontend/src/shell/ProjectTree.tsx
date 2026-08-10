/**
 * shell/ProjectTree.tsx — S10-001 Project Tree。
 *
 * S10-006.5 P0 修复: 真实项目列表 (GET /api/projects) 替换硬编码 mock;
 * 每项目可选中 (stages 阶段链在项目有 workflow 后展示 — 当前显示项目名 + 状态)。
 */

import { StatusBadge } from '../components/ds';

export interface TreeProject {
  id: string;
  name: string;
  status?: string | null;
}

export function ProjectTree({
  projects,
  selectedId,
  onSelectProject,
}: {
  projects: TreeProject[];
  selectedId: string | null;
  onSelectProject: (projectId: string) => void;
}): JSX.Element {
  return (
    <section className="ws-tree" aria-label="项目阶段树" data-testid="ws-project-tree">
      <div className="ws-tree-header">项目</div>
      {projects.length === 0 ? (
        <p className="ws-tree-empty" data-testid="ws-tree-empty">
          还没有项目 — 输入一句话开始
        </p>
      ) : (
        projects.map((project) => {
          const selected = selectedId === project.id;
          return (
            <button
              key={project.id}
              type="button"
              className={`ws-tree-project${selected ? ' selected' : ''}`}
              data-project-id={project.id}
              data-testid={`ws-tree-project-${project.id}`}
              aria-pressed={selected}
              onClick={() => onSelectProject(project.id)}
            >
              <span className="ws-tree-caret" aria-hidden="true">
                {selected ? '▾' : '▸'}
              </span>
              <span className="ws-tree-project-name">{project.name}</span>
              {project.status != null ? (
                <StatusBadge status={project.status} label={project.status} />
              ) : null}
            </button>
          );
        })
      )}
    </section>
  );
}
