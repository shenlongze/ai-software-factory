/**
 * theme.tsx — 主题 + 自定义背景 (Founder 2026-08-26)。
 *
 * - ThemeProvider + useTheme (theme: dark | light; localStorage af.theme)
 * - 自定义背景: 用户选图 (本地文件→dataURL / URL) + 透明化(opacity) + 模糊(blur),
 *   持久 localStorage (af.bg.*); 渲染固定背景层 + 可读性遮罩
 * - AfThemeSwitch: 顶栏/设置 主题选择器
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

export type Theme = 'dark' | 'light';

export interface BackgroundSettings {
  image: string | null;
  opacity: number; // 0-100 (图像不透明度)
  blur: number; // 0-40 px (背景模糊)
}

const THEME_KEY = 'af.theme';
const BG_IMAGE_KEY = 'af.bg.image';
const BG_OPACITY_KEY = 'af.bg.opacity';
const BG_BLUR_KEY = 'af.bg.blur';

function readTheme(): Theme {
  try {
    return window.localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}
function readBg(): BackgroundSettings {
  const read = (k: string): string | null => {
    try {
      return window.localStorage.getItem(k);
    } catch {
      return null;
    }
  };
  const num = (v: string | null, def: number): number => {
    const n = Number(v);
    return Number.isFinite(n) ? n : def;
  };
  return {
    image: read(BG_IMAGE_KEY),
    opacity: num(read(BG_OPACITY_KEY), 30),
    blur: num(read(BG_BLUR_KEY), 8),
  };
}

interface ThemeValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  bg: BackgroundSettings;
  setBackgroundImage: (image: string | null) => void;
  setBackgroundOpacity: (opacity: number) => void;
  setBackgroundBlur: (blur: number) => void;
  clearBackground: () => void;
}

const ThemeContext = createContext<ThemeValue>({
  theme: 'dark',
  setTheme: () => {},
  toggleTheme: () => {},
  bg: { image: null, opacity: 30, blur: 8 },
  setBackgroundImage: () => {},
  setBackgroundOpacity: () => {},
  setBackgroundBlur: () => {},
  clearBackground: () => {},
});

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* 仅内存态 */
  }
}

export function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  const [theme, setThemeState] = useState<Theme>(readTheme);
  const [bg, setBg] = useState<BackgroundSettings>(readBg);

  useEffect(() => {
    try {
      document.documentElement.dataset.theme = theme;
    } catch {
      /* ignore */
    }
  }, [theme]);

  // 背景应用到 body: 开启时透明壳 + 背景层
  useEffect(() => {
    try {
      if (bg.image) {
        document.body.dataset.bg = '1';
      } else {
        delete document.body.dataset.bg;
      }
    } catch {
      /* ignore */
    }
  }, [bg.image]);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    write(THEME_KEY, t);
  }, []);
  const toggleTheme = useCallback(() => {
    setThemeState((prev) => {
      const next: Theme = prev === 'dark' ? 'light' : 'dark';
      write(THEME_KEY, next);
      return next;
    });
  }, []);

  const setBackgroundImage = useCallback((image: string | null) => {
    setBg((prev) => ({ ...prev, image }));
    if (image) write(BG_IMAGE_KEY, image);
    else {
      try {
        window.localStorage.removeItem(BG_IMAGE_KEY);
      } catch {
        /* ignore */
      }
    }
  }, []);
  const setBackgroundOpacity = useCallback((opacity: number) => {
    setBg((prev) => ({ ...prev, opacity }));
    write(BG_OPACITY_KEY, String(opacity));
  }, []);
  const setBackgroundBlur = useCallback((blur: number) => {
    setBg((prev) => ({ ...prev, blur }));
    write(BG_BLUR_KEY, String(blur));
  }, []);
  const clearBackground = useCallback(() => {
    setBg({ image: null, opacity: 30, blur: 8 });
    try {
      window.localStorage.removeItem(BG_IMAGE_KEY);
      window.localStorage.removeItem(BG_OPACITY_KEY);
      window.localStorage.removeItem(BG_BLUR_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(
    () => ({
      theme,
      setTheme,
      toggleTheme,
      bg,
      setBackgroundImage,
      setBackgroundOpacity,
      setBackgroundBlur,
      clearBackground,
    }),
    [theme, setTheme, toggleTheme, bg, setBackgroundImage, setBackgroundOpacity, setBackgroundBlur, clearBackground],
  );

  return (
    <ThemeContext.Provider value={value}>
      {bg.image ? (
        <div
          className="af-bg-layer"
          data-testid="af-bg-layer"
          aria-hidden="true"
          style={{
            backgroundImage: `url("${bg.image}")`,
            opacity: Math.min(Math.max(bg.opacity / 100, 0), 1),
            filter: `blur(${Math.min(Math.max(bg.blur, 0), 40)}px)`,
          }}
        />
      ) : null}
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeValue {
  return useContext(ThemeContext);
}

/** 主题选择器 (顶栏紧凑 / 设置完整)。 */
export function AfThemeSwitch({ compact = false }: { compact?: boolean }): JSX.Element {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      type="button"
      className={compact ? 'af-theme-switch af-theme-switch--compact' : 'af-theme-switch'}
      aria-label={theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'}
      title={theme === 'dark' ? '浅色主题' : '深色主题'}
      onClick={toggleTheme}
      data-testid="af-theme-switch"
    >
      {theme === 'dark' ? '☀️' : '🌙'}
    </button>
  );
}
