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

  it('兼容: ExecuteResponse 形态 (task_id/agent_id/status) → RuntimeActivity', () => {
    // S10-016 Task 002: POST /api/runtime/execute 响应 → 复用 toRuntimeSession 映射
    const activity = toRuntimeSession({
      session_id: 'SES-EXEC-1',
      agent_id: 'developer-1',
      task_id: 'TASK-b2',
      workflow_id: 'WF-2',
      status: 'success',
      created_at: '2026-08-12T14:00:00Z',
      started_at: '2026-08-12T14:00:05Z',
      finished_at: '2026-08-12T14:00:30Z',
      events: [],
    });
    expect(activity.action).toBe('执行任务 TASK-b2 (WF-2)');
    expect(activity.result).toBe('成功');
    expect(activity.eventType).toBe('runtime_session.success');
  });

  it('S10-017: execute 响应含 execution_steps → 类型兼容 (步骤结构保留)', () => {
    // ExecutionStep 结构来自后端 AgentExecutionLoop (RECEIVE_TASK→ANALYZE→DECISION→FINAL)
    const steps = [
      { step_number: 1, step_type: 'RECEIVE_TASK', status: 'completed' },
      { step_number: 2, step_type: 'ANALYZE', status: 'completed' },
      { step_number: 3, step_type: 'DECISION', status: 'completed' },
      { step_number: 4, step_type: 'FINAL', status: 'completed' },
    ] as const;
    expect(steps).toHaveLength(4);
    expect(steps.map((s) => s.step_type)).toEqual([
      'RECEIVE_TASK',
      'ANALYZE',
      'DECISION',
      'FINAL',
    ]);
    expect(steps.every((s) => s.status === 'completed')).toBe(true);
  });

  it('S10-018: tool_* 事件人话映射 (toRuntimeActivity)', async () => {
    const { toRuntimeActivity } = await import('../api/domain');
    const events = [
      { event_id: 'e1', session_id: 's1', type: 'tool_requested', message: '请求工具', status: 'OK', created_at: '2026-08-12T15:00:00Z' },
      { event_id: 'e2', session_id: 's1', type: 'tool_completed', message: '工具完成', status: 'OK', created_at: '2026-08-12T15:00:01Z' },
      { event_id: 'e3', session_id: 's1', type: 'tool_failed', message: '工具失败', status: 'FAIL', created_at: '2026-08-12T15:00:02Z' },
    ] as unknown as Parameters<typeof toRuntimeActivity>[0];
    const acts = toRuntimeActivity(events);
    // S10-015 §5.3: message 优先于映射 — 事件用 message 作为 action
    expect(acts[0].action).toBe('请求工具');
    expect(acts[1].action).toBe('工具完成');
    expect(acts[2].action).toBe('工具失败');
  });
});
