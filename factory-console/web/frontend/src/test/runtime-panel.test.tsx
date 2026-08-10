/**
 * src/test/runtime-panel.test.tsx — S10-004 Runtime Workspace Panel 测试。
 *
 * 覆盖 (Instances 列表 / Create Modal / Browser iframe 工具栏 / Terminal mock
 * 流 / 状态徽章 / 空态 / mock fallback 诚实标注 / Screenshot 预留 / Timeline
 * 联动 / REST 轮询 / 纯函数):
 * - runtimeClient S10-004 新方法: listRuntimes (mock fallback) / createRuntime
 *   (POST) / screenshotRuntime (POST)
 * - RuntimePanel 直接渲染: 卡片 (类型图标/状态徽章/Artifact/时间) / Browser
 *   iframe + 工具栏 (刷新/截图/新窗口) / Terminal mock stream (演示标注) /
 *   空态 / 演示数据徽章 / Create Modal / 轮询 2s 状态刷新 / 卸载停止轮询
 * - Timeline 联动 (WorkspaceShell 集成): artifact 查看 → Runtime Tab 激活 +
 *   定位绑定实例或提示创建
 * 唯一 basename, 不与 S10-001/002/003 测试冲突; 不删既有测试。
 */

import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RUNTIME_POLL_MS, runtimeClient } from '../api/runtimeClient';
import { ThemeProvider } from '../design/theme';
import { AppStateProvider } from '../state/AppState';
import { WorkspaceShell } from '../shell/WorkspaceShell';
import {
  RuntimePanel,
  TERMINAL_MOCK_LINES,
  TerminalMockStream,
  formatRuntimeTime,
} from '../shell/RuntimePanel';
import type { RuntimeInstance } from '../models/types';
import { stubFetch } from './fixtures';

const PROJECT = 'ledger-app';
const RUNTIMES_URL = `/api/projects/${PROJECT}/runtimes`;

/** 成功 JSON 响应 (client 只消费 ok + json())。 */
function okResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response;
}

/** RuntimeInstance 工厂 (形状对齐 models/types.ts RuntimeInstance)。 */
function runtimeInstance(
  id: string,
  overrides: Partial<RuntimeInstance> = {},
): RuntimeInstance {
  return {
    id,
    project_id: PROJECT,
    type: 'browser',
    status: 'running',
    artifact_id: null,
    url: null,
    session: null,
    created_at: '2026-08-10T00:05:00+00:00',
    ...overrides,
  };
}

function browserInstance(id: string, status: RuntimeInstance['status'] = 'running', artifactId: string | null = 'mock-art-ux_ui'): RuntimeInstance {
  return runtimeInstance(id, {
    type: 'browser',
    status,
    artifact_id: artifactId,
    url: 'http://sandbox.local/preview',
  });
}

function terminalInstance(id: string, status: RuntimeInstance['status'] = 'running', artifactId: string | null = 'mock-art-code'): RuntimeInstance {
  return runtimeInstance(id, {
    type: 'terminal',
    status,
    artifact_id: artifactId,
    session: `sess-${id}`,
  });
}

/** jsdom EventSource 桩 (AgentTimeline 订阅 SSE 用, 与 S10-003 测试同模式)。 */
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

afterEach(() => {
  vi.useRealTimers();
});

