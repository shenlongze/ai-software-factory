/**
 * src/test/runtimeClient.test.ts — S10-002 Runtime 前端客户端测试。
 *
 * 覆盖 (runtimeClient: workflow/timeline 查询 + SSE 订阅):
 * - getWorkflow / getTimeline: 成功 → {data, is_mock:false};
 *   ApiError (后端不可达) → mock fallback + is_mock:true (诚实标注, 不冒充)
 * - subscribeEvents:
 *   - 订阅全部 RUNTIME_EVENT_NAMES (含 runtime.created / runtime.status.changed)
 *   - 事件 JSON 解析后回调 onEvent
 *   - 收到后端 mock error 事件 (mock:true) → isMock()=true 且停止重连
 *   - 连接错误 → onError + 延迟重连 (新 EventSource); close() 后不再重连
 * - 只读契约: 全部 GET (无写路径)
 *
 * jsdom 无原生 EventSource → FakeEventSource 桩 (记录实例/监听器, 手动派发
 * 事件/触发错误); 重连延迟用 vi.useFakeTimers 推进。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { runtimeClient, SSE_RECONNECT_DELAY_MS } from '../api/runtimeClient';
import { RUNTIME_EVENT_NAMES } from '../models/types';
import { stubFetch } from './fixtures';

/** jsdom EventSource 桩 (记录实例 + 监听器, 可手动派发事件/触发错误)。 */
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

  /** 手动派发命名事件 (data 为 SSE data 行原始字符串)。 */
  dispatch(name: string, data: string): void {
    for (const cb of this.listeners[name] ?? []) {
      cb({ data } as MessageEvent<string>);
    }
  }

  /** 触发连接错误 (模拟 EventSource onerror)。 */
  fail(): void {
    this.onerror?.(new Event('error'));
  }

  close(): void {
    this.closed = true;
  }
}

/** 最近一个 EventSource 实例。 */
function lastSource(): FakeEventSource {
  return FakeEventSource.instances[FakeEventSource.instances.length - 1];
}

describe('runtimeClient — workflow/timeline 查询 (mock fallback)', () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('getWorkflow 成功 → {data, is_mock:false} (真实数据)', async () => {
    stubFetch({
      '/api/projects/demo/workflow': {
        id: 'wf-1',
        project_id: 'demo',
        project_name: 'Demo',
        name: 'Chain',
        status: 'active',
        failed_reason: '',
        created_at: null,
        started_at: null,
        completed_at: null,
        stages: [],
        pending_approvals: [],
        template: [],
      },
    });
    const got = await runtimeClient.getWorkflow('demo');
    expect(got.is_mock).toBe(false);
    expect(got.data.id).toBe('wf-1');
  });

  it('getWorkflow 后端不可达 (ApiError) → mock 工作流 + is_mock:true', async () => {
    stubFetch({}); // 全 404 → ApiError → mock fallback
    const got = await runtimeClient.getWorkflow('ledger-app');
    expect(got.is_mock).toBe(true);
    expect(got.data.is_mock).toBe(true); // mock 数据自身诚实标注
    expect(got.data.stages[0].name).toBe('Product');
    expect(got.data.project_id).toBe('ledger-app');
  });

  it('getTimeline 成功 → {data, is_mock:false}', async () => {
    stubFetch({
      '/api/projects/demo/timeline?limit=200': [
        { id: 'evt-1', seq: 1, project_id: 'demo', type: 'stage' },
      ],
    });
    const got = await runtimeClient.getTimeline('demo');
    expect(got.is_mock).toBe(false);
    expect(got.data[0].seq).toBe(1);
  });

  it('getTimeline 后端不可达 → mock 事件流 + is_mock:true (打开 Workspace 可见 AI 事件)', async () => {
    stubFetch({});
    const got = await runtimeClient.getTimeline('ledger-app');
    expect(got.is_mock).toBe(true);
    expect(got.data.length).toBeGreaterThan(0);
    expect(got.data[0].type).toBe('user');
  });
});

