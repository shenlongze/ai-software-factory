/**
 * src/test/af-status-badge.test.tsx — AfStatusBadge + afTokens 设计令牌 (S10-014 Task 003)。
 *
 * 依据 S10-014-plan §4.2 / AF-UI-Architecture §9.2:
 * - 6 态语义色: 完成=绿 / 执行中=蓝 / 待办=灰 / 阻塞=紫 / 失败=红 / 待审核=橙
 * - 徽标 = 色点 + 人话文字 (§9.4 状态标签; §9.8 状态不只靠颜色)
 * - 未知状态降级: 原样显示 + 中性色
 * - 颜色板/间距/圆角/字号/字体/CSS 变量 (双用: TS 常量 + CSS 变量)
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  AGENT_STATUS_LABELS,
  colors,
  cssVars,
  fontFamily,
  fontSizes,
  monoFamily,
  radius,
  spacing,
  statusColor,
  STATUS_COLORS,
} from '../components/af/afTokens';
import { AfStatusBadge } from '../components/af/AfStatusBadge';

/* ------------------------------------------------------------ afTokens */

describe('afTokens (AI OS 深色主题设计令牌, S10-014-plan §4.2)', () => {
  it('颜色板: 背景/面板/卡片/主色/状态色/边框', () => {
    expect(colors.bg).toBe('#0F1115');
    expect(colors.panel).toBe('#161A22');
    expect(colors.card).toBe('#1D232E');
    expect(colors.primary).toBe('#4C8DFF');
    expect(colors.success).toBe('#22C55E');
    expect(colors.warning).toBe('#F59E0B');
    expect(colors.danger).toBe('#EF4444');
    expect(colors.blocked).toBe('#8B5CF6');
    expect(colors.neutral).toBe('#9CA3AF');
    expect(colors.border).toBe('#2A3140');
  });

  it('6 态语义映射: completed→绿 / running→蓝 / pending→灰 / blocked→紫 / failed→红 / review→橙', () => {
    expect(STATUS_COLORS.completed).toBe('#22C55E');
    expect(STATUS_COLORS.running).toBe('#4C8DFF');
    expect(STATUS_COLORS.pending).toBe('#9CA3AF');
    expect(STATUS_COLORS.blocked).toBe('#8B5CF6');
    expect(STATUS_COLORS.failed).toBe('#EF4444');
    expect(STATUS_COLORS.review).toBe('#F59E0B');
  });

  it('statusColor: 未知/缺失状态降级为中性色', () => {
    expect(statusColor('completed')).toBe('#22C55E');
    expect(statusColor('weird-status')).toBe(colors.neutral);
    expect(statusColor(null)).toBe(colors.neutral);
    expect(statusColor(undefined)).toBe(colors.neutral);
  });

  it('间距 8pt (4/8/12/16/24/32) / 圆角 (卡片12/按钮8/标签6) / 字号 (20/16/14/12)', () => {
    expect(spacing).toEqual({ xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 });
    expect(radius).toEqual({ card: 12, button: 8, label: 6 });
    expect(fontSizes).toEqual({ title: 20, heading: 16, body: 14, caption: 12 });
  });

  it('字体栈: 系统栈 (PingFang SC/Microsoft YaHei) + 等宽 (SF Mono/JetBrains Mono)', () => {
    expect(fontFamily).toContain('PingFang SC');
    expect(fontFamily).toContain('Microsoft YaHei');
    expect(monoFamily).toContain('SF Mono');
    expect(monoFamily).toContain('JetBrains Mono');
  });

  it('CSS 变量双用: 覆盖全部颜色/状态色 token (TS 常量 ↔ CSS 变量)', () => {
    expect(cssVars['--af-bg']).toBe('#0F1115');
    expect(cssVars['--af-panel']).toBe('#161A22');
    expect(cssVars['--af-card']).toBe('#1D232E');
    expect(cssVars['--af-primary']).toBe('#4C8DFF');
    expect(cssVars['--af-success']).toBe('#22C55E');
    expect(cssVars['--af-warning']).toBe('#F59E0B');
    expect(cssVars['--af-danger']).toBe('#EF4444');
    expect(cssVars['--af-blocked']).toBe('#8B5CF6');
    expect(cssVars['--af-neutral']).toBe('#9CA3AF');
    expect(cssVars['--af-border']).toBe('#2A3140');
    // 状态色变量
    expect(cssVars['--af-status-completed']).toBe('#22C55E');
    expect(cssVars['--af-status-running']).toBe('#4C8DFF');
    expect(cssVars['--af-status-pending']).toBe('#9CA3AF');
    expect(cssVars['--af-status-blocked']).toBe('#8B5CF6');
    expect(cssVars['--af-status-failed']).toBe('#EF4444');
    expect(cssVars['--af-status-review']).toBe('#F59E0B');
  });

  it('Agent 状态人话 (S10-013 §6.2: 可用/停用/废弃)', () => {
    expect(AGENT_STATUS_LABELS.available).toBe('可用');
    expect(AGENT_STATUS_LABELS.disabled).toBe('停用');
    expect(AGENT_STATUS_LABELS.retired).toBe('废弃');
  });
});

/* ------------------------------------------------------ AfStatusBadge */

describe('AfStatusBadge (6 态色点 + 人话, §4.3)', () => {
  it('6 态全部渲染: 人话文字 + 对应状态色点 class', () => {
    const cases: [string, string][] = [
      ['completed', '已完成'],
      ['running', '执行中'],
      ['pending', '待办'],
      ['blocked', '阻塞'],
      ['failed', '失败'],
      ['review', '待审核'],
    ];
    for (const [status, label] of cases) {
      const { unmount } = render(<AfStatusBadge status={status} />);
      const badge = screen.getByTestId('af-status-badge');
      expect(badge).toHaveTextContent(label);
      expect(badge.querySelector('.af-status-dot')).toHaveClass(`af-status-dot--${status}`);
      unmount();
    }
  });

  it('label prop 覆盖人话文字', () => {
    render(<AfStatusBadge status="running" label="正在干活" />);
    expect(screen.getByTestId('af-status-badge')).toHaveTextContent('正在干活');
  });

  it('未知状态降级: 原样显示 + 中性色点', () => {
    render(<AfStatusBadge status="mystery" />);
    const badge = screen.getByTestId('af-status-badge');
    expect(badge).toHaveTextContent('mystery');
    expect(badge.querySelector('.af-status-dot')).toHaveClass('af-status-dot--neutral');
  });

  it('缺失状态 → "—" + 中性色点 (不崩溃)', () => {
    const { rerender } = render(<AfStatusBadge status={undefined as never} />);
    expect(screen.getByTestId('af-status-badge')).toHaveTextContent('—');
    rerender(<AfStatusBadge status={null as never} />);
    expect(screen.getByTestId('af-status-badge')).toHaveTextContent('—');
  });

  it('无障碍: 色点 + 文字并存 (状态不只靠颜色, §9.8)', () => {
    render(<AfStatusBadge status="blocked" />);
    const badge = screen.getByTestId('af-status-badge');
    expect(badge.querySelector('.af-status-dot')).toBeInTheDocument();
    expect(badge).toHaveTextContent('阻塞');
    expect(badge).toHaveAttribute('aria-label');
  });
});
