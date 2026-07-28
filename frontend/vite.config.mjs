import { defineConfig } from 'vite';
import { resolve } from 'node:path';

const repositoryRoot = resolve(import.meta.dirname, '..');
const sourceRoot = resolve(import.meta.dirname, 'src');
const apiProxyTarget = process.env.SIMLAB_API_PROXY_TARGET ?? 'http://127.0.0.1:8765';

export default defineConfig({
  root: sourceRoot,
  base: './',
  publicDir: resolve(import.meta.dirname, 'public'),
  plugins: [{
    name: 'simlab-development-runtime-config',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/simlab-config.json', (_request, response) => {
        response.statusCode = 200;
        response.setHeader('Content-Type', 'application/json');
        response.setHeader('Cache-Control', 'no-store');
        response.end(JSON.stringify({
          apiBaseUrl: 'same-origin',
          webSocketBaseUrl: 'same-origin',
          apiVersion: 'v1',
          projectId: null,
          accessToken: null,
        }));
      });
    },
  }],
  build: {
    outDir: resolve(import.meta.dirname, 'dist'),
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    fs: { allow: [repositoryRoot] },
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
  },
});
