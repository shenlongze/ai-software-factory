/**
 * src/test/AppState.test.tsx — 应用状态 (mode/page 导航)。
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { AppStateProvider, useAppState } from '../state/AppState';

function Probe(): JSX.Element {
  const { mode, page, setMode, navigate } = useAppState();
  return (
    <div>
      <span data-testid="mode">{mode}</span>
      <span data-testid="page">{page.name}</span>
      <button type="button" onClick={() => setMode('expert')}>
        切专业
      </button>
      <button type="button" onClick={() => navigate({ name: 'projects' })}>
        去项目
      </button>
    </div>
  );
}

describe('AppState', () => {
  it('默认 simple 模式 + dashboard 页', () => {
    render(
      <AppStateProvider>
        <Probe />
      </AppStateProvider>,
    );
    expect(screen.getByTestId('mode')).toHaveTextContent('simple');
    expect(screen.getByTestId('page')).toHaveTextContent('dashboard');
  });

  it('setMode 切换模式, navigate 切换页面', async () => {
    const user = userEvent.setup();
    render(
      <AppStateProvider>
        <Probe />
      </AppStateProvider>,
    );
    await user.click(screen.getByRole('button', { name: '切专业' }));
    expect(screen.getByTestId('mode')).toHaveTextContent('expert');
    await user.click(screen.getByRole('button', { name: '去项目' }));
    expect(screen.getByTestId('page')).toHaveTextContent('projects');
  });

  it('useAppState 在 Provider 外抛错', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow('useAppState 必须在 <AppStateProvider> 内使用');
    spy.mockRestore();
  });
});
