/**
 * src/test/runtime-session-adapter.test.ts — S10-016 toRuntimeSession Adapter 映射。
 *
 * 数据流: RuntimeSession (API) → toRuntimeSession → RuntimeActivity (兼容 S10-015)。
 */

import { describe, expect, it } from 'vitest';
import { toRuntimeSession } from '../api/domain';
import type { RuntimeSessionPayload } from '../models/types';

/** 真实结构 fixture: 后端 POST /api/agents/{id}/sessions 返回形态。 */
function sampleSession(overrides: Partial<RuntimeSessionPayload> = {}): RuntimeSessionPayload {
  return {
    session_id: 'SES-001',
    agent_id: 'developer-1',
    task_id: 'TASK-a1',
    workflow_id: 'WF-1',
    status: 'running',
    created_at: '2026-08-12T13:00:00Z',
    started_at: '2026-08-12T13:01:00Z',
    finished_at: null,
    events: [],
    ...overrides,
  };
}

describe('api/domain — toRuntimeSession (S10-016 映射)', () => {
  it('running session → RuntimeActivity (time/actor/action/result 人话)', () => {
    const activity = toRuntimeSession(sampleSession());
    expect(activity.time).toBe('2026-08-12T13:01:00Z'); // started_at 优先
    expect(activity.action).toBe('执行任务 TASK-a1 (WF-1)');
    expect(activity.result).toBe('执行中');
    expect(activity.eventType).toBe('runtime_session.running');
  });

  it('无 started_at → 用 created_at', () => {
    const activity = toRuntimeSession(sampleSession({ started_at: undefined }));
    expect(activity.time).toBe('2026-08-12T13:00:00Z');
  });

  it('五态人话映射: pending/success/failed/cancelled', () => {
    expect(toRuntimeSession(sampleSession({ status: 'pending' })).result).toBe('待处理');
    expect(toRuntimeSession(sampleSession({ status: 'success' })).result).toBe('成功');
    expect(toRuntimeSession(sampleSession({ status: 'failed' })).result).toBe('失败');
    expect(toRuntimeSession(sampleSession({ status: 'cancelled' })).result).toBe('已取消');
  });

  it('无 workflow_id → 动作仅任务; 无 task_id → 会话兜底', () => {
    expect(toRuntimeSession(sampleSession({ workflow_id: undefined })).action).toBe('执行任务 TASK-a1');
    expect(
      toRuntimeSession(sampleSession({ task_id: undefined, workflow_id: undefined })).action,
    ).toBe('Agent 执行会话');
  });

  it('降级: null 输入 → 空活动条目不崩溃', () => {
    const activity = toRuntimeSession(null);
    expect(activity).toBeDefined();
    expect(activity.result).toBe('');
    expect(activity.action).toBe('Agent 执行会话');
  });
});
