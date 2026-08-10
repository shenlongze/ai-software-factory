/**
 * src/test/suggest-flow.test.tsx — S10-007 收尾: 想法确认对话前端测试。
 *
 * 覆盖 Welcome 两阶段创建 (输入想法 → [分析需求] loading → AI 理解卡片:
 * 名称可编辑+slug+摘要+澄清问题 → [确认创建]/[重新分析]) + 快速模式标注
 * (ai_generated=false 诚实 fallback) + 失败可重试 + 旧直接创建兼容 (无 name)。
 * 唯一 basename, 不与 workspace-shell/project-mgmt 测试冲突。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '../design/theme';
import { AppStateProvider } from '../state/AppState';
import { WorkspaceShell } from '../shell/WorkspaceShell';
import type { IdeaSuggestion } from '../models/types';

/** jsdom EventSource 桩 (选中项目后 AgentTimeline 订阅 SSE 用)。 */
class FakeEventSource {
  static instances: FakeEventSource[] = [];

  url: string;
  listeners: Record<string, Array<(ev: MessageEvent<string>) => void>> = {};
  onerror: ((ev: Event) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, cb: (ev: MessageEvent<string>) => void): void {
    (this.listeners[name] ??= []).push(cb);
  }

  close(): void {
    this.closed = true;
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});

/** 只读 JSON 响应 (client 只消费 ok + json())。 */
function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function jsonError(status: number, detail: string): Response {
  return { ok: false, status, json: async () => ({ detail }) } as Response;
}

/** AI 模式建议 (真实 LLM 返回; ai_generated=true + 2 澄清问题)。 */
const SUGGESTION: IdeaSuggestion = {
  idea: '一个记账 App',
  suggested_name: '记账小助手',
  slug: 'ledger-app',
  summary: '一个简洁的个人记账与月度统计工具',
  questions: ['需要多用户支持吗?', '需要报表导出吗?'],
  ai_generated: true,
};

/** 快速模式建议 (诚实 fallback; ai_generated=false + 无问题)。 */
const QUICK_SUGGESTION: IdeaSuggestion = {
  idea: '一个待办清单 App',
  suggested_name: '待办清单',
  slug: 'todo-app',
  summary: 'AI 理解暂不可用 — 已按规则从想法中提炼项目名 (快速模式)',
  questions: [],
  ai_generated: false,
};

const CREATED = {
  project_id: 'ledger-new',
  name: '记账小助手',
  idea: '一个记账 App',
  status: 'active',
};

/** 方法感知 fetch 桩 (GET/POST /api/projects + suggest + 工作台轮询路径)。 */
function makeFetch(options: {
  suggest?: IdeaSuggestion;
  suggestGate?: Promise<void>;
  suggestFail?: boolean;
  createGate?: Promise<void>;
  createFail?: boolean;
  created?: typeof CREATED;
} = {}): ReturnType<typeof vi.fn> {
  const created = options.created ?? CREATED;
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? 'GET';
    if (path === '/api/projects/suggest') {
      if (options.suggestFail === true) return jsonError(503, 'llm unavailable');
      if (options.suggestGate != null) await options.suggestGate;
      return jsonResponse(options.suggest ?? SUGGESTION);
    }
    if (path === '/api/projects' && method === 'POST') {
      if (options.createFail === true) return jsonError(500, 'store unavailable');
      if (options.createGate != null) await options.createGate;
      const body = JSON.parse(String(init?.body ?? '{}')) as { idea?: string; name?: string };
      return jsonResponse({
        ...created,
        name: body.name && body.name.length > 0 ? body.name : created.name,
        idea: body.idea ?? created.idea,
      });
    }
    if (path === '/api/projects' && method === 'GET') return jsonResponse([]);
    if (path === '/api/projects/ledger-new/timeline?limit=200') return jsonResponse([]);
    if (path === '/api/projects/ledger-new/run-status') {
      return jsonResponse({ project_id: 'ledger-new', status: 'none', current_run_id: null, runs: [] });
    }
    return jsonError(404, 'not found');
  });
}

