/**
 * src/test/af-task-detail-panel.test.tsx — AfTaskDetailPanel (S10-015 Task 005b)。
 *
 * 验证 (用户 Task 005 设计约束 — TaskDetail 统一面板):
 * - 全字段: 标题 / 状态 (AfStatusBadge) / 所属 Epic→Feature→Story (为什么存在) /
 *   负责人 / Agent / 优先级 / 依赖 / 下一步 / 历史
 * - 缺失降级: 字段缺失 → '—' 或不渲染, 不崩溃
 * - 右侧面板样式 + onClose 关闭回调
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AfTaskDetailPanel } from '../components/af/AfTaskDetailPanel';
import type { TaskDetail } from '../models/domain';

/** 全字段 TaskDetail (domain; 形状对齐 toTaskDetail 真实输出)。 */
function fullTaskDetail(): TaskDetail {
  return {
    id: 'TASK-a8a01f8d',
    title: '实现注册 API',
    status: 'running',
    statusLabel: '执行中',
    owner: 'developer',
    agent: '开发工程师',
    priority: 'P1',
    description: 'POST /api/register',
    dependency: ['TASK-e10a6043', 'TASK-425bf30b'],
    startedAt: '2026-08-12T00:00:00Z',
    nextAction: '正在执行 — 等待当前工作完成',
    epicName: '开发阶段',
    featureName: '用户系统',
    storyName: '用户注册',
    history: [
      { time: '2026-08-12T00:00:00Z', actor: '开发工程师 Agent', action: '开始任务', result: '执行中' },
      { time: '2026-08-12T00:05:00Z', actor: '开发工程师 Agent', action: '完成任务', result: '通过' },
    ],
    artifacts: [],
  };
}

/** 缺失字段 TaskDetail (id/title/status 之外全缺 — 降级路径)。 */
function minimalTaskDetail(): TaskDetail {
  return {
    id: 'TASK-min',
    title: '孤立任务',
    status: 'pending',
    statusLabel: '待办',
    history: [],
    artifacts: [],
  };
}

