/**
 * utils/wireframe.ts — wireframe ASCII → 页面预览解析 (S9-003)。
 *
 * UX/UI Designer Agent (S8-002) 的 wireframe 产物为机器可读纯 JSON:
 *   wireframe: { screens: [ { name, ascii, components[], actions[] }, ... ] }
 * 本模块把该结构解析为页面预览数据 (纯函数, 零副作用, 可单测):
 * - 每屏 ASCII 布局 → <pre> 原样渲染 (线框预览主体)
 * - Screen 结构 (name/components/actions) → 组件卡片 (组件清单 + 交互动作)
 * 宽容失败安全: 结构缺失/类型不符 → 空数组 (预览缺数据不拖垮 Review 页)。
 */

import type { WireframeScreen } from '../models/types';

function toStrList(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.filter((x): x is string => typeof x === 'string' && x.length > 0);
}

/** 从 wireframe 载荷提取屏幕清单 (宽容解析: 畸形结构 → [])。 */
export function parseWireframeScreens(wireframe: unknown): WireframeScreen[] {
  if (typeof wireframe !== 'object' || wireframe === null) return [];
  const screens = (wireframe as Record<string, unknown>).screens;
  if (!Array.isArray(screens)) return [];
  const out: WireframeScreen[] = [];
  for (const raw of screens) {
    if (typeof raw !== 'object' || raw === null) continue;
    const item = raw as Record<string, unknown>;
    const name = typeof item.name === 'string' ? item.name : '';
    const ascii = typeof item.ascii === 'string' ? item.ascii : '';
    if (!name && !ascii) continue; // 空屏跳过
    out.push({
      name,
      ascii,
      components: toStrList(item.components),
      actions: toStrList(item.actions),
    });
  }
  return out;
}
