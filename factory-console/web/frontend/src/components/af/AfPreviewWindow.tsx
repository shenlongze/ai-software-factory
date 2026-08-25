/**
 * components/af/AfPreviewWindow.tsx — 右栏预览窗口 (K-7b, 类浏览器, Codex 式)。
 *
 * - 地址栏 + 前进/后退/刷新
 * - 内容: iframe 预览 (运行中的应用 / 文档渲染 / 任意 URL)
 * - 独立收起/展开 (默认展开), 收起后中央区自动扩宽
 * 数据源: 项目 runtimes (GET /api/projects/{id}/runtimes) → 默认预览运行 URL;
 *         无运行实例 → 占位提示输入 URL / 选产物。
 */

import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';

export interface AfPreviewWindowProps {
  /** 项目 id (可选) — 用于取默认运行预览 URL。 */
  projectId?: string | null;
  /** 默认展开? (K-7b: 预览是主要用途, 默认展开) */
  defaultOpen?: boolean;
  /** 顶部附加内容 (如产物链接) */
  headerExtra?: ReactNode;
}

export function AfPreviewWindow({
  projectId,
  defaultOpen = true,
  headerExtra,
}: AfPreviewWindowProps): JSX.Element {
  const [open, setOpen] = useState<boolean>(defaultOpen);
  const [url, setUrl] = useState<string>('');
  const [current, setCurrent] = useState<string>('');
  const [history, setHistory] = useState<string[]>([]);
  const [histIdx, setHistIdx] = useState<number>(-1);

  // 项目运行实例 → 默认预览地址 (失败安全: 无实例 → 空占位)
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/runtimes`, {
          headers: { Accept: 'application/json' },
        });
        if (!cancelled && res.ok) {
          const list = (await res.json()) as { id?: string; url?: string; status?: string }[];
          const live = list.find((r) => r.status === 'running' || r.status === 'started');
          const defaultUrl = live?.url || (list[0] ? list[0].url : '');
          if (defaultUrl) {
            setUrl(defaultUrl);
            setCurrent(defaultUrl);
            setHistory([defaultUrl]);
            setHistIdx(0);
          }
        }
      } catch {
        /* 后端不可达 → 保持占位 (失败安全) */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const navigate = (target: string) => {
    const trimmed = target.trim();
    if (!trimmed) return;
    const resolved = /^https?:\/\//.test(trimmed) ? trimmed : `http://${trimmed}`;
    setCurrent(resolved);
    setUrl(resolved);
    const next = [...history.slice(0, histIdx + 1), resolved];
    setHistory(next);
    setHistIdx(next.length - 1);
  };

  const goBack = () => {
    if (histIdx > 0) {
      const idx = histIdx - 1;
      setHistIdx(idx);
      setCurrent(history[idx]);
      setUrl(history[idx]);
    }
  };

  const goForward = () => {
    if (histIdx < history.length - 1) {
      const idx = histIdx + 1;
      setHistIdx(idx);
      setCurrent(history[idx]);
      setUrl(history[idx]);
    }
  };

  const reload = () => {
    if (current) setCurrent((c) => `${c}${c.includes('?') ? '&' : '?'}_r=${Date.now()}`);
  };

  if (!open) {
    return (
      <aside
        className="af-preview af-preview--collapsed"
        data-testid="af-preview-window"
        aria-label="预览窗口 (已收起)"
      >
        <button type="button" className="af-context-toggle" onClick={() => setOpen(true)} aria-label="展开预览窗口">
          ▶
        </button>
      </aside>
    );
  }

  return (
    <aside
      className="af-preview af-preview--open"
      data-testid="af-preview-window"
      aria-label="预览窗口"
    >
      <div className="af-preview-bar">
        <div className="af-preview-controls">
          <button type="button" className="af-preview-btn" onClick={goBack} disabled={histIdx <= 0} aria-label="后退">
            ◀
          </button>
          <button
            type="button"
            className="af-preview-btn"
            onClick={goForward}
            disabled={histIdx >= history.length - 1}
            aria-label="前进"
          >
            ▶
          </button>
          <button type="button" className="af-preview-btn" onClick={reload} aria-label="刷新">
            ⟳
          </button>
        </div>
        <input
          className="af-preview-address"
          placeholder="输入 URL 预览 (如 http://127.0.0.1:8000)"
          aria-label="预览地址"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') navigate(url);
          }}
        />
        <button type="button" className="af-preview-btn" onClick={() => setOpen(false)} aria-label="收起预览窗口">
          »
        </button>
      </div>
      {headerExtra}
      <div className="af-preview-body">
        {current ? (
          <iframe
            className="af-preview-frame"
            title="预览窗口"
            src={current}
            sandbox="allow-scripts allow-same-origin allow-forms"
          />
        ) : (
          <div className="af-preview-empty">
            暂无预览 — 输入 URL 打开，或从项目产物/运行实例进入。
          </div>
        )}
      </div>
    </aside>
  );
}
