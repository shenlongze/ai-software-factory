/**
 * components/af/AfTaskDetailPanel.tsx — Task Detail 统一面板 (S10-015 Task 005b + W-3)。
 *
 * 依据 (唯一): S10-015-architecture-review §6 (Task Detail 数据流) + 用户 Task 005
 * 设计约束 (TaskDetail 全字段: Epic/Feature/Story 关联 — 为什么存在 / 负责人 / Agent /
 * 优先级 / 依赖 / 历史; 缺失降级, 不崩溃)。
 *
 * W-3 (v1.1.142, Founder: todo 编辑/优先级/归档/审计溯源):
 *   - 操作区 (仅 onUpdate 提供时渲染): 状态流转 (开始/完成/重新开始 — 按受控状态机
 *     合法路径序列化 PATCH) + 优先级选择 + 标题/描述内联编辑; 保存后页面 PATCH + 刷新
 *   - 审计溯源增强: 展示 exec_ref / exec_result (方案A 执行绑定, 若有)
 *   - statusPathTo: 受控状态机 (org.management TASK_TRANSITIONS) 合法最短路径
 *     (todo→[ready,in_progress] / in_progress→[review,done] / blocked→[in_progress] …)
 *
 * 展示 (Context Panel 基础, Task 006 树节点点击集成):
 *   - 标题 + 状态 (AfStatusBadge)
 *   - 所属: Epic → Feature → Story (为什么存在; 部分缺失 → 显示已有部分; 全缺 → 不渲染)
 *   - 字段: 负责人 / Agent / 优先级 / 依赖 (多值连接) / 下一步 / 开始时间 / 执行绑定
 *   - 历史: 复用 AfTimeline (time/actor/action/result)
 * 降级 (§6.3): 缺失字段 → '—' 或整体不渲染, 不崩溃。
 */

import { useState } from 'react';
import type { Activity, TaskDetail, TaskExecTrace, TaskSessionRef } from '../../models/domain';
import { formatTime } from './afLabels';
import { AfStatusBadge } from './AfStatusBadge';
import { AfTimeline, type AfTimelineItem } from './AfTimeline';
import './af.css';

/** 任务更新载荷 (页面执行 PATCH; statusPath = 状态机合法路径, 逐布 PATCH 后一次刷新)。 */
export interface TaskPatch {
  title?: string;
  description?: string;
  priority?: string;
  status?: string;
  statusPath?: string[];
}

export interface AfTaskDetailPanelProps {
  /** 任务详情 (domain; 由 toTaskDetail 真实转换; 空对象 → 降级展示)。 */
  task: TaskDetail;
  /** 关闭回调 (Context Panel 收起; 缺省 → 不渲染关闭按钮)。 */
  onClose?: () => void;
  /** 保存回调 (页面 PATCH + 刷新; 返回 Promise — 面板据此显示忙/错误)。缺省 → 不渲染操作区。 */
  onUpdate?: (changes: TaskPatch, taskId: string) => Promise<void>;
  /** 关联会话 (T-4 双向追溯): 哪些会话讨论过它; 点击 → onOpenSession。 */
  sessions?: TaskSessionRef[];
  /** 点关联会话 → 打开该会话 (页面接线 ConversationContext)。 */
  onOpenSession?: (sessionId: string) => void;
  /** 执行溯源 (T-9): exec_ref → EXR request → EXS result → 证据包。 */
  execTrace?: TaskExecTrace | null;
}

/**
 * 受控状态机合法路径 (org.management TASK_TRANSITIONS: todo→(ready,blocked);
 * ready→(in_progress,blocked); in_progress→(blocked,review); blocked→(ready,
 * in_progress); review→(in_progress,done); done→()) — W-3 按钮按此逐步 PATCH。
 */