// ------------------------------------------------------------------ runtimeClient S10-004 方法
describe('runtimeClient — S10-004 Runtime REST 方法', () => {
  it('listRuntimes 成功 → {data, is_mock:false} (真实数据)', async () => {
    stubFetch({ [RUNTIMES_URL]: [browserInstance('rt-1')] });
    const got = await runtimeClient.listRuntimes(PROJECT);
    expect(got.is_mock).toBe(false);
    expect(got.data[0].id).toBe('rt-1');
    expect(got.data[0].type).toBe('browser');
  });

  it('listRuntimes 后端不可达 (ApiError) → mock 实例 + is_mock:true (诚实标注)', async () => {
    stubFetch({}); // 全 404 → ApiError → mock fallback
    const got = await runtimeClient.listRuntimes(PROJECT);
    expect(got.is_mock).toBe(true);
    expect(got.data.length).toBe(2); // browser + terminal 各一
    expect(got.data.some((inst) => inst.type === 'browser')).toBe(true);
    expect(got.data.some((inst) => inst.type === 'terminal')).toBe(true);
  });

  it('createRuntime → POST /api/projects/{id}/runtimes {type:browser}', async () => {
    stubFetch({ [RUNTIMES_URL]: runtimeInstance('rt-new', { type: 'browser' }) });
    const created = await runtimeClient.createRuntime(PROJECT, 'browser');
    expect(created.id).toBe('rt-new');
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
    const post = calls.find((call) => String(call[0]) === RUNTIMES_URL);
    expect(post).toBeDefined();
    const init = post?.[1] as RequestInit | undefined;
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ type: 'browser' });
  });

  it('createRuntime 带 artifactId → body 含 artifact_id', async () => {
    stubFetch({ [RUNTIMES_URL]: runtimeInstance('rt-new') });
    await runtimeClient.createRuntime(PROJECT, 'terminal', 'art-9');
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
    const post = calls.find((call) => String(call[0]) === RUNTIMES_URL);
    expect(post).toBeDefined();
    const init = post?.[1] as RequestInit | undefined;
    expect(JSON.parse(String(init?.body))).toEqual({
      type: 'terminal',
      artifact_id: 'art-9',
    });
  });

  it('screenshotRuntime → POST /api/runtimes/{id}/screenshot → RuntimeScreenshot', async () => {
    stubFetch({
      '/api/runtimes/rt-1/screenshot': {
        id: 'shot-1',
        instance_id: 'rt-1',
        project_id: PROJECT,
        artifact_id: 'shot-art-1',
        created_at: null,
      },
    });
    const shot = await runtimeClient.screenshotRuntime('rt-1');
    expect(shot.id).toBe('shot-1');
    expect(shot.artifact_id).toBe('shot-art-1');
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
    const post = calls.find((call) => String(call[0]) === '/api/runtimes/rt-1/screenshot');
    expect(post).toBeDefined();
    expect((post?.[1] as RequestInit | undefined)?.method).toBe('POST');
  });
});

// ------------------------------------------------------------------ Instances 列表
describe('RuntimePanel — Instances 列表', () => {
  it('渲染 browser + terminal 卡片 (类型标签/图标/状态)', async () => {
    stubFetch({ [RUNTIMES_URL]: [browserInstance('rt-b'), terminalInstance('rt-t')] });
    render(<RuntimePanel projectId={PROJECT} />);
    const browserCard = await screen.findByTestId('runtime-card-rt-b');
    const terminalCard = screen.getByTestId('runtime-card-rt-t');
    expect(browserCard).toHaveAttribute('data-runtime-type', 'browser');
    expect(terminalCard).toHaveAttribute('data-runtime-type', 'terminal');
    expect(within(browserCard).getByText('Browser Runtime')).toBeInTheDocument();
    expect(within(terminalCard).getByText('Terminal Runtime')).toBeInTheDocument();
    expect(within(browserCard).getByText('🌐')).toBeInTheDocument();
    expect(within(terminalCard).getByText('💻')).toBeInTheDocument();
  });

  it('卡片 meta: 绑定 Artifact + 实例 id + 创建时间 (未绑定 → 未绑定)', async () => {
    stubFetch({
      [RUNTIMES_URL]: [
        browserInstance('rt-a', 'running', 'art-ux'),
        runtimeInstance('rt-null', { type: 'terminal', artifact_id: null }),
      ],
    });
    render(<RuntimePanel projectId={PROJECT} />);
    const bound = await screen.findByTestId('runtime-card-rt-a');
    expect(within(bound).getByText('art-ux')).toBeInTheDocument();
    const unbound = screen.getByTestId('runtime-card-rt-null');
    expect(within(unbound).getByText('未绑定')).toBeInTheDocument();
    expect(within(unbound).getByText('rt-null')).toBeInTheDocument();
    expect(within(bound).getByText(/^\d{2}-\d{2} \d{2}:\d{2}$/)).toBeInTheDocument();
  });

  it('状态徽章: starting/running/stopped/error → 中文标签 + data-status', async () => {
    stubFetch({
      [RUNTIMES_URL]: [
        runtimeInstance('rt-1', { type: 'browser', status: 'starting' }),
        runtimeInstance('rt-2', { type: 'terminal', status: 'running' }),
        runtimeInstance('rt-3', { type: 'browser', status: 'stopped' }),
        runtimeInstance('rt-4', { type: 'terminal', status: 'error' }),
      ],
    });
    render(<RuntimePanel projectId={PROJECT} />);
    const card1 = await screen.findByTestId('runtime-card-rt-1');
    expect(card1).toHaveAttribute('data-status', 'starting');
    expect(within(card1).getByText('启动中')).toBeInTheDocument();
    expect(screen.getByTestId('runtime-card-rt-2')).toHaveAttribute('data-status', 'running');
    expect(within(screen.getByTestId('runtime-card-rt-2')).getByText('运行中')).toBeInTheDocument();
    expect(screen.getByTestId('runtime-card-rt-3')).toHaveAttribute('data-status', 'stopped');
    expect(within(screen.getByTestId('runtime-card-rt-3')).getByText('已停止')).toBeInTheDocument();
    expect(screen.getByTestId('runtime-card-rt-4')).toHaveAttribute('data-status', 'error');
    expect(within(screen.getByTestId('runtime-card-rt-4')).getByText('异常')).toBeInTheDocument();
  });

  it('空态: 空列表 → "还没有 Runtime — 点击 + 创建"', async () => {
    stubFetch({ [RUNTIMES_URL]: [] });
    render(<RuntimePanel projectId={PROJECT} />);
    const empty = await screen.findByTestId('runtime-panel-empty');
    expect(within(empty).getByText('还没有 Runtime — 点击 + 创建')).toBeInTheDocument();
  });

  it('mock fallback (无后端) → 演示数据徽章 + mock 实例渲染 (诚实标注)', async () => {
    stubFetch({}); // 全 404 → mockRuntimes fallback
    render(<RuntimePanel projectId={PROJECT} />);
    expect(await screen.findByTestId('runtime-panel-mock')).toHaveTextContent('演示数据');
    expect(await screen.findByTestId('runtime-card-mock-rt-browser-1')).toBeInTheDocument();
    expect(screen.getByTestId('runtime-card-mock-rt-terminal-1')).toBeInTheDocument();
  });

  it('真实数据 (is_mock=false) → 无演示数据徽章', async () => {
    stubFetch({ [RUNTIMES_URL]: [browserInstance('rt-1')] });
    render(<RuntimePanel projectId={PROJECT} />);
    await screen.findByTestId('runtime-card-rt-1');
    expect(screen.queryByTestId('runtime-panel-mock')).toBeNull();
  });
});

