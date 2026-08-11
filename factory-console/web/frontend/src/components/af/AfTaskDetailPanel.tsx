/**
 * components/af/AfTaskDetailPanel.tsx — Task Detail 统一面板 (S10-015 Task 005b)。
 *
 * 依据 (唯一): S10-015-architecture-review §6 (Task Detail 数据流) + 用户 Task 005
 * 设计约束 (TaskDetail 全字段: Epic/Feature/Story 关联 — 为什么存在 / 负责人 / Agent /
 * 优先级 / 依赖 / 历史; 缺失降级, 不崩溃)。
 *
 * 展示 (Context Panel 基础, Task 006 树节点点击集成):
 *   - 标题 + 状态 (AfStatusBadge)
 *   - 所属: Epic → Feature → Story (为什么存在; 部分缺失 → 显示已有部分; 全缺 → 不渲染)
 *   - 字段: 负责人 / Agent / 优先级 / 依赖 (多值连接) / 下一步 / 开始时间
 *   - 历史: 复用 AfTimeline (time/actor/action/result)
 * 降级 (§6.3): 缺失字段 → '—' 或整体不渲染, 不崩溃。
 * 纯展示组件: 不 fetch; TaskDetail 由父层传入 (来自 toTaskDetail 真实转换)。
 */

import type { Activity, TaskDetail } from '../../models/domain';
import { formatTime } from './afLabels';
import { AfStatusBadge } from './AfStatusBadge';
import { AfTimeline, type AfTimelineItem } from './AfTimeline';
import './af.css';

export interface AfTaskDetailPanelProps {
  /** 任务详情 (domain; 由 toTaskDetail 真实转换; 空对象 → 降级展示)。 */
  task: TaskDetail;
  /** 关闭回调 (Context Panel 收起; 缺省 → 不渲染关闭按钮)。 */
  onClose?: () => void;
}

/** Activity → AfTimelineItem (状态点色: result → DomainStatus 语义)。 */
function toTimelineItems(history: Activity[]): AfTimelineItem[] {
  return history.map((ev) => ({
    time: ev.time,
    actor: ev.actor,
    action: ev.action,
    result: ev.result,
    status: undefined,
  }));
}

/** 单字段行: label + value (缺失 → '—' 降级)。 */
function DetailField({
  label,
  testId,
  value,
}: {
  label: string;
  testId: string;
  value: string | undefined;
}): JSX.Element {
  return (
    <div className="af-task-detail-field">
      <span className="af-task-detail-label">{label}</span>
      <span className="af-task-detail-value" data-testid={testId}>
        {value != null && value.length > 0 ? value : '—'}
      </span>
    </div>
  );
}

export function AfTaskDetailPanel({ task, onClose }: AfTaskDetailPanelProps): JSX.Element {
  const belong = [task.epicName, task.featureName, task.storyName]
    .filter((name): name is string => name != null && name.length > 0)
    .join(' → ');
  const dependency =
    Array.isArray(task.dependency) && task.dependency.length > 0
      ? task.dependency.join(', ')
      : undefined;

  return (
    <aside className="af-task-detail-panel" data-testid="af-task-detail-panel">
      <header className="af-task-detail-head">
        <h3 className="af-task-detail-title" data-testid="af-task-detail-title">
          {task.title != null && task.title.length > 0 ? task.title : '未命名任务'}
        </h3>
        {onClose != null ? (
          <button
            type="button"
            className="af-task-detail-close"
            data-testid="af-task-detail-close"
            aria-label="关闭"
            onClick={onClose}
          >
            ✕
          </button>
        ) : null}
      </header>
      <div className="af-task-detail-body">
        <div className="af-task-detail-status">
          <AfStatusBadge status={task.status} label={task.statusLabel} />
        </div>
        {belong.length > 0 ? (
          <p className="af-task-detail-belong" data-testid="af-task-detail-belong">
            所属: {belong}
          </p>
        ) : null}
        <div className="af-task-detail-grid">
          <DetailField label="负责人" testId="af-task-detail-owner" value={task.owner} />
          <DetailField label="Agent" testId="af-task-detail-agent" value={task.agent} />
          <DetailField label="优先级" testId="af-task-detail-priority" value={task.priority} />
          <DetailField label="依赖" testId="af-task-detail-dependency" value={dependency} />
          <DetailField label="下一步" testId="af-task-detail-next" value={task.nextAction} />
          <DetailField
            label="开始时间"
            testId="af-task-detail-started"
            value={task.startedAt != null ? formatTime(task.startedAt) : undefined}
          />
        </div>
        <section className="af-task-detail-history" data-testid="af-task-detail-history">
          <h4 className="af-task-detail-section-title">历史</h4>
          <AfTimeline items={toTimelineItems(task.history)} />
        </section>
      </div>
    </aside>
  );
}
