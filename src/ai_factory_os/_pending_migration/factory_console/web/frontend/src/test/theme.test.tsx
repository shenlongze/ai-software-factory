/**
 * src/test/theme.test.tsx — 主题切换 (Founder 2026-08-26: 深色 + 新增浅色)。
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { ThemeProvider, useTheme } from '../theme';
import { AfBrandHeader } from '../components/af/AfBrandHeader';

afterEach(() => {
  try {
    delete document.documentElement.dataset.theme;
    window.localStorage.removeItem('af.theme');
  } catch {
    /* ignore */
  }
});

describe('主题切换', () => {
  it('默认深色 → 点击 ☀️ 切浅色 (data-theme=light)', async () => {
    render(
      <ThemeProvider>
        <AfBrandHeader />
      </ThemeProvider>,
    );
    expect(document.documentElement.dataset.theme).toBe('dark');
    await userEvent.click(screen.getByTestId('af-theme-switch'));
    expect(document.documentElement.dataset.theme).toBe('light');
    await userEvent.click(screen.getByTestId('af-theme-switch'));
    expect(document.documentElement.dataset.theme).toBe('dark');
  });
});

/* ================= 自定义背景 (选择图片 + 透明化) ================= */

function ThemeHarness(): JSX.Element {
  const { bg, setBackgroundImage, setBackgroundOpacity } = useTheme();
  return (
    <div>
      <span data-testid="bg-image">{bg.image ?? 'none'}</span>
      <span data-testid="bg-opacity">{bg.opacity}</span>
      <button type="button" onClick={() => setBackgroundImage('https://example.com/bg.png')}>set-url</button>
      <button type="button" onClick={() => setBackgroundImage(null)}>clear</button>
      <button type="button" onClick={() => setBackgroundOpacity(60)}>opacity60</button>
    </div>
  );
}

describe('自定义背景', () => {
  it('设置 URL → 背景层渲染 + body[data-bg=1] + 透明化生效', async () => {
    render(
      <ThemeProvider>
        <ThemeHarness />
      </ThemeProvider>,
    );
    await userEvent.click(screen.getByText('set-url'));
    expect(await screen.findByTestId('af-bg-layer')).toBeInTheDocument();
    expect(document.body.dataset.bg).toBe('1');
    expect(screen.getByTestId('bg-image').textContent).toBe('https://example.com/bg.png');
    await userEvent.click(screen.getByText('opacity60'));
    expect(screen.getByTestId('bg-opacity').textContent).toBe('60');
    await userEvent.click(screen.getByText('clear'));
    expect(screen.queryByTestId('af-bg-layer')).not.toBeInTheDocument();
    expect(document.body.dataset.bg).toBeUndefined();
  });
});