/** 渲染 Workspace Shell (双 Provider 与 main.tsx 一致) + 注册 fetch 桩。 */
function renderShell(fetchMock: ReturnType<typeof vi.fn> = makeFetch()): ReturnType<typeof vi.fn> {
  try {
    window.localStorage.clear();
  } catch {
    /* 忽略 */
  }
  document.documentElement.dataset.theme = 'light';
  vi.stubGlobal('fetch', fetchMock);
  render(
    <AppStateProvider>
      <ThemeProvider>
        <WorkspaceShell />
      </ThemeProvider>
    </AppStateProvider>,
  );
  return fetchMock;
}

/** 输入想法 → 点击 [分析需求]。 */
async function typeIdeaAndAnalyze(text = '一个记账 App'): Promise<void> {
  const user = userEvent.setup();
  fireEvent.change(screen.getByTestId('ws-create-input'), { target: { value: text } });
  await user.click(screen.getByTestId('ws-suggest-submit'));
}

describe('想法确认对话 — 阶段一: 分析需求', () => {
  it('Welcome 首屏: [分析需求] 主按钮 + [开始生产] 保留 (旧直接创建兼容)', () => {
    renderShell();
    expect(screen.getByTestId('ws-suggest-submit')).toHaveTextContent('分析需求');
    expect(screen.getByRole('button', { name: '开始生产' })).toBeInTheDocument();
  });

  it('空想法 → 错误提示 + 不发 suggest 请求', async () => {
    const fetchMock = renderShell();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('ws-suggest-submit'));
    expect(screen.getByTestId('ws-create-error')).toHaveTextContent('请先输入你想开发的软件');
    const suggestCalls = fetchMock.mock.calls.filter(([path]) => String(path) === '/api/projects/suggest');
    expect(suggestCalls).toHaveLength(0);
  });

  it('点击 [分析需求] → loading (分析中… + 按钮禁用) 直到响应返回', async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderShell(makeFetch({ suggestGate: gate }));
    await typeIdeaAndAnalyze();
    // 响应未返回 → 按钮 loading 态 (文案 + 禁用 + aria-busy)
    expect(screen.getByTestId('ws-suggest-submit')).toHaveTextContent('分析中…');
    expect(screen.getByTestId('ws-suggest-submit')).toBeDisabled();
    expect(screen.getByTestId('ws-suggest-submit')).toHaveAttribute('aria-busy', 'true');
    release();
    expect(await screen.findByTestId('ws-suggest-card')).toBeInTheDocument();
  });

  it('POST /api/projects/suggest 调用形状: {idea} 原样透传', async () => {
    const fetchMock = renderShell();
    await typeIdeaAndAnalyze('开发一个博客网站');
    await screen.findByTestId('ws-suggest-card');
    const suggestCall = fetchMock.mock.calls.find(([path]) => String(path) === '/api/projects/suggest');
    expect(suggestCall).toBeDefined();
    const [, init] = suggestCall as unknown as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ idea: '开发一个博客网站' });
  });
});

