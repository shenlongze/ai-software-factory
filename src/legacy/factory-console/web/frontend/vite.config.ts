import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Phase 11B Human Console Web (ADR-0035)
// - dev: vite dev server, /api 代理到本地 FastAPI Adapter (DEFAULT_PORT 8011)
// - test: Vitest + jsdom + RTL (覆盖率 ≥80, v8 provider)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8011',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      reportsDirectory: 'coverage',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/main.tsx', 'src/test/**', 'src/**/__tests__/**', 'src/vite-env.d.ts'],
    },
  },
});