describe('AfTaskDetailPanel (Task Detail 统一面板 — 全字段 + 缺失降级)', () => {
  it('T-4 关联会话: 渲染会话列表, 点击 → onOpenSession (双向追溯)', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(
      <AfTaskDetailPanel
        task={fullTaskDetail()}
        sessions={[
          { id: 'sess-1', title: '讨论导出', updated_at: '2026-08-26T04:10:00Z', project_id: 'P-1' },
          { id: 'sess-2', title: '继续推进', updated_at: '2026-08-26T06:21:00Z', project_id: 'P-1' },
        ]}
        onOpenSession={onOpen}
      />,
    );
    const section = screen.getByTestId('af-task-detail-sessions');
    expect(within(section).getByText('关联会话 (2)')).toBeInTheDocument();
    expect(within(section).getByText('💬 讨论导出')).toBeInTheDocument();
    expect(within(section).getByText('💬 继续推进')).toBeInTheDocument();
    await user.click(screen.getByTestId('af-task-detail-session-sess-2'));
    expect(onOpen).toHaveBeenCalledWith('sess-2');
  });

  it('T-4 无关联会话 → 不渲染会话区 (诚实降级)', () => {
    render(<AfTaskDetailPanel task={fullTaskDetail()} sessions={[]} />);
    expect(screen.queryByTestId('af-task-detail-sessions')).not.toBeInTheDocument();
  });

  it('T-9 执行溯源: exec_ref + 请求 + 结果 + 证据包; 无绑定 → 不渲染', () => {
    render(
      <AfTaskDetailPanel
        task={fullTaskDetail()}
        execTrace={{
          exec_ref: 'EXR-99',
          exec_result: 'EXS-99',
          request: { id: 'EXR-99', objective: '完善导出功能', created_at: '2026-08-26T04:00:00Z' },
          results: [{ result_id: 'EXS-99', result: 'success', timestamp: '2026-08-26T04:05:00Z' }],
          evidence: [{ id: 'EXS-99', report: 'EXS-99.report.md' }],
        }}
      />,
    );
    const section = screen.getByTestId('af-task-detail-exec');
    expect(within(section).getByTestId('af-task-detail-exec-ref')).toHaveTextContent('EXR-99');
    expect(within(section).getByText('完善导出功能')).toBeInTheDocument();
    expect(within(section).getByTestId('af-task-detail-exec-results')).toHaveTextContent('EXS-99');
    expect(within(section).getByTestId('af-task-detail-exec-evidence')).toHaveTextContent('EXS-99.report.md');
  });

  it('T-9 无执行绑定 → 不渲染执行溯源区 (诚实降级)', () => {
    render(
      <AfTaskDetailPanel
        task={fullTaskDetail()}
        execTrace={{ exec_ref: '', exec_result: '', request: null, results: [], evidence: [] }}
      />,
    );
    expect(screen.queryByTestId('af-task-detail-exec')).not.toBeInTheDocument();
  });

  it('全字段渲染: 标题/状态/Epic→Feature→Story/负责人/Agent/优先级/依赖/下一步', () => {
    render(<AfTaskDetailPanel task={fullTaskDetail()} />);
    const panel = screen.getByTestId('af-task-detail-panel');

    expect(within(panel).getByTestId('af-task-detail-title')).toHaveTextContent('实现注册 API');
    // 状态 (AfStatusBadge)
    expect(within(panel).getByTestId('af-status-badge')).toHaveTextContent('执行中');
    // 所属 (为什么存在): Epic → Feature → Story
    expect(within(panel).getByTestId('af-task-detail-belong')).toHaveTextContent(
      '开发阶段 → 用户系统 → 用户注册',
    );
    // 负责人 / Agent / 优先级
    expect(within(panel).getByTestId('af-task-detail-owner')).toHaveTextContent('developer');
    expect(within(panel).getByTestId('af-task-detail-agent')).toHaveTextContent('开发工程师');
    expect(within(panel).getByTestId('af-task-detail-priority')).toHaveTextContent('P1');
    // 依赖 (多值连接)
    expect(within(panel).getByTestId('af-task-detail-dependency')).toHaveTextContent(
      'TASK-e10a6043, TASK-425bf30b',
    );
    // 下一步
    expect(within(panel).getByTestId('af-task-detail-next')).toHaveTextContent(
      '正在执行 — 等待当前工作完成',
    );
  });

  it('历史: 复用 AfTimeline 渲染 history 条目 (time/actor/action/result)', () => {
    render(<AfTaskDetailPanel task={fullTaskDetail()} />);
    const history = screen.getByTestId('af-task-detail-history');
    const items = within(history).getAllByTestId('af-timeline-item');
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText('开发工程师 Agent')).toBeInTheDocument();
    expect(within(items[0]).getByText('开始任务')).toBeInTheDocument();
    expect(within(items[0]).getByText('执行中')).toBeInTheDocument();
  });

  it('缺失降级: 仅 id/title/status → 不崩溃, 所属不渲染, 负责人/依赖/下一步显示 —', () => {
    render(<AfTaskDetailPanel task={minimalTaskDetail()} />);
    const panel = screen.getByTestId('af-task-detail-panel');
    expect(within(panel).getByTestId('af-task-detail-title')).toHaveTextContent('孤立任务');
    // 所属行整体不渲染 (Epic/Feature/Story 全缺)
    expect(within(panel).queryByTestId('af-task-detail-belong')).not.toBeInTheDocument();
    // 缺失字段 → '—' 降级
    expect(within(panel).getByTestId('af-task-detail-owner')).toHaveTextContent('—');
    expect(within(panel).getByTestId('af-task-detail-dependency')).toHaveTextContent('—');
    expect(within(panel).getByTestId('af-task-detail-next')).toHaveTextContent('—');
    // 空历史 → AfTimeline 空态
    expect(within(panel).getByText('暂无活动')).toBeInTheDocument();
  });

  it('部分关联缺失: 有 Epic 无 Feature/Story → 只显示 Epic', () => {
    render(
      <AfTaskDetailPanel
        task={{ ...fullTaskDetail(), featureName: undefined, storyName: undefined }}
      />,
    );
    expect(screen.getByTestId('af-task-detail-belong')).toHaveTextContent('开发阶段');
    expect(screen.getByTestId('af-task-detail-belong')).not.toHaveTextContent('用户系统');
  });

  it('onClose: 点击关闭按钮 → 回调被调用', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<AfTaskDetailPanel task={fullTaskDetail()} onClose={onClose} />);
    await user.click(screen.getByTestId('af-task-detail-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('无 onClose → 不渲染关闭按钮', () => {
    render(<AfTaskDetailPanel task={fullTaskDetail()} />);
    expect(screen.queryByTestId('af-task-detail-close')).not.toBeInTheDocument();
  });
});
