import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = fileURLToPath(new URL('.', import.meta.url));
const repositoryRoot = resolve(frontendRoot, '../..');
const landingRoot = resolve(repositoryRoot, 'landingpage');

function paceWiseLanding(): Plugin {
  return {
    name: 'pacewise-landing',
    configureServer(server) {
      server.middlewares.use(async (request, response, next) => {
        const pathname = request.url?.split('?', 1)[0];
        if (pathname === '/') {
          response.setHeader('Content-Type', 'text/html; charset=utf-8');
          response.end(readFileSync(resolve(landingRoot, 'PaceWise.html'), 'utf8'));
          return;
        }
        if (pathname === '/landing-responsive.css') {
          response.setHeader('Content-Type', 'text/css; charset=utf-8');
          response.end(readFileSync(resolve(landingRoot, 'landing-responsive.css')));
          return;
        }
        if (pathname === '/landing-integration.js') {
          response.setHeader('Content-Type', 'text/javascript; charset=utf-8');
          response.end(readFileSync(resolve(landingRoot, 'landing-integration.js')));
          return;
        }
        if (pathname === '/app') {
          const appShell = readFileSync(resolve(frontendRoot, 'index.html'), 'utf8');
          response.setHeader('Content-Type', 'text/html; charset=utf-8');
          response.end(await server.transformIndexHtml('/app', appShell));
          return;
        }
        next();
      });
    },
  };
}

// PaceWise frontend. HashRouter is used so the build can be hosted as static files.
export default defineConfig({
  plugins: [paceWiseLanding(), react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
