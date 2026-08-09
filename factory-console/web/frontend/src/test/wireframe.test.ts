/**
 * src/test/wireframe.test.ts — utils/wireframe.ts 单测 (S9-003 线框解析)。
 *
 * parseWireframeScreens: wireframe 载荷 (UX/UI Designer Agent S8-002 机器
 * 可读结构: screens[{name, ascii, components[], actions[]}]) → 页面预览数据。
 * 宽容失败安全: 畸形结构/类型不符 → 空数组 (预览缺数据不拖垮 Review 页)。
 */

import { describe, expect, it } from 'vitest';
import { parseWireframeScreens } from '../utils/wireframe';

describe('parseWireframeScreens', () => {
  it('解析合法 wireframe 载荷 (name/ascii/components/actions 全字段)', () => {
    const screens = parseWireframeScreens({
      screens: [
        {
          name: 'screen_home',
          ascii: '+----------+\n| 余额卡片 |\n+----------+',
          components: ['BalanceCard', 'TransactionList'],
          actions: ['下拉刷新', '点击流水进入详情'],
        },
        { name: 'screen_record', ascii: '+----+', components: [], actions: [] },
      ],
    });
    expect(screens).toHaveLength(2);
    expect(screens[0]).toEqual({
      name: 'screen_home',
      ascii: '+----------+\n| 余额卡片 |\n+----------+',
      components: ['BalanceCard', 'TransactionList'],
      actions: ['下拉刷新', '点击流水进入详情'],
    });
    expect(screens[1].components).toEqual([]);
    expect(screens[1].actions).toEqual([]);
  });

  it('畸形结构 → 空数组 (宽容失败安全)', () => {
    expect(parseWireframeScreens(null)).toEqual([]);
    expect(parseWireframeScreens(undefined)).toEqual([]);
    expect(parseWireframeScreens('x')).toEqual([]);
    expect(parseWireframeScreens(42)).toEqual([]);
    expect(parseWireframeScreens({})).toEqual([]);
    expect(parseWireframeScreens({ screens: 'not-array' })).toEqual([]);
    expect(parseWireframeScreens({ screens: [{ ascii: 123 }] })).toEqual([]);
    expect(parseWireframeScreens({ screens: [null, 'x'] })).toEqual([]);
  });

  it('空屏 (无 name 无 ascii) 跳过; 非字符串字段过滤', () => {
    const screens = parseWireframeScreens({
      screens: [
        {},
        { name: 'ok', ascii: '', components: ['A', 42, '', null], actions: ['act', 7, ''] },
      ],
    });
    expect(screens).toHaveLength(1);
    expect(screens[0].name).toBe('ok');
    expect(screens[0].components).toEqual(['A']);
    expect(screens[0].actions).toEqual(['act']);
  });

  it('非字符串 name/ascii 字段 → 视为无效屏跳过 (无预览内容, 宽容不抛错)', () => {
    const screens = parseWireframeScreens({
      screens: [{ name: 42, ascii: true, components: ['A'], actions: [] }],
    });
    // name/ascii 均非字符串 → 空串 → 无预览内容的屏跳过 (失败安全)
    expect(screens).toHaveLength(0);
  });
});
