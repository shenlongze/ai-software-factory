/**
 * src/test/components.test.tsx — 基础组件渲染测试。
 *
 * Card / Badge (statusBadge / riskBadge) / ScoreBar / State (Empty/Loading/
 * Error/Modal) / Table / EvidenceChain / ModeToggle。
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Badge, riskBadge, statusBadge } from '../components/Badge';
import { Card } from '../components/Card';
import { EvidenceChain } from '../components/EvidenceChain';
import { ModeToggle } from '../components/ModeToggle';
import { ScoreBar } from '../components/ScoreBar';
import { EmptyState, ErrorState, LoadingState, Modal } from '../components/State';
import { Table } from '../components/Table';
import type { Column } from '../components/Table';
import { AppStateProvider } from '../state/AppState';

describe('Card', () => {
  it('渲染标题/副标题/内容', () => {
    render(
      <Card title="成本汇总" subtitle="估算">
        <p>内容</p>
      </Card>,
    );
    expect(screen.getByText('成本汇总')).toBeInTheDocument();
    expect(screen.getByText('估算')).toBeInTheDocument();
    expect(screen.getByText('内容')).toBeInTheDocument();
  });

  it('无副标题时不渲染副标题节点', () => {
    render(<Card title="仅标题">x</Card>);
    expect(screen.getByText('仅标题')).toBeInTheDocument();
    expect(document.querySelector('.card-subtitle')).toBeNull();
  });
});

describe('Badge', () => {
  it('Badge 默认 neutral tone', () => {
    render(<Badge text="idle" />);
    const badge = screen.getByText('idle');
    expect(badge).toHaveClass('badge-neutral');
  });

  it('statusBadge 映射: pending→warn, approved→ok, rejected→danger, 未知→neutral', () => {
    render(<Badge text="x" />);
    expect(statusBadge('pending')).toBeDefined();
    const warn = statusBadge('pending');
    const ok = statusBadge('approved');
    const danger = statusBadge('rejected');
    const neutral = statusBadge('weird');
    expect(warn.props.tone).toBe('warn');
    expect(ok.props.tone).toBe('ok');
    expect(danger.props.tone).toBe('danger');
    expect(neutral.props.tone).toBe('neutral');
  });

  it('riskBadge: high→danger, medium→warn, low/null→ok', () => {
    expect(riskBadge('high').props.tone).toBe('danger');
    expect(riskBadge('medium').props.tone).toBe('warn');
    expect(riskBadge('low').props.tone).toBe('ok');
    expect(riskBadge(null).props.tone).toBe('ok');
  });
});

describe('ScoreBar', () => {
  it('value 0..1 → 百分比宽度, null → 无数据占位', () => {
    render(<ScoreBar label="Confidence" value={0.5} />);
    const fill = document.querySelector('.score-fill') as HTMLElement;
    expect(fill.style.width).toBe('50%');
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('value 超界被 clamp 到 [0, max]', () => {
    render(<ScoreBar label="Over" value={2} max={1} />);
    const fill = document.querySelector('.score-fill') as HTMLElement;
    expect(fill.style.width).toBe('100%');
  });

  it('value null → 显示 —', () => {
    render(<ScoreBar label="Cost" value={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});

describe('State 组件', () => {
  it('EmptyState / LoadingState / ErrorState 渲染 testid', () => {
    const { rerender } = render(<EmptyState message="暂无数据" />);
    expect(screen.getByTestId('empty-state')).toHaveTextContent('暂无数据');
    rerender(<LoadingState label="加载中…" />);
    expect(screen.getByTestId('loading-state')).toHaveTextContent('加载中…');
    rerender(<ErrorState message="boom" />);
    expect(screen.getByTestId('error-state')).toHaveTextContent('boom');
  });

  it('LoadingState 默认文案', () => {
    render(<LoadingState />);
    expect(screen.getByTestId('loading-state')).toHaveTextContent('加载中…');
  });

  it('Modal: 渲染标题/内容, 关闭按钮与遮罩点击触发 onClose', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Modal title="审批" onClose={onClose}>
        <p>决定通道指引</p>
      </Modal>,
    );
    expect(screen.getByRole('dialog', { name: '审批' })).toBeInTheDocument();
    expect(screen.getByText('决定通道指引')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '关闭' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('Modal 内容区点击不冒泡关闭, 遮罩点击关闭', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { container } = render(
      <Modal title="t" onClose={onClose}>
        <p>body</p>
      </Modal>,
    );
    await user.click(screen.getByText('body'));
    expect(onClose).not.toHaveBeenCalled();
    await user.click(container.querySelector('.modal-overlay') as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe('Table', () => {
  const columns: Column<{ id: string; name: string }>[] = [
    { key: 'id', header: 'ID', render: (r) => <strong>{r.id}</strong> },
    { key: 'name', header: '名称', render: (r) => r.name },
  ];

  it('空数据 → 空态文案', () => {
    render(<Table columns={columns} rows={[]} rowKey={(r) => r.id} empty="暂无 Provider" />);
    expect(screen.getByText('暂无 Provider')).toBeInTheDocument();
    expect(document.querySelector('table')).toBeNull();
  });

  it('渲染表头与行; onRowClick 触发', async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    render(
      <Table
        columns={columns}
        rows={[{ id: 'a', name: 'Alpha' }]}
        rowKey={(r) => r.id}
        onRowClick={onRowClick}
      />,
    );
    expect(screen.getByText('ID')).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    await user.click(screen.getByText('Alpha'));
    expect(onRowClick).toHaveBeenCalledWith({ id: 'a', name: 'Alpha' });
  });

  it('无 onRowClick → 行不可点击', () => {
    render(<Table columns={columns} rows={[{ id: 'a', name: 'Alpha' }]} rowKey={(r) => r.id} />);
    expect(document.querySelector('tr.clickable')).toBeNull();
  });
});

describe('EvidenceChain', () => {
  it('空证据 → 无证据链占位', () => {
    render(
      <AppStateProvider>
        <EvidenceChain evidence={[]} />
      </AppStateProvider>,
    );
    expect(screen.getByText('无证据链')).toBeInTheDocument();
  });

  it('普通模式: 只显示前 2 条 + 省略提示', () => {
    render(
      <AppStateProvider>
        <EvidenceChain evidence={['e1', 'e2', 'e3', 'e4']} />
      </AppStateProvider>,
    );
    expect(screen.getByText('4 条证据')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByText(/共 4 条/)).toBeInTheDocument();
  });

  it('专业模式: 显示全部证据', async () => {
    const user = userEvent.setup();
    render(
      <AppStateProvider>
        <ModeToggle />
        <EvidenceChain evidence={['e1', 'e2', 'e3']} />
      </AppStateProvider>,
    );
    await user.click(screen.getByRole('button', { name: '专业模式' }));
    expect(screen.getByText('3 条证据')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
  });
});

describe('ModeToggle', () => {
  it('默认普通模式 active, 点击切换到专业模式', async () => {
    const user = userEvent.setup();
    render(
      <AppStateProvider>
        <ModeToggle />
      </AppStateProvider>,
    );
    const simple = screen.getByRole('button', { name: '普通模式' });
    const expert = screen.getByRole('button', { name: '专业模式' });
    expect(simple).toHaveAttribute('aria-pressed', 'true');
    expect(expert).toHaveAttribute('aria-pressed', 'false');
    await user.click(expert);
    expect(simple).toHaveAttribute('aria-pressed', 'false');
    expect(expert).toHaveAttribute('aria-pressed', 'true');
  });
});
