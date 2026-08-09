/**
 * design/theme.tsx — S10-000 Design System 主题切换 (light/dark, 默认 light)。
 *
 * ThemeProvider 把主题写到 <html data-theme="...">, 由 design.css
 * 的 [data-theme='dark'] 覆盖层消费; 同时持久化到 localStorage。
 * 与 S9 控制台零耦合 (S9 用自身 :root 变量, 不受 data-theme 影响)。
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { ThemeName } from './tokens';

const THEME_STORAGE_KEY = 'factory-theme';

export interface ThemeContextValue {
  theme: ThemeName;
  setTheme: (theme: ThemeName) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'light',
  setTheme: () => undefined,
  toggleTheme: () => undefined,
});

function readInitialTheme(): ThemeName {
  try {
    const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    /* 隐私模式/SSR 无 localStorage → 默认 light */
  }
  return 'light';
}

export function ThemeProvider({
  children,
  initialTheme,
}: {
  children: ReactNode;
  initialTheme?: ThemeName;
}): JSX.Element {
  const [theme, setThemeState] = useState<ThemeName>(initialTheme ?? readInitialTheme());

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      /* 忽略持久化失败 (主题仍在内存生效) */
    }
  }, [theme]);

  const setTheme = useCallback((next: ThemeName) => setThemeState(next), []);
  const toggleTheme = useCallback(
    () => setThemeState((current) => (current === 'light' ? 'dark' : 'light')),
    [],
  );
  const value = useMemo(() => ({ theme, setTheme, toggleTheme }), [theme, setTheme, toggleTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}

/** 主题切换按钮 (亮/暗, 默认 light)。 */
export function ThemeToggle(): JSX.Element {
  const { theme, toggleTheme } = useTheme();
  const isLight = theme === 'light';
  return (
    <button
      type="button"
      className="ds-theme-toggle"
      onClick={toggleTheme}
      aria-label={isLight ? '切换到暗色主题' : '切换到亮色主题'}
      data-testid="ds-theme-toggle"
      data-theme-toggle={theme}
    >
      <span aria-hidden="true">{isLight ? '🌙' : '☀️'}</span>
      <span className="ds-theme-toggle-label">{isLight ? '暗色' : '亮色'}</span>
    </button>
  );
}
