import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// 每个测试后清理 DOM + 恢复 fetch 桩
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
