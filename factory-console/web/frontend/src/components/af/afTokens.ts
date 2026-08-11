/**
 * components/af/afTokens.ts — AI Factory Design Tokens (AI OS 深色主题, S10-014 Task 003)。
 *
 * 依据 (唯一): S10-014-plan §4.2 + AF-UI-Architecture §9.2/9.3 (已审核通过)。
 * 独立于 console 的 src/design/tokens.ts (Human Console Apple 风) — 不破坏现有 console。
 *
 * 双用设计: 同一份值导出为 TS 常量 (组件逻辑/测试) + CSS 变量 (af.css :root 消费,
 * 与下方 cssVars 保持同步; TS 侧由测试锁定, CSS 侧由视觉验证)。
 */

import type { DomainStatus } from '../../models/domain';

// ---------------------------------------------------------------- 颜色板 (§9.2)
export const colors = {
  bg: '#0F1115', // 深空背景
  panel: '#161A22', // 面板 (侧栏/头部)
  card: '#1D232E', // 卡片
  primary: '#4C8DFF', // 科技蓝 (动作/链接/焦点/执行中)
  success: '#22C55E', // 青绿 (成功/完成)
  warning: '#F59E0B', // 橙 (警示/待审核)
  danger: '#EF4444', // 红 (失败/错误)
  blocked: '#8B5CF6', // 紫 (阻塞/依赖)
  neutral: '#9CA3AF', // 灰 (待办/禁用/中性)
  border: '#2A3140', // 边框
} as const;

// ------------------------------------------------------- 状态色语义 (6 态, §4.2)
/** 6 态语义色: 完成=绿 / 执行中=蓝 / 待办=灰 / 阻塞=紫 / 失败=红 / 待审核=橙。 */
export const STATUS_COLORS: Record<DomainStatus, string> = {
  completed: colors.success,
  running: colors.primary,
  pending: colors.neutral,
  blocked: colors.blocked,
  failed: colors.danger,
  review: colors.warning,
};

/** 状态 → 语义色 (未知/缺失 → 中性灰降级, §6.3)。 */
export function statusColor(status: string | null | undefined): string {
  if (status == null) return colors.neutral;
  const key = status.toLowerCase();
  return (STATUS_COLORS as Record<string, string>)[key] ?? colors.neutral;
}

// ---------------------------------------------------------------- 其他令牌 (§9.3)
/** 间距 (8pt 网格: 4/8/12/16/24/32)。 */
export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

/** 圆角: 卡片 12 / 按钮 8 / 标签 6。 */
export const radius = { card: 12, button: 8, label: 6 } as const;

/** 字号: 标题 20/16 / 正文 14 / 辅助 12。 */
export const fontSizes = { title: 20, heading: 16, body: 14, caption: 12 } as const;

/** 系统字体栈 (中文: PingFang SC / Microsoft YaHei)。 */
export const fontFamily =
  "-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Segoe UI', Roboto, sans-serif";

/** 等宽字体 (数字/代码: SF Mono / JetBrains Mono)。 */
export const monoFamily = "'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace";

// ------------------------------------------------------- Agent 状态人话 (§6.2)
/** AI 员工状态人话 (S10-013 §6.2: 可用/停用/废弃)。 */
export const AGENT_STATUS_LABELS: Record<string, string> = {
  available: '可用',
  disabled: '停用',
  retired: '废弃',
};

/** Agent 状态 → 人话 (未知原样, 缺失 → '—')。 */
export function agentStatusLabel(status: string | null | undefined): string {
  if (status == null || status.length === 0) return '—';
  return AGENT_STATUS_LABELS[status] ?? status;
}

// ------------------------------------------------------------ CSS 变量 (双用)
/** AI OS CSS 变量映射 (TS 侧真源; af.css :root 同值, 视觉消费方)。 */
export const cssVars: Record<string, string> = {
  '--af-bg': colors.bg,
  '--af-panel': colors.panel,
  '--af-card': colors.card,
  '--af-primary': colors.primary,
  '--af-success': colors.success,
  '--af-warning': colors.warning,
  '--af-danger': colors.danger,
  '--af-blocked': colors.blocked,
  '--af-neutral': colors.neutral,
  '--af-border': colors.border,
  // 状态色语义变量 (6 态)
  '--af-status-completed': STATUS_COLORS.completed,
  '--af-status-running': STATUS_COLORS.running,
  '--af-status-pending': STATUS_COLORS.pending,
  '--af-status-blocked': STATUS_COLORS.blocked,
  '--af-status-failed': STATUS_COLORS.failed,
  '--af-status-review': STATUS_COLORS.review,
};

/** 完整 `:root { ... }` 块 (注入用; af.css 已静态内置同值)。 */
export function cssVarsText(): string {
  const body = Object.entries(cssVars)
    .map(([k, v]) => `  ${k}: ${v};`)
    .join('\n');
  return `:root {\n${body}\n}`;
}

// ---------------------------------------------------------- 统计格式化 (§4.3)
/** 成功率 (0..1 小数) → '90%' (0..1 按百分比; 已百分比原样; 缺失/非法 → '—')。 */
export function formatSuccessRate(rate: number | null | undefined): string {
  if (rate == null || Number.isNaN(rate)) return '—';
  if (rate >= 0 && rate <= 1) return `${Math.round(rate * 100)}%`;
  return `${Math.round(rate)}%`;
}

/** 耗时 (秒) → 人话 ('42s' / '1m 20s' / '2h 5m'; 缺失/非法 → '—')。 */
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
