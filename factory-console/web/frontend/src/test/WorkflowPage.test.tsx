/**
 * src/test/WorkflowPage.test.tsx — 组织级工作流视图 (S9-002, 轻量)。
 *
 * - 工作流表格渲染 (名称/项目/状态/进度)
 * - 行点击 → 阶段链详情 (8 阶段链)
 * - 空清单 / API 错误
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AppStateProvider } from '../state/AppState';
import { WorkflowPage } from '../pages/WorkflowPage';
import { sampleWorkflow, sampleWorkflowDetail, stubFetch } from './fixtures';

function renderWorkflow() {
  return render(
    <AppStateProvider>
      <WorkflowPage />
    </AppStateProvider>,
  );
}

describe('WorkflowPage', () => {
  it('渲染工作流表格 (名称/项目/状态/进度)', async () => {
    stubFetch({
      '/api/workflows': [
        sampleWorkflow(),
        sampleWorkflow({ id: 'wf-2', name: '打卡 App', project_name: 'Second Project', status: 'completed', progress: 1 }),
      ],
    });
    renderWorkflow();
    expect(await screen.findByRole('heading', { name: '工作流' })).toBeInTheDocument();
    expect(screen.getByText('记账 App')).toBeInTheDocument();
    expect(screen.getByText('打卡 App')).toBeInTheDocument();
    expect(screen.getByText('Demo Project')).toBeInTheDocument();
    expect(screen.getByText('Second Project')).toBeInTheDocument();
    expect(screen.getByText('38%')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('行点击 → 加载阶段链详情', async () => {
    const user = userEvent.setup();
    stubFetch({
      '/api/workflows': [sampleWorkflow()],
      '/api/workflows?project_id=demo': [sampleWorkflow()],
      '/api/workflows/wf-1': sampleWorkflowDetail(),
    });
    renderWorkflow();
    await user.click(await screen.findByText('记账 App'));
    expect(await screen.findByText('Design')).toBeInTheDocument();
    expect(screen.getByText('designer')).toBeInTheDocument();
  });

  it('空清单 → 空态 (暂无数据)', async () => {
    stubFetch({ '/api/workflows': [] });
    renderWorkflow();
    expect(await screen.findByText('暂无数据')).toBeInTheDocument();
  });

  it('API 错误 → ErrorState', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response),
    );
    renderWorkflow();
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/500/);
  });
});