// ------------------------------------------------------------------ Create Modal
describe('RuntimePanel — Create Modal ([+] 创建)', () => {
  /** 404 响应 (stubFetch 未命中路径语义)。 */
  function notFound(): Response {
    return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) } as Response;
  }

  /** Runtime API 桩: GET 列表 (默认空) + POST 创建 (默认成功返回实例) 分方法。 */
  function stubRuntimeApi(list: unknown[], created: unknown): ReturnType<typeof vi.fn> {
    const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === RUNTIMES_URL) {
        if (init?.method === 'POST') return okResponse(created);
        return okResponse(list);
      }
      return notFound();
    });
    vi.stubGlobal('fetch', fn);
    return fn;
  }

  it('点击 + → Modal 打开 (Browser/Terminal 类型选项)', async () => {
    const user = userEvent.setup();
    stubFetch({ [RUNTIMES_URL]: [] });
    render(<RuntimePanel projectId={PROJECT} />);
    await screen.findByTestId('runtime-panel-empty');
    expect(screen.queryByTestId('ds-modal')).toBeNull();
    await user.click(screen.getByTestId('runtime-create-open'));
    const modal = screen.getByTestId('ds-modal');
    expect(within(modal).getByText('创建 Runtime')).toBeInTheDocument();
    expect(within(modal).getByTestId('create-browser')).toBeInTheDocument();
    expect(within(modal).getByTestId('create-terminal')).toBeInTheDocument();
  });

  it('选择 Browser Runtime → POST 创建 + Modal 关闭', async () => {
    const user = userEvent.setup();
    const fetchMock = stubRuntimeApi([], runtimeInstance('rt-new', { type: 'browser' }));
    render(<RuntimePanel projectId={PROJECT} />);
    await screen.findByTestId('runtime-panel-empty');
    await user.click(screen.getByTestId('runtime-create-open'));
    await user.click(screen.getByTestId('create-browser'));
    await waitFor(() => expect(screen.queryByTestId('ds-modal')).toBeNull());
    const post = fetchMock.mock.calls.find(
      (call) => String(call[0]) === RUNTIMES_URL && (call[1] as RequestInit | undefined)?.method === 'POST',
    );
    expect(post).toBeDefined();
    expect(JSON.parse(String((post?.[1] as RequestInit | undefined)?.body))).toEqual({ type: 'browser' });
  });

  it('选择 Terminal Runtime → POST {type:terminal}', async () => {
    const user = userEvent.setup();
    const fetchMock = stubRuntimeApi([], runtimeInstance('rt-t', { type: 'terminal' }));
    render(<RuntimePanel projectId={PROJECT} />);
    await screen.findByTestId('runtime-panel-empty');
    await user.click(screen.getByTestId('runtime-create-open'));
    await user.click(screen.getByTestId('create-terminal'));
    await waitFor(() => expect(screen.queryByTestId('ds-modal')).toBeNull());
    const post = fetchMock.mock.calls.find(
      (call) => String(call[0]) === RUNTIMES_URL && (call[1] as RequestInit | undefined)?.method === 'POST',
    );
    expect(post).toBeDefined();
    expect(JSON.parse(String((post?.[1] as RequestInit | undefined)?.body))).toEqual({ type: 'terminal' });
  });

  it('创建失败 (404) → 错误提示, Modal 保持 (诚实不掩盖)', async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch({ [RUNTIMES_URL]: [] });
    fetchMock.mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      if (String(input) === RUNTIMES_URL && init?.method === 'POST') return notFound();
      if (String(input) === RUNTIMES_URL) return okResponse([]);
      return notFound();
    });
    render(<RuntimePanel projectId={PROJECT} />);
    await screen.findByTestId('runtime-panel-empty');
    await user.click(screen.getByTestId('runtime-create-open'));
    await user.click(screen.getByTestId('create-terminal'));
    const error = await screen.findByTestId('runtime-create-error');
    expect(error).toHaveTextContent('创建失败');
    expect(screen.getByTestId('ds-modal')).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ Browser Instance
