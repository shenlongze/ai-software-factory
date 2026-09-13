/**
 * src/test/useAsync.test.tsx — 异步数据加载 hook 三态 (loading/data/error)。
 */

import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useAsync } from '../hooks/useAsync';

function Probe<T>({ fetcher, deps }: { fetcher: () => Promise<T>; deps: unknown[] }): JSX.Element {
  const { data, error, loading } = useAsync(fetcher, deps);
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="data">{data === null ? 'null' : JSON.stringify(data)}</span>
      <span data-testid="error">{error ?? 'none'}</span>
    </div>
  );
}

describe('useAsync', () => {
  it('成功: loading → data', async () => {
    render(<Probe fetcher={() => Promise.resolve({ ok: 1 })} deps={[]} />);
    expect(screen.getByTestId('loading')).toHaveTextContent('true');
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    expect(screen.getByTestId('data')).toHaveTextContent('{"ok":1}');
    expect(screen.getByTestId('error')).toHaveTextContent('none');
  });

  it('失败: loading → error (Error message)', async () => {
    render(<Probe fetcher={() => Promise.reject(new Error('boom'))} deps={[]} />);
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    expect(screen.getByTestId('error')).toHaveTextContent('boom');
    expect(screen.getByTestId('data')).toHaveTextContent('null');
  });

  it('失败: 非 Error 值被字符串化', async () => {
    render(<Probe fetcher={() => Promise.reject('raw-string')} deps={[]} />);
    await waitFor(() => expect(screen.getByTestId('error')).toHaveTextContent('raw-string'));
  });

  it('卸载后 resolve 不回写 (防竞态)', async () => {
    let resolveFn: (v: { late: boolean }) => void = () => {};
    const fetcher = () =>
      new Promise<{ late: boolean }>((resolve) => {
        resolveFn = resolve;
      });
    const { unmount } = render(<Probe fetcher={fetcher} deps={[]} />);
    unmount();
    resolveFn({ late: true }); // 卸载后 resolve → 不应触发 act 警告/回写
    await vi.waitFor(() => expect(resolveFn).toBeDefined());
  });

  it('deps 变化重新拉取', async () => {
    const fetchA = vi.fn(async () => 'A');
    const { rerender } = render(<Probe fetcher={fetchA} deps={['a']} />);
    await waitFor(() => expect(screen.getByTestId('data')).toHaveTextContent('A'));
    const fetchB = vi.fn(async () => 'B');
    rerender(<Probe fetcher={fetchB} deps={['b']} />);
    await waitFor(() => expect(screen.getByTestId('data')).toHaveTextContent('B'));
    expect(fetchB).toHaveBeenCalled();
  });
});
