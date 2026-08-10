/**
 * design/tokens.ts — S10-000 Design System 设计令牌。
 *
 * 同源: AI 自产 uxui.json design_tokens (primary #007ACC / success #4CAF50 /
 * error #F44336 / warning #FF9800 / 亮暗双主题)。
 *
 * 本文件是 TS 侧令牌 (组件逻辑/颜色映射/格式化用); 实际样式消费
 * design.css 的 CSS 变量 (--ds-*)。两边同值, 改一处必须同步另一处。
 */

// ------------------------------------------------------------------ 主题
export type ThemeName = 'light' | 'dark';

export interface ThemeColors {
  bg: string;
  surface: string;
  surface2: string;
  border: string;
  text: string;
  textSecondary: string;
  primary: string;
  primaryHover: string;
  success: string;
  error: string;
  warning: string;
  info: string;
  overlay: string;
}

/** 亮色主题 (默认)。 */
export const lightTheme: ThemeColors = {
  bg: '#FFFFFF',
  surface: '#F5F5F5',
  surface2: '#EBEBEB',
  border: '#E0E0E0',
  text: '#1E1E1E',
  textSecondary: '#757575',
  primary: '#007ACC',
  primaryHover: '#0062A3',
  success: '#4CAF50',
  error: '#F44336',
  warning: '#FF9800',
  info: '#007ACC',
  overlay: 'rgba(0, 0, 0, 0.5)',
};

/** 暗色主题。 */
export const darkTheme: ThemeColors = {
  bg: '#1E1E1E',
  surface: '#252526',
  surface2: '#2D2D30',
  border: '#3E3E3E',
  text: '#D4D4D4',
  textSecondary: '#999999',
  primary: '#007ACC',
  primaryHover: '#1A8AD4',
  success: '#4CAF50',
  error: '#F44336',
  warning: '#FF9800',
  info: '#007ACC',
  overlay: 'rgba(0, 0, 0, 0.55)',
};

export const themes: Record<ThemeName, ThemeColors> = {
  light: lightTheme,
  dark: darkTheme,
};

// ------------------------------------------------------------------ 间距 / 圆角 / 字体 / 阴影
export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48 } as const;
export const radius = { sm: 4, md: 8, lg: 12, full: 999 } as const;

export const fontFamily =
  "system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif";
export const monoFamily = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
export const fontSizes = { xs: 11, sm: 12, body: 14, md: 16, lg: 18, title: 24 } as const;
export const fontWeights = { regular: 400, medium: 500, bold: 700 } as const;
export const shadows = {
  light: '0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.08)',
  dark: '0 2px 8px rgba(0, 0, 0, 0.45)',
} as const;

// ------------------------------------------------------------------ 阶段状态 (8 状态)
export type StageStatus =
  | 'pending'
  | 'running'
  | 'waiting_review'
  | 'approved'
  | 'completed'
  | 'failed'
  | 'rejected'
  | 'rework';

/** 状态中文标签。 */
export const STATUS_LABELS: Record<StageStatus, string> = {
  pending: '待执行',
  running: '运行中',
  waiting_review: '待审核',
  approved: '已批准',
  completed: '已完成',
  failed: '失败',
  rejected: '已驳回',
  rework: '返工中',
};

// S10-003: api-data-model §1 Stage 状态机同义状态 (WAITING/RUNNING/SUCCESS/FAILED/
// APPROVAL_REQUIRED — 大写由组件层 toLowerCase 归一; 标签补齐中文, tone 已覆盖)。
export const STAGE_STATUS_LABELS: Record<string, string> = {
  waiting: '等待中',
  success: '成功',
  approval_required: '待审批',
};

/** 状态色调 (状态 → 语义色; 未知回退 neutral)。 */
export type StatusTone = 'neutral' | 'running' | 'success' | 'failed' | 'warning';

export function statusTone(status: string): StatusTone {
  switch (status.toLowerCase()) {
    case 'pending':
    case 'waiting':
      return 'neutral';
    case 'running':
    case 'in_progress':
    case 'active':
      return 'running';
    case 'waiting_review':
    case 'approval_required':
    case 'awaiting_approval':
    case 'review':
    case 'rework':
      return 'warning';
    case 'approved':
    case 'completed':
    case 'success':
    case 'done':
    case 'passed':
      return 'success';
    case 'failed':
    case 'rejected':
    case 'error':
    case 'failure':
      return 'failed';
    default:
      return 'neutral';
  }
}

/** 状态中文显示名 (未知状态原样返回; S10-003 兼容 Stage 状态机同义状态)。 */
export function statusLabel(status: string): string {
  const key = status.toLowerCase();
  return STATUS_LABELS[key as StageStatus] ?? STAGE_STATUS_LABELS[key] ?? status;
}

// ------------------------------------------------------------------ Agent (6)
export type AgentRole = 'pm' | 'ux_ui' | 'architecture' | 'developer' | 'tester' | 'release';

export const AGENT_ROLES: readonly AgentRole[] = [
  'pm',
  'ux_ui',
  'architecture',
  'developer',
  'tester',
  'release',
];

export interface AgentMeta {
  label: string;
  color: string;
  icon: string;
}

export const AGENT_META: Record<AgentRole, AgentMeta> = {
  pm: { label: '产品经理', color: '#007ACC', icon: '📋' },
  ux_ui: { label: 'UX/UI 设计师', color: '#9C27B0', icon: '🎨' },
  architecture: { label: '架构师', color: '#FF9800', icon: '🏗️' },
  developer: { label: '开发工程师', color: '#4CAF50', icon: '💻' },
  tester: { label: '测试工程师', color: '#E91E63', icon: '🧪' },
  release: { label: '发布工程师', color: '#607D8B', icon: '🚀' },
};

/** role 键 → 元信息 (未知角色回退中性灰 + 🤖)。 */
export function agentMeta(role: string): AgentMeta {
  return AGENT_META[role.toLowerCase() as AgentRole] ?? { label: role, color: '#9E9E9E', icon: '🤖' };
}

// ------------------------------------------------------------------ 格式化
/** 秒 → 人类可读耗时 (79s / 1m 20s / 2h 5m; 空值 → —)。 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds) || seconds < 0) return '—';
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rest = s % 60;
  if (m < 60) return rest > 0 ? `${m}m ${rest}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

/** 成本 → $0.0038 (尾零裁剪; 空值 → —)。 */
export function formatCost(cost: number | null | undefined): string {
  if (cost == null || Number.isNaN(cost)) return '—';
  const fixed = cost.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
  return `$${fixed}`;
}
