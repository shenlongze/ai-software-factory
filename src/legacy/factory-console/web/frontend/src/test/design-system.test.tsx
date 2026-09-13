/**
 * src/test/design-system.test.tsx — S10-000 Design System 测试。
 *
 * 覆盖: 设计令牌 (双主题色/状态色/间距/圆角/Agent 元信息/格式化)、
 * 主题切换 (context + toggle)、组件库 (Button/Card/StatusBadge/AgentAvatar/
 * Timeline/StageCard/ArtifactCard/Modal/Input/Textarea/Select/Layout)。
 * 唯一 basename, 不与 S9 测试冲突。
 */

import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import {
  AGENT_META,
  AGENT_ROLES,
  agentMeta,
  darkTheme,
  fontSizes,
  formatCost,
  formatDuration,
  lightTheme,
  radius,
  spacing,
  statusLabel,
  statusTone,
  themes,
} from '../design/tokens';
import { ThemeProvider, ThemeToggle, useTheme } from '../design/theme';
import { AgentAvatar } from '../components/ds/AgentAvatar';
import { ArtifactCard } from '../components/ds/ArtifactCard';
import { Button } from '../components/ds/Button';
import { Card } from '../components/ds/Card';
import { Input } from '../components/ds/Input';
import { Layout } from '../components/ds/Layout';
import { Modal } from '../components/ds/Modal';
import { Select } from '../components/ds/Select';
import { StageCard } from '../components/ds/StageCard';
import { StatusBadge } from '../components/ds/StatusBadge';
import { Textarea } from '../components/ds/Textarea';
import { Timeline, TimelineNode } from '../components/ds/Timeline';

// ------------------------------------------------------------------ 设计令牌
describe('设计令牌 (tokens)', () => {
  it('亮/暗双主题核心色值符合设计规范', () => {
    expect(lightTheme.bg).toBe('#FFFFFF');
    expect(lightTheme.surface).toBe('#F5F5F5');
    expect(lightTheme.border).toBe('#E0E0E0');
    expect(lightTheme.primary).toBe('#007ACC');
    expect(darkTheme.bg).toBe('#1E1E1E');
    expect(darkTheme.surface).toBe('#252526');
    expect(darkTheme.border).toBe('#3E3E3E');
    expect(lightTheme.success).toBe('#4CAF50');
    expect(lightTheme.error).toBe('#F44336');
    expect(lightTheme.warning).toBe('#FF9800');
    expect(themes.light).toBe(lightTheme);
    expect(themes.dark).toBe(darkTheme);
  });

  it('8 阶段状态 → 语义色调映射', () => {
    expect(statusTone('pending')).toBe('neutral');
    expect(statusTone('running')).toBe('running');
    expect(statusTone('waiting_review')).toBe('warning');
    expect(statusTone('approved')).toBe('success');
    expect(statusTone('completed')).toBe('success');
    expect(statusTone('failed')).toBe('failed');
    expect(statusTone('rejected')).toBe('failed');
    expect(statusTone('rework')).toBe('warning');
    expect(statusTone('unknown_state')).toBe('neutral');
  });

  it('状态中文标签 + 未知状态原样回退', () => {
    expect(statusLabel('pending')).toBe('待执行');
    expect(statusLabel('running')).toBe('运行中');
    expect(statusLabel('waiting_review')).toBe('待审核');
    expect(statusLabel('failed')).toBe('失败');
    expect(statusLabel('something_new')).toBe('something_new');
  });

  it('6 Agent 元信息 (PM/UX-UI/Arch/Dev/Tester/Release)', () => {
    expect(AGENT_ROLES).toHaveLength(6);
    expect(AGENT_META.pm.label).toBe('产品经理');
    expect(AGENT_META.ux_ui.label).toBe('UX/UI 设计师');
    expect(AGENT_META.architecture.label).toBe('架构师');
    expect(AGENT_META.developer.label).toBe('开发工程师');
    expect(AGENT_META.tester.label).toBe('测试工程师');
    expect(AGENT_META.release.label).toBe('发布工程师');
    expect(agentMeta('pm').color).toBe('#007ACC');
    // 未知角色回退中性灰 + 🤖
    expect(agentMeta('unknown').color).toBe('#9E9E9E');
    expect(agentMeta('unknown').icon).toBe('🤖');
  });

  it('间距/圆角/字号 scale', () => {
    expect(spacing).toEqual({ xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48 });
    expect(radius).toEqual({ sm: 4, md: 8, lg: 12, full: 999 });
    expect(fontSizes.body).toBe(14);
    expect(fontSizes.title).toBe(24);
  });

  it('耗时/成本格式化', () => {
    expect(formatDuration(42)).toBe('42s');
    expect(formatDuration(80)).toBe('1m 20s');
    expect(formatDuration(3900)).toBe('1h 5m');
    expect(formatDuration(null)).toBe('—');
    expect(formatCost(0.0038)).toBe('$0.0038');
    expect(formatCost(12)).toBe('$12');
    expect(formatCost(null)).toBe('—');
  });
});

