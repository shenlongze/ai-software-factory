/**
 * src/test/mock-data.test.ts — mock/projects.ts 数据结构测试 (S10-014 Task 008)。
 *
 * 职责 (用户约束: Mock 仅测试/开发占位, 禁接生产):
 *   1. MOCK_PROJECT_SUMMARIES 结构与真实 GET /api/projects 响应一致 (ProjectSummary)
 *   2. toMockWorkspaceProject() 用 api/domain.ts toWorkspaceProject 转换 (复用 Adapter)
 *   3. MOCK_USAGE_DECLARATION 声明存在 (文件头同步锚点: "Mock 数据仅用于 UI 开发早期
 *      占位/测试; 禁止作为最终实现数据源; 页面必须接真实后端 API")
 *   4. 现有 MOCK_PROJECTS (WorkspaceProject) / MOCK_TODO_TREE 保持 (Task 001 已有测试)
 */

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { WorkspaceProject } from '../models/domain';
import type { ProjectSummary } from '../models/types';
import {
  MOCK_PROJECTS,
  MOCK_PROJECT_SUMMARIES,
  MOCK_TODO_TREE,
  MOCK_USAGE_DECLARATION,
  toMockWorkspaceProject,
} from '../mock/projects';

/** GET /api/projects 真实响应键集合 (验证于 2026-08-11)。 */
const PROJECT_KEYS = [
  'id',
  'name',
  'description',
  'language',
  'repository',
  'tech_stack',
  'status',
  'lifecycle_stage',
  'lifecycle_status',
  'pending_approvals',
  'tasks',
  'last_activity',
  'workflow_id',
  'workflow_name',
  'workflow_status',
  'current_stage',
  'current_stage_status',
  'progress',
  'stage_counts',
] as const;

function hasKeys(obj: unknown, keys: readonly string[]): boolean {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    keys.every((k) => k in (obj as Record<string, unknown>))
  );
}

describe('mock/projects.ts — MOCK_PROJECT_SUMMARIES (结构 = GET /api/projects 真实响应)', () => {
  it('非空且每条满足 ProjectSummary 键子集', () => {
    expect(MOCK_PROJECT_SUMMARIES.length).toBeGreaterThan(0);
    for (const p of MOCK_PROJECT_SUMMARIES) {
      expect(hasKeys(p, PROJECT_KEYS)).toBe(true);
      expect(Array.isArray(p.tech_stack)).toBe(true);
      expect(typeof p.stage_counts).toBe('object');
    }
  });

  it('包含 ScorePocket 示例项目', () => {
    const pocket = MOCK_PROJECT_SUMMARIES.find((p) => p.id === 'score-pocket');
    expect(pocket).toBeDefined();
    expect(pocket?.name).toBe('ScorePocket');
    expectTypeOf(pocket).toMatchTypeOf<ProjectSummary | undefined>();
  });

  it('编译期与 ProjectSummary 类型兼容', () => {
    // readonly ProjectSummary[] → 断言元素类型 (readonly 数组不满足 toMatchTypeOf 约束)
    expect(Array.isArray(MOCK_PROJECT_SUMMARIES)).toBe(true);
    expectTypeOf(MOCK_PROJECT_SUMMARIES[0]).toMatchTypeOf<ProjectSummary>();
  });
});

describe('mock/projects.ts — toMockWorkspaceProject (复用 domain.ts 转换)', () => {
  it('默认 ScorePocket → WorkspaceProject 派生正确 (进度/标签/风险数)', () => {
    const wp = toMockWorkspaceProject();
    expect(wp.id).toBe('score-pocket');
    expect(wp.name).toBe('ScorePocket');
    expect(wp.lifecycleStage).toBe('development');
    // Adapter 真实输出: lifecycle_stage 'development' → 人话 '开发' (afLabels)
    expect(wp.lifecycleLabel).toBe('开发');
    expect(wp.progress).toBe(62); // progress 0.62 → 62%
    expect(wp.pendingApprovals).toBe(1);
    expect(wp.riskCount).toBe(2); // stage_counts.failed(1) + blocked(1)
  });

  it('接受 ProjectSummary 覆盖参数 (partial)', () => {
    const wp = toMockWorkspaceProject({ id: 'ledger-app', progress: 0.5, pending_approvals: 3 });
    expect(wp.id).toBe('ledger-app');
    expect(wp.progress).toBe(50);
    expect(wp.pendingApprovals).toBe(3);
  });

  it('返回类型与 WorkspaceProject 兼容', () => {
    expectTypeOf(toMockWorkspaceProject()).toMatchTypeOf<WorkspaceProject>();
  });
});

describe('mock/projects.ts — 现有导出保持 (Task 001 兼容)', () => {
  it('MOCK_PROJECTS (WorkspaceProject) 与 MOCK_TODO_TREE 仍可用', () => {
    expect(MOCK_PROJECTS.length).toBeGreaterThan(0);
    expect(MOCK_PROJECTS.find((p) => p.id === 'score-pocket')?.name).toBe('ScorePocket');
    expect(MOCK_TODO_TREE.root.type).toBe('phase');
  });
});

describe('mock/projects.ts — Mock 用途声明 (仅测试/开发占位, 禁接生产)', () => {
  it('MOCK_USAGE_DECLARATION 包含 ⚠️ 占位声明与禁接生产约束', () => {
    expect(MOCK_USAGE_DECLARATION).toContain('⚠️ Mock 数据仅用于');
    expect(MOCK_USAGE_DECLARATION).toContain('禁止作为最终实现数据源');
    expect(MOCK_USAGE_DECLARATION).toContain('禁接生产');
  });

  it('MOCK_USAGE_DECLARATION 声明页面必须接真实后端 API', () => {
    expect(MOCK_USAGE_DECLARATION).toContain('真实后端');
  });
});
