/**
 * components/af/afLabels.ts — AI Factory 人话标签/格式化工具 (S10-014 Task 002b)。
 *
 * 后端 JSON 状态值 → 前端人话标签 (§6.3 降级: 未知值原样展示, 缺失 → 默认)。
 * 与 models/domain.ts 的 DomainStatus 语义对齐 (完成绿/执行中蓝/待办灰/阻塞紫/失败红/待审核橙)。
 */

import type { ProjectSummary } from '../../models/types';

/** 生命周期阶段人话标签 (lifecycle_stage → 标签; 含常见后端值)。 */
export const LIFECYCLE_LABELS: Record<string, string> = {
  draft: '草稿',
  discovery: '探索',
  definition: '定义',
  development: '开发',
  release: '发布',
  maintenance: '维护',
  build: '构建',
  idea: '想法',
  active: '活跃',
  completed: '已完成',
  paused: '暂停',
  archived: '已归档',
};

/** 通用状态人话标签 (project.status / lifecycle_status / stage 状态)。 */
export const STATUS_LABELS: Record<string, string> = {
  idea: '想法',
  active: '活跃',
  completed: '已完成',
  done: '已完成',
  success: '已完成',
  failed: '失败',
  paused: '暂停',
  archived: '已归档',
  running: '执行中',
  pending: '待办',
  waiting: '等待',
  blocked: '阻塞',
  review: '待审核',
};

/** workflow 状态人话标签 (workflow_status; null → 未启动)。 */
export const WORKFLOW_LABELS: Record<string, string> = {
  active: '执行中',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  pending: '待开始',
  waiting: '待开始',
};

/**
 * 项目生命周期标签: lifecycle_stage → 人话; 缺失 → status 人话; 都缺 → '—'。
 * (任务验收: "lifecycle_stage→人话标签, 缺失→status")
 */
export function lifecycleLabel(
  p: Pick<ProjectSummary, 'lifecycle_stage' | 'status'>,
): string {
  if (p.lifecycle_stage != null && p.lifecycle_stage.length > 0) {
    return LIFECYCLE_LABELS[p.lifecycle_stage] ?? p.lifecycle_stage;
  }
  if (p.status != null && p.status.length > 0) {
    return STATUS_LABELS[p.status] ?? p.status;
  }
  return '—';
}

/** 通用状态人话标签 (未知值原样, 缺失 → '—')。 */
export function statusLabel(status: string | null | undefined): string {
  if (status == null || status.length === 0) return '—';
  return STATUS_LABELS[status] ?? status;
}

/** workflow 状态人话标签 (缺失 → '未启动')。 */
export function workflowLabel(status: string | null | undefined): string {
  if (status == null || status.length === 0) return '未启动';
  return WORKFLOW_LABELS[status] ?? status;
}

/** stage_counts 芯片数据 (status → 人话; count>0 过滤, 按数量降序)。 */
export function stageCountChips(
  counts: Record<string, number> | undefined | null,
): { label: string; count: number }[] {
  if (counts == null) return [];
  return Object.entries(counts)
    .filter(([, count]) => typeof count === 'number' && count > 0)
    .map(([key, count]) => ({ label: STATUS_LABELS[key] ?? key, count }))
    .sort((a, b) => b.count - a.count);
}

/** ISO 时间 → "YYYY-MM-DD HH:mm" (本地时区; 非法 → 原样返回; 缺失 → '')。 */
export function formatTime(iso: string | null | undefined): string {
  if (iso == null || iso.length === 0) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

/** progress (0..1 小数) → 0..100 整数百分比 (非法/越界 → 夹取)。 */
export function progressPercent(progress: number | null | undefined): number {
  const raw = Number(progress ?? 0);
  if (!Number.isFinite(raw)) return 0;
  return Math.max(0, Math.min(100, Math.round(raw * 100)));
}
