/**
 * src/test/af-projects-view.test.tsx — 项目管理视图 (S35-UI)。
 *
 * 验证 AfProjectsView 从统一后端渲染真实项目列表 (GET /api/projects):
 * - 项目卡片 (名称/ID/阶段)
 * - 空态不崩 / 后端不可达不崩
 * - 点击卡片 → #/project/:id (项目详情)
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { AfProjectsView } from '../components/af/AfProjectsView';
import { stubFetch } from './fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AfProjectsView 项目管理视图 (S35-UI)', () => {
  it('渲染真实项目列表 (名称/ID/阶段)', async () => {
    stubFetch({
      '/api/projects': [
        { id: 'P-b0adfaa6', name: '飞机大战', lifecycle_stage: 'idea', status: 'idea' },
        { id: 'P-5be3a04a', name: '番茄钟', lifecycle_stage: 'development', status: 'active' },
      ],
    });
    render(<AfProjectsView />);
    expect(await screen.findByText('飞机大战')).toBeInTheDocument();
    expect(screen.getByText('番茄钟')).toBeInTheDocument();
    expect(screen.getByText('P-b0adfaa6')).toBeInTheDocument();
    expect(screen.getByText('idea')).toBeInTheDocument();
    expect(screen.getByText('development')).toBeInTheDocument();
  });

  it('后端不可达 → 空态不崩', async () => {
    stubFetch({});
    render(<AfProjectsView />);
    expect(await screen.findByTestId('af-projects-view')).toBeInTheDocument();
    expect(screen.getByText(/后端不可达|暂无项目/)).toBeInTheDocument();
  });

  it('点击项目卡片 → 回调选中 (不跳独立页)', async () => {
    stubFetch({
      '/api/projects': [{ id: 'P-b0adfaa6', name: '飞机大战', lifecycle_stage: 'idea', status: 'idea' }],
    });
    let selected = '';
    render(<AfProjectsView onSelectProject={(id) => { selected = id; }} />);
    const card = await screen.findByRole('button', { name: /飞机大战/ });
    fireEvent.click(card);
    expect(selected).toBe('P-b0adfaa6');
  });
});