export function statusPathTo(raw: string | undefined, target: 'in_progress' | 'done'): string[] {
  const s = (raw ?? '').toLowerCase();
  if (target === 'in_progress') {
    if (s === 'todo') return ['ready', 'in_progress'];
    if (s === 'ready' || s === 'blocked') return ['in_progress'];
    return [];
  }
  // target === 'done'
  if (s === 'in_progress') return ['review', 'done'];
  if (s === 'review') return ['done'];
  return [];
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

const PRIORITIES = ['P0', 'P1', 'P2', 'P3'] as const;

export function AfTaskDetailPanel({
  task,
  onClose,
  onUpdate,
  sessions,
  onOpenSession,
  execTrace,
}: AfTaskDetailPanelProps): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(task.title ?? '');
  const [editDesc, setEditDesc] = useState(task.description ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const raw = task.rawStatus ?? '';
  const startPath = statusPathTo(raw, 'in_progress');
  const finishPath = statusPathTo(raw, 'done');
  const startLabel = raw === 'blocked' ? '重新开始' : '开始';
  const canStart = startPath.length > 0;
  const canFinish = finishPath.length > 0;

  async function apply(changes: TaskPatch): Promise<void> {
    if (onUpdate == null) return;
    setBusy(true);
    setError('');
    try {
      await onUpdate(changes, task.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleStart(): Promise<void> {
    if (startPath.length > 0) await apply({ statusPath: startPath });
  }

  async function handleFinish(): Promise<void> {
    if (finishPath.length > 0) await apply({ statusPath: finishPath });
  }

  async function handlePriority(priority: string): Promise<void> {
    await apply({ priority });
  }

  async function handleEditSave(): Promise<void> {
    const title = editTitle.trim();
    if (title.length === 0) {
      setError('标题不能为空');
      return;
    }
    await apply({
      ...(title !== task.title ? { title } : {}),
      ...(editDesc !== (task.description ?? '') ? { description: editDesc } : {}),
    });
    if (onUpdate != null) setEditing(false);
  }

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
          <DetailField label="执行绑定" testId="af-task-detail-exec-ref" value={task.execRef} />
          <DetailField label="执行结果" testId="af-task-detail-exec-result" value={task.execResult} />
        </div>

        {onUpdate != null ? (
          <section className="af-task-detail-ops" data-testid="af-task-detail-ops">
            <h4 className="af-task-detail-section-title">操作</h4>
            {!editing ? (
              <div className="af-task-detail-ops-row">
                {canStart ? (
                  <button
                    type="button"
                    className="af-btn"
                    data-testid="af-task-detail-start"
                    disabled={busy}
                    onClick={handleStart}
                  >
                    {startLabel}
                  </button>
                ) : null}
                {canFinish ? (
                  <button
                    type="button"
                    className="af-btn"
                    data-testid="af-task-detail-finish"
                    disabled={busy}
                    onClick={handleFinish}
                  >
                    完成
                  </button>
                ) : null}
                <select
                  className="af-task-detail-priority-select"
                  data-testid="af-task-detail-priority-select"
                  value={task.priority ?? 'P2'}
                  disabled={busy}
                  aria-label="优先级"
                  onChange={(e) => handlePriority(e.target.value)}
                >
                  {PRIORITIES.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="af-btn"
                  data-testid="af-task-detail-edit"
                  disabled={busy}
                  onClick={() => {
                    setEditTitle(task.title ?? '');
                    setEditDesc(task.description ?? '');
                    setEditing(true);
                    setError('');
                  }}
                >
                  编辑
                </button>
              </div>
            ) : (
              <div className="af-task-detail-edit" data-testid="af-task-detail-edit-form">
                <input
                  className="af-input"
                  data-testid="af-task-detail-edit-title"
                  value={editTitle}
                  aria-label="任务标题"
                  onChange={(e) => setEditTitle(e.target.value)}
                />
                <textarea
                  className="af-input af-task-detail-edit-desc"
                  data-testid="af-task-detail-edit-desc"
                  value={editDesc}
                  aria-label="任务描述"
                  rows={3}
                  onChange={(e) => setEditDesc(e.target.value)}
                />
                <div className="af-task-detail-ops-row">
                  <button
                    type="button"
                    className="af-btn"
                    data-testid="af-task-detail-edit-save"
                    disabled={busy}
                    onClick={handleEditSave}
                  >
                    保存
                  </button>
                  <button
                    type="button"
                    className="af-btn"
                    data-testid="af-task-detail-edit-cancel"
                    disabled={busy}
                    onClick={() => setEditing(false)}
                  >
                    取消
                  </button>
                </div>
              </div>
            )}
            {busy ? <span className="af-task-detail-op-status">保存中…</span> : null}
            {error.length > 0 ? (
              <span className="af-task-detail-error" data-testid="af-task-detail-error">
                {error}
              </span>
            ) : null}
          </section>
        ) : null}

        {execTrace != null && (execTrace.request != null || (execTrace.results ?? []).length > 0) ? (
          <section className="af-task-detail-exec" data-testid="af-task-detail-exec">
            <h4 className="af-task-detail-section-title">执行溯源</h4>
            <p className="af-task-detail-sessions-hint">exec_ref → 执行记录 → 证据包 (T-9 绑定完整性)</p>
            {execTrace.exec_ref != null && execTrace.exec_ref.length > 0 ? (
              <div className="af-task-detail-field">
                <span className="af-task-detail-label">exec_ref</span>
                <span className="af-task-detail-value" data-testid="af-task-detail-exec-ref">
                  {execTrace.exec_ref}
                </span>
              </div>
            ) : null}
            {execTrace.request != null ? (
              <div className="af-task-detail-exec-request" data-testid="af-task-detail-exec-request">
                <div className="af-task-detail-field">
                  <span className="af-task-detail-label">执行请求</span>
                  <span className="af-task-detail-value">{execTrace.request.id ?? '—'}</span>
                </div>
                <div className="af-task-detail-field">
                  <span className="af-task-detail-label">目标</span>
                  <span className="af-task-detail-value">{execTrace.request.objective ?? '—'}</span>
                </div>
                {execTrace.request.created_at != null ? (
                  <div className="af-task-detail-field">
                    <span className="af-task-detail-label">发起</span>
                    <span className="af-task-detail-value">{formatTime(execTrace.request.created_at)}</span>
                  </div>
                ) : null}
              </div>
            ) : null}
            {(execTrace.results ?? []).length > 0 ? (
              <ul className="af-task-detail-exec-results" data-testid="af-task-detail-exec-results">
                {(execTrace.results ?? []).map((r) => (
                  <li key={r.result_id ?? ''} className="af-task-detail-exec-result">
                    <span className="af-task-detail-exec-result-id">{r.result_id ?? '—'}</span>
                    <span className={`af-exec-result af-exec-result--${String(r.result ?? '').toLowerCase()}`}>
                      {r.result ?? '—'}
                    </span>
                    {r.error != null && r.error.length > 0 ? (
                      <span className="af-task-detail-exec-error">{String(r.error).slice(0, 120)}</span>
                    ) : null}
                    {r.timestamp != null ? (
                      <span className="af-task-detail-session-meta">{formatTime(String(r.timestamp))}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
            {(execTrace.evidence ?? []).length > 0 ? (
              <div className="af-task-detail-exec-evidence" data-testid="af-task-detail-exec-evidence">
                {execTrace.evidence?.map((ev) => (
                  <span key={ev.id} className="af-task-detail-exec-file">
                    📄 {ev.report ?? ev.test ?? ev.id}
                  </span>
                ))}
              </div>
            ) : null}
          </section>
        ) : null}

        {sessions != null && sessions.length > 0 ? (
          <section className="af-task-detail-sessions" data-testid="af-task-detail-sessions">
            <h4 className="af-task-detail-section-title">
              关联会话 ({sessions.length})
            </h4>
            <p className="af-task-detail-sessions-hint">哪些会话讨论过这个任务 — 点击打开接续上下文</p>
            <ul className="af-task-detail-sessions-list">
              {sessions.map((sess) => (
                <li key={sess.id}>
                  <button
                    type="button"
                    className="af-task-detail-session"
                    data-testid={`af-task-detail-session-${sess.id}`}
                    title={`打开会话: ${sess.title}`}
                    onClick={() => onOpenSession?.(sess.id)}
                  >
                    <span className="af-task-detail-session-title">💬 {sess.title}</span>
                    <span className="af-task-detail-session-meta">
                      {sess.updated_at != null ? formatTime(sess.updated_at) : ''}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <section className="af-task-detail-history" data-testid="af-task-detail-history">
          <h4 className="af-task-detail-section-title">历史</h4>
          <AfTimeline items={toTimelineItems(task.history)} />
        </section>
      </div>
    </aside>
  );
}
