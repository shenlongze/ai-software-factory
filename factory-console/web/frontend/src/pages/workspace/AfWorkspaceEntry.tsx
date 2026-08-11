/**
 * pages/workspace/AfWorkspaceEntry.tsx — AI Factory 工作台入口 (S10-014 Task 004 升级)。
 *
 * #/workspace 与 #/workspace/* 打开后渲染 AI OS Workspace 三栏壳 (AfWorkspaceShell):
 *   Browser → Router → AfWorkspaceShell (三栏: Header + Sidebar 7 导航 + Main)
 *   → dashboard/projects 页真实项目列表 (GET /api/dashboard → 项目卡)
 *   → team/workflows/runtime/audit/settings 页 AfModulePlaceholder (禁空白)
 *
 * 入口兼容: 保持导出名与 data-testid="af-workspace-entry" (根节点在 Shell 上),
 * App.tsx 路由分发无需改动。Task 002b 的项目列表逻辑迁入 AfWorkspaceShell.AfProjectListView。
 */

import type { ParsedRoute } from '../../router';
import { AfWorkspaceShell } from '../../components/af/AfWorkspaceShell';

export function AfWorkspaceEntry({ route }: { route: ParsedRoute }): JSX.Element {
  return <AfWorkspaceShell route={route} />;
}
