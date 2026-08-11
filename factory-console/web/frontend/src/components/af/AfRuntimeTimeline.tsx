/**
 * components/af/AfRuntimeTimeline.tsx — Runtime Timeline (S10-015 Task 005b)。
 *
 * 依据 (唯一): S10-015-architecture-review §5 (Runtime Adapter) + 用户 Task 005
 * 设计约束 (Runtime Timeline ≠ Log Viewer — 展示 8 项: 当前 Agent / 当前 Task /
 * Workflow Stage / 开始时间 / 持续时间 / 最近事件 / 下一步 / 阻塞原因;
 * 禁 mock / 静态 / 前端自行生成状态)。
 *
 * 当前执行卡 (全部字段来自真实 workflow/timeline, 无前端生成):
 *   ① 当前 Agent   — failed/running 阶段 agentName 人话 (ROLE_LABELS 映射)
 *   ② Workflow Stage — 当前阶段名 (人话)
 *   ③ 状态         — AfStatusBadge (FAILED/RUNNING/…)
 *   ④ 开始时间     — startedAt (formatTime)
 *   ⑤ 持续时间     — started_at → completed_at / → now (人话 分钟/小时)
 *   ⑥ 最近事件     — 事件流最新一条 (action + result)
 *   ⑦ 失败原因     — failedReason 红色横幅 ("为什么阻塞/失败")
 *   ⑧ 下一步       — 第一个 pending 阶段推导 (人话 Agent + 阶段名)
 * 事件流: 复用 AfTimeline, 倒序 (最新在上)。
 * 空态: 无 workflow + 无 events → AfEmptyState。
 * 纯展示组件: 不 fetch; pipeline/events 由父层传入 (页面数据必须来自真实后端)。
 */

import { toDomainStatus } from '../../api/domain';
import type { DomainStatus, RuntimeActivity, WorkflowPipeline, WorkflowStage } from '../../models/domain';
import { formatTime } from './afLabels';
import { AfEmptyState } from './AfState';
import { AfStatusBadge } from './AfStatusBadge';
import { AfTimeline, type AfTimelineItem } from './AfTimeline';
import './af.css';

export interface AfRuntimeTimelineProps {
  /** 流水线 (domain; 由 toWorkflowPipeline(workflowDetail) 真实转换; 无 → 空态)。 */
  pipeline?: WorkflowPipeline | null;
  /** 运行事件 (domain; 由 toRuntimeActivity(timeline) 真实转换)。 */
  events?: RuntimeActivity[];
  /** 项目名 (透传展示; 可选)。 */
  projectName?: string;
}

/** 当前执行阶段: 按 order 排序后第一个 failed/running 阶段 (无 → undefined, 降级 '—')。 */
function currentRuntimeStage(pipeline: WorkflowPipeline): WorkflowStage | undefined {
  const active = [...pipeline.stages]
    .sort((a, b) => a.order - b.order)
    .find((s) => s.status === 'failed' || s.status === 'running');
  return active;
}

/** 下一步推导: 第一个 pending 阶段 → "等待 {Agent 人话} 开始「{阶段名}」" (无 → undefined)。 */
function nextRuntimeStep(pipeline: WorkflowPipeline): string | undefined {
  const next = [...pipeline.stages]
    .sort((a, b) => a.order - b.order)
    .find((s) => s.status === 'pending');
  if (next == null) return undefined;
  const agent = next.agentName ?? next.roleId;
  if (agent != null && agent.length > 0) {
    return `等待 ${agent} 开始「${next.name}」`;
  }
  return `等待开始「${next.name}」`;
}

/** 持续时间: started_at → completed_at (完成) / → now (进行中); 缺失/非法 → '—'。 */
export function formatRuntimeDuration(
  startedAt: string | undefined,
  completedAt: string | undefined,
  now: number = Date.now(),
): string {
  if (startedAt == null || startedAt.length === 0) return '—';
  const start = new Date(startedAt).getTime();
  if (Number.isNaN(start)) return '—';
  const end =
    completedAt != null && completedAt.length > 0 ? new Date(completedAt).getTime() : now;
  if (Number.isNaN(end)) return '—';
  const mins = Math.max(0, Math.round((end - start) / 60000));
  if (mins < 1) return '不足 1 分钟';
  if (mins < 60) return `${mins} 分钟`;
  const hours = Math.floor(mins / 60);
  const rest = mins % 60;
  return rest > 0 ? `${hours} 小时 ${rest} 分钟` : `${hours} 小时`;
}

/** 事件倒序 (最新在上; 按 time 字典序 — ISO 时间保证时间序; 缺失 time 排最后)。 */
function sortEventsDesc(events: RuntimeActivity[]): RuntimeActivity[] {
  return [...events].sort((a, b) => (b.time ?? '').localeCompare(a.time ?? ''));
}

