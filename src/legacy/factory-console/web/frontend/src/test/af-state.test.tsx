/**
 * src/test/af-state.test.tsx — AfState 三态组件 (S10-014 Task 003)。
 *
 * AI OS 深色风格独立版 (components/State.tsx 是 console 版, 互不干扰):
 * - AfEmptyState: 空态 (默认/自定义文案 + 可选提示)
 * - AfLoadingState: 加载态 (默认/自定义 label)
 * - AfErrorState: 错误态 (message + 可选重试按钮)
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { AfEmptyState, AfErrorState, AfLoadingState } from '../components/af/AfState';

describe('AfEmptyState (空态)', () => {
  it('默认文案 "暂无数据"', () => {
    render(<AfEmptyState />);
    const el = screen.getByTestId('af-empty-state');
    expect(el).toHaveTextContent('暂无数据');
  });

  it('自定义 message + hint 提示', () => {
    render(<AfEmptyState message="暂无项目" hint="输入想法创建一个" />);
    const el = screen.getByTestId('af-empty-state');
    expect(el).toHaveTextContent('暂无项目');
    expect(el).toHaveTextContent('输入想法创建一个');
  });
});

describe('AfLoadingState (加载态)', () => {
  it('默认 label "加载中…"', () => {
    render(<AfLoadingState />);
    expect(screen.getByTestId('af-loading-state')).toHaveTextContent('加载中…');
  });

  it('自定义 label', () => {
    render(<AfLoadingState label="正在加载员工数据…" />);
    expect(screen.getByTestId('af-loading-state')).toHaveTextContent('正在加载员工数据…');
  });
});

describe('AfErrorState (错误态)', () => {
  it('渲染错误 message', () => {
    render(<AfErrorState message="工作台数据加载失败: network down" />);
    expect(screen.getByTestId('af-error-state')).toHaveTextContent(
      '工作台数据加载失败: network down',
    );
  });

  it('提供 onRetry → 重试按钮可点击', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<AfErrorState message="加载失败" onRetry={onRetry} />);
    const btn = screen.getByRole('button', { name: '重试' });
    await user.click(btn);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('无 onRetry → 不渲染重试按钮', () => {
    render(<AfErrorState message="加载失败" />);
    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
  });
});