describe('想法确认对话 — 阶段二: AI 理解卡片', () => {
  it('卡片渲染: 名称预填 suggested_name + slug 提示 + 摘要 + 澄清问题列表', async () => {
    renderShell();
    await typeIdeaAndAnalyze();
    const card = await screen.findByTestId('ws-suggest-card');
    expect(card).toBeInTheDocument();
    expect(screen.getByTestId('ws-suggest-name')).toHaveValue('记账小助手');
    expect(screen.getByTestId('ws-suggest-slug')).toHaveTextContent('slug: ledger-app');
    expect(screen.getByTestId('ws-suggest-summary')).toHaveTextContent('简洁的个人记账');
    const questions = screen.getByTestId('ws-suggest-questions');
    expect(questions).toBeInTheDocument();
    expect(screen.getByTestId('ws-suggest-question-0')).toHaveTextContent('需要多用户支持吗?');
    expect(screen.getByTestId('ws-suggest-question-1')).toHaveTextContent('需要报表导出吗?');
  });

  it('AI 模式 (ai_generated=true) → 无「快速模式」标注', async () => {
    renderShell();
    await typeIdeaAndAnalyze();
    await screen.findByTestId('ws-suggest-card');
    expect(screen.queryByTestId('ws-suggest-quick')).toBeNull();
  });

  it('快速模式 (ai_generated=false) → 卡片标注「快速模式」+ 无澄清问题区', async () => {
    renderShell(makeFetch({ suggest: QUICK_SUGGESTION }));
    await typeIdeaAndAnalyze('一个待办清单 App');
    await screen.findByTestId('ws-suggest-card');
    expect(screen.getByTestId('ws-suggest-quick')).toHaveTextContent('快速模式');
    expect(screen.queryByTestId('ws-suggest-questions')).toBeNull();
    // 名称仍预填规则提炼结果 (诚实: 规则提炼不冒充 AI)
    expect(screen.getByTestId('ws-suggest-name')).toHaveValue('待办清单');
  });

  it('AI 模式但 questions 为空 → 不渲染问题区', async () => {
    renderShell(makeFetch({ suggest: { ...SUGGESTION, questions: [] } }));
    await typeIdeaAndAnalyze();
    await screen.findByTestId('ws-suggest-card');
    expect(screen.queryByTestId('ws-suggest-questions')).toBeNull();
  });
});

describe('想法确认对话 — 确认创建 / 重新分析', () => {
  it('编辑名称 → [确认创建] → POST /api/projects {idea, name} → 进入项目工作台', async () => {
    const fetchMock = renderShell();
    await typeIdeaAndAnalyze();
    await screen.findByTestId('ws-suggest-card');
    fireEvent.change(screen.getByTestId('ws-suggest-name'), { target: { value: '我的记账本' } });
    const user = userEvent.setup();
    await user.click(screen.getByTestId('ws-suggest-confirm'));

    // POST 调用形状: {idea, name} (用户编辑后的名称显式落库)
    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([path, init]) => String(path) === '/api/projects' && (init as RequestInit | undefined)?.method === 'POST',
      );
      expect(createCall).toBeDefined();
      const [, init] = createCall as unknown as [string, RequestInit];
      expect(JSON.parse(String(init.body))).toEqual({ idea: '一个记账 App', name: '我的记账本' });
    });

    // 创建成功 → Shell 选中新项目 → 项目工作台 (显示回显名)
    expect(await screen.findByTestId('ws-project-workspace')).toBeInTheDocument();
    expect(screen.getByTestId('ws-project-name')).toHaveTextContent('我的记账本');
    expect(screen.queryByTestId('ws-suggest-card')).toBeNull();
  });

  it('确认创建进行中 → 按钮 loading (创建中… + 禁用)', async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderShell(makeFetch({ createGate: gate }));
    await typeIdeaAndAnalyze();
    await screen.findByTestId('ws-suggest-card');
    const user = userEvent.setup();
    await user.click(screen.getByTestId('ws-suggest-confirm'));
    expect(screen.getByTestId('ws-suggest-confirm')).toHaveTextContent('创建中…');
    expect(screen.getByTestId('ws-suggest-confirm')).toBeDisabled();
    release();
    expect(await screen.findByTestId('ws-project-workspace')).toBeInTheDocument();
  });

  it('确认创建失败 → 卡片内错误提示 + 卡片停留 (可重试)', async () => {
    const fetchMock = renderShell(makeFetch({ createFail: true }));
    await typeIdeaAndAnalyze();
    await screen.findByTestId('ws-suggest-card');
    const user = userEvent.setup();
    await user.click(screen.getByTestId('ws-suggest-confirm'));

    expect(await screen.findByTestId('ws-suggest-confirm-error')).toHaveTextContent('HTTP 500');
    expect(screen.getByTestId('ws-suggest-card')).toBeInTheDocument(); // 卡片停留
    // 无重试风暴: 一次点击只发一次 POST
    const createCalls = fetchMock.mock.calls.filter(
      ([path, init]) => String(path) === '/api/projects' && (init as RequestInit | undefined)?.method === 'POST',
    );
    expect(createCalls).toHaveLength(1);
  });

  it('[重新分析] → 收起卡片回输入态 (想法保留) → 再次分析发第二次 suggest', async () => {
    const fetchMock = renderShell();
    await typeIdeaAndAnalyze();
    await screen.findByTestId('ws-suggest-card');
    const user = userEvent.setup();
    await user.click(screen.getByTestId('ws-suggest-reanalyze'));

    // 回输入态: 卡片消失 + 输入框想法保留
    expect(screen.queryByTestId('ws-suggest-card')).toBeNull();
    expect(screen.getByTestId('ws-create-input')).toHaveValue('一个记账 App');
    await user.click(screen.getByTestId('ws-suggest-submit'));
    await screen.findByTestId('ws-suggest-card');
    const suggestCalls = fetchMock.mock.calls.filter(([path]) => String(path) === '/api/projects/suggest');
    expect(suggestCalls).toHaveLength(2);
  });
});

