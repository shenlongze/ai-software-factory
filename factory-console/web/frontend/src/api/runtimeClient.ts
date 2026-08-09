/**
 * api/runtimeClient.ts — S10-002 Runtime 前端客户端 (UI 数据源统一入口)。
 *
 * 三个能力 (不写 UI, 只提供数据/事件契约 — S10-003 Timeline UI 消费):
 * - getWorkflow(projectId): 项目工作流详情 (8 阶段链) — 无后端 → mock fallback
 *   (is_mock=true, 诚实标注; 打开 Workspace 可见 AI 工作事件)
 * - getTimeline(projectId): Timeline 事件聚合 (user/stage/artifact/review/error)
 *   — 无后端 → mock fallback (is_mock=true)
 * - subscribeEvents(projectId, onEvent): SSE 事件流 (EventSource 封装)
 *   — 断线重连 (固定延迟, 指数退避留作后续) + isMock 检测: 收到后端
 *   mock error 事件 (mock: true) → 停止重连, 诚实进入演示模式
 *
 * 只读契约 (与 api/client.ts 同: 全部 GET / 只读 SSE; 无写路径)。
 */

import { api, ApiError } from './client';
import { mockTimeline, mockWorkflowDetail } from '../mock/runtime';
import {
  RUNTIME_EVENT_NAMES,
  type RuntimeEventName,
  type TimelineEventSummary,
  type WorkflowDetail,
} from '../models/types';

/** 查询结果统一包装: data + is_mock (mock fallback 诚实标记)。 */
export interface RuntimeQueryResult<T> {
  data: T;
  /** true = 后端不可达/数据缺失 → mock 演示数据 (前端据此显示演示标识)。 */
  is_mock: boolean;
}

/** SSE 事件 handler (event: 名 → data 回调; onError 连接错误 — 不含 mock 关闭)。 */
export interface RuntimeEventHandlers {
  onEvent: (name: RuntimeEventName, data: Record<string, unknown>) => void;
  onError?: (event: Event | null) => void;
}

/** SSE 订阅控制器 (close 停止; isMock 查询当前演示模式)。 */
export interface RuntimeEventSubscription {
  close: () => void;
  /** true = 已收到 mock error 事件 (后端不可达), 流已停止不重连。 */
  isMock: () => boolean;
}

/** 断线重连延迟 (ms; 固定延迟, KISS — 指数退避/抖动留作后续)。 */
export const SSE_RECONNECT_DELAY_MS = 2000;

async function fetchWithMockFallback<T>(
  request: () => Promise<T>,
  mock: () => T,
): Promise<RuntimeQueryResult<T>> {
  try {
    const data = await request();
    return { data, is_mock: (data as { is_mock?: boolean }).is_mock ?? false };
  } catch (err) {
    if (err instanceof ApiError) {
      // 只兜底 ApiError (后端不可达/数据缺失); 其他异常照抛 (诚实不掩盖)
      return { data: mock(), is_mock: true };
    }
    throw err;
  }
}

/** Runtime 前端客户端 (workflow/timeline 查询 + SSE 事件流)。 */
export const runtimeClient = {
  /** 项目工作流详情 (无后端 → mock 工作流, is_mock=true)。 */
  getWorkflow: (projectId: string): Promise<RuntimeQueryResult<WorkflowDetail>> =>
    fetchWithMockFallback(
      () => api.projectWorkflow(projectId),
      () => mockWorkflowDetail(projectId),
    ),

  /** Timeline 事件聚合 (无后端 → mock 事件流, is_mock=true)。 */
  getTimeline: (
    projectId: string,
    limit = 200,
  ): Promise<RuntimeQueryResult<TimelineEventSummary[]>> =>
    fetchWithMockFallback(
      () => api.projectTimeline(projectId, limit),
      () => mockTimeline(projectId),
    ),

  /**
   * SSE 事件流订阅 (断线重连 + isMock 标记)。
   *
   * EventSource 封装: 订阅 RUNTIME_EVENT_NAMES 全部事件; 连接错误 →
   * onError + 延迟重连 (close 后/收到 mock error 后不再重连); 后端不可达
   * (无事件库) → 后端推单条 error 事件 (mock: true) 后关闭 — 收到即置
   * mock 模式并停止重连 (诚实演示降级, 不无限空转)。
   */
  subscribeEvents: (
    projectId: string,
    handlers: RuntimeEventHandlers,
  ): RuntimeEventSubscription => subscribeEvents(projectId, handlers),
};

/** SSE 事件流订阅 (见 runtimeClient.subscribeEvents 说明)。 */
export function subscribeEvents(
  projectId: string,
  handlers: RuntimeEventHandlers,
): RuntimeEventSubscription {
  const url = `/api/events/stream?project_id=${encodeURIComponent(projectId)}`;
  let source: EventSource | null = null;
  let closed = false;
  let mockMode = false;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const teardown = (): void => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    if (source !== null) {
      source.close();
      source = null;
    }
  };

  const connect = (): void => {
    if (closed || mockMode) return;
    source = new EventSource(url);
    for (const name of RUNTIME_EVENT_NAMES) {
      source.addEventListener(name, (ev: Event) => {
        const message = ev as MessageEvent<string>;
        let data: Record<string, unknown> = {};
        try {
          data = JSON.parse(message.data) as Record<string, unknown>;
        } catch {
          data = { raw: message.data };
        }
        if (data.mock === true) {
          // 后端不可达 → 诚实演示模式: 停止重连, 流保持关闭
          mockMode = true;
        }
        handlers.onEvent(name, data);
      });
    }
    source.onerror = (ev: Event) => {
      if (closed || mockMode) return;
      handlers.onError?.(ev);
      // 断线重连 (固定延迟; 已 close / mock 模式不重连)
      if (timer === null) {
        timer = setTimeout(() => {
          timer = null;
          connect();
        }, SSE_RECONNECT_DELAY_MS);
      }
    };
  };

  connect();
  return {
    close: () => {
      closed = true;
      teardown();
    },
    isMock: () => mockMode,
  };
}
