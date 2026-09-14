/** S47-C1 — useRuntimeProjection + ActiveRuntimePanel 测试。

 * hook/组件 = 纯投影: 事件来自 runtimeClient.subscribeEvents (真实 SSE
 * 封装); 测试 mock subscribeEvents 返回受控 subscription — 验证
 * 事件投影 / seq 记录 / project isolation / close 清理 / UI 状态。
 * 不 mock 生产事实; 断言 UI 仅渲染注入的真实形状事件。
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { runtimeClient } from '../api/runtimeClient';
import type { RuntimeEventHandlers } from '../api/runtimeClient';
import { ActiveRuntimePanel } from '../components/af/ActiveRuntimePanel';
import { useRuntimeProjection } from '../hooks/useRuntimeProjection';

function TestProjection({ projectId }: { projectId: string }) {
  const p = useRuntimeProjection(projectId);
  return (
    <div data-testid="proj">
      <span data-testid="conn">{p.connection}</span>
      <span data-testid="seq">{p.lastSeq}</span>
      <span data-testid="stage">{p.currentStage ?? ''}</span>
      <span data-testid="err">{p.lastError ?? ''}</span>
      <ul>
        {p.recentEvents.map((e) => <li key={`${e.seq}`}>{e.name}</li>)}
      </ul>
    </div>
  );
}

interface MockSub {
  close: ReturnType<typeof vi.fn>;
  isMock: () => boolean;
  onEvent?: RuntimeEventHandlers['onEvent'];
  onOpen?: () => void;
  onError?: (e: Event | null) => void;
  onMock?: () => void;
}

function installMockSub() {
  const subs: MockSub[] = [];
  vi.spyOn(runtimeClient, 'subscribeEvents').mockImplementation(
    ((_pid: string, handlers: RuntimeEventHandlers) => {
      const sub: MockSub = {
        close: vi.fn(),
        isMock: () => false,
        ...handlers,
      };
      subs.push(sub);
      return sub as unknown as ReturnType<typeof runtimeClient.subscribeEvents>;
    }) as typeof runtimeClient.subscribeEvents,
  );
  return subs;
}

const RUNNING = { run_id: 'R-1', status: 'running', totals: {} };
const COMPLETED = { run_id: 'R-0', status: 'completed', totals: {} };

describe('useRuntimeProjection', () => {
  afterEach(() => vi.restoreAllMocks());

  it('subscribes on mount with project id; opens → connected', async () => {
    const subs = installMockSub();
    render(<TestProjection projectId="P-a" />);
    expect(runtimeClient.subscribeEvents).toHaveBeenCalledWith('P-a', expect.anything(), 0);
    await act(async () => subs[0].onOpen?.());
    expect(screen.getByTestId('conn').textContent).toBe('connected');
  });

  it('projects stage events + records seq (snapshot+delta merge)', async () => {
    const subs = installMockSub();
    render(<TestProjection projectId="P-a" />);
    await act(async () => {
      subs[0].onEvent?.('stage.started', { stage_id: 'S1', name: 'Development', seq: 5 });
      subs[0].onEvent?.('artifact.created', { artifact_id: 'A-1', seq: 6 });
    });
    expect(screen.getByTestId('stage').textContent).toBe('Development');
    expect(screen.getByTestId('seq').textContent).toBe('6');
    const items = screen.getAllByRole('listitem');
    expect(items.map((i) => i.textContent)).toEqual(['stage.started', 'artifact.created']);
  });

  it('unknown event type does not crash (forward-compatible)', async () => {
    const subs = installMockSub();
    render(<TestProjection projectId="P-a" />);
    await act(async () => {
      subs[0].onEvent?.('stage.completed', { name: 'Dev', seq: 7 });
      subs[0].onEvent?.('something.unknown' as never, { seq: 8 });
    });
    expect(screen.getByTestId('seq').textContent).toBe('8');
  });

  it('reconnect via onError → reconnecting; does not lose events', async () => {
    const subs = installMockSub();
    render(<TestProjection projectId="P-a" />);
    await act(async () => {
      subs[0].onEvent?.('stage.started', { name: 'X', seq: 1 });
      subs[0].onError?.(null);
    });
    expect(screen.getByTestId('conn').textContent).toBe('reconnecting');
    expect(screen.getByTestId('stage').textContent).toBe('X');
  });

  it('project isolation: switching id closes old sub, opens new', async () => {
    const subs = installMockSub();
    const { rerender } = render(<TestProjection projectId="P-a" />);
    rerender(<TestProjection projectId="P-b" />);
    expect(subs[0].close).toHaveBeenCalled();
    expect(runtimeClient.subscribeEvents).toHaveBeenLastCalledWith('P-b', expect.anything(), 0);
  });

  it('unmount closes subscription', async () => {
    const subs = installMockSub();
    const { unmount } = render(<TestProjection projectId="P-a" />);
    unmount();
    expect(subs[0].close).toHaveBeenCalled();
  });
});

describe('ActiveRuntimePanel', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows LIVE + active run + current stage from projection', async () => {
    installMockSub();
    const subHolder: MockSub[] = [];
    vi.spyOn(runtimeClient, 'subscribeEvents').mockImplementation(
      ((_pid: string, handlers: RuntimeEventHandlers) => {
        const s: MockSub = { close: vi.fn(), isMock: () => false, ...handlers };
        subHolder.push(s);
        return s as unknown as ReturnType<typeof runtimeClient.subscribeEvents>;
      }) as typeof runtimeClient.subscribeEvents,
    );
    render(
      <ActiveRuntimePanel
        projectId="P-a"
        runs={[RUNNING]}
        workflowStages={[{ name: 'Discovery', status: 'completed' }]}
      />,
    );
    await act(async () => {
      subHolder[0].onOpen?.();
      subHolder[0].onEvent?.('stage.started', { name: 'Development', seq: 2 });
    });
    await waitFor(() => {
      expect(screen.getByTestId('af-conn-state').textContent).toContain('LIVE');
      expect(screen.getByTestId('af-active-run-id').textContent).toBe('R-1');
      expect(screen.getByTestId('af-current-stage').textContent).toBe('Development');
    });
  });

  it('no active run → No active run', async () => {
    vi.spyOn(runtimeClient, 'subscribeEvents').mockReturnValue({
      close: vi.fn(), isMock: () => false,
    } as never);
    render(<ActiveRuntimePanel projectId="P-x" runs={[COMPLETED]} />);
    expect(await screen.findByText(/No active run/)).toBeTruthy();
  });
});