describe('RuntimePanel — Browser Instance (iframe + 工具栏)', () => {
  it('browser 实例: iframe 渲染 (src + sandbox 沙箱属性)', async () => {
    stubFetch({ [RUNTIMES_URL]: [browserInstance('rt-b')] });
    render(<RuntimePanel projectId={PROJECT} />);
    const iframe = await screen.findByTestId('runtime-iframe-rt-b');
    expect(iframe).toHaveAttribute('src', 'http://sandbox.local/preview');
    expect(iframe).toHaveAttribute('sandbox', 'allow-scripts allow-same-origin');
  });

  it('browser 无 url → 预览地址未就绪 (占位, 无 iframe)', async () => {
    stubFetch({
      [RUNTIMES_URL]: [runtimeInstance('rt-b', { type: 'browser', url: null })],
    });
    render(<RuntimePanel projectId={PROJECT} />);
    expect(await screen.findByTestId('runtime-unready-rt-b')).toHaveTextContent('预览地址未就绪');
    expect(screen.queryByTestId('runtime-iframe-rt-b')).toBeNull();
  });

  it('工具栏 刷新 → iframe 重挂载 (key 变化)', async () => {
    const user = userEvent.setup();
    stubFetch({ [RUNTIMES_URL]: [browserInstance('rt-b')] });
    render(<RuntimePanel projectId={PROJECT} />);
    const iframe1 = await screen.findByTestId('runtime-iframe-rt-b');
    await user.click(within(screen.getByTestId('runtime-toolbar-rt-b')).getByRole('button', { name: '刷新' }));
    const iframe2 = screen.getByTestId('runtime-iframe-rt-b');
    expect(iframe2).not.toBe(iframe1); // key 变化 → 新 DOM 节点
    expect(iframe2).toHaveAttribute('src', 'http://sandbox.local/preview');
  });

  it('工具栏 新窗口 → window.open(url, _blank)', async () => {
    const user = userEvent.setup();
    const openSpy = vi.fn(() => null);
    vi.spyOn(window, 'open').mockImplementation(openSpy);
    stubFetch({ [RUNTIMES_URL]: [browserInstance('rt-b')] });
    render(<RuntimePanel projectId={PROJECT} />);
    await screen.findByTestId('runtime-iframe-rt-b');
    await user.click(within(screen.getByTestId('runtime-toolbar-rt-b')).getByRole('button', { name: '新窗口' }));
    expect(openSpy).toHaveBeenCalledWith('http://sandbox.local/preview', '_blank', 'noopener');
  });

  it('Screenshot → POST /api/runtimes/{id}/screenshot → "已保存截图 artifact" 提示', async () => {
    const user = userEvent.setup();
    stubFetch({
      [RUNTIMES_URL]: [browserInstance('rt-b')],
      '/api/runtimes/rt-b/screenshot': {
        id: 'shot-1',
        instance_id: 'rt-b',
        project_id: PROJECT,
        artifact_id: 'shot-art-1',
        created_at: null,
      },
    });
    render(<RuntimePanel projectId={PROJECT} />);
    await screen.findByTestId('runtime-iframe-rt-b');
    await user.click(within(screen.getByTestId('runtime-toolbar-rt-b')).getByRole('button', { name: '截图' }));
    const notice = await screen.findByTestId('runtime-notice');
    expect(notice).toHaveTextContent('已保存截图 artifact shot-art-1');
    expect(notice).toHaveTextContent('rt-b');
  });

  it('Screenshot 失败 (409) → 错误提示 (截图门禁: 非 running 不可截)', async () => {
    const user = userEvent.setup();
    stubFetch({ [RUNTIMES_URL]: [browserInstance('rt-b')] });
    (fetch as unknown as ReturnType<typeof vi.fn>).mockImplementation(async (input: RequestInfo) => {
      if (String(input) === '/api/runtimes/rt-b/screenshot') {
        return { ok: false, status: 409, json: async () => ({ detail: 'runtime not running' }) } as Response;
      }
      if (String(input) === RUNTIMES_URL) {
        return okResponse([browserInstance('rt-b')]);
      }
      return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) } as Response;
    });
    render(<RuntimePanel projectId={PROJECT} />);
    await screen.findByTestId('runtime-iframe-rt-b');
    await user.click(within(screen.getByTestId('runtime-toolbar-rt-b')).getByRole('button', { name: '截图' }));
    const notice = await screen.findByTestId('runtime-notice');
    expect(notice).toHaveTextContent('截图失败');
    expect(notice).toHaveTextContent('409');
  });
});