// ------------------------------------------------------------------ 主题切换
function ThemeProbe(): JSX.Element {
  const { theme } = useTheme();
  return <span data-testid="theme-probe">{theme}</span>;
}

function ThemeControl(): JSX.Element {
  const { theme, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme-probe">{theme}</span>
      <button type="button" onClick={() => setTheme('dark')}>
        to-dark
      </button>
    </div>
  );
}

describe('主题切换 (ThemeProvider/ThemeToggle)', () => {
  it('默认 light, 并写入 <html data-theme>', () => {
    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId('theme-probe')).toHaveTextContent('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('ThemeToggle 点击切到暗色, 同步 data-theme + 按钮状态', async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider initialTheme="light">
        <ThemeToggle />
      </ThemeProvider>,
    );
    expect(screen.getByTestId('ds-theme-toggle')).toHaveAttribute('data-theme-toggle', 'light');
    await user.click(screen.getByTestId('ds-theme-toggle'));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(screen.getByTestId('ds-theme-toggle')).toHaveAttribute('data-theme-toggle', 'dark');
  });

  it('useTheme().setTheme 切换主题', async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider initialTheme="light">
        <ThemeControl />
      </ThemeProvider>,
    );
    await user.click(screen.getByText('to-dark'));
    expect(screen.getByTestId('theme-probe')).toHaveTextContent('dark');
  });
});

