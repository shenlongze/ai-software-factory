/**
 * useRuntimeProjection — S47-C1 实时运行投影 (Human Control Plane)。
 *
 * 设计 (纯 Projection, 非 truth):
 * - 首帧 = 真实 snapshot (projectRuns + workflow/timeline 由页面拉)
 * - SSE 增量 (subscribeEvents) → 投影 recentEvents/currentStage/errors
 * - lastSeq 记录 (data.seq) → reconnect since_seq 续推 (不重不漏)
 * - projectId 变化 → 关闭旧订阅 → 新订阅 (backend project_id 过滤,
 *   前端 filter 仅防御)
 * - connectionState = UI transport 状态 (connecting/connected/
 *   reconnecting/disconnected/mock) — 非生产事实
 * - 不生成 run/stage/status; 不制造 progress; 不 localStorage 生产事实
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { runtimeClient } from '../api/runtimeClient';
import type { RuntimeEventName } from '../models/types';

export type ConnectionState =
  | 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'mock';

export interface RuntimeProjectionEvent {
  name: string;
  data: Record<string, unknown>;
  seq: number;
  at: string;
}

export interface RuntimeProjection {
  /** transport 状态 (非生产状态) */
  connection: ConnectionState;
  /** 最近事件 (按 seq 升序; 上限保留) */
  recentEvents: RuntimeProjectionEvent[];
  /** 从事件派生的当前 stage (stage.started 未 completed) */
  currentStage: string | null;
  /** 最近一条 error 语义事件 (org.workflow.failed / org.artifact.failed) */
  lastError: string | null;
  /** 最近阶段 (stage.completed name, 含 repair/retest 阶段名) */
  lastStageCompleted: string | null;
  lastSeq: number;
  isMock: boolean;
}

export const PROJECTION_EVENT_LIMIT = 100;

const EMPTY: RuntimeProjection = {
  connection: 'connecting',
  recentEvents: [],
  currentStage: null,
  lastError: null,
  lastStageCompleted: null,
  lastSeq: 0,
  isMock: false,
};

function eventSeq(data: Record<string, unknown>): number {
  const s = Number(data.seq);
  return Number.isFinite(s) && s > 0 ? s : 0;
}

export function useRuntimeProjection(projectId: string): RuntimeProjection {
  const [proj, setProj] = useState<RuntimeProjection>(EMPTY);
  const lastSeqRef = useRef(0);
  const stateRef = useRef(EMPTY);
  const closedRef = useRef(false);

  const apply = useCallback((updater: (p: RuntimeProjection) => RuntimeProjection) => {
    setProj((prev) => {
      const next = updater(prev);
      stateRef.current = next;
      return next;
    });
  }, []);

  useEffect(() => {
    closedRef.current = false;
    lastSeqRef.current = 0;
    apply(() => ({ ...EMPTY, connection: 'connecting' }));
    const sub = runtimeClient.subscribeEvents(
      projectId,
      {
        onOpen: () => apply((p) => ({ ...p, connection: 'connected' })),
        onError: () => apply((p) => ({
          ...p,
          connection: p.connection === 'connected' ? 'reconnecting' : 'connecting',
        })),
        onMock: () => apply((p) => ({ ...p, connection: 'mock', isMock: true })),
        onEvent: (name: RuntimeEventName, data: Record<string, unknown>) => {
          if (closedRef.current) return;
          const seq = eventSeq(data);
          if (seq > lastSeqRef.current) lastSeqRef.current = seq;
          apply((p) => {
            const ev: RuntimeProjectionEvent = {
              name, data, seq, at: new Date().toISOString(),
            };
            const recentEvents = [...p.recentEvents, ev]
              .slice(-PROJECTION_EVENT_LIMIT);
            let currentStage = p.currentStage;
            let lastStageCompleted = p.lastStageCompleted;
            if (name === 'stage.started') {
              currentStage = String(data.name ?? data.stage_id ?? '');
            } else if (name === 'stage.completed') {
              if (currentStage && data.name) currentStage = null;
              lastStageCompleted = String(data.name ?? '');
            }
            // error 语义: 事件名 'error' 与 EventSource 保留名冲突 (既有
            // 限制, SSE 侧映射 org.*.failed → error), 故以 payload 兜底判断
            // (forward-compatible: 未知事件名只记录不崩流)。
            const isError = String(data.type ?? '').includes('failed')
              || (String(data.reason ?? '') !== ''
                && String(data.reason ?? '') !== 'event store unavailable');
            return {
              ...p,
              recentEvents,
              currentStage,
              lastStageCompleted,
              lastError: isError
                ? String(data.reason ?? data.type ?? name)
                : p.lastError,
              lastSeq: seq > p.lastSeq ? seq : p.lastSeq,
              connection: 'connected',
            };
          });
        },
      },
      lastSeqRef.current,
    );
    return () => {
      closedRef.current = true;
      sub.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  return proj;
}
