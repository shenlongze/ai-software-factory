/**
 * shell/RunStatusBar.tsx — S10-007 阶段三: 项目工作台「开始开发」入口 + run 状态条。
 *
 * 数据源 (真实 API, 无 mock fallback — 诚实失败):
 * - GET  /api/projects/{id}/run-status → {status: none|running|completed|failed, runs[]}
 * - POST /api/projects/{id}/start      → 启动真实 Agent 执行链 (503 = key 缺失)
 *
 * 交互状态机:
 * - run-status none → 大按钮「🚀 开始开发」(data-testid ws-start-dev)
 * - 点击 → POST start → 轮询 run-status (3s) → 状态条:
 *   待启动 (pending / 刚启动尚未见 run) / 开发中 (阶段进度 X/6) /
 *   完成 (totals 统计) / 失败 (原因 + 重试)
 * - POST start 503 → key 缺失引导 (见 .env.example / ./factory config)
 *
 * 轮询: setTimeout 链 (每轮完成再排下一轮, 不重叠); 终态 (completed/failed)
 * 自动停止; 查询失败停止并给出重试 (避免错误风暴)。
 */

import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import { Button } from '../components/ds';
import type { RunInfo, RunStatusResponse } from '../models/types';

/** run-status 轮询间隔 (3s; 导出供测试引用, 不硬编码魔法数字)。 */
export const RUN_STATUS_POLL_MS = 3000;

/** 流水线固定 6 阶段 (产品 → UX/UI → 架构 → 开发 → 测试 → 发布; 与 workflow_runner 链一致)。 */
export const RUN_TOTAL_STAGES = 6;

/** 阶段显示名 (进度文件字段宽松读取: stage → role → workflow 兜底)。 */
export function runStageLabel(stage: RunInfo['stages'][number]): string {
  return stage.stage ?? stage.role ?? stage.workflow ?? '阶段';
}

/** 最近 run 的进度计数 (完成/失败; 总阶段固定 6)。 */
export function countRunProgress(
  runs: RunInfo[],
): { completed: number; failed: number; total: number } {
  const latest = runs[0];
  if (latest == null) return { completed: 0, failed: 0, total: RUN_TOTAL_STAGES };
  const completed = latest.stages.filter(
    (stage) => (stage.status ?? '').toUpperCase() === 'COMPLETED',
  ).length;
  const failed = latest.stages.filter(
    (stage) => (stage.status ?? '').toUpperCase() === 'FAILED',
  ).length;
  return { completed, failed, total: RUN_TOTAL_STAGES };
}