describe('runtimeClient — subscribeEvents (SSE 断线重连 + isMock)', () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('订阅全部 RUNTIME_EVENT_NAMES (含 runtime.created / runtime.status.changed)', () => {
    runtimeClient.subscribeEvents('demo', { onEvent: () => {} });
    const source = lastSource();
    expect(source.url).toBe('/api/events/stream?project_id=demo');
    expect(Object.keys(source.listeners).sort()).toEqual([...RUNTIME_EVENT_NAMES].sort());
  });

  it('事件 JSON 解析后回调 onEvent (stage.started)', () => {
    const seen: Array<[string, Record<string, unknown>]> = [];
    const sub = runtimeClient.subscribeEvents('demo', {
      onEvent: (name, data) => seen.push([name, data]),
    });
    const source = lastSource();
    source.dispatch(
      'stage.started',
      JSON.stringify({ stage_id: 'STG-1', agent_id: 'pm', name: 'PM' }),
    );
    expect(seen).toEqual([['stage.started', { stage_id: 'STG-1', agent_id: 'pm', name: 'PM' }]]);
    expect(sub.isMock()).toBe(false);
  });

  it('runtime.created 事件透传 (契约: instance/type/status)', () => {
    const seen: Array<[string, Record<string, unknown>]> = [];
    runtimeClient.subscribeEvents('demo', { onEvent: (name, data) => seen.push([name, data]) });
    lastSource().dispatch(
      'runtime.created',
      JSON.stringify({ instance_id: 'RT-1', type: 'browser', status: 'starting' }),
    );
    expect(seen).toEqual([
      ['runtime.created', { instance_id: 'RT-1', type: 'browser', status: 'starting' }],
    ]);
  });

  it('收到后端 mock error 事件 (mock:true) → isMock()=true 且停止重连', () => {
    vi.useFakeTimers();
    const onError = vi.fn();
    const seen: Array<[string, Record<string, unknown>]> = [];
    const sub = runtimeClient.subscribeEvents('demo', { onEvent: (n, d) => seen.push([n, d]), onError });
    const source = lastSource();
    source.dispatch('error', JSON.stringify({ stage_id: null, reason: 'event store unavailable', mock: true }));
    expect(seen[0][0]).toBe('error');
    expect((seen[0][1] as { mock?: boolean }).mock).toBe(true);
    expect(sub.isMock()).toBe(true);
    // 连接关闭后不应重连 (mock 模式诚实停止)
    source.fail();
    vi.advanceTimersByTime(SSE_RECONNECT_DELAY_MS * 3);
    expect(FakeEventSource.instances.length).toBe(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it('连接错误 → onError + 延迟重连 (新 EventSource)', () => {
    vi.useFakeTimers();
    const onError = vi.fn();
    const sub = runtimeClient.subscribeEvents('demo', { onEvent: () => {}, onError });
    const first = lastSource();
    first.fail();
    expect(onError).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(SSE_RECONNECT_DELAY_MS);
    expect(FakeEventSource.instances.length).toBe(2); // 已重连
    expect(lastSource()).not.toBe(first);
    // 重连后新连接同样处理事件
    lastSource().dispatch('stage.started', JSON.stringify({ stage_id: 'S2' }));
    sub.close();
  });

  it('close() 后不再重连 (onError 静默)', () => {
    vi.useFakeTimers();
    const onError = vi.fn();
    const sub = runtimeClient.subscribeEvents('demo', { onEvent: () => {}, onError });
    const source = lastSource();
    sub.close();
    expect(source.closed).toBe(true);
    source.fail();
    vi.advanceTimersByTime(SSE_RECONNECT_DELAY_MS * 3);
    expect(FakeEventSource.instances.length).toBe(1);
    expect(onError).not.toHaveBeenCalled();
  });
});
