import { useEffect, useState } from 'react';
import { AppStateProvider } from './state/AppState';
import { LanguageProvider } from './i18n';
import { ThemeProvider } from './theme';
import { ConversationProvider } from './components/af/ConversationContext';
import { parseHash } from './router';
import { AfWorkspaceEntry } from './pages/workspace/AfWorkspaceEntry';
import { AfProjectEntry } from './pages/project/AfProjectEntry';

/**
 * K-7a: 一套导航 (砍双模式) — Human Console 普通模式导航移除 (组件文件保留, K-7b 清理)。
 *   #/workspace 或空 hash → AfWorkspaceEntry (项目列表首页 + 工作台)
 *   #/project/:id[/<subpage>] → AfProjectEntry (项目工作区)
 *   #/workspace?project=id → parseHash 直链 → AfProjectEntry
 */
export default function App(): JSX.Element {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <AppStateProvider>
          <AppRouter />
        </AppStateProvider>
      </LanguageProvider>
    </ThemeProvider>
  );
}

/** 路由 + Context 注入 (S32-004B: URL ?project= 恢复项目 Context)。 */
function AppRouter(): JSX.Element {
  const [, setHashTick] = useState(0);
  useEffect(() => {
    const onChange = () => setHashTick((tick) => tick + 1);
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  const raw = window.location.hash || '#/workspace';
  const route = parseHash(raw);
  // S32-004B: #/workspace?project=id → 注入 Context (不离开 Workbench)
  const contextProjectId = route.level === 'workspace' ? route.projectId ?? null : null;
  return (
    <ConversationProvider initialProjectId={contextProjectId}>
      {route.level === 'project' ? <AfProjectEntry route={route} /> : <AfWorkspaceEntry route={route} />}
    </ConversationProvider>
  );
}
