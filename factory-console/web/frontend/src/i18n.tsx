/**
 * i18n.tsx — 系统级中英文切换 (Founder 2026-08-26)。
 *
 * - LanguageProvider + useI18n (locale: zh | en; localStorage af.locale 持久)
 * - t(key, vars?) 查表; 缺 key → 回退 zh → key 原样 (诚实, 不静默空)
 * - AfLangSwitch: 顶栏/设置 语言选择器
 * 原则: 默认 zh (现有体验/测试不破坏); 切换 en 全局生效; 未迁移的文案回退中文。
 */

import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

export type Locale = 'zh' | 'en';

const LOCALE_KEY = 'af.locale';

function readLocale(): Locale {
  try {
    return window.localStorage.getItem(LOCALE_KEY) === 'en' ? 'en' : 'zh';
  } catch {
    return 'zh';
  }
}

export const MESSAGES: Record<Locale, Record<string, string>> = {
  zh: {
    // 通用
    'common.refresh': '⟳ 刷新',
    'common.save': '保存',
    'common.cancel': '取消',
    'common.remove': '移除',
    'common.edit': '编辑',
    'common.add': '新增',
    'common.enabled': '启用',
    'common.disabled': '停用',
    'common.loading': '加载中…',
    'common.empty': '（暂无数据）',
    'common.unknown': '—',
    // 导航 (workspace)
    'nav.workspace.dashboard': '我的公司',
    'nav.workspace.projects': '项目',
    'nav.workspace.settings': '设置',
    'nav.section.workspace': '工作区',
    // 导航 (project)
    'nav.project.overview': '概览',
    'nav.project.docs': '文档',
    'nav.project.todo': '任务',
    'nav.project.workflow': '执行',
    'nav.project.runtime': '运行时',
    'nav.project.quality': '质量',
    // 顶栏/状态栏
    'header.backWorkspace': '← 返回工作台',
    'header.console': '进入 Human Console',
    'header.llm': 'LLM',
    'statusbar.model': '模型',
    'statusbar.scope': '作用域',
    'statusbar.session': '会话',
    'statusbar.msg': '消息',
    'statusbar.version': '版本',
    // 公司首页
    'company.title': '我的公司',
    'company.focused': '⭐ 关注项目（近期有更新）',
    'company.focusedEmpty': '（暂无近期有更新的收藏项目 — 收藏后自动出现；或点左栏项目 ⭐ 收藏）',
    'company.todo': '📋 我的待办',
    'company.todoAll': '全部（公司）',
    'company.todoEmpty': '✅ 无待处理（当前过滤维度）',
    'company.todoPending': '待接入',
    'company.qaNote': '质量待检 / 成本告警 API 待接入（真实数据后自动出现）',
    // 设置
    'settings.title': '设置',
    'settings.tab.llm': '🤖 LLM / 模型',
    'settings.tab.agent': '👤 AI 员工',
    'settings.tab.skill': '🧩 技能',
    'settings.tab.mcp': '🔌 MCP',
    'settings.tab.plugin': '📦 插件',
    'settings.tab.lang': '🌐 语言',
    'settings.lang.label': '界面语言',
    'settings.lang.zh': '中文',
    'settings.lang.en': 'English',
    // 文档/产出物
    'docs.title': '📄 文档',
    'docs.tab.docs': '📄 文档',
    'docs.tab.artifacts': '📦 产出物',
    // 会话栏
    'chat.scope.company': '🏢 公司',
    'chat.scope.project': '📁 项目',
    'chat.newSession': '新建会话',
    'chat.pin': '常驻',
    'chat.unpin': '取消常驻',
    'chat.collapse': '收起 AI 会话',
    'chat.reopen': '展开 AI 会话',
    'chat.noSessions': '暂无会话 — 点 + 新建（新会话 = 新任务线程）',
    'chat.selectFirst': '选择一个会话，或点 + 新建后开始对话。',
    'chat.newSessionHint': '新会话 — 说点什么开始。',
    'chat.sending': 'AI 思考中…',
    'chat.send': '发送',
    'chat.input.company': '我想做一个App / 讨论想法…',
    'chat.input.project': '改需求 / 看状态 / 分析影响…',
  },
  en: {
    'common.refresh': '⟳ Refresh',
    'common.save': 'Save',
    'common.cancel': 'Cancel',
    'common.remove': 'Remove',
    'common.edit': 'Edit',
    'common.add': 'Add',
    'common.enabled': 'Enable',
    'common.disabled': 'Disable',
    'common.loading': 'Loading…',
    'common.empty': '（empty）',
    'common.unknown': '—',
    'nav.workspace.dashboard': 'My Company',
    'nav.workspace.projects': 'Projects',
    'nav.workspace.settings': 'Settings',
    'nav.section.workspace': 'Workspace',
    'nav.project.overview': 'Overview',
    'nav.project.docs': 'Docs',
    'nav.project.todo': 'Tasks',
    'nav.project.workflow': 'Execute',
    'nav.project.runtime': 'Runtime',
    'nav.project.quality': 'Quality',
    'header.backWorkspace': '← Back to Workspace',
    'header.console': 'Human Console',
    'header.llm': 'LLM',
    'statusbar.model': 'Model',
    'statusbar.scope': 'Scope',
    'statusbar.session': 'Sessions',
    'statusbar.msg': 'Messages',
    'statusbar.version': 'Version',
    'company.title': 'My Company',
    'company.focused': '⭐ Focused Projects (recent)',
    'company.focusedEmpty': '（No recently-updated starred projects — star one from the sidebar to see it here）',
    'company.todo': '📋 My Todos',
    'company.todoAll': 'All (company)',
    'company.todoEmpty': '✅ Nothing pending (current filter)',
    'company.todoPending': 'pending',
    'company.qaNote': 'Quality / cost alerts: API pending (will appear with real data)',
    'settings.title': 'Settings',
    'settings.tab.llm': '🤖 LLM / Models',
    'settings.tab.agent': '👤 AI Staff',
    'settings.tab.skill': '🧩 Skills',
    'settings.tab.mcp': '🔌 MCP',
    'settings.tab.plugin': '📦 Plugins',
    'settings.tab.lang': '🌐 Language',
    'settings.lang.label': 'Interface language',
    'settings.lang.zh': '中文',
    'settings.lang.en': 'English',
    'docs.title': '📄 Docs',
    'docs.tab.docs': '📄 Docs',
    'docs.tab.artifacts': '📦 Artifacts',
    'chat.scope.company': '🏢 Company',
    'chat.scope.project': '📁 Project',
    'chat.newSession': 'New session',
    'chat.pin': 'Pin',
    'chat.unpin': 'Unpin',
    'chat.collapse': 'Collapse chat',
    'chat.reopen': 'Expand chat',
    'chat.noSessions': 'No sessions — click + to create (new session = new thread)',
    'chat.selectFirst': 'Select a session, or click + to start a new conversation.',
    'chat.newSessionHint': 'New session — say something to start.',
    'chat.sending': 'AI thinking…',
    'chat.send': 'Send',
    'chat.input.company': 'I want to build an app / discuss ideas…',
    'chat.input.project': 'Change requirements / check status / analyze impact…',
  },
};

