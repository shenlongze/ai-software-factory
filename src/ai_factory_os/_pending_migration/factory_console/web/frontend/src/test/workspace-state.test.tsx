/**
 * src/test/workspace-state.test.tsx — Workspace/Project 选中状态 (S10-014 Task 001)。
 *
 * state/workspace.tsx 为 Domain Store 骨架 (§2.4): 当前项目上下文
 * { currentProjectId, currentProject, setProject } — Task 005 Project Shell 接入。
 * Provider 空壳: 默认 null, setProject 更新/清空。
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { WorkspaceProject } from '../models/domain';
import { WorkspaceProvider, useWorkspace } from '../state/workspace';

const SAMPLE_PROJECT: WorkspaceProject = {
  id: 'score-pocket',
  name: 'ScorePocket',
  lifecycleStage: 'development',
  lifecycleLabel: '开发中',
  progress: 62,
  pendingApprovals: 1,
  riskCount: 2,
};

function Probe(): JSX.Element {
  const { currentProjectId, currentProject, setProject } = useWorkspace();
  return (
    <div>
      <span data-testid="project-id">{currentProjectId ?? '(none)'}</span>
      <span data-testid="project-name">{currentProject?.name ?? '(none)'}</span>
      <span data-testid="project-stage">{currentProject?.lifecycleStage ?? '(none)'}</span>
      <button type="button" onClick={() => setProject(SAMPLE_PROJECT)}>
        选择项目
      </button>
      <button type="button" onClick={() => setProject(null)}>
        清空
      </button>
    </div>
  );
}

function renderProbe(): void {
  render(
    <WorkspaceProvider>
      <Probe />
    </WorkspaceProvider>,
  );
}

describe('WorkspaceContext (state/workspace)', () => {
  it('默认 currentProjectId / currentProject 均为 null', () => {
    renderProbe();
    expect(screen.getByTestId('project-id')).toHaveTextContent('(none)');
    expect(screen.getByTestId('project-name')).toHaveTextContent('(none)');
    expect(screen.getByTestId('project-stage')).toHaveTextContent('(none)');
  });

  it('setProject 更新 currentProjectId + currentProject', async () => {
    const user = userEvent.setup();
    renderProbe();
    await user.click(screen.getByRole('button', { name: '选择项目' }));
    expect(screen.getByTestId('project-id')).toHaveTextContent('score-pocket');
    expect(screen.getByTestId('project-name')).toHaveTextContent('ScorePocket');
    expect(screen.getByTestId('project-stage')).toHaveTextContent('development');
  });

  it('setProject(null) 清空选中状态', async () => {
    const user = userEvent.setup();
    renderProbe();
    await user.click(screen.getByRole('button', { name: '选择项目' }));
    await user.click(screen.getByRole('button', { name: '清空' }));
    expect(screen.getByTestId('project-id')).toHaveTextContent('(none)');
    expect(screen.getByTestId('project-name')).toHaveTextContent('(none)');
  });

  it('useWorkspace 在 Provider 外抛错', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow('useWorkspace 必须在 <WorkspaceProvider> 内使用');
    spy.mockRestore();
  });
});