// ------------------------------------------------------------------ Terminal Instance
describe('RuntimePanel — Terminal Instance (mock stream)', () => {
  it('terminal 实例: 终端样式等宽流渲染 (npm test/build 模拟)', async () => {
    stubFetch({ [RUNTIMES_URL]: [terminalInstance('rt-t')] });
    render(<RuntimePanel projectId={PROJECT} />);
    const term = await screen.findByTestId('runtime-terminal-rt-t');
    expect(term.className).toContain('ws-rt-terminal');
    expect(within(term).getByText(/\$ npm test/)).toBeInTheDocument();
    expect(within(term).getByText(/✓ 213 tests passed/)).toBeInTheDocument();
    expect(within(term).getByText(/\$ npm run build/)).toBeInTheDocument();
  });

  it('mock stream 诚实标注 "演示数据" (不冒充真实日志)', async () => {
    stubFetch({ [RUNTIMES_URL]: [terminalInstance('rt-t')] });
    render(<RuntimePanel projectId={PROJECT} />);
    const term = await screen.findByTestId('runtime-terminal-rt-t');
    expect(within(term).getByText(/演示数据/)).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ REST 轮询
describe('RuntimePanel — REST 轮询 (2s, 不依赖 SSE runtime.*)', () => {
  it('2s 后重新拉取列表并更新状态 (starting → running)', async () => {
    vi.useFakeTimers();
    const fetchMock = stubFetch({ [RUNTIMES_URL]: [browserInstance('rt-1', 'starting')] });
    render(<RuntimePanel projectId={PROJECT} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByTestId('runtime-card-rt-1')).toHaveAttribute('data-status', 'starting');

    fetchMock.mockImplementation(async () => okResponse([browserInstance('rt-1', 'running')]));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RUNTIME_POLL_MS);
    });
    expect(screen.getByTestId('runtime-card-rt-1')).toHaveAttribute('data-status', 'running');
  });

  it('卸载后轮询停止 (interval 清理, 无泄漏)', async () => {
    vi.useFakeTimers();
    const fetchMock = stubFetch({ [RUNTIMES_URL]: [] });
    const { unmount } = render(<RuntimePanel projectId={PROJECT} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const callsAfterMount = fetchMock.mock.calls.length;
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RUNTIME_POLL_MS * 3);
    });
    expect(fetchMock.mock.calls.length).toBe(callsAfterMount);
  });

  it('RUNTIME_POLL_MS = 2000 (契约: REST 轮询 2s)', () => {
    expect(RUNTIME_POLL_MS).toBe(2000);
  });
});

