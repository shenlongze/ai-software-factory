/**
 * src/test/ProvidersPage.test.tsx — Provider 目录 (专业模式页面)。
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AppStateProvider } from '../state/AppState';
import { ProvidersPage } from '../pages/ProvidersPage';
import { sampleProvider, stubFetch } from './fixtures';

describe('ProvidersPage', () => {
  it('渲染 Provider 表格 (能力/成本/性能/经验/调用数)', async () => {
    stubFetch({ '/api/providers': [sampleProvider()] });
    render(
      <AppStateProvider>
        <ProvidersPage />
      </AppStateProvider>,
    );
    expect(await screen.findByText('Hermes')).toBeInTheDocument();
    expect(screen.getByText('code, reasoning')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText('90%')).toBeInTheDocument();
    expect(screen.getByText('80%')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('null 成本/性能/经验 → 占位 — (冷启动不臆造)', async () => {
    stubFetch({
      '/api/providers': [sampleProvider({ cost: null, performance: null, experience: null })],
    });
    render(
      <AppStateProvider>
        <ProvidersPage />
      </AppStateProvider>,
    );
    expect(await screen.findByText('Hermes')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3);
  });

  it('空清单 → 空态', async () => {
    stubFetch({ '/api/providers': [] });
    render(
      <AppStateProvider>
        <ProvidersPage />
      </AppStateProvider>,
    );
    expect(await screen.findByText('暂无 Provider')).toBeInTheDocument();
  });

  it('API 错误 → ErrorState', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response),
    );
    render(
      <AppStateProvider>
        <ProvidersPage />
      </AppStateProvider>,
    );
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/500/);
  });
});