interface I18nValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

function formatMessage(text: string, vars?: Record<string, string | number>): string {
  if (!vars) return text;
  let out = text;
  for (const [k, v] of Object.entries(vars)) {
    out = out.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v));
  }
  return out;
}

const I18nContext = createContext<I18nValue>({
  locale: 'zh',
  setLocale: () => {},
  t: (k, vars) => formatMessage(MESSAGES.zh[k] ?? k, vars),
});

export function LanguageProvider({ children }: { children: ReactNode }): JSX.Element {
  const [locale, setLocaleState] = useState<Locale>(readLocale);
  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      window.localStorage.setItem(LOCALE_KEY, l);
    } catch {
      /* 仅内存态 */
    }
  }, []);
  const t = useCallback(
    (key: string, vars?: Record<string, string | number>): string =>
      formatMessage(MESSAGES[locale][key] ?? MESSAGES.zh[key] ?? key, vars),
    [locale],
  );
  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  return useContext(I18nContext);
}

/** 语言切换器 (顶栏/设置 通用)。 */
export function AfLangSwitch({ compact = false }: { compact?: boolean }): JSX.Element {
  const { locale, setLocale } = useI18n();
  return (
    <select
      className={compact ? 'af-lang-switch af-lang-switch--compact' : 'af-lang-switch'}
      aria-label="界面语言 / Language"
      value={locale}
      onChange={(e) => setLocale(e.target.value as Locale)}
      data-testid="af-lang-switch"
    >
      <option value="zh">中文</option>
      <option value="en">English</option>
    </select>
  );
}
