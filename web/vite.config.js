import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],

  server: {
    // The engine pins CORS to an exact origin list (app.cors.allowed-origins,
    // default http://localhost:3000) and rejects "*" at startup, and password
    // reset links are built from app.frontend.base-url (also :3000). Vite's
    // default is :5173, which the backend would reject, so we stay on :3000
    // and fail loudly rather than silently drifting to another port.
    port: 3000,
    strictPort: true,
  },
  preview: {
    port: 3000,
    strictPort: true,
  },

  build: {
    // CRA emitted to build/; .gitignore and the README already say so, and the
    // deployment files are owned by another slice. Keep the contract.
    outDir: 'build',
    sourcemap: true,
  },

  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.js',
    restoreMocks: true,
    unstubEnvs: true,
    include: ['src/**/*.{test,spec}.{js,jsx}'],
  },
});
