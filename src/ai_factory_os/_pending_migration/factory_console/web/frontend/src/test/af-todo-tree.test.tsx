/**
 * src/test/af-todo-tree.test.tsx — AfTodoTree 组件 (S10-015 Task 003)。
 *
 * 验证 (S10-015-architecture-review §3 + AF-UI-Architecture §4):
 * - 完整树渲染: 项目头 (root) + 阶段 → 模块 → 任务 层级 (默认全展开)
 * - 状态徽标: 6 态人话 (复用 AfStatusBadge)
 * - 优先级标签: P0 红 / P1 橙 / P2 蓝 / P3 灰 (来自 taskMeta 投影)
 * - 叶子任务额外字段: 负责人/开始时间/下一步 (若字段有)
 * - 折叠/展开: 单击箭头 (aria-expanded) + 全折叠/全展开按钮
 * - 状态过滤: [全部][执行中][阻塞][待审核][失败] — 只显示匹配任务及其祖先
 * - 空树 → AfEmptyState (禁空白); 过滤无匹配 → 空态
 * - onSelectTask 回调; 执行中节点焦点高亮
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { toTodoTree } from '../api/domain';
import { AfTodoTree } from '../components/af/AfTodoTree';
import { buildChainLines } from '../pages/project/AfTodoTreePage';
import type { TodoTree } from '../models/domain';
import { sampleTaskMeta, sampleTodoBacklog, sampleTodoFixture } from './fixtures';

const { tree, meta } = sampleTodoFixture();

/** 节点行 (data-testid="af-tree-node-<id>")。 */
function nodeRow(id: string): HTMLElement {
  return screen.getByTestId(`af-tree-node-${id}`);
}