describe('想法确认对话 — 失败可重试 / 旧兼容', () => {
  it('suggest 失败 → 错误提示 (HTTP 503) + 表单停留, 可重试成功', async () => {
    let fail = true;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? 'GET';
      if (path === '/api/projects/suggest') {
        if (fail) return jsonError(503, 'llm unavailable');
        return jsonResponse(SUGGESTION);
      }
      if (path === '/api/projects' && method === 'POST') {
        return jsonResponse({ ...CREATED, name: '记账小助手' });
      }
      if (path === '/api/projects' && method === 'GET') return jsonResponse([]);
      if (path === '/api/projects/ledger-new/timeline?limit=200') return jsonResponse([]);
      if (path === '/api/projects/ledger-new/run-status') {
        return jsonResponse({ project_id: 'ledger-new', status: 'none', current_run_id: null, runs: [] });
      }
      return jsonError(404, 'not found');
    });
    renderShell(fetchMock);

    await typeIdeaAndAnalyze();
    expect(await screen.findByTestId('ws-create-error')).toHaveTextContent('HTTP 503');
    expect(screen.queryByTestId('ws-suggest-card')).toBeNull(); // 不假装出卡片

    // 可重试: 后端恢复 → 再次分析成功
    fail = false;
    const user = userEvent.setup();
    await user.click(screen.getByTestId('ws-suggest-submit'));
    expect(await screen.findByTestId('ws-suggest-card')).toBeInTheDocument();
    expect(screen.queryByTestId('ws-create-error')).toBeNull();
  });

  it('旧直接创建兼容: [开始生产] → POST /api/projects 无 name 键 → 进入工作台', async () => {
    const fetchMock = renderShell();
    const user = userEvent.setup();
    fireEvent.change(screen.getByTestId('ws-create-input'), { target: { value: '一个记账 App' } });
    await user.click(screen.getByTestId('ws-create-submit'));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([path, init]) => String(path) === '/api/projects' && (init as RequestInit | undefined)?.method === 'POST',
      );
      expect(createCall).toBeDefined();
      const [, init] = createCall as unknown as [string, RequestInit];
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      expect(body).toEqual({ idea: '一个记账 App' });
      expect('name' in body).toBe(false);
    });
    expect(await screen.findByTestId('ws-project-workspace')).toBeInTheDocument();
  });

  it('示例 chips 点击 → 填入输入框 → 分析需求携带示例文本', async () => {
    const fetchMock = renderShell();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('ws-example-chip-0')); // '一个记账 App'
    expect(screen.getByTestId('ws-create-input')).toHaveValue('一个记账 App');
    await user.click(screen.getByTestId('ws-suggest-submit'));
    await screen.findByTestId('ws-suggest-card');
    const suggestCall = fetchMock.mock.calls.find(([path]) => String(path) === '/api/projects/suggest');
    const [, init] = suggestCall as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ idea: '一个记账 App' });
  });
});
