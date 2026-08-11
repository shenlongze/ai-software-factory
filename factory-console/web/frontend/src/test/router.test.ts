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
  it('Workspace 级 7 条路由 (dashboard 默认 + 6 子页)', () => {
    expect(WORKSPACE_ROUTES).toHaveLength(7);
    expect(WORKSPACE_ROUTES.map((r) => r.path)).toEqual([
      '#/workspace',
      '#/workspace/projects',
      '#/workspace/team',
      '#/workspace/workflows',
      '#/workspace/runtime',
      '#/workspace/audit',
      '#/workspace/settings',
    ]);
    expect(WORKSPACE_ROUTES.map((r) => r.page)).toEqual([
      'dashboard',
      'projects',
      'team',
      'workflows',
      'runtime',
      'audit',
      'settings',
    ]);
  });

  it('Project 级 11 条路由 (overview 默认 + 10 子页, :id 模板)', () => {
    expect(PROJECT_ROUTES).toHaveLength(11);
    expect(PROJECT_ROUTES.map((r) => r.path)).toEqual([
      '#/project/:id',
      '#/project/:id/vision',
      '#/project/:id/discovery',
      '#/project/:id/prd',
      '#/project/:id/roadmap',
      '#/project/:id/backlog',
      '#/project/:id/sprint',
      '#/project/:id/todo',
      '#/project/:id/workflow',
      '#/project/:id/runtime',
      '#/project/:id/logs',
    ]);
    expect(PROJECT_ROUTES.map((r) => r.page)).toEqual([
      'overview',
      'vision',
      'discovery',
      'prd',
      'roadmap',
      'backlog',
      'sprint',
      'todo',
      'workflow',
      'runtime',
      'logs',
    ]);
  });
});

describe('parseHash — Workspace 级 (7 条)', () => {
  it.each([
    ['#/workspace', 'dashboard'],
    ['#/workspace/projects', 'projects'],
    ['#/workspace/team', 'team'],
    ['#/workspace/workflows', 'workflows'],
    ['#/workspace/runtime', 'runtime'],
    ['#/workspace/audit', 'audit'],
    ['#/workspace/settings', 'settings'],
  ] as const)('%s → workspace/%s', (hash, page) => {
    expect(parseHash(hash)).toEqual({ level: 'workspace', page });
  });

  it('Workspace 未知子页 → 默认 dashboard (不崩)', () => {
    expect(parseHash('#/workspace/nope')).toEqual({ level: 'workspace', page: 'dashboard' });
  });
});

describe('parseHash — Project 级 (11 条)', () => {
  it.each([
    ['#/project/markpad', 'overview'],
    ['#/project/markpad/vision', 'vision'],
    ['#/project/markpad/discovery', 'discovery'],
    ['#/project/markpad/prd', 'prd'],
    ['#/project/markpad/roadmap', 'roadmap'],
    ['#/project/markpad/backlog', 'backlog'],
    ['#/project/markpad/sprint', 'sprint'],
    ['#/project/markpad/todo', 'todo'],
    ['#/project/markpad/workflow', 'workflow'],
    ['#/project/markpad/runtime', 'runtime'],
    ['#/project/markpad/logs', 'logs'],
  ] as const)('%s → project/markpad/%s', (hash, page) => {
    expect(parseHash(hash)).toEqual({ level: 'project', page, projectId: 'markpad' });
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

  it('#/workspace?project= (空 id) → workspace/dashboard', () => {
    expect(parseHash('#/workspace?project=')).toEqual({ level: 'workspace', page: 'dashboard' });
  });

  it('空 hash / 纯 # / 未知路径 / 缺 project id → 默认 workspace/dashboard', () => {
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
