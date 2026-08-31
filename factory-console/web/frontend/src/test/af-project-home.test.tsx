/**
 * src/test/af-project-home.test.tsx — 项目管理信息卡 (S35)。
 *
 * 验证 AfProjectHome 从统一后端渲染真实数据 (GET /api/projects/{id} + /workspace):
 * - 项目 ID / 状态 / 阶段 / 类型
 * - Workspace 路径 / Git 状态
 * - Requirement / Plan 计数
 * - 后端不可达 → 空态不崩 (失败安全)
 */

import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { AfProjectHome } from '../pages/project/AfProjectHome';
import { stubFetch } from './fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

const BASE = '/api/projects/P-b0adfaa6';

function detailRoutes() {
  return {
    [BASE]: {
      project: {
        id: 'P-b0adfaa6',
        name: '飞机大战',
        status: 'idea',
        lifecycle_stage: 'idea',
        project_type: 'web',
        framework: '',
        created_at: '2026-08-31 16:27',
      },
      counts: { requirements: 6, plans: 4, tasks: 20, runs: 0 },
      repository: { enabled: false, status: 'not_initialized', path: '' },
      requirements: [
        { id: 'req_abc', title: '开发一个纯前端 Web 的飞机大战游戏', status: 'VALIDATED' },
      ],
      plans: [{ plan_id: 'plan_123', status: 'planning' }],
    },
    [`${BASE}/workspace`]: {
      name: '飞机大战',
      lifecycle_status: 'idea',
      root_path: '/Users/agentdev/.factory/workspace/projects/P-b0adfaa6',
      stages: [],
      done_stages: [],
      progress: 0,
      tasks: [],
      task_source: 'execution_state',
    },
    [`${BASE}/monitor`]: { project: { runtimes: 0, failed: 0, quality: null } },
    [`${BASE}/runs`]: { runs: [] },
  };
}

describe('AfProjectHome 项目管理卡 (S35)', () => {
  it('渲染真实项目信息 (ID/状态/阶段/Git/Requirement/Plan)', async () => {
    stubFetch(detailRoutes());
    render(<AfProjectHome projectId="P-b0adfaa6" projectName="飞机大战" />);
    // 详情卡出现
    expect(await screen.findByTestId('af-home-detail')).toBeInTheDocument();
    expect(screen.getByText('📁 项目管理')).toBeInTheDocument();
    // Identity
    expect(screen.getByText('P-b0adfaa6')).toBeInTheDocument();
    expect(screen.getByText('idea / idea')).toBeInTheDocument();
    // Workspace 路径
    expect(
      screen.getByText('/Users/agentdev/.factory/workspace/projects/P-b0adfaa6'),
    ).toBeInTheDocument();
    // Git 未初始化
    expect(screen.getByText('未初始化')).toBeInTheDocument();
    // Requirement / Plan 计数
    expect(screen.getByText('6 条')).toBeInTheDocument();
    expect(screen.getByText('4 份')).toBeInTheDocument();
  });

  it('后端不可达 → 空态不崩', async () => {
    stubFetch({});
    render(<AfProjectHome projectId="P-x" projectName="X" />);
    expect(await screen.findByTestId('af-home-detail')).toBeInTheDocument();
    // 空态显示 ID (兜底 projectId) 而非崩溃
    expect(screen.getByText('P-x')).toBeInTheDocument();
    expect(screen.getByText('未初始化')).toBeInTheDocument();
  });
});