// ------------------------------------------------------------------ Timeline 联动
describe('RuntimePanel — Timeline Artifact 联动 (WorkspaceShell 集成)', () => {
  const TIMELINE_URL = `/api/projects/${PROJECT}/timeline?limit=200`;

  function artifactEvent(artifactId: string, message = `生成 ${artifactId} Artifact`) {
    return {
      id: `evt-art-${artifactId}`,
      seq: 9,
      project_id: PROJECT,
      type: 'artifact',
      event_type: 'org.artifact.created',
      stage_id: null,
      agent_id: null,
      artifact_id: artifactId,
      gate_id: null,
      message,
      status: 'OK',
      payload: { artifact_id: artifactId, type: 'ux_ui' },
      created_at: '2026-08-10T00:00:00+00:00',
    };
  }

  function renderShell(runtimes: unknown[]) {
    stubFetch({
      [TIMELINE_URL]: [artifactEvent('mock-art-ux_ui')],
      [RUNTIMES_URL]: runtimes,
    });
    return render(
      <AppStateProvider>
        <ThemeProvider>
          <WorkspaceShell initialProjectId={PROJECT} />
        </ThemeProvider>
      </AppStateProvider>,
    );
  }

  it('artifact 查看 (S10-005) → Artifact Tab 激活 + 打开产物详情 (Artifact Center)', async () => {
    const user = userEvent.setup();
    renderShell([browserInstance('rt-b', 'running', 'mock-art-ux_ui')]);
    // Timeline artifact 节点渲染
    await screen.findByTestId('agent-timeline-artifact');
    await user.click(screen.getByRole('button', { name: '查看' }));
    // Artifact Center 可见 (artifact tab 激活) + 打开产物详情 (focus 优先)
    expect(screen.getByTestId('artifact-center')).toBeInTheDocument();
    expect(await screen.findByTestId('artifact-detail')).toBeInTheDocument();
  });

  it('artifact 查看 (无对应产物) → Artifact Center 空态/兜底 (简单联动)', async () => {
    const user = userEvent.setup();
    renderShell([]);
    await screen.findByTestId('agent-timeline-artifact');
    await user.click(screen.getByRole('button', { name: '查看' }));
    expect(screen.getByTestId('artifact-center')).toBeInTheDocument();
  });

  it('联动后再次点击 artifact → 定位仍生效 (nonce 递增, 无重复消费问题)', async () => {
    const user = userEvent.setup();
    renderShell([browserInstance('rt-b', 'running', 'mock-art-ux_ui')]);
    await screen.findByTestId('agent-timeline-artifact');
    await user.click(screen.getByRole('button', { name: '查看' }));
    await screen.findByTestId('artifact-detail');
    await user.click(screen.getByRole('button', { name: '查看' }));
    expect(await screen.findByTestId('artifact-detail')).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ 纯函数
describe('RuntimePanel — 纯函数', () => {
  it('formatRuntimeTime: 合法时间 → MM-DD HH:MM; 非法/缺失 → —', () => {
    expect(formatRuntimeTime('2026-08-10T00:05:00+00:00')).toMatch(/^\d{2}-\d{2} \d{2}:\d{2}$/);
    expect(formatRuntimeTime(null)).toBe('—');
    expect(formatRuntimeTime('not-a-date')).toBe('—');
  });

  it('TERMINAL_MOCK_LINES: npm test/build 演示流 (标注演示)', () => {
    expect(TERMINAL_MOCK_LINES[0]).toBe('$ npm test');
    expect(TERMINAL_MOCK_LINES.some((line) => line.includes('tests passed'))).toBe(true);
    expect(TERMINAL_MOCK_LINES.some((line) => line.includes('npm run build'))).toBe(true);
  });

  it('TerminalMockStream 直接渲染: 演示标注 + 等宽 pre', () => {
    render(<TerminalMockStream instanceId="rt-x" />);
    const term = screen.getByTestId('runtime-terminal-rt-x');
    expect(term.querySelector('pre')).not.toBeNull();
    expect(within(term).getByText(/演示数据/)).toBeInTheDocument();
  });
});
