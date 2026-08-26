import { useEffect, useState } from 'react';
import { AppStateProvider } from './state/AppState';
import { LanguageProvider } from './i18n';
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
function Shell(): JSX.Element {
  const [, setHashTick] = useState(0);
  useEffect(() => {
    const onChange = () => setHashTick((tick) => tick + 1);
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  const raw = window.location.hash || '#/workspace';
  const route = parseHash(raw);
  if (route.level === 'project') {
    return <AfProjectEntry route={route} />;
  }
  return <AfWorkspaceEntry route={route} />;
}

export default function App(): JSX.Element {
  return (
    <LanguageProvider>
      <AppStateProvider>
        <ConversationProvider>
          <Shell />
        </ConversationProvider>
      </AppStateProvider>
    </LanguageProvider>
  );
}
