/**
 * src/test/agent-timeline.test.tsx — S10-003 Agent Timeline 组件测试。
 *
 * 覆盖 (事件流渲染 / Stage Card 状态色 / SSE 实时追加 / 滚动到底 / mock 徽章 /
 * 空态 / 错误态 / 查看详情 / 底部持续开发输入占位):
 * - 初始历史: runtimeClient.getTimeline (fetch 桩) — 6 类节点渲染
 * - 实时: subscribeEvents (FakeEventSource 桩, 与 runtimeClient.test 同模式)
 * - is_mock: 查询 fallback / SSE mock error 事件 → "演示数据" 徽章
 * - 滚动: defineProperty 覆盖 scrollHeight/clientHeight → 断言 scrollTop
 * - 错误态: 非 ApiError (TypeError) → 错误提示 + 重试重载
 * 唯一 basename, 不与 S10-001/002 测试冲突。
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AgentTimeline, roleKeyFromAgentId, sseEventToTimelineNode, timelineNodeStatus } from '../shell/AgentTimeline';
import type { TimelineEventSummary } from '../models/types';
import { stubFetch } from './fixtures';

/** jsdom EventSource 桩 (记录实例 + 监听器, 手动派发事件/触发错误)。 */
class FakeEventSource {
  static instances: FakeEventSource[] = [];

  url: string;
  listeners: Record<string, Array<(ev: MessageEvent<string>) => void>> = {};
  onerror: ((ev: Event) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, cb: (ev: MessageEvent<string>) => void): void {
    (this.listeners[name] ??= []).push(cb);
  }

  dispatch(name: string, data: string): void {
    for (const cb of this.listeners[name] ?? []) {
      cb({ data } as MessageEvent<string>);
    }
  }

  fail(): void {
    this.onerror?.(new Event('error'));
  }

  close(): void {
    this.closed = true;
  }
}

function lastSource(): FakeEventSource {
  return FakeEventSource.instances[FakeEventSource.instances.length - 1];
}

/** Timeline 事件工厂 (形状对齐 TimelineEventSummary; 只读投影)。 */
function tlEvent(overrides: Omit<Partial<TimelineEventSummary>, 'type'> & { type: TimelineEventSummary['type'] }): TimelineEventSummary {
  return {
    id: 'evt-1',
    seq: 1,
    project_id: 'ledger-app',
    event_type: '',
    stage_id: null,
    agent_id: null,
    artifact_id: null,
    gate_id: null,
    message: '',
    status: null,
    payload: {},
    created_at: null,
    ...overrides,
  };
}

const PROJECT = 'ledger-app';
const TIMELINE_URL = `/api/projects/${PROJECT}/timeline?limit=200`;

