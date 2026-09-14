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

/* ============================================= v1.1.104: AI 员工/技能人话标签
 * 普通人友好: 内部 role/skill id → 中文标签+分组+职责说明 (未知值原样兜底)。
 */

/** AI 员工角色信息 (role → 中文标签/分组/一句职责说明)。 */
export const AGENT_ROLE_INFO: Record<string, { label: string; group: string; desc: string }> = {
  // 产品线
  product_manager: { label: '产品经理', group: '产品', desc: '定义产品需求与方向' },
  'product-manager': { label: '产品经理', group: '产品', desc: '定义产品需求与方向' },
  pm: { label: '产品经理', group: '产品', desc: '定义产品需求与方向' },
  'Product Manager': { label: '产品经理', group: '产品', desc: '定义产品需求与方向' },
  // 设计线
  ux: { label: '体验设计师', group: '设计', desc: '界面与交互设计' },
  designer: { label: '设计师', group: '设计', desc: '视觉与交互设计' },
  // 研发线
  architect: { label: '架构师', group: '研发', desc: '设计技术方案与系统架构' },
  Architect: { label: '架构师', group: '研发', desc: '设计技术方案与系统架构' },
  'backend-developer': { label: '后端开发', group: '研发', desc: '服务端逻辑与接口开发' },
  backend_developer: { label: '后端开发', group: '研发', desc: '服务端逻辑与接口开发' },
  developer: { label: '开发工程师', group: '研发', desc: '编码实现功能' },
  'frontend-engineer': { label: '前端开发', group: '研发', desc: '界面与前端功能开发' },
  frontend: { label: '前端开发', group: '研发', desc: '界面与前端功能开发' },
  'Frontend Engineer': { label: '前端开发', group: '研发', desc: '界面与前端功能开发' },
  flutter_dev: { label: 'Flutter 开发', group: '研发', desc: '跨平台 App 开发' },
  'flutter-dev': { label: 'Flutter 开发', group: '研发', desc: '跨平台 App 开发' },
  // 质量线
  tester: { label: '测试工程师', group: '质量', desc: '功能与回归测试' },
  qa: { label: 'QA 工程师', group: '质量', desc: '质量保障与测试' },
  'qa-engineer': { label: 'QA 工程师', group: '质量', desc: '质量保障与测试' },
  'QA Engineer': { label: 'QA 工程师', group: '质量', desc: '质量保障与测试' },
};

/** 角色 → 中文信息 (未知 → 原样 + 自定义说明)。 */
export function agentRoleInfo(role: string | null | undefined): { label: string; group: string; desc: string } {
  const key = String(role ?? '').trim();
  const hit = AGENT_ROLE_INFO[key] ?? AGENT_ROLE_INFO[key.toLowerCase()];
  return hit ?? { label: key || '未知角色', group: '其他', desc: '自定义角色' };
}

/** Agent 状态人话标签 (AVAILABLE → 可用; 未知原样)。 */
export function agentStatusLabel(status: string | null | undefined): string {
  const s = String(status ?? '').trim().toUpperCase();
  if (s === 'AVAILABLE') return '可用';
  if (s === 'BUSY') return '忙碌';
  if (s === 'OFFLINE' || s === 'DISABLED') return '停用';
  return status || '—';
}

/** Skill 人话标签 (skill id → 中文; 未知原样)。 */
export const SKILL_LABELS: Record<string, string> = {
  'backend.development': '后端开发',
  'flutter.development': 'Flutter 开发',
  flutter: 'Flutter',
  dart: 'Dart',
  python: 'Python',
  development: '开发',
  testing: '测试',
  test: '测试',
  qa: '质量保障',
  pytest: 'Pytest',
  product_management: '产品管理',
  pm: '产品管理',
  analysis: '需求分析',
  requirement: '需求',
  requirement_analysis: '需求分析',
  architecture: '架构设计',
  system: '系统设计',
  design: '设计',
  ui: 'UI 设计',
  frontend: '前端',
  react: 'React',
  typescript: 'TypeScript',
  product_documentation: '产品文档',
};

/** Skill 人话标签函数 (未知名原样)。 */
export function skillLabel(skill: string | null | undefined): string {
  const s = String(skill ?? '').trim();
  return SKILL_LABELS[s] ?? SKILL_LABELS[s.toLowerCase()] ?? (s || '—');
}

/** Skill 分类人话标签 (backend→后端 等; 未知原样)。 */
export const SKILL_CATEGORY_LABELS: Record<string, string> = {
  backend: '后端',
  frontend: '前端',
  testing: '测试',
  general: '通用',
  product: '产品',
  design: '设计',
};
export function skillCategoryLabel(category: string | null | undefined): string {
  const c = String(category ?? '').trim();
  return SKILL_CATEGORY_LABELS[c] ?? SKILL_CATEGORY_LABELS[c.toLowerCase()] ?? (c || '—');
}
