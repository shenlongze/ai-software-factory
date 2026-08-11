/**
 * src/test/af-progress-bar.test.tsx — AfProgressBar (S10-014 Task 003, §4.3)。
 *
 * 规格 (AF-UI-Architecture §9.4): 细 4px + 圆角 + 状态色填充 + 百分比文字。
 * - value 语义: 0..100 百分比; 0/100 边界; 非法值夹取 (NaN/越界 → 夹取)
 * - 状态色填充 class (6 态); 默认主色蓝
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AfProgressBar } from '../components/af/AfProgressBar';

describe('AfProgressBar (细进度条 + 百分比文字, §4.3)', () => {
  it('渲染百分比文字 + 填充宽度', () => {
    render(<AfProgressBar value={42} />);
    const bar = screen.getByTestId('af-progress-bar');
    expect(bar).toHaveTextContent('42%');
    expect(screen.getByTestId('af-progress-fill')).toHaveStyle('width: 42%');
  });

  it('0 边界: 0% + 空填充', () => {
    render(<AfProgressBar value={0} />);
    expect(screen.getByTestId('af-progress-bar')).toHaveTextContent('0%');
    expect(screen.getByTestId('af-progress-fill')).toHaveStyle('width: 0%');
  });

  it('100 边界: 100% + 满填充', () => {
    render(<AfProgressBar value={100} />);
    expect(screen.getByTestId('af-progress-bar')).toHaveTextContent('100%');
    expect(screen.getByTestId('af-progress-fill')).toHaveStyle('width: 100%');
  });

  it('非法值夹取: 负数→0 / 超界→100 / NaN→0', () => {
    const { rerender } = render(<AfProgressBar value={-5} />);
    expect(screen.getByTestId('af-progress-bar')).toHaveTextContent('0%');
    rerender(<AfProgressBar value={150} />);
    expect(screen.getByTestId('af-progress-bar')).toHaveTextContent('100%');
    rerender(<AfProgressBar value={Number.NaN} />);
    expect(screen.getByTestId('af-progress-bar')).toHaveTextContent('0%');
  });

  it('小数四舍五入显示', () => {
    render(<AfProgressBar value={66.6} />);
    expect(screen.getByTestId('af-progress-bar')).toHaveTextContent('67%');
  });

  it('状态色填充 class (6 态语义色)', () => {
    const statuses = [
      'completed',
      'running',
      'pending',
      'blocked',
      'failed',
      'review',
    ] as const;
    for (const status of statuses) {
      const { unmount } = render(<AfProgressBar value={50} status={status} />);
      expect(screen.getByTestId('af-progress-fill')).toHaveClass(`af-progress-fill--${status}`);
      unmount();
    }
  });

  it('无状态 → 默认主色蓝 (af-progress-fill)', () => {
    render(<AfProgressBar value={50} />);
    expect(screen.getByTestId('af-progress-fill')).not.toHaveClass(/--/);
  });

  it('无障碍: role=progressbar + aria-valuenow/valuemin/valuemax', () => {
    render(<AfProgressBar value={42} />);
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '42');
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
  });
});
