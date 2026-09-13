/**
 * src/test/af-agent-card.test.tsx — AfAgentCard 员工卡片 (S10-014 Task 003)。
 *
 * 规格 (S10-013 §6.2 / S10-014-plan §4.3): 🤖 头像 + 名称 + 状态 (可用/停用/废弃)
 * + 擅长标签 (skills) + 版本 + 统计 (成功率/耗时)。
 * 降级 (§6.3): 缺失 successRate/avgDuration → '—'; 空 skills → 无标签; 未知状态 → 原样。
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { AgentSummary } from '../models/domain';
import { AfAgentCard } from '../components/af/AfAgentCard';

function sampleAgent(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return {
    id: 'dev-1',
    name: '开发工程师',
    role: 'developer',
    status: 'available',
    skills: ['TypeScript', 'React'],
    version: '2.1.0',
    successRate: 0.9,
    avgDuration: 90,
    ...overrides,
  };
}

describe('AfAgentCard (员工卡片, §6.2)', () => {
  it('渲染 🤖 头像 + 名称 + 状态 + 技能标签 + 版本 + 统计', () => {
    render(<AfAgentCard agent={sampleAgent()} />);
    const card = screen.getByTestId('af-agent-card');
    expect(card).toHaveTextContent('🤖');
    expect(card).toHaveTextContent('开发工程师');
    expect(card).toHaveTextContent('developer');
    expect(card).toHaveTextContent('可用');
    expect(card).toHaveTextContent('TypeScript');
    expect(card).toHaveTextContent('React');
    expect(card).toHaveTextContent('v2.1.0');
    expect(card).toHaveTextContent('成功率');
    expect(card).toHaveTextContent('90%');
    expect(card).toHaveTextContent('耗时');
    expect(card).toHaveTextContent('1m 30s');
  });

  it('技能标签独立渲染 (每项一个 chip)', () => {
    render(<AfAgentCard agent={sampleAgent({ skills: ['Python', 'FastAPI', 'SQL'] })} />);
    const tags = screen.getAllByTestId('af-agent-skill');
    expect(tags).toHaveLength(3);
    expect(tags[0]).toHaveTextContent('Python');
    expect(tags[2]).toHaveTextContent('SQL');
  });

  it('状态: 停用/废弃 → 人话标签', () => {
    const { rerender } = render(<AfAgentCard agent={sampleAgent({ status: 'disabled' })} />);
    expect(screen.getByTestId('af-agent-card')).toHaveTextContent('停用');
    rerender(<AfAgentCard agent={sampleAgent({ status: 'retired' })} />);
    expect(screen.getByTestId('af-agent-card')).toHaveTextContent('废弃');
  });

  it('未知状态降级: 原样显示', () => {
    render(<AfAgentCard agent={sampleAgent({ status: 'mystery' as AgentSummary['status'] })} />);
    expect(screen.getByTestId('af-agent-card')).toHaveTextContent('mystery');
  });

  it('缺失统计 → "—" (成功率/耗时 不崩溃)', () => {
    render(<AfAgentCard agent={sampleAgent({ successRate: undefined, avgDuration: undefined })} />);
    const card = screen.getByTestId('af-agent-card');
    expect(card).toHaveTextContent('成功率');
    expect(card).toHaveTextContent('—');
  });

  it('空技能数组 → 不渲染技能标签区', () => {
    render(<AfAgentCard agent={sampleAgent({ skills: [] })} />);
    expect(screen.queryAllByTestId('af-agent-skill')).toHaveLength(0);
  });

  it('成功率边界: 0 → 0% / 1 → 100% / 已百分比原样', () => {
    const { rerender } = render(<AfAgentCard agent={sampleAgent({ successRate: 0 })} />);
    expect(screen.getByTestId('af-agent-card')).toHaveTextContent('0%');
    rerender(<AfAgentCard agent={sampleAgent({ successRate: 1 })} />);
    expect(screen.getByTestId('af-agent-card')).toHaveTextContent('100%');
    rerender(<AfAgentCard agent={sampleAgent({ successRate: 92 })} />);
    expect(screen.getByTestId('af-agent-card')).toHaveTextContent('92%');
  });
});
