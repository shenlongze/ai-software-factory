/**
 * src/test/ProjectsPage.test.tsx — 项目清单 + 行点击 → 项目工作区。
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AppStateProvider, useAppState } from '../state/AppState';
import { ProjectsPage } from '../pages/ProjectsPage';
import { sampleProject, stubFetch } from './fixtures';

describe('ProjectsPage', () => {
  it('渲染项目表格 (名称/阶段/状态/待审批/最近活动)', async () => {
    stubFetch({
      '/api/projects': [
        sampleProject(),
        sampleProject({ id: 'p2', name: 'Second', pending_approvals: 0 }),
      ],
    });
    render(
      <AppStateProvider>
        <ProjectsPage />
      </AppStateProvider>,
    );
    expect(await screen.findByText('Demo Project')).toBeInTheDocument();
    expect(screen.getByText('生命周期阶段')).toBeInTheDocument();
    expect(screen.getAllByText('build').length).toBeGreaterThan(0);
    expect(screen.getByText('Second')).toBeInTheDocument();
  });

  it('行点击 → 导航到 lifecycle 页面', async () => {
    const user = userEvent.setup();
    stubFetch({ '/api/projects': [sampleProject()] });
    render(
      <AppStateProvider>
        <ProjectsPage />
        <ProbePage />
      </AppStateProvider>,
    );
    await user.click(await screen.findByText('Demo Project'));
    expect(screen.getByTestId('probe-page')).toHaveTextContent('lifecycle');
  });

  it('空清单 → 空态 (含 CLI 指引)', async () => {
    stubFetch({ '/api/projects': [] });
    render(
      <AppStateProvider>
        <ProjectsPage />
      </AppStateProvider>,
    );
    expect(await screen.findByText(/暂无项目/)).toBeInTheDocument();
  });

  it('API 错误 → ErrorState', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response),
    );
    render(
      <AppStateProvider>
        <ProjectsPage />
      </AppStateProvider>,
    );
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/500/);
  });
});

function ProbePage(): JSX.Element {
  const { page } = useAppState();
  return <span data-testid="probe-page">{page.name}</span>;
}