/** RuntimeActivity → AfTimelineItem (状态点色: result → DomainStatus 语义)。 */
function toTimelineItems(events: RuntimeActivity[]): AfTimelineItem[] {
  return events.map((ev) => ({
    time: ev.time,
    actor: ev.actor,
    action: ev.action,
    result: ev.result,
    status: toDomainStatus(ev.result),
  }));
}

export function AfRuntimeTimeline({
  pipeline,
  events = [],
  projectName,
}: AfRuntimeTimelineProps): JSX.Element {
  const sorted = sortEventsDesc(events);
  const hasWorkflow = pipeline != null && pipeline.stages.length > 0;
  // 空态: 无 workflow (null/无 stages) + 无事件 → AfEmptyState
  if (!hasWorkflow && sorted.length === 0) {
    return (
      <div className="af-runtime-timeline" data-testid="af-runtime-timeline">
        <AfEmptyState
          message="暂无运行活动"
          hint="项目启动工作流后, 将在此展示 AI 正在做什么 (当前 Agent/阶段/失败原因/事件流)"
        />
      </div>
    );
  }

  const workflowStatus: DomainStatus = pipeline?.status ?? 'pending';
  const current = pipeline != null ? currentRuntimeStage(pipeline) : undefined;
  const agent = current?.agentName;
  const stageName = current?.name;
  const started = pipeline?.startedAt != null ? formatTime(pipeline.startedAt) : '';
  const duration = formatRuntimeDuration(pipeline?.startedAt, pipeline?.completedAt);
  const latest = sorted.length > 0 ? sorted[0] : undefined;
  const recent =
    latest != null
      ? latest.result != null && latest.result.length > 0
        ? `${latest.action} · ${latest.result}`
        : latest.action
      : '—';
  const next = pipeline != null ? nextRuntimeStep(pipeline) : undefined;

  return (
    <div className="af-runtime-timeline" data-testid="af-runtime-timeline">
      {projectName != null && projectName.length > 0 ? (
        <h3 className="af-runtime-title" data-testid="af-runtime-title">
          {projectName} · 运行状态
        </h3>
      ) : null}

      {hasWorkflow ? (
        <section className="af-runtime-card" data-testid="af-runtime-card">
          <div className="af-runtime-card-head">
            <span className="af-runtime-card-title">当前执行</span>
            <span className="af-runtime-status" data-testid="af-runtime-status">
              <AfStatusBadge status={workflowStatus} />
            </span>
          </div>
          <div className="af-runtime-grid">
            <div className="af-runtime-field">
              <span className="af-runtime-label">当前 Agent</span>
              <span className="af-runtime-value" data-testid="af-runtime-agent">
                {agent != null && agent.length > 0 ? `${agent} Agent` : '—'}
              </span>
            </div>
            <div className="af-runtime-field">
              <span className="af-runtime-label">Workflow Stage</span>
              <span className="af-runtime-value" data-testid="af-runtime-stage">
                {stageName ?? '—'}
              </span>
            </div>
            <div className="af-runtime-field">
              <span className="af-runtime-label">开始时间</span>
              <span className="af-runtime-value" data-testid="af-runtime-started">
                {started.length > 0 ? started : '—'}
              </span>
            </div>
            <div className="af-runtime-field">
              <span className="af-runtime-label">持续时间</span>
              <span className="af-runtime-value" data-testid="af-runtime-duration">
                {duration}
              </span>
            </div>
            <div className="af-runtime-field af-runtime-field--wide">
              <span className="af-runtime-label">最近事件</span>
              <span className="af-runtime-value" data-testid="af-runtime-recent">
                {recent}
              </span>
            </div>
            <div className="af-runtime-field af-runtime-field--wide">
              <span className="af-runtime-label">下一步</span>
              <span className="af-runtime-value" data-testid="af-runtime-next">
                {next ?? '—'}
              </span>
            </div>
          </div>
          {pipeline?.failedReason != null && pipeline.failedReason.length > 0 ? (
            <div className="af-runtime-failed" data-testid="af-runtime-failed" role="alert">
              <span className="af-runtime-failed-icon" aria-hidden="true">
                ✕
              </span>
              <div className="af-runtime-failed-body">
                <div className="af-runtime-failed-title">失败原因 (为什么阻塞/失败)</div>
                <div className="af-runtime-failed-reason">{pipeline.failedReason}</div>
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="af-runtime-events" data-testid="af-runtime-events">
        <h4 className="af-runtime-section-title">
          事件流 <span className="af-runtime-section-sub">Event Timeline</span>
        </h4>
        <AfTimeline items={toTimelineItems(sorted)} />
      </section>
    </div>
  );
}