/** 渲染 AgentTimeline (fetch 桩 + EventSource 桩)。 */
function renderTimeline(events: unknown[]) {
  stubFetch({ [TIMELINE_URL]: events });
  return render(<AgentTimeline projectId={PROJECT} />);
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ------------------------------------------------------------------ 事件流渲染 (各类型节点)
describe('AgentTimeline — 事件流渲染 (6 类节点)', () => {
  it('渲染 user/stage/artifact/review/diff/error 六类节点 + 状态色 data-status', async () => {
    renderTimeline([
      tlEvent({ id: 'e-user', seq: 1, type: 'user', message: '项目创建: 记账 App' }),
      tlEvent({
        id: 'e-stage-running',
        seq: 2,
        type: 'stage',
        event_type: 'org.workflow.stage_started',
        agent_id: 'pm',
        message: '阶段开始: PM',
        payload: { name: 'PM' },
      }),
      tlEvent({ id: 'e-art', seq: 3, type: 'artifact', event_type: 'org.artifact.created', message: '产物生成' }),
      tlEvent({ id: 'e-review', seq: 4, type: 'review', event_type: 'org.approval.created', message: '等待你审核' }),
      tlEvent({ id: 'e-diff', seq: 5, type: 'diff', message: 'Developer 修改', payload: { files: ['app/index.ts'] } }),
      tlEvent({ id: 'e-err', seq: 6, type: 'error', message: 'LLM 调用失败', payload: { reason: 'timeout' } }),
    ]);
    const nodes = await screen.findAllByTestId('ds-timeline-node');
    expect(nodes).toHaveLength(6);
    expect(nodes[0]).toHaveAttribute('data-status', 'pending'); // user
    expect(nodes[1]).toHaveAttribute('data-status', 'running'); // stage started
    expect(nodes[2]).toHaveAttribute('data-status', 'success'); // artifact
    expect(nodes[3]).toHaveAttribute('data-status', 'approval_required'); // review
    expect(nodes[4]).toHaveAttribute('data-status', 'success'); // diff
    expect(nodes[5]).toHaveAttribute('data-status', 'failed'); // error
  });

  it('user 节点: 只读气泡显示用户输入', async () => {
    renderTimeline([tlEvent({ id: 'e1', type: 'user', message: '开发一个记账 App' })]);
    const bubble = await screen.findByTestId('agent-timeline-user');
    expect(bubble).toHaveTextContent('开发一个记账 App');
    expect(within(bubble).queryByRole('button')).toBeNull(); // 只读记录, 无操作按钮
  });

  it('stage 节点: StageCard 渲染 Agent 图标/状态/输入/输出/耗时/成本', async () => {
    renderTimeline([
      tlEvent({
        id: 'e1',
        type: 'stage',
        event_type: 'org.workflow.stage_completed',
        agent_id: 'product-manager',
        message: '阶段完成: 需求分析',
        payload: {
          name: '需求分析',
          input_artifacts: ['用户需求'],
          output_artifacts: ['PRD 文档'],
          duration_s: 42,
          cost_usd: 0.0038,
        },
      }),
    ]);
    const card = await screen.findByTestId('ds-stage-card');
    expect(card).toHaveAttribute('data-status', 'success');
    expect(card.querySelector('[data-role="pm"]')).not.toBeNull(); // product-manager → pm 头像
    expect(within(card).getByText('需求分析')).toBeInTheDocument();
    expect(within(card).getByText('产品经理')).toBeInTheDocument();
    expect(within(card).getByText('成功')).toBeInTheDocument();
    expect(within(card).getByText('用户需求')).toBeInTheDocument();
    expect(within(card).getByText('PRD 文档')).toBeInTheDocument();
    expect(within(card).getByText('42s')).toBeInTheDocument();
    expect(within(card).getByText('$0.0038')).toBeInTheDocument();
  });

  it('stage 节点状态色: running 蓝点 / success 绿点 / failed 红点 / approval_required 橙徽章', async () => {
    renderTimeline([
      tlEvent({
        id: 'e-run',
        type: 'stage',
        event_type: 'org.workflow.stage_started',
        message: '阶段开始: Dev',
        payload: { name: 'Dev' },
      }),
      tlEvent({
        id: 'e-ok',
        type: 'stage',
        event_type: 'org.workflow.stage_completed',
        message: '阶段完成: Dev',
        payload: { name: 'Dev' },
      }),
      tlEvent({
        id: 'e-fail',
        type: 'stage',
        event_type: 'org.workflow.stage_failed',
        message: '阶段失败: Test',
        payload: { name: 'Test' },
      }),
      tlEvent({
        id: 'e-review',
        type: 'stage',
        message: '阶段等待审核',
        payload: { name: 'Architecture', status: 'approval_required' },
      }),
    ]);
    const nodes = await screen.findAllByTestId('ds-timeline-node');
    expect(nodes[0].querySelector('.ds-dot-running')).not.toBeNull();
    expect(nodes[1].querySelector('.ds-dot-success')).not.toBeNull();
    expect(nodes[2].querySelector('.ds-dot-failed')).not.toBeNull();
    expect(within(nodes[3]).getByText('待审批')).toBeInTheDocument();
    expect(within(nodes[3]).getByText('待审批')).toHaveClass('ds-badge-warning');
  });

  it('artifact 节点: 产物消息 + 查看按钮 (secondary)', async () => {
    renderTimeline([
      tlEvent({
        id: 'e1',
        type: 'artifact',
        event_type: 'org.artifact.created',
        artifact_id: 'art-1',
        message: '生成 Product Artifact',
        payload: { artifact_id: 'art-1', type: 'product' },
      }),
    ]);
    await screen.findByTestId('agent-timeline-artifact');
    expect(screen.getByText('生成 Product Artifact')).toBeInTheDocument();
    const viewBtn = screen.getByRole('button', { name: '查看' });
    expect(viewBtn).toHaveAttribute('data-variant', 'secondary');
  });

  it('review 节点: 等待审核 + 去审核按钮 (primary 高亮)', async () => {
    renderTimeline([
      tlEvent({
        id: 'e1',
        type: 'review',
        event_type: 'org.approval.created',
        gate_id: 'gate-1',
        message: '等待你审核',
        payload: { artifact_type: 'PRD' },
      }),
    ]);
    await screen.findByTestId('agent-timeline-review');
    expect(screen.getByText('PRD')).toBeInTheDocument();
    const reviewBtn = screen.getByRole('button', { name: '去审核' });
    expect(reviewBtn).toHaveAttribute('data-variant', 'primary');
  });

  it('diff 节点: 文件清单 chips + 展开 diff 显示 payload', async () => {
    const user = userEvent.setup();
    renderTimeline([
      tlEvent({
        id: 'e1',
        type: 'diff',
        message: 'Developer 修改 2 个文件',
        payload: { files: ['src/app.ts', 'src/api.ts'], diff: '+export const x = 1;' },
      }),
    ]);
    const files = await screen.findByTestId('agent-timeline-diff-files');
    expect(within(files).getByText('src/app.ts')).toBeInTheDocument();
    expect(within(files).getByText('src/api.ts')).toBeInTheDocument();
    expect(screen.queryByTestId('agent-timeline-detail')).toBeNull();
    await user.click(screen.getByRole('button', { name: '展开 diff' }));
    const detail = screen.getByTestId('agent-timeline-detail');
    expect(detail).toHaveTextContent('+export const x = 1;');
  });

  it('error 节点: 失败原因红色展示', async () => {
    renderTimeline([
      tlEvent({ id: 'e1', type: 'error', message: 'LLM 调用超时', payload: { reason: 'timeout' } }),
    ]);
    const error = await screen.findByTestId('agent-timeline-error');
    expect(error).toHaveTextContent('LLM 调用超时');
    expect(error.className).toContain('ws-tl-error');
  });
});

// ------------------------------------------------------------------ mock 徽章
describe('AgentTimeline — is_mock 演示数据徽章', () => {
  it('后端不可达 (ApiError → mock fallback) → 显示 演示数据 徽章 + mock 事件', async () => {
    stubFetch({}); // 全 404 → ApiError → mockTimeline (is_mock=true)
    render(<AgentTimeline projectId={PROJECT} />);
    expect(await screen.findByTestId('agent-timeline-mock')).toHaveTextContent('演示数据');
    // mock 事件流真实渲染 (诚实标注, 不冒充)
    expect(await screen.findByTestId('agent-timeline-user')).toHaveTextContent('项目创建: 记账 App');
    expect(screen.getByText('审批待处理 (需求/设计/发布门)')).toBeInTheDocument();
  });

  it('真实数据 (is_mock=false) → 无演示数据徽章', async () => {
    renderTimeline([tlEvent({ id: 'e1', type: 'user', message: '真实事件' })]);
    await screen.findByTestId('agent-timeline-user');
    expect(screen.queryByTestId('agent-timeline-mock')).toBeNull();
  });
});

// ------------------------------------------------------------------ SSE 实时追加
describe('AgentTimeline — SSE 实时追加', () => {
  it('SSE stage.started 事件 → 实时追加 stage 节点 (StageCard)', async () => {
    renderTimeline([tlEvent({ id: 'e0', type: 'user', message: '初始事件' })]);
    await screen.findByTestId('agent-timeline-user');
    expect(screen.queryByText('阶段开始: PM')).toBeNull();

    lastSource().dispatch('stage.started', JSON.stringify({ stage_id: 'STG-1', agent_id: 'pm', name: 'PM' }));
    const card = await screen.findByTestId('ds-stage-card');
    expect(within(card).getByText('PM')).toBeInTheDocument(); // StageCard name (SSE data.name)
    expect(card).toHaveAttribute('data-status', 'running');
    expect(screen.getByTestId('agent-timeline-scroll').querySelectorAll('.ds-timeline-node')).toHaveLength(2);
  });

  it('SSE artifact.created → 追加 生成 Product Artifact 节点', async () => {
    renderTimeline([tlEvent({ id: 'e0', type: 'user', message: '初始事件' })]);
    await screen.findByTestId('agent-timeline-user');
    lastSource().dispatch('artifact.created', JSON.stringify({ artifact_id: 'ART-9', type: 'product' }));
    expect(await screen.findByText('生成 Product Artifact')).toBeInTheDocument();
  });

  it('SSE approval.required → 追加 review 节点 (去审核)', async () => {
    renderTimeline([tlEvent({ id: 'e0', type: 'user', message: '初始事件' })]);
    await screen.findByTestId('agent-timeline-user');
    lastSource().dispatch(
      'approval.required',
      JSON.stringify({ stage_id: 'STG-3', gate_id: 'GATE-3' }),
    );
    expect(await screen.findByRole('button', { name: '去审核' })).toBeInTheDocument();
  });

  it('SSE error 事件 (mock:true) → 演示数据徽章 (诚实演示降级)', async () => {
    renderTimeline([tlEvent({ id: 'e0', type: 'user', message: '初始事件' })]);
    await screen.findByTestId('agent-timeline-user');
    expect(screen.queryByTestId('agent-timeline-mock')).toBeNull();
    lastSource().dispatch('error', JSON.stringify({ reason: 'event store unavailable', mock: true }));
    expect(await screen.findByTestId('agent-timeline-mock')).toHaveTextContent('演示数据');
  });

  it('SSE error 事件 (真实失败) → 追加红色 error 节点', async () => {
    renderTimeline([tlEvent({ id: 'e0', type: 'user', message: '初始事件' })]);
    await screen.findByTestId('agent-timeline-user');
    lastSource().dispatch('error', JSON.stringify({ stage_id: 'STG-2', reason: 'build failed' }));
    const error = await screen.findByTestId('agent-timeline-error');
    expect(error).toHaveTextContent('build failed');
  });

  it('卸载时关闭 SSE 订阅 (无泄漏)', async () => {
    const { unmount } = renderTimeline([tlEvent({ id: 'e0', type: 'user', message: '初始事件' })]);
    await screen.findByTestId('agent-timeline-user');
    const source = lastSource();
    expect(source.closed).toBe(false);
    unmount();
    expect(source.closed).toBe(true);
  });
});

// ------------------------------------------------------------------ 滚动到底
describe('AgentTimeline — 滚动到底', () => {
  it('初始历史加载后滚动到底部 (scrollTop = scrollHeight - clientHeight)', async () => {
    const { container } = renderTimeline([tlEvent({ id: 'e0', type: 'user', message: '初始事件' })]);
    const scroll = screen.getByTestId('agent-timeline-scroll');
    Object.defineProperty(scroll, 'scrollHeight', { value: 600, configurable: true });
    Object.defineProperty(scroll, 'clientHeight', { value: 300, configurable: true });
    await screen.findByTestId('agent-timeline-user');
    expect(scroll.scrollTop).toBe(300);
    expect(container).not.toBeNull();
  });

  it('SSE 追加后再次滚动到底部', async () => {
    renderTimeline([tlEvent({ id: 'e0', type: 'user', message: '初始事件' })]);
    const scroll = screen.getByTestId('agent-timeline-scroll');
    Object.defineProperty(scroll, 'scrollHeight', { value: 600, configurable: true });
    Object.defineProperty(scroll, 'clientHeight', { value: 300, configurable: true });
    await screen.findByTestId('agent-timeline-user');
    expect(scroll.scrollTop).toBe(300);

    // 追加后重新计算 (模拟内容增高)
    Object.defineProperty(scroll, 'scrollHeight', { value: 900, configurable: true });
    lastSource().dispatch('stage.started', JSON.stringify({ stage_id: 'STG-1', agent_id: 'pm', name: 'PM' }));
    await screen.findByTestId('ds-stage-card');
    expect(scroll.scrollTop).toBe(600);
  });
});

// ------------------------------------------------------------------ 空态 / 错误态
describe('AgentTimeline — 空态 / 错误态', () => {
  it('无事件 → 空态 "等待 AI 开始工作…"', async () => {
    renderTimeline([]);
    const empty = await screen.findByTestId('agent-timeline-empty');
    expect(within(empty).getByText('等待 AI 开始工作…')).toBeInTheDocument();
    expect(screen.queryByTestId('agent-timeline-mock')).toBeNull(); // 空态不是 mock
  });

  it('非 ApiError (TypeError) → 错误态 + 重试重载成功', async () => {
    const user = userEvent.setup();
    let calls = 0;
    const failingFetch = vi.fn(async () => {
      calls += 1;
      if (calls === 1) throw new TypeError('Failed to parse URL');
      return {
        ok: true,
        status: 200,
        json: async () => [tlEvent({ id: 'e1', type: 'user', message: '重试后的事件' })],
      } as Response;
    });
    vi.stubGlobal('fetch', failingFetch);
    render(<AgentTimeline projectId={PROJECT} />);

    const errorState = await screen.findByTestId('agent-timeline-error-state');
    expect(within(errorState).getByText(/时间线加载失败/)).toBeInTheDocument();
    expect(within(errorState).getByText(/Failed to parse URL/)).toBeInTheDocument();

    await user.click(within(errorState).getByRole('button', { name: '重试' }));
    expect(await screen.findByTestId('agent-timeline-user')).toHaveTextContent('重试后的事件');
    expect(calls).toBe(2);
  });
});

// ------------------------------------------------------------------ 查看详情 / 底部输入
describe('AgentTimeline — 查看详情 / 底部持续开发输入', () => {
  it('Stage Card 查看详情 → 展开 payload 详情块, 再点收起', async () => {
    const user = userEvent.setup();
    renderTimeline([
      tlEvent({
        id: 'e1',
        type: 'stage',
        event_type: 'org.workflow.stage_completed',
        message: '阶段完成: PM',
        payload: { name: 'PM', duration_s: 12, cost_usd: 0.01 },
      }),
    ]);
    await screen.findByTestId('ds-stage-card');
    expect(screen.queryByTestId('agent-timeline-detail')).toBeNull();
    await user.click(screen.getByRole('button', { name: '查看详情' }));
    const detail = screen.getByTestId('agent-timeline-detail');
    expect(detail).toHaveTextContent('"duration_s"');
    expect(detail).toHaveTextContent('0.01');
    await user.click(screen.getByRole('button', { name: '查看详情' }));
    expect(screen.queryByTestId('agent-timeline-detail')).toBeNull();
  });

  it('artifact 查看按钮 → 详情块 (点击有反馈)', async () => {
    const user = userEvent.setup();
    renderTimeline([
      tlEvent({
        id: 'e1',
        type: 'artifact',
        message: '生成 Code Artifact',
        payload: { artifact_id: 'ART-1', type: 'code' },
      }),
    ]);
    await screen.findByTestId('agent-timeline-artifact');
    await user.click(screen.getByRole('button', { name: '查看' }));
    expect(screen.getByTestId('agent-timeline-detail')).toHaveTextContent('"artifact_id"');
  });

  it('底部输入: placeholder + 发送 → 提示 S10-006 接入 (仅占位)', async () => {
    const user = userEvent.setup();
    renderTimeline([tlEvent({ id: 'e0', type: 'user', message: '初始事件' })]);
    await screen.findByTestId('agent-timeline-user');
    const input = screen.getByTestId('agent-timeline-input-box');
    expect(input).toHaveAttribute('placeholder', expect.stringContaining('S10-006'));
    expect(screen.queryByTestId('agent-timeline-input-hint')).toBeNull();
    await user.type(input, '修改首页颜色');
    await user.click(screen.getByRole('button', { name: '发送' }));
    expect(screen.getByTestId('agent-timeline-input-hint')).toHaveTextContent('S10-006');
  });
});

// ------------------------------------------------------------------ 纯函数映射
describe('AgentTimeline — 事件映射纯函数', () => {
  it('roleKeyFromAgentId: org role_id → Design System 角色键', () => {
    expect(roleKeyFromAgentId('product-manager')).toBe('pm');
    expect(roleKeyFromAgentId('ui-designer')).toBe('ux_ui');
    expect(roleKeyFromAgentId('architect')).toBe('architecture');
    expect(roleKeyFromAgentId('devops')).toBe('release');
    expect(roleKeyFromAgentId('pm')).toBe('pm');
    expect(roleKeyFromAgentId('unknown-role')).toBe('unknown-role');
    expect(roleKeyFromAgentId(null)).toBe('agent');
  });

  it('sseEventToTimelineNode: SSE 事件 → Timeline 节点映射 (含跳过)', () => {
    const node = sseEventToTimelineNode('p1', 'stage.started', { stage_id: 'S1', agent_id: 'pm', name: 'PM' }, 7);
    expect(node?.type).toBe('stage');
    expect(node?.status).toBe('running');
    expect(node?.message).toBe('阶段开始: PM');
    expect(node?.seq).toBe(7);
    expect(node?.stage_id).toBe('S1');

    const done = sseEventToTimelineNode('p1', 'stage.completed', { stage_id: 'S1', name: 'PM', duration_s: 9 }, 8);
    expect(done?.status).toBe('success');
    expect(done?.payload.duration_s).toBe(9);

    const error = sseEventToTimelineNode('p1', 'error', { reason: 'boom' }, 9);
    expect(error?.type).toBe('error');
    expect(error?.message).toBe('boom');

    // runtime.* 与 approval.completed 不进 Timeline (S10-004/006 面板)
    expect(sseEventToTimelineNode('p1', 'runtime.created', {}, 10)).toBeNull();
    expect(sseEventToTimelineNode('p1', 'approval.completed', {}, 11)).toBeNull();
  });

  it('timelineNodeStatus: event_type → 节点状态', () => {
    expect(
      timelineNodeStatus(tlEvent({ type: 'stage', event_type: 'org.workflow.stage_started' })),
    ).toBe('running');
    expect(
      timelineNodeStatus(tlEvent({ type: 'stage', event_type: 'org.workflow.stage_completed' })),
    ).toBe('success');
    expect(
      timelineNodeStatus(tlEvent({ type: 'stage', event_type: 'org.workflow.stage_failed' })),
    ).toBe('failed');
    expect(
      timelineNodeStatus(tlEvent({ type: 'stage', payload: { status: 'approval_required' } })),
    ).toBe('approval_required');
    expect(timelineNodeStatus(tlEvent({ type: 'user' }))).toBe('pending');
    expect(timelineNodeStatus(tlEvent({ type: 'review' }))).toBe('approval_required');
    expect(timelineNodeStatus(tlEvent({ type: 'error' }))).toBe('failed');
  });
});
