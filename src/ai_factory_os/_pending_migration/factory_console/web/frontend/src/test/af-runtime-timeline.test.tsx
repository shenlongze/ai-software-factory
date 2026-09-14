/**
 * src/test/af-runtime-timeline.test.tsx — AfRuntimeTimeline (S10-015 Task 005b)。
 *
 * 验证 (用户 Task 005 设计约束 — Runtime Timeline 展示 8 项, 非 Log Viewer):
 * - 当前执行卡: 当前 Agent (failed/running 阶段 role 人话) + Workflow Stage + 状态
 *   (AfStatusBadge) + 开始时间 + 持续时间 (started_at→completed_at / →now) + 失败原因
 *   (failed_reason 红色, "为什么阻塞/失败") + 下一步 (从 pending 阶段推导) + 最近事件
 * - 事件流: 复用 AfTimeline, 倒序 (最新在上)
 * - 空态: 无 workflow + 无 events → AfEmptyState
 * - 数据全部来自真实 workflow/timeline (toWorkflowPipeline + toRuntimeActivity),
 *   禁止前端自行生成状态
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { toRuntimeActivity, toWorkflowPipeline } from '../api/domain';
import { AfRuntimeTimeline } from '../components/af/AfRuntimeTimeline';
import { formatTime } from '../components/af/afLabels';
import {
  sampleFailedTimeline,
  sampleFailedWorkflow,
  sampleWorkflowInstance,
} from './fixtures';

const FAILED_REASON =
  'DeveloperError: provider response contains no parseable patch or operations (after 1 retry)';

/** 真实失败 pipeline (toWorkflowPipeline 转换, 非手工构造)。 */
function failedPipeline() {
  return toWorkflowPipeline(undefined, sampleFailedWorkflow());
}

/** 真实失败事件 (toRuntimeActivity 转换, 升序输入 — 组件应倒序展示)。 */
function failedEvents() {
  return toRuntimeActivity(sampleFailedTimeline());
}

describe('AfRuntimeTimeline (Runtime Timeline — 当前执行卡 8 项 + 事件流 + 空态)', () => {
  it('当前执行卡: 失败 workflow → Agent/阶段/状态/开始时间/持续时间/失败原因/下一步/最近事件 (8 项)', () => {
    const pipeline = failedPipeline();
    const events = failedEvents();
    render(
      <AfRuntimeTimeline
        pipeline={pipeline}
        events={events}
        projectName="ScorePocket"
      />,
    );

    const card = screen.getByTestId('af-runtime-card');

    // ① 当前 Agent (failed 阶段 developer → 人话)
    expect(within(card).getByTestId('af-runtime-agent')).toHaveTextContent('开发工程师 Agent');
    // ② Workflow Stage (失败阶段名 → 人话 开发)
    expect(within(card).getByTestId('af-runtime-stage')).toHaveTextContent('开发');
    // ③ 状态 (AfStatusBadge → 失败)
    expect(within(card).getByTestId('af-runtime-status')).toHaveTextContent('失败');
    // ④ 开始时间 (started_at → formatTime)
    expect(within(card).getByTestId('af-runtime-started')).toHaveTextContent(
      formatTime('2026-08-12T03:00:00.000000+00:00'),
    );
    // ⑤ 持续时间 (started_at → completed_at = 45 分钟)
    expect(within(card).getByTestId('af-runtime-duration')).toHaveTextContent('45 分钟');
    // ⑥ 最近事件 (最新一条: 工作流失败)
    expect(within(card).getByTestId('af-runtime-recent')).toHaveTextContent('工作流失败');
    // ⑦ 失败原因 (failed_reason 全文, 红色横幅)
    expect(screen.getByTestId('af-runtime-failed')).toHaveTextContent(FAILED_REASON);
    // ⑧ 下一步 (第一个 pending 阶段 → 测试工程师 开始「测试」)
    expect(within(card).getByTestId('af-runtime-next')).toHaveTextContent(
      '等待 测试工程师 开始「测试」',
    );
  });

  it('running workflow → 当前 Agent = running 阶段 (非 completed/pending)', () => {
    const pipeline = toWorkflowPipeline(undefined, sampleWorkflowInstance());
    render(<AfRuntimeTimeline pipeline={pipeline} events={[]} />);
    const card = screen.getByTestId('af-runtime-card');
    // ux_ui running → UI 设计师; 状态 执行中
    expect(within(card).getByTestId('af-runtime-agent')).toHaveTextContent('UI 设计师 Agent');
    expect(within(card).getByTestId('af-runtime-status')).toHaveTextContent('执行中');
  });

  it('事件流: 复用 AfTimeline 且倒序 (最新在上)', () => {
    const events = failedEvents();
    render(<AfRuntimeTimeline pipeline={failedPipeline()} events={events} />);

    const items = screen.getAllByTestId('af-timeline-item');
    expect(items).toHaveLength(4);
    // 最新事件 (工作流失败, seq 504) 在最上
    expect(within(items[0]).getByText(/工作流失败/)).toBeInTheDocument();
    // 最早事件 (工作流创建, seq 501) 在最下
    expect(within(items[items.length - 1]).getByText(/工作流创建/)).toBeInTheDocument();
  });

  it('事件流: actor 人话化 (开发工程师 Agent) + result 人话化 (通过/失败)', () => {
    const events = failedEvents();
    render(<AfRuntimeTimeline pipeline={failedPipeline()} events={events} />);
    expect(screen.getAllByText('开发工程师 Agent').length).toBeGreaterThanOrEqual(1);
    // 工作流失败事件 result FAIL → 人话 失败
    const failedItem = screen
      .getAllByTestId('af-timeline-item')
      .find((el) => el.textContent?.includes('工作流失败'));
    expect(failedItem).toBeTruthy();
    expect(failedItem).toHaveTextContent('失败');
  });

  it('空态: 无 workflow (null) + 无 events → AfEmptyState', () => {
    render(<AfRuntimeTimeline pipeline={null} events={[]} />);
    expect(screen.getByTestId('af-empty-state')).toBeInTheDocument();
    expect(screen.getByText(/暂无运行活动/)).toBeInTheDocument();
  });

  it('空态: workflow 无 stages + 无 events → AfEmptyState', () => {
    const pipeline = toWorkflowPipeline(
      undefined,
      sampleFailedWorkflow({ stages: [] }),
    );
    render(<AfRuntimeTimeline pipeline={pipeline} events={[]} />);
    expect(screen.getByTestId('af-empty-state')).toBeInTheDocument();
  });

  it('仅事件流 (workflow 无 stages): 无执行卡, 事件流正常渲染', () => {
    const pipeline = toWorkflowPipeline(
      undefined,
      sampleFailedWorkflow({ stages: [] }),
    );
    render(<AfRuntimeTimeline pipeline={pipeline} events={failedEvents()} />);
    expect(screen.queryByTestId('af-runtime-card')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('af-timeline-item')).toHaveLength(4);
  });
});
