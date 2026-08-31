/**
 * src/test/router.test.ts — AI Factory 两级路由表 + parseHash 解析 (S10-014-plan §2.3)。
 *
 * - 路由常量表: Workspace 7 条 + Project 11 条 (路径与 §2.3 完全一致)
 * - parseHash: 两级解析 → {level, page, projectId?}
 *   - #/workspace?project=id 直链兼容 (S10-003 → §2.3 重定向 project/overview)
 *   - 非法/无法识别 → 默认 (workspace/dashboard)
 */

import { describe, expect, it } from 'vitest';
import { DEFAULT_ROUTE, PROJECT_ROUTES, WORKSPACE_ROUTES, parseHash } from '../router';

describe('S10-014 路由常量表 (§2.3)', () => {
  it('Workspace 级 2 条路由 (S32-001 IA Freeze: 唯一 Conversation 主入口)', () => {
    expect(WORKSPACE_ROUTES).toHaveLength(2);
    expect(WORKSPACE_ROUTES.map((r) => r.path)).toEqual([
      '#/workspace',
      '#/workspace/conversation',
    ]);
    expect(WORKSPACE_ROUTES.map((r) => r.page)).toEqual([
      'conversation',
      'conversation',
    ]);
  });

  it('Project 级 7 条路由 (Founder 精简 + 运维)', () => {
    expect(PROJECT_ROUTES).toHaveLength(7);
    expect(PROJECT_ROUTES.map((r) => r.path)).toEqual([
      '#/project/:id',
      '#/project/:id/docs',
      '#/project/:id/todo',
      '#/project/:id/workflow',
      '#/project/:id/runtime',
      '#/project/:id/quality',
      '#/project/:id/ops',
    ]);
    expect(PROJECT_ROUTES.map((r) => r.page)).toEqual([
      'overview',
      'docs',
      'todo',
      'workflow',
      'runtime',
      'quality',
      'ops',
    ]);
  });
});

describe('parseHash — Workspace 级 (S32-001 收敛)', () => {
  it.each([
    ['#/workspace', 'conversation'],
    ['#/workspace/conversation', 'conversation'],
  ] as const)('%s → workspace/%s', (hash, page) => {
    expect(parseHash(hash)).toEqual({ level: 'workspace', page });
  });

  it('已删除的旧子页 (work/tower/projects/settings/manage) → 回退 conversation', () => {
    expect(parseHash('#/workspace/work')).toEqual({ level: 'workspace', page: 'conversation' });
    expect(parseHash('#/workspace/tower')).toEqual({ level: 'workspace', page: 'conversation' });
    expect(parseHash('#/workspace/projects')).toEqual({ level: 'workspace', page: 'conversation' });
    expect(parseHash('#/workspace/settings')).toEqual({ level: 'workspace', page: 'conversation' });
    expect(parseHash('#/workspace/manage')).toEqual({ level: 'workspace', page: 'conversation' });
  });

  it('已移 board 的旧子页 (team/workflows/runtime/audit) → 回退 conversation', () => {
    expect(parseHash('#/workspace/team')).toEqual({ level: 'workspace', page: 'conversation' });
    expect(parseHash('#/workspace/workflows')).toEqual({ level: 'workspace', page: 'conversation' });
    expect(parseHash('#/workspace/runtime')).toEqual({ level: 'workspace', page: 'conversation' });
    expect(parseHash('#/workspace/audit')).toEqual({ level: 'workspace', page: 'conversation' });
  });

  it('Workspace 未知子页 → 默认 conversation (不崩)', () => {
    expect(parseHash('#/workspace/nope')).toEqual({ level: 'workspace', page: 'conversation' });
  });
});

describe('parseHash — Project 级 (11 条)', () => {
  it.each([
    ['#/project/markpad', 'overview'],
    ['#/project/markpad/docs', 'docs'],
    ['#/project/markpad/todo', 'todo'],
    ['#/project/markpad/workflow', 'workflow'],
    ['#/project/markpad/runtime', 'runtime'],
    ['#/project/markpad/quality', 'quality'],
    ['#/project/markpad/ops', 'ops'],
  ] as const)('%s → project/markpad/%s', (hash, page) => {
    expect(parseHash(hash)).toEqual({ level: 'project', page, projectId: 'markpad' });
  });

  it('已隐藏子页 (vision/prd/roadmap/backlog/sprint/logs) → 回退 overview', () => {
    expect(parseHash('#/project/markpad/vision')).toEqual({ level: 'project', page: 'overview', projectId: 'markpad' });
    expect(parseHash('#/project/markpad/prd')).toEqual({ level: 'project', page: 'overview', projectId: 'markpad' });
    expect(parseHash('#/project/markpad/logs')).toEqual({ level: 'project', page: 'overview', projectId: 'markpad' });
  });

  it('Project 未知子页 → 项目 Overview (projectId 不丢)', () => {
    expect(parseHash('#/project/markpad/nope')).toEqual({
      level: 'project',
      page: 'overview',
      projectId: 'markpad',
    });
  });

  it('projectId 含 URL 编码段 (a%2Fb → a/b) 正确解码', () => {
    expect(parseHash('#/project/a%2Fb/todo')).toEqual({
      level: 'project',
      page: 'todo',
      projectId: 'a/b',
    });
  });

  it('尾部斜杠容忍 (#/project/markpad/todo/)', () => {
    expect(parseHash('#/project/markpad/todo/')).toEqual({
      level: 'project',
      page: 'todo',
      projectId: 'markpad',
    });
  });
});

describe('parseHash — S10-003 直链兼容 + 非法/默认', () => {
  it('#/workspace?project=ledger-app → project/overview (直链重定向 §2.3)', () => {
    expect(parseHash('#/workspace?project=ledger-app')).toEqual({
      level: 'project',
      page: 'overview',
      projectId: 'ledger-app',
    });
  });

  it('#/workspace?project= (空 id) → workspace/conversation', () => {
    expect(parseHash('#/workspace?project=')).toEqual({ level: 'workspace', page: 'conversation' });
  });

  it('空 hash / 纯 # / 未知路径 / 缺 project id → 默认 workspace/conversation', () => {
    expect(parseHash('')).toEqual(DEFAULT_ROUTE);
    expect(parseHash('#')).toEqual(DEFAULT_ROUTE);
    expect(parseHash('#/unknown')).toEqual(DEFAULT_ROUTE);
    expect(parseHash('#/project')).toEqual(DEFAULT_ROUTE);
    expect(parseHash('not-a-hash')).toEqual(DEFAULT_ROUTE);
  });

  it('非法 URL 编码的 projectId → 默认 (不抛异常)', () => {
    expect(parseHash('#/project/%E0%A4%A')).toEqual(DEFAULT_ROUTE);
  });
});