describe('AfTodoTree (Todo Tree 组件)', () => {
  it('渲染完整树: 项目头 + 阶段 → 模块 → 任务 层级 (默认全展开; 已完成任务在树内显示)', async () => {
    const user = userEvent.setup();
    render(<AfTodoTree tree={tree} taskMeta={meta} />);
    // 项目头 (root): 标题 + 进度条 + 状态徽标
    expect(screen.getByText('演示项目')).toBeInTheDocument();
    expect(screen.getAllByTestId('af-progress-bar').length).toBeGreaterThanOrEqual(1);
    // 主树节点: 2 阶段 + 2 模块 + 4 故事 + 6 任务 (done 也显示) = 14
    expect(screen.getAllByTestId(/^af-tree-node-/)).toHaveLength(14);
    // 每个节点行都有进度条 (折叠时也可见 — Founder)
    expect(screen.getAllByTestId('af-progress-bar').length).toBeGreaterThanOrEqual(14);
    // 「隐藏已完成」开关: done 任务 t-reg-db 计数 (默认显示已完成)
    expect(screen.getByTestId('af-tree-hide-completed-toggle')).toHaveTextContent('隐藏已完成');
    // 层级: 阶段行标题 → 子容器 → 模块行 → 子容器 → 故事行 → 子容器 → 任务行
    expect(within(nodeRow('epic-dev')).getByText('开发阶段')).toBeInTheDocument();
    expect(within(screen.getByTestId('af-tree-children-epic-dev')).getByText('用户系统')).toBeInTheDocument();
    expect(within(screen.getByTestId('af-tree-children-feat-user')).getByText('用户注册')).toBeInTheDocument();
    expect(within(screen.getByTestId('af-tree-children-story-reg')).getByText('实现注册 API')).toBeInTheDocument();
    // done 任务 t-reg-db 默认在主树 (已完成任务要在列表里 — Founder 2026-08-27)
    expect(screen.getByTestId('af-tree-node-t-reg-db')).toBeInTheDocument();
    // 开启「隐藏已完成」→ 归入归档区可见
    await user.click(screen.getByTestId('af-tree-hide-completed-toggle'));
    expect(screen.queryByTestId('af-tree-node-t-reg-db')).not.toBeInTheDocument();
    expect(within(screen.getByTestId('af-tree-archive')).getByText('用户数据模型')).toBeInTheDocument();
  });

  it('状态徽标: 6 态人话正确渲染 (复用 AfStatusBadge; done 也在主树)', () => {
    render(<AfTodoTree tree={tree} taskMeta={meta} />);
    expect(within(nodeRow('t-reg-api')).getByText('执行中')).toBeInTheDocument();
    expect(within(nodeRow('t-login-api')).getByText('阻塞')).toBeInTheDocument();
    expect(within(nodeRow('t-regr-run')).getByText('待审核')).toBeInTheDocument();
    expect(within(nodeRow('t-regr-report')).getByText('失败')).toBeInTheDocument();
    expect(within(nodeRow('t-release-check')).getByText('待办')).toBeInTheDocument();
    for (const id of ['t-reg-api', 't-login-api', 't-regr-run', 't-regr-report', 't-release-check']) {
      expect(within(nodeRow(id)).getByTestId('af-status-badge')).toBeInTheDocument();
    }
    // done 任务默认在主树 (已完成徽标)
    expect(within(nodeRow('t-reg-db')).getByText('已完成')).toBeInTheDocument();
  });

  it('优先级标签: P0/P1/P2/P3 对应色类 (来自 taskMeta; done 也在主树)', () => {
    render(<AfTodoTree tree={tree} taskMeta={meta} />);
    const p0 = within(nodeRow('t-release-check')).getByTestId('af-priority');
    expect(p0).toHaveTextContent('P0');
    expect(p0).toHaveClass('af-priority--P0');
    expect(within(nodeRow('t-reg-api')).getByTestId('af-priority')).toHaveClass('af-priority--P1');
    expect(within(nodeRow('t-regr-run')).getByTestId('af-priority')).toHaveClass('af-priority--P3');
    // done 任务 P2 默认在主树
    expect(within(nodeRow('t-reg-db')).getByTestId('af-priority')).toHaveClass('af-priority--P2');
  });

  it('无优先级数据 → 不渲染优先级标签 (若字段有才显示)', () => {
    // 任务无 priority 字段 + taskMeta 空 → 全树无优先级徽标
    const noPrioTree: TodoTree = {
      root: {
        id: 'root', title: '无优先级项目', type: 'phase', status: 'pending',
        statusLabel: '待办', progress: 0, children: [
          {
            id: 'm1', title: '模块一', type: 'module', status: 'pending',
            statusLabel: '待办', progress: 0, children: [
              {
                id: 's1', title: '故事一', type: 'task', status: 'pending',
                statusLabel: '待办', progress: 0, children: [
                  { id: 't1', title: '任务一', type: 'task', status: 'pending', statusLabel: '待办', progress: 0, children: [] },
                ],
              },
            ],
          },
        ],
      },
    };
    render(<AfTodoTree tree={noPrioTree} taskMeta={{}} />);
    expect(screen.queryAllByTestId('af-priority')).toHaveLength(0);
  });

  it('叶子任务额外字段: 负责人 (taskMeta.owner) / 开始时间 / 下一步 (若字段有)', () => {
    // 负责人来自 taskMeta (真实 assignee 投影)
    render(<AfTodoTree tree={tree} taskMeta={meta} />);
    expect(within(nodeRow('t-reg-api')).getByText('developer')).toBeInTheDocument();
    // done 任务 t-reg-db 负责人默认在主树
    expect(within(nodeRow('t-reg-db')).getByText('developer')).toBeInTheDocument();
    // 开始时间/下一步: 手工节点带字段 (Adapter 当前不投影, 组件按"若字段有"诚实展示)
    const richTree: TodoTree = {
      root: {
        id: 'root',
        title: '手工项目',
        type: 'phase',
        status: 'running',
        statusLabel: '执行中',
        progress: 50,
        children: [
          {
            id: 'phase-1',
            title: '开发',
            type: 'phase',
            status: 'running',
            statusLabel: '执行中',
            progress: 50,
            children: [
              {
                id: 't-x',
                title: '联调任务',
                type: 'task',
                status: 'running',
                statusLabel: '执行中',
                progress: 50,
                startedAt: '2026-08-12T00:00:00Z',
                nextAction: '联调数据库',
                owner: 'dev-agent',
                children: [],
              },
            ],
          },
        ],
      },
    };
    render(<AfTodoTree tree={richTree} taskMeta={{}} />);
    expect(within(nodeRow('t-x')).getByText('dev-agent')).toBeInTheDocument();
    expect(within(nodeRow('t-x')).getByText('下一步: 联调数据库')).toBeInTheDocument();
    expect(within(nodeRow('t-x')).getByText(/^开始/)).toBeInTheDocument();
  });

  it('折叠/展开: 单击箭头隐藏/显示子节点 (aria-expanded 跟随)', async () => {
    const user = userEvent.setup();
    render(<AfTodoTree tree={tree} taskMeta={meta} />);
    const toggle = within(nodeRow('epic-dev')).getByRole('button', { name: '折叠 开发阶段' });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await user.click(toggle);
    // 子节点行隐藏, 折叠摘要显示子模块名 (Founder: 不清楚里面是什么)
    expect(screen.queryByTestId('af-tree-node-feat-user')).not.toBeInTheDocument();
    expect(screen.getByTestId('af-tree-summary-epic-dev')).toHaveTextContent('用户系统');
    expect(within(nodeRow('epic-dev')).getByRole('button', { name: '展开 开发阶段' })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    await user.click(within(nodeRow('epic-dev')).getByRole('button', { name: '展开 开发阶段' }));
    expect(screen.getByText('用户系统')).toBeInTheDocument();
  });

  it('折叠摘要: 子节点名与节点同名 (legacy M2→feature=M2) → 钻取叶子任务名', async () => {
    const user = userEvent.setup();
    const legacyTree: TodoTree = {
      root: {
        id: 'root', title: '项目', type: 'phase', status: 'pending', statusLabel: '待办', progress: 0,
        children: [
          {
            id: 'M2', title: 'M2', type: 'phase', status: 'pending', statusLabel: '待办', progress: 0,
            children: [
              {
                id: 'M2-feat', title: 'M2', type: 'module', status: 'pending', statusLabel: '待办', progress: 0,
                children: [
                  {
                    id: 'M2-story', title: 'M2 · M2', type: 'task', status: 'pending', statusLabel: '待办', progress: 0,
                    children: [
                      { id: 't1', title: '**AgentEntity** 统一字段', type: 'task', status: 'pending', statusLabel: '待办', progress: 0, children: [] },
                      { id: 't2', title: '**AgentRegistry** 工厂层', type: 'task', status: 'pending', statusLabel: '待办', progress: 0, children: [] },
                      { id: 't3', title: 'ExpertFactory 装配器', type: 'task', status: 'pending', statusLabel: '待办', progress: 0, children: [] },
                      { id: 't4', title: 'HandoffBus 交接', type: 'task', status: 'pending', statusLabel: '待办', progress: 0, children: [] },
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
    };
    render(<AfTodoTree tree={legacyTree} />);
    // 默认展开 → 先折叠 M2 才出现摘要 (M2 module 也有同名按钮 → 用 epic 行内按钮)
    await user.click(within(nodeRow('M2')).getByRole('button', { name: '折叠 M2' }));
    const summary = screen.getByTestId('af-tree-summary-M2');
    expect(summary).toHaveTextContent('**AgentEntity** 统一字段');
    expect(summary).toHaveTextContent('ExpertFactory 装配器');
    expect(summary).toHaveTextContent('等4个');
    expect(summary).not.toHaveTextContent('M2 · M2');
  });

  it('多维筛选: 按优先级 P0 + 按更新时间 (Founder 2026-08-27)', async () => {
    const user = userEvent.setup();
    const backlog = sampleTodoBacklog({
      tasks: [
        { ...sampleTodoBacklog().tasks![0], id: 'T-p0', title: 'P0任务', status: 'todo', priority: 'P0', updated_at: '2026-08-27T00:00:00Z' },
        { ...sampleTodoBacklog().tasks![1], id: 'T-p2', title: 'P2任务', status: 'todo', priority: 'P2', updated_at: '2026-08-20T00:00:00Z' },
      ],
      epics: [{ ...sampleTodoBacklog().epics![0], id: 'E1', children: ['F1'] }],
      features: [{ ...sampleTodoBacklog().features![0], id: 'F1', children: ['S1'] }],
      stories: [{ ...sampleTodoBacklog().stories![0], id: 'S1', children: ['T-p0', 'T-p2'] }],
    });
    const tree = toTodoTree(backlog, '演示项目');
    render(<AfTodoTree tree={tree} />);
    // 选优先级 P0 → 只显示 P0 任务
    await user.selectOptions(screen.getByTestId('af-filter-priority'), 'P0');
    expect(screen.getByText(/P0任务/)).toBeInTheDocument();
    expect(screen.queryByText(/P2任务/)).not.toBeInTheDocument();
    // 清优先级 + 选时间 今日 → 只显示今日更新
    await user.selectOptions(screen.getByTestId('af-filter-priority'), 'all');
    await user.selectOptions(screen.getByTestId('af-filter-time'), 'today');
    expect(screen.getByText(/P0任务/)).toBeInTheDocument(); // 今日
    expect(screen.queryByText(/P2任务/)).not.toBeInTheDocument(); // 08-20 非今日
  });

  it('任务链进度摘要 (同一任务链逐链) + 排序切换 (Founder 2026-08-27)', async () => {
    const user = userEvent.setup();
    const backlog = sampleTodoBacklog({
      tasks: [
        { ...sampleTodoBacklog().tasks![0], id: 'T-a', title: 'A', status: 'todo', priority: 'P1', description: '[X-1] x', updated_at: '2026-08-20T00:00:00Z' },
        { ...sampleTodoBacklog().tasks![1], id: 'T-b', title: 'B', status: 'todo', priority: 'P0', description: '[X-2] x', updated_at: '2026-08-22T00:00:00Z' },
        { ...sampleTodoBacklog().tasks![2], id: 'T-c', title: 'C', status: 'done', priority: 'P0', description: '[X-3] x', updated_at: '2026-08-19T00:00:00Z' },
      ],
      epics: [{ ...sampleTodoBacklog().epics![0], id: 'E1', children: ['F1'] }],
      features: [{ ...sampleTodoBacklog().features![0], id: 'F1', children: ['S1'] }],
      stories: [{ ...sampleTodoBacklog().stories![0], id: 'S1', children: ['T-a', 'T-b', 'T-c'] }],
    });
    const chain = buildChainLines(backlog);
    expect(chain.length).toBe(1); // 只统计战役任务链 (S/T/U/V/X), 其他系列不混入
    expect(chain[0]).toContain('X-3✅'); // done → ✅ (同一任务链, 不筛优先级)
    expect(chain[0]).toContain('X 链 1/3');
    expect(chain[0]).toContain('剩 X-1·X-2'); // X-1 P1 也在链上
    render(<AfTodoTree tree={toTodoTree(backlog, '演示项目')} chainProgress={chain} />);
    expect(screen.getByTestId('af-tree-chain-progress')).toHaveTextContent('X-3✅');
    // 排序切换: 默认时间倒序 (T-b 08-22 最新) → 切优先级 (P0 前; done 任务也在主树)
    const storyChildren = () =>
      [...document.querySelectorAll('[data-testid^="af-tree-node-T-"]')].map((n) => n.getAttribute('data-node-id'));
    expect(storyChildren()).toHaveLength(3); // done T-c 也在主树
    expect(storyChildren()[0]).toBe('T-b'); // 时间倒序: T-b 08-22 最新
    await user.click(screen.getByTestId('af-sort-toggle'));
    expect(storyChildren()[0]).toBe('T-b'); // 优先级: P0 前 (T-b 08-22 比 T-c 08-19 新)
    expect(storyChildren()[1]).toBe('T-c'); // T-c P0 done 也在主树
    expect(storyChildren()[2]).toBe('T-a'); // T-a P1 次之
  });

  it('父行完成计数: N/M 完成 (含已归档), 百分比可对账 (Founder 2026-08-27)', () => {
    render(<AfTodoTree tree={tree} taskMeta={meta} />);
    // root: 6 任务 1 done (t-reg-db 归档隐藏) → 1/6 完成, 与 17% 对得上
    expect(screen.getByTestId('af-tree-count-root')).toHaveTextContent('1/6 完成');
    // story-reg: 2 子任务, 1 done 归档 + 1 执行中 → 1/2 完成
    expect(within(screen.getByTestId('af-tree-node-story-reg')).getByTestId('af-tree-count-story-reg')).toHaveTextContent('1/2 完成');
    // done 子任务默认在主树 → 百分比与可见子任务直接对得上
    expect(screen.getByTestId('af-tree-node-t-reg-db')).toBeInTheDocument();
  });

  it('主任务有未完成子任务 → 不归档, 树内聚合显示 (Founder 2026-08-27)', async () => {
    // legacy M2 结构: 主任务 M2-1 标 done 但有 2 个 todo 子任务 → 应留在主树, 不归档
    const backlog = sampleTodoBacklog({
      epics: [{ id: 'E1', name: 'M2', description: '', children: ['F1'], created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z' }],
      features: [{ id: 'F1', name: 'M2', description: '', children: ['S1'], created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z' }],
      stories: [{ id: 'S1', name: 'M2 · M2', description: '', children: ['M2-1', 'M2-2'], created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z' }],
      tasks: [
        { id: 'M2-1', title: '主任务', description: '', status: 'done', priority: 'P0', assignee: '', dependency: [], created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z', history: [], children: ['M2-1-1', 'M2-1-2'] },
        { id: 'M2-1-1', title: '子任务A', description: '', status: 'todo', priority: 'P1', assignee: '', dependency: [], created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z', history: [] },
        { id: 'M2-1-2', title: '子任务B', description: '', status: 'todo', priority: 'P1', assignee: '', dependency: [], created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z', history: [] },
        { id: 'M2-2', title: '独立任务', description: '', status: 'done', priority: 'P2', assignee: '', dependency: [], created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z', history: [] },
      ],
    });
    render(<AfTodoTree tree={toTodoTree(backlog, '演示')} taskMeta={sampleTaskMeta(backlog)} />);
    // 主任务在主树 (有子任务未完成 → 不归档), 状态聚合为待办
    const parent = screen.getByTestId('af-tree-node-M2-1');
    expect(parent).toBeInTheDocument();
    expect(within(parent).getByText('待办')).toBeInTheDocument();
    // 子任务在主树
    expect(screen.getByTestId('af-tree-node-M2-1-1')).toBeInTheDocument();
    expect(screen.getByTestId('af-tree-node-M2-1-2')).toBeInTheDocument();
    // 独立 done 任务 M2-2 默认也在主树 (已完成任务要在列表里)
    expect(screen.getByTestId('af-tree-node-M2-2')).toBeInTheDocument();
    expect(screen.getByTestId('af-tree-count-M2-1')).toHaveTextContent('0/2 完成');
    // 开启「隐藏已完成」→ M2-2 归入归档区, 主任务 M2-1 (有未完成子任务) 仍留主树
    const user = userEvent.setup();
    await user.click(screen.getByTestId('af-tree-hide-completed-toggle'));
    expect(screen.queryByTestId('af-tree-node-M2-2')).not.toBeInTheDocument();
    expect(screen.getByTestId('af-tree-node-M2-1')).toBeInTheDocument();
  });

  it('全折叠/全展开: 工具栏按钮一键收起/展开全部', async () => {
    const user = userEvent.setup();
    render(<AfTodoTree tree={tree} taskMeta={meta} />);
    await user.click(screen.getByRole('button', { name: '全折叠' }));
    expect(screen.queryByTestId('af-tree-node-feat-user')).not.toBeInTheDocument();
    expect(screen.queryByTestId('af-tree-node-t-reg-api')).not.toBeInTheDocument();
    // 项目头 + 工具栏仍在 (不空白)
    expect(screen.getByText('演示项目')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '全展开' }));
    expect(screen.getByText('实现注册 API')).toBeInTheDocument();
  });

  it('过滤 [执行中]: 只显示执行中任务及其祖先', async () => {
    const user = userEvent.setup();
    render(<AfTodoTree tree={tree} taskMeta={meta} />);
    await user.click(screen.getByRole('button', { name: '执行中' }));
    expect(screen.getByText('实现注册 API')).toBeInTheDocument();
    // 非执行中任务隐藏
    expect(screen.queryByText('用户数据模型')).not.toBeInTheDocument(); // completed
    expect(screen.queryByText('实现登录 API')).not.toBeInTheDocument(); // blocked
    expect(screen.queryByText('回归测试执行')).not.toBeInTheDocument(); // review
    // 祖先保留
    expect(screen.getByText('开发阶段')).toBeInTheDocument();
    expect(screen.getByText('用户系统')).toBeInTheDocument();
    expect(screen.getByText('用户注册')).toBeInTheDocument();
    // 无匹配分支整体隐藏
    expect(screen.queryByText('质量保障')).not.toBeInTheDocument();
  });

  it('过滤 [阻塞]: 阻塞任务可见, 其他隐藏', async () => {
    const user = userEvent.setup();
    render(<AfTodoTree tree={tree} taskMeta={meta} />);
    await user.click(screen.getByRole('button', { name: '阻塞' }));
    expect(screen.getByText('实现登录 API')).toBeInTheDocument();
    expect(screen.getByText('用户登录')).toBeInTheDocument(); // 祖先
    expect(screen.queryByText('实现注册 API')).not.toBeInTheDocument();
    expect(screen.queryByText('回归测试')).not.toBeInTheDocument();
  });

  it('过滤 [待审核] 与 [失败]: 各自状态可见', async () => {
    const user = userEvent.setup();
    render(<AfTodoTree tree={tree} taskMeta={meta} />);
    await user.click(screen.getByRole('button', { name: '待审核' }));
    expect(screen.getByText('回归测试执行')).toBeInTheDocument();
    expect(screen.queryByText('测试报告')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '失败' }));
    expect(screen.getByText('测试报告')).toBeInTheDocument();
    expect(screen.queryByText('回归测试执行')).not.toBeInTheDocument();
  });

  it('过滤无匹配 → 空态 "没有匹配的任务" (禁空白)', async () => {
    const user = userEvent.setup();
    const pendingOnly = toTodoTree(
      {
        project_id: 'p1',
        epics: [{ id: 'e1', name: '阶段一', children: ['f1'] }],
        features: [{ id: 'f1', name: '模块一', children: ['s1'] }],
        stories: [{ id: 's1', name: '故事一', children: ['t1'] }],
        tasks: [
          {
            id: 't1',
            title: '待办任务',
            priority: 'P1',
            status: 'todo',
            assignee: '',
            dependency: [],
            created_at: null,
            updated_at: null,
            history: [],
          },
        ],
      },
      '纯待办项目',
    );
    render(<AfTodoTree tree={pendingOnly} taskMeta={{ t1: { priority: 'P1' } }} />);
    await user.click(screen.getByRole('button', { name: '执行中' }));
    expect(screen.getByTestId('af-empty-state')).toHaveTextContent('没有匹配的任务');
    expect(screen.queryByText('待办任务')).not.toBeInTheDocument();
  });

  it('空树 (无阶段) → AfEmptyState "暂无任务 — AI 正在规划" (禁空白)', () => {
    const emptyTree: TodoTree = {
      root: {
        id: 'root',
        title: '空项目',
        type: 'phase',
        status: 'pending',
        statusLabel: '待办',
        progress: 0,
        children: [],
      },
    };
    render(<AfTodoTree tree={emptyTree} taskMeta={{}} />);
    expect(screen.getByTestId('af-empty-state')).toBeInTheDocument();
    expect(screen.getByText('暂无任务 — AI 正在规划')).toBeInTheDocument();
  });

  it('onSelectTask: 点击任务节点 → 回调 taskId', async () => {
    const user = userEvent.setup();
    const onSelectTask = vi.fn();
    render(<AfTodoTree tree={tree} taskMeta={meta} onSelectTask={onSelectTask} />);
    await user.click(screen.getByText('实现注册 API'));
    expect(onSelectTask).toHaveBeenCalledTimes(1);
    expect(onSelectTask).toHaveBeenCalledWith('t-reg-api');
    await user.click(screen.getByText('用户注册'));
    expect(onSelectTask).toHaveBeenCalledWith('story-reg');
  });

  it('焦点高亮: 执行中节点带 af-tree-node--focus; done 任务也在主树', () => {
    render(<AfTodoTree tree={tree} taskMeta={meta} />);
    expect(nodeRow('t-reg-api')).toHaveClass('af-tree-node--focus'); // running
    expect(nodeRow('story-reg')).toHaveClass('af-tree-node--focus'); // running (聚合)
    // done 任务 t-reg-db 默认在主树 (已完成任务要在列表里)
    expect(screen.getByTestId('af-tree-node-t-reg-db')).toBeInTheDocument();
  });
});
