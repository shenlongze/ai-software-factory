/**
 * src/test/ArtifactsPage.test.tsx — Artifact 查看器 (S9-002, 轻量)。
 *
 * - 产物表格渲染 (ID/类型/状态/阶段/产出角色/内容)
 * - 类型过滤下拉 → 带 type 查询参数重拉
 * - 空清单 / API 错误
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AppStateProvider } from '../state/AppState';
import { ArtifactsPage } from '../pages/ArtifactsPage';
import { ReviewPage } from '../pages/ReviewPage';
import { sampleArtifact, sampleArtifactDetail, stubFetch } from './fixtures';

function renderArtifacts() {
  return render(
    <AppStateProvider>
      <ArtifactsPage />
    </AppStateProvider>,
  );
}

describe('ArtifactsPage', () => {
  it('渲染产物表格 (类型/状态/产出角色/内容)', async () => {
    stubFetch({
      '/api/artifacts': [
        sampleArtifact(),
        sampleArtifact({
          id: 'art-2',
          type: 'code',
          stage_id: 'development',
          producer_role: 'developer',
          status: 'pending',
          location: 'org/artifacts/app.py',
        }),
      ],
    });
    renderArtifacts();
    expect(await screen.findByRole('heading', { name: '产物' })).toBeInTheDocument();
    expect(screen.getByText('designer')).toBeInTheDocument();
    expect(screen.getByText('developer')).toBeInTheDocument();
    expect(screen.getByText(/org\/artifacts\/design-1\.md \(v3\)/)).toBeInTheDocument();
    expect(screen.getByText(/org\/artifacts\/app\.py \(v3\)/)).toBeInTheDocument();
  });

  it('类型过滤下拉 → 重拉带 type 参数', async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch({
      '/api/artifacts': [sampleArtifact()],
      '/api/artifacts?type=code': [sampleArtifact({ id: 'art-2', type: 'code' })],
    });
    renderArtifacts();
    await screen.findByRole('heading', { name: '产物' });
    await user.selectOptions(screen.getByRole('combobox'), 'code');
    await screen.findByText('art-2');
    const last = fetchMock.mock.calls.at(-1);
    expect(String(last![0])).toBe('/api/artifacts?type=code');
  });

  it('空清单 → 空态 (暂无数据)', async () => {
    stubFetch({ '/api/artifacts': [] });
    renderArtifacts();
    expect(await screen.findByText('暂无数据')).toBeInTheDocument();
  });

  it('API 错误 → ErrorState', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) }) as Response),
    );
    renderArtifacts();
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/503/);
  });

  it('点击评审按钮 → 跳转 Review 页 (GET /api/artifacts/{id} 详情)', async () => {
    const user = userEvent.setup();
    stubFetch({
      '/api/artifacts': [sampleArtifact({ id: 'art-1', type: 'product' })],
      '/api/artifacts/art-1': sampleArtifactDetail(),
    });
    render(
      <AppStateProvider>
        <ArtifactsPage />
        <ReviewPage />
      </AppStateProvider>,
    );
    await screen.findByRole('heading', { name: '产物' });
    await user.click(screen.getByRole('button', { name: '评审' }));
    expect(await screen.findByRole('heading', { name: '评审 · Product' })).toBeInTheDocument();
    expect(screen.getByText('市场分析')).toBeInTheDocument();
  });
});
