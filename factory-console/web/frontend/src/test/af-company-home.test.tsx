/**
 * src/test/af-company-home.test.tsx — 我的公司首页 (AfCompanyHome, K-7b)。
 *
 * 验证 (Founder 2026-08-26 设计): 信息量小 · 真实数据 · 关注项目 (收藏+近期) · 待办聚合+过滤。
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { AfCompanyHome } from '../pages/workspace/AfCompanyHome';
import { sampleProject, stubFetch } from './fixtures';

afterEach(() => {
  window.location.hash = '';
});

function recentDays(n: number): string {
  return new Date(Date.now() - n * 24 * 3600 * 1000).toISOString();
}

function stubData(projects: unknown[], approvals: unknown[]) {
  stubFetch({
    '/api/projects': projects,
    '/api/approvals?pending_only=true': approvals,
  });
}

describe('AfCompanyHome (我的公司首页)', () => {
  it('关注项目: 仅展示 收藏+近期更新 (无近期/未收藏不占位)', async () => {
    stubData(
      [
        sampleProject({ id: 'p1', name: '近期收藏', starred: true, last_activity: recentDays(1), status: 'development' }),
        sampleProject({ id: 'p2', name: '旧收藏', starred: true, last_activity: recentDays(30) }),
        sampleProject({ id: 'p3', name: '未收藏', starred: false, last_activity: recentDays(1) }),
      ],
      [],
    );
    render(<AfCompanyHome />);
    expect(await screen.findByTestId('af-company-home')).toBeInTheDocument();
    expect(screen.getByTestId('af-focused-p1')).toBeInTheDocument();
    expect(screen.queryByTestId('af-focused-p2')).not.toBeInTheDocument();
    expect(screen.queryByTestId('af-focused-p3')).not.toBeInTheDocument();
    expect(screen.getByText('近期收藏')).toBeInTheDocument();
  });

  it('无收藏/无近期 → 诚实空态提示 (不伪造数据)', async () => {
    stubData([sampleProject({ id: 'p1', name: '普通项目', starred: false, last_activity: null })], []);
    render(<AfCompanyHome />);
    expect(await screen.findByTestId('af-company-home')).toBeInTheDocument();
    expect(screen.queryByTestId(/af-focused-/)).not.toBeInTheDocument();
    expect(screen.getByText(/暂无近期有更新的收藏项目/)).toBeInTheDocument();
    expect(screen.getByText(/无待处理/)).toBeInTheDocument();
  });

  it('我的待办: 展示真实待审批 (公司级聚合)', async () => {
    stubData(
      [sampleProject({ id: 'p1', name: '旅行记账', starred: false })],
      [{ id: 'APR-1', artifact_type: 'prd', gate: 'prd', status: 'pending', requested_at: recentDays(0) }],
    );
    render(<AfCompanyHome />);
    expect(await screen.findByTestId('af-todo-APR-1')).toBeInTheDocument();
    expect(screen.getByText(/PRD · 项目 —/)).toBeInTheDocument();
  });

  it('我的待办: 项目级过滤 (有 project_id 时)', async () => {
    const user = userEvent.setup();
    stubData(
      [
        sampleProject({ id: 'pa', name: '项目A', starred: false }),
        sampleProject({ id: 'pb', name: '项目B', starred: false }),
      ],
      [
        { id: 'A-1', artifact_type: 'prd', gate: 'prd', status: 'pending', project_id: 'pa', requested_at: recentDays(0) },
        { id: 'B-1', artifact_type: 'ui', gate: 'ui', status: 'pending', project_id: 'pb', requested_at: recentDays(0) },
      ],
    );
    render(<AfCompanyHome />);
    const todo = await screen.findByTestId('af-home-todo');
    expect(within(todo).getByTestId('af-todo-A-1')).toBeInTheDocument();
    expect(within(todo).getByTestId('af-todo-B-1')).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('待办过滤维度'), 'pb');
    expect(within(todo).queryByTestId('af-todo-A-1')).not.toBeInTheDocument();
    expect(within(todo).getByTestId('af-todo-B-1')).toBeInTheDocument();
  });

  it('数据加载失败 → 诚实空态 (不抛错, 不伪造)', async () => {
    stubFetch({});
    render(<AfCompanyHome />);
    expect(await screen.findByTestId('af-company-home')).toBeInTheDocument();
    expect(screen.getByText(/暂无近期有更新的收藏项目/)).toBeInTheDocument();
    expect(screen.getByText(/无待处理/)).toBeInTheDocument();
  });
});