/** totals 数值字段 (宽松读取: 数字 → 原值; 其余 → null)。 */
function totalNumber(totals: Record<string, unknown>, key: string): number | null {
  const value = totals[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function RunStatusBar({ projectId }: { projectId: string }): JSX.Element {
  // 最近一次 run-status 查询结果 (null = 尚未成功查询)
  const [run, setRun] = useState<RunStatusResponse | null>(null);
  // run-status 查询错误 (初始/轮询; 终态后不轮询)
  const [queryError, setQueryError] = useState<string | null>(null);
  // 轮询开关 (true → 持续轮询; 终态/失败后关闭)
  const [polling, setPolling] = useState(true);
  // 查询重试令牌 (错误态点重试 → 重新拉取)
  const [retryToken, setRetryToken] = useState(0);
  // POST start 进行中
  const [starting, setStarting] = useState(false);
  // POST start 错误 (503 = key 缺失引导)
  const [startError, setStartError] = useState<string | null>(null);
  // 本地已成功发起 start (run-status 尚未反映 running 时显示「待启动」)
  const [startedLocal, setStartedLocal] = useState(false);

  // run-status 轮询 (setTimeout 链; 终态/错误自动停止)
  useEffect(() => {
    if (!polling) return undefined;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async (): Promise<void> => {
      try {
        const data = await api.runStatus(projectId);
        if (cancelled) return;
        setRun(data);
        setQueryError(null);
        if (data.status === 'completed' || data.status === 'failed') {
          setPolling(false);
          return;
        }
        timer = window.setTimeout(() => void poll(), RUN_STATUS_POLL_MS);
      } catch (err) {
        if (cancelled) return;
        setQueryError(err instanceof Error ? err.message : String(err));
        setPolling(false); // 查询失败停止轮询 (错误风暴防御), 展示重试
      }
    };
    void poll();
    return () => {
      cancelled = true;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [projectId, polling, retryToken]);

  /** 点击「开始开发」→ POST start → 开始轮询进度。 */
  const handleStart = async (): Promise<void> => {
    setStarting(true);
    setStartError(null);
    try {
      await api.startWorkflow(projectId);
      setStartedLocal(true);
      // 本地先进入「待启动」— 后端 _RUNNING 生效后 run-status 即返回 running
      setRun((prev) => ({
        project_id: projectId,
        status: 'pending',
        current_run_id: prev?.current_run_id ?? null,
        runs: prev?.runs ?? [],
        updated_at: prev?.updated_at ?? null,
      }));
      setPolling(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setStartError('未配置 LLM API Key — 请见项目根目录 .env.example 或运行 ./factory config');
      } else {
        setStartError(err instanceof Error ? err.message : '启动失败, 请稍后重试');
      }
    } finally {
      setStarting(false);
    }
  };

  // ------------------------------------------------------------ 状态分支

  // 1) POST start 失败 (503 key 缺失 → 引导文案)
  if (startError != null) {
    return (
      <div className="ws-run ws-run-warn" data-testid="ws-start-error">
        <span className="ws-run-icon" aria-hidden="true">
          ⚠️
        </span>
        <div className="ws-run-body">
          <p className="ws-run-title">无法启动 AI 开发</p>
          <p className="ws-run-desc">{startError}</p>
        </div>
      </div>
    );
  }

  // 2) 查询失败且无已知状态 → 错误条 + 重试查询
  if (queryError != null && run == null) {
    return (
      <div className="ws-run ws-run-warn" data-testid="ws-run-query-error">
        <span className="ws-run-icon" aria-hidden="true">
          ⚠️
        </span>
        <div className="ws-run-body">
          <p className="ws-run-title">无法获取运行状态</p>
          <p className="ws-run-desc">{queryError}</p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            setQueryError(null);
            setPolling(true);
            setRetryToken((token) => token + 1);
          }}
          data-testid="ws-run-query-retry"
        >
          重试
        </Button>
      </div>
    );
  }

  // 3) 从未启动 (run-status none) → 大按钮「开始开发」
  const effectiveStatus = run?.status ?? 'none';
  if (effectiveStatus === 'none' && !startedLocal) {
    return (
      <div className="ws-run-none" data-testid="ws-run-none">
        <Button
          variant="primary"
          size="md"
          onClick={() => void handleStart()}
          disabled={starting}
          loading={starting}
          data-testid="ws-start-dev"
        >
          {starting ? '启动中…' : '🚀 开始开发'}
        </Button>
        <p className="ws-run-none-hint">
          点击后 AI 团队 (产品 → UX/UI → 架构 → 开发 → 测试 → 发布) 将为你自动开发
        </p>
      </div>
    );
  }

  // 4) 待启动 (刚发起 / 后端 pending, 尚未出现运行进度)
  const isPending = startedLocal && effectiveStatus === 'none';
  if (effectiveStatus === 'pending' || isPending) {
    return (
      <div className="ws-run ws-run-pending" data-status="pending" data-testid="ws-run-status">
        <span className="ws-run-icon" aria-hidden="true">
          ⏳
        </span>
        <div className="ws-run-body">
          <p className="ws-run-title">AI 团队启动中…</p>
          <p className="ws-run-desc">正在准备 6 阶段开发流水线, 事件将实时出现在下方 Timeline</p>
        </div>
      </div>
    );
  }

  // 5) 开发中 (running) → 阶段进度条
  if (effectiveStatus === 'running') {
    const { completed, failed, total } = countRunProgress(run?.runs ?? []);
    const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
    const doneStages = run?.runs[0]?.stages ?? [];
    return (
      <div className="ws-run ws-run-running" data-status="running" data-testid="ws-run-status">
        <span className="ws-run-icon" aria-hidden="true">
          🤖
        </span>
        <div className="ws-run-body">
          <p className="ws-run-title">
            开发中 · 已完成 {completed}/{total} 阶段
            {failed > 0 ? ` · ${failed} 个阶段失败` : ''}
          </p>
          <div className="ws-run-track" role="progressbar" aria-valuenow={completed} aria-valuemin={0} aria-valuemax={total}>
            <div className="ws-run-fill" style={{ width: `${percent}%` }} />
          </div>
          {doneStages.length > 0 ? (
            <div className="ws-run-stages" data-testid="ws-run-stages">
              {doneStages.map((stage) => (
                <span key={`${stage.workflow ?? ''}-${stage.stage ?? ''}-${runStageLabel(stage)}`} className="ws-run-stage">
                  {runStageLabel(stage)}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  // 6) 完成 (completed) → 统计摘要
  if (effectiveStatus === 'completed') {
    const { completed } = countRunProgress(run?.runs ?? []);
    const totals = run?.runs[0]?.totals ?? {};
    const calls = totalNumber(totals, 'calls');
    const tokens = totalNumber(totals, 'total_tokens');
    const cost = totalNumber(totals, 'cost_usd_est');
    const meta = [
      calls != null ? `调用 ${calls} 次` : null,
      tokens != null ? `tokens ${tokens}` : null,
      cost != null ? `成本 $${cost}` : null,
    ]
      .filter((part): part is string => part != null)
      .join(' · ');
    return (
      <div className="ws-run ws-run-success" data-status="completed" data-testid="ws-run-status">
        <span className="ws-run-icon" aria-hidden="true">
          🎉
        </span>
        <div className="ws-run-body">
          <p className="ws-run-title">开发完成 ({completed}/{RUN_TOTAL_STAGES} 阶段)</p>
          {meta.length > 0 ? <p className="ws-run-desc">{meta}</p> : null}
          <p className="ws-run-desc">产物已在右侧 Artifact 面板与下方 Timeline 中, 可继续输入新需求迭代</p>
        </div>
      </div>
    );
  }

  // 7) 失败 (failed) → 原因 + 重试
  const latest = run?.runs[0];
  const reason =
    latest?.errors.find((error) => error.message != null && error.message.length > 0)?.message ??
    null;
  return (
    <div className="ws-run ws-run-failed" data-status="failed" data-testid="ws-run-status">
      <span className="ws-run-icon" aria-hidden="true">
        ⛔
      </span>
      <div className="ws-run-body">
        <p className="ws-run-title">开发失败</p>
        <p className="ws-run-desc" data-testid="ws-run-reason">
          {reason != null ? reason : '详细原因见下方 Timeline 错误事件'}
        </p>
      </div>
      <Button
        variant="primary"
        size="sm"
        onClick={() => void handleStart()}
        disabled={starting}
        loading={starting}
        data-testid="ws-run-retry"
      >
        {starting ? '启动中…' : '重试'}
      </Button>
    </div>
  );
}
