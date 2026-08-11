/**
 * src/test/af-timeline.test.tsx — AfTimeline 垂直时间线 (S10-014 Task 003)。
 *
 * 规格 (AF-UI-Architecture §9.5): 左侧时间戳 (灰) + 状态色圆点 8px + 连接线 2px
 * + 右侧内容 (执行者/动作/结果)。
 * 空态: items=[] → 空态提示; 时间: ISO → YYYY-MM-DD HH:mm (非法原样)。
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { AfTimelineItem } from '../components/af/AfTimeline';
import { AfTimeline } from '../components/af/AfTimeline';

function sampleItems(): AfTimelineItem[] {
  return [
    {
      time: '2026-08-11T02:35:12Z',
      actor: '开发工程师',
      action: '开始执行',
      result: 'Agent 接手任务',
      status: 'running',
    },
    {
      time: '2026-08-11T03:00:00Z',
      actor: '开发工程师',
      action: '提交代码',
      result: 'feat: login api',
      status: 'completed',
    },
    {
      time: '2026-08-11T03:05:00Z',
      actor: '测试工程师',
      action: '运行测试',
      result: '12 passed 0 failed',
    },
  ];
}

describe('AfTimeline (垂直时间线, §9.5)', () => {
  it('渲染全部事件: 时间/执行者/动作/结果', () => {
    render(<AfTimeline items={sampleItems()} />);
    expect(screen.getAllByTestId('af-timeline-item')).toHaveLength(3);
    expect(screen.getByText('开始执行')).toBeInTheDocument();
    expect(screen.getByText('提交代码')).toBeInTheDocument();
    expect(screen.getByText('feat: login api')).toBeInTheDocument();
    expect(screen.getByText('12 passed 0 failed')).toBeInTheDocument();
    // 执行者出现 (至少 2 个时间线条目中有 开发工程师/测试工程师)
    expect(screen.getAllByText('开发工程师').length).toBeGreaterThan(0);
    expect(screen.getByText('测试工程师')).toBeInTheDocument();
  });

  it('事件按传入顺序渲染', () => {
    render(<AfTimeline items={sampleItems()} />);
    const items = screen.getAllByTestId('af-timeline-item');
    expect(items[0]).toHaveTextContent('开始执行');
    expect(items[1]).toHaveTextContent('提交代码');
    expect(items[2]).toHaveTextContent('运行测试');
  });

  it('时间戳: ISO → "YYYY-MM-DD HH:mm" 格式 (本地时区无关)', () => {
    render(<AfTimeline items={sampleItems()} />);
    const times = screen.getAllByTestId('af-timeline-time');
    expect(times[0]).toHaveTextContent(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}/);
  });

  it('非法时间原样显示 (不崩溃)', () => {
    render(<AfTimeline items={[{ time: 'just-now', actor: 'a', action: 'x', result: 'y' }]} />);
    expect(screen.getByTestId('af-timeline-time')).toHaveTextContent('just-now');
  });

  it('状态色圆点: 有 status → 对应色; 无 status → 中性', () => {
    render(<AfTimeline items={sampleItems()} />);
    const dots = screen.getAllByTestId('af-timeline-dot');
    expect(dots[0]).toHaveClass('af-timeline-dot--running');
    expect(dots[1]).toHaveClass('af-timeline-dot--completed');
    expect(dots[2]).toHaveClass('af-timeline-dot--neutral');
  });

  it('空数组 → 空态提示', () => {
    render(<AfTimeline items={[]} />);
    expect(screen.getByTestId('af-timeline-empty')).toHaveTextContent('暂无活动');
    expect(screen.queryAllByTestId('af-timeline-item')).toHaveLength(0);
  });
});
