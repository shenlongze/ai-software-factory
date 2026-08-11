/**
 * src/test/api-domain.test.ts — Domain Adapter 占位测试 (S10-014 Task 001)。
 *
 * api/domain.ts 本 Task 只建签名 + 返回默认值 (空/未实现状态), 转换逻辑由
 * S10-014 Task 007 实现; 本测试锁定"占位不崩溃 + 返回结构完整"的契约。
 */

import { describe, expect, it } from 'vitest';
import {
  toAgentSummary,
  toRuntimeActivity,
  toTaskDetail,
  toTodoTree,
  toWorkflowPipeline,
  toWorkspaceProject,
} from '../api/domain';

describe('api/domain — toWorkspaceProject 占位', () => {
  it('返回空默认项目 (不崩溃)', () => {
    const p = toWorkspaceProject();
    expect(p.id).toBe('');
    expect(p.name).toBe('');
    expect(p.lifecycleStage).toBe('draft');
    expect(p.lifecycleLabel).toBe('');
    expect(p.progress).toBe(0);
    expect(p.pendingApprovals).toBe(0);
    expect(p.riskCount).toBe(0);
  });
});

describe('api/domain — toTodoTree 占位', () => {
  it('返回空树 (root 存在, 无子节点)', () => {
    const tree = toTodoTree();
    expect(tree.root.id).toBe('');
    expect(tree.root.title).toBe('');
    expect(tree.root.type).toBe('phase');
    expect(tree.root.children).toHaveLength(0);
  });
});

describe('api/domain — toWorkflowPipeline 占位', () => {
  it('返回空流水线 (无阶段)', () => {
    const pipeline = toWorkflowPipeline();
    expect(pipeline.templateId).toBe('');
    expect(pipeline.templateName).toBe('');
    expect(pipeline.stages).toHaveLength(0);
  });
});

describe('api/domain — toTaskDetail 占位', () => {
  it('返回空任务详情 (空 history/artifacts)', () => {
    const detail = toTaskDetail();
    expect(detail.id).toBe('');
    expect(detail.title).toBe('');
    expect(detail.status).toBe('pending');
    expect(detail.history).toHaveLength(0);
    expect(detail.artifacts).toHaveLength(0);
  });
});

describe('api/domain — toRuntimeActivity 占位', () => {
  it('返回空活动条目', () => {
    const activity = toRuntimeActivity();
    expect(activity.time).toBe('');
    expect(activity.actor).toBe('');
    expect(activity.action).toBe('');
    expect(activity.result).toBe('');
  });
});

describe('api/domain — toAgentSummary 占位', () => {
  it('返回空 Agent 摘要 (空技能列表)', () => {
    const agent = toAgentSummary();
    expect(agent.id).toBe('');
    expect(agent.name).toBe('');
    expect(agent.version).toBe('');
    expect(agent.skills).toHaveLength(0);
  });
});
