/**
 * src/test/i18n.test.tsx — 中英文切换 (Founder 2026-08-26)。
 *
 * 默认中文; 切 English → 导航/首页文案全局切换; localStorage 持久。
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { LanguageProvider } from '../i18n';
import { AfWorkspaceShell } from '../components/af/AfWorkspaceShell';
import { stubFetch } from './fixtures';

function renderShell() {
  return render(
    <LanguageProvider>
      <AfWorkspaceShell route={{ level: 'workspace', page: 'dashboard' }} />
    </LanguageProvider>,
  );
}

afterEach(() => {
  try {
    window.localStorage.removeItem('af.locale');
  } catch {
    /* ignore */
  }
});

describe('i18n 中英文切换', () => {
  it('默认中文: 中栏对话引导 (你今天想做什么?)', async () => {
    stubFetch({ '/api/projects': [], '/api/approvals?pending_only=true': [], '/api/sessions': { items: [], count: 0 }, '/api/conversations': { items: [], count: 0 }, '/api/projects-os': { items: [], count: 0 }, '/api/ops/overview': { projects: { total: 0, running: 0, waiting: 0, blocked: 0, approval: 0, failed: 0 }, workforce: { running: 0, waiting: 0, blocked: 0, error: 0, idle: 0 }, recent_activity: [], calculated_at: 'now' } });
    renderShell();
    expect(await screen.findByText(/你今天想做什么/)).toBeInTheDocument();
  });

  it('切换 English → 界面文案切换 (输入框 placeholder)', async () => {
    stubFetch({ '/api/projects': [], '/api/approvals?pending_only=true': [], '/api/sessions': { items: [], count: 0 }, '/api/conversations': { items: [], count: 0 }, '/api/projects-os': { items: [], count: 0 }, '/api/ops/overview': { projects: { total: 0, running: 0, waiting: 0, blocked: 0, approval: 0, failed: 0 }, workforce: { running: 0, waiting: 0, blocked: 0, error: 0, idle: 0 }, recent_activity: [], calculated_at: 'now' } });
    renderShell();
    await userEvent.selectOptions(screen.getByTestId('af-lang-switch'), 'en');
    expect(await screen.findByPlaceholderText(/Talk to the company/)).toBeInTheDocument();
  });
});