// ------------------------------------------------------------------ Button
describe('Button', () => {
  it('默认 primary variant + data-variant 属性', () => {
    render(<Button>确定</Button>);
    const btn = screen.getByRole('button', { name: '确定' });
    expect(btn).toHaveClass('ds-btn', 'ds-btn-primary');
    expect(btn).toHaveAttribute('data-variant', 'primary');
  });

  it('danger/ghost variant 类名', () => {
    render(<Button variant="danger">删除</Button>);
    expect(screen.getByRole('button', { name: '删除' })).toHaveClass('ds-btn-danger');
    render(<Button variant="ghost">取消</Button>);
    expect(screen.getByRole('button', { name: '取消' })).toHaveClass('ds-btn-ghost');
  });

  it('loading → disabled + spinner + aria-busy, 点击不触发 onClick', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        保存
      </Button>,
    );
    const btn = screen.getByRole('button', { name: '保存' });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('aria-busy', 'true');
    expect(btn.querySelector('.ds-btn-spinner')).not.toBeNull();
    await user.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('onClick 触发', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button onClick={onClick}>点击</Button>);
    await user.click(screen.getByRole('button', { name: '点击' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

// ------------------------------------------------------------------ Card
describe('Card', () => {
  it('渲染标题/副标题/内容/操作区', () => {
    render(
      <Card title="阶段状态" subtitle="实时" actions={<button type="button">操作</button>}>
        <p>卡片内容</p>
      </Card>,
    );
    expect(screen.getByText('阶段状态')).toBeInTheDocument();
    expect(screen.getByText('实时')).toBeInTheDocument();
    expect(screen.getByText('卡片内容')).toBeInTheDocument();
    expect(screen.getByText('操作')).toBeInTheDocument();
  });

  it('无标题时仍渲染内容 (ds-card 容器)', () => {
    render(<Card>纯内容</Card>);
    expect(screen.getByTestId('ds-card')).toBeInTheDocument();
    expect(screen.getByText('纯内容')).toBeInTheDocument();
    expect(document.querySelector('.ds-card-title')).toBeNull();
  });
});

// ------------------------------------------------------------------ StatusBadge
describe('StatusBadge', () => {
  it('running → 运行中 + running 色调; failed → 失败 + failed 色调', () => {
    render(<StatusBadge status="running" />);
    const badge = screen.getByText('运行中');
    expect(badge).toHaveClass('ds-badge-running');
    expect(badge).toHaveAttribute('data-tone', 'running');
    render(<StatusBadge status="failed" />);
    expect(screen.getByText('失败')).toHaveClass('ds-badge-failed');
  });

  it('未知状态 → neutral + 原样标签', () => {
    render(<StatusBadge status="weird_state" />);
    const badge = screen.getByText('weird_state');
    expect(badge).toHaveClass('ds-badge-neutral');
  });
});

// ------------------------------------------------------------------ AgentAvatar
describe('AgentAvatar', () => {
  it('role → data-role + aria-label (中文名)', () => {
    render(<AgentAvatar role="pm" />);
    const avatar = screen.getByRole('img');
    expect(avatar).toHaveAttribute('data-role', 'pm');
    expect(avatar).toHaveAttribute('aria-label', '产品经理');
  });

  it('6 Agent 角色均可渲染 (含未知回退)', () => {
    AGENT_ROLES.forEach((role) => {
      render(<AgentAvatar role={role} />);
    });
    render(<AgentAvatar role="unknown" />);
    expect(screen.getAllByRole('img')).toHaveLength(AGENT_ROLES.length + 1);
    expect(screen.getAllByRole('img').at(-1)).toHaveAttribute('data-role', 'unknown');
  });
});

// ------------------------------------------------------------------ Timeline / StageCard
describe('Timeline + StageCard', () => {
  it('Timeline 渲染节点 + 状态色圆点 + 时间', () => {
    render(
      <Timeline>
        <TimelineNode status="running" title="PM 分析需求" time="10:02" />
        <TimelineNode status="completed" title="UX/UI 设计">
          <p>设计产物</p>
        </TimelineNode>
      </Timeline>,
    );
    expect(screen.getByTestId('ds-timeline')).toBeInTheDocument();
    const nodes = screen.getAllByTestId('ds-timeline-node');
    expect(nodes).toHaveLength(2);
    expect(nodes[0]).toHaveAttribute('data-status', 'running');
    expect(nodes[0].querySelector('.ds-dot-running')).not.toBeNull();
    expect(screen.getByText('10:02')).toBeInTheDocument();
    expect(screen.getByText('设计产物')).toBeInTheDocument();
  });

  it('StageCard 渲染 Agent/状态/输入/输出/耗时/成本 + 查看详情点击', async () => {
    const user = userEvent.setup();
    const onViewDetails = vi.fn();
    render(
      <StageCard
        name="需求分析"
        agent="pm"
        status="completed"
        input={['用户需求']}
        output={['PRD 文档']}
        durationSec={42}
        cost={0.0038}
        onViewDetails={onViewDetails}
      />,
    );
    expect(screen.getByText('需求分析')).toBeInTheDocument();
    expect(screen.getByText('产品经理')).toBeInTheDocument();
    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(screen.getByText('用户需求')).toBeInTheDocument();
    expect(screen.getByText('PRD 文档')).toBeInTheDocument();
    expect(screen.getByText('42s')).toBeInTheDocument();
    expect(screen.getByText('$0.0038')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '查看详情' }));
    expect(onViewDetails).toHaveBeenCalledTimes(1);
  });

  it('StageCard inTimeline 包 TimelineNode', () => {
    render(
      <Timeline>
        <StageCard name="开发" agent="developer" status="running" inTimeline />
      </Timeline>,
    );
    const node = screen.getByTestId('ds-timeline-node');
    expect(node).toHaveAttribute('data-status', 'running');
    expect(node.querySelector('.ds-stage-card')).not.toBeNull();
  });
});

// ------------------------------------------------------------------ ArtifactCard
describe('ArtifactCard', () => {
  it('渲染 类型中文/名称/创建者/输入/输出 + 状态徽章', () => {
    render(
      <ArtifactCard
        type="prd"
        name="记账 App PRD"
        createdBy="pm"
        input="需求说明"
        output="PRD 文档"
        status="completed"
      />,
    );
    expect(screen.getByText('PRD 文档')).toBeInTheDocument(); // 类型中文标签
    expect(screen.getByText('记账 App PRD')).toBeInTheDocument();
    expect(screen.getByText('创建: 产品经理')).toBeInTheDocument();
    expect(screen.getByText('输入: 需求说明')).toBeInTheDocument();
    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(screen.getByTestId('ds-artifact-card')).toHaveAttribute('data-type', 'prd');
  });
});

// ------------------------------------------------------------------ Modal
describe('Modal', () => {
  it('open=false 不渲染; open=true 渲染标题+内容', () => {
    const { rerender } = render(
      <Modal open={false} title="审核" onClose={vi.fn()}>
        隐藏
      </Modal>,
    );
    expect(screen.queryByTestId('ds-modal')).toBeNull();
    rerender(
      <Modal open title="审核" onClose={vi.fn()}>
        <p>弹窗内容</p>
      </Modal>,
    );
    expect(screen.getByTestId('ds-modal')).toBeInTheDocument();
    expect(screen.getByText('审核')).toBeInTheDocument();
    expect(screen.getByText('弹窗内容')).toBeInTheDocument();
  });

  it('遮罩点击 + Escape 关闭', () => {
    const onClose = vi.fn();
    render(
      <Modal open title="审核" onClose={onClose}>
        内容
      </Modal>,
    );
    fireEvent.click(screen.getByTestId('ds-modal-overlay'));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

// ------------------------------------------------------------------ 表单
describe('表单 (Input/Textarea/Select)', () => {
  it('Input: label + 输入触发 onChange', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Input label="项目名" value="" onChange={onChange} placeholder="输入项目名" />);
    expect(screen.getByText('项目名')).toBeInTheDocument();
    await user.type(screen.getByTestId('ds-input'), '记账');
    expect(onChange).toHaveBeenCalled();
  });

  it('Textarea: label + 输入', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Textarea label="需求描述" value="" onChange={onChange} />);
    await user.type(screen.getByTestId('ds-textarea'), '做一个记账 App');
    expect(onChange).toHaveBeenCalled();
  });

  it('Select: options 渲染 + 选择触发 onChange(value)', () => {
    const onChange = vi.fn();
    render(
      <Select
        label="负责 Agent"
        options={[
          { value: 'pm', label: '产品经理' },
          { value: 'dev', label: '开发工程师' },
        ]}
        value=""
        onChange={onChange}
        placeholder="请选择"
      />,
    );
    const select = screen.getByTestId('ds-select');
    expect(screen.getAllByRole('option')).toHaveLength(3);
    fireEvent.change(select, { target: { value: 'pm' } });
    expect(onChange).toHaveBeenCalledWith('pm');
  });
});

// ------------------------------------------------------------------ Layout
describe('Layout 三栏', () => {
  it('渲染 Explorer/Workspace/Panel + 默认尺寸', () => {
    render(
      <Layout explorer={<span>左侧</span>} workspace={<span>中间</span>} panel={<span>右侧</span>} />,
    );
    expect(screen.getByTestId('ds-layout')).toBeInTheDocument();
    expect(screen.getByText('左侧')).toBeInTheDocument();
    expect(screen.getByText('中间')).toBeInTheDocument();
    expect(screen.getByText('右侧')).toBeInTheDocument();
    expect(screen.getByTestId('ds-explorer').getAttribute('style')).toContain('width: 220px');
    expect(screen.getByTestId('ds-panel').getAttribute('style')).toContain('width: 360px');
  });

  it('折叠按钮隐藏 pane 内容', async () => {
    const user = userEvent.setup();
    render(
      <Layout explorer={<span>左侧内容</span>} workspace={<span>中间内容</span>} panel={<span>右侧内容</span>} />,
    );
    await user.click(screen.getByTestId('ds-explorer-toggle'));
    expect(screen.queryByText('左侧内容')).toBeNull();
    expect(screen.getByTestId('ds-explorer')).toHaveClass('is-collapsed');
    expect(screen.getByText('中间内容')).toBeInTheDocument();
    await user.click(screen.getByTestId('ds-panel-toggle'));
    expect(screen.queryByText('右侧内容')).toBeNull();
    expect(screen.getByTestId('ds-panel')).toHaveClass('is-collapsed');
  });
});
