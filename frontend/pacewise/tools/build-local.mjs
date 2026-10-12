// LOCAL BUILD ONLY (sandbox without npm registry access).
// Bundles the app with esbuild + Tailwind CLI into a single self-contained HTML file.
// On a normal machine use `npm install && npm run dev` / `npm run build` (Vite).
import { build } from '/home/claude/.npm-global/lib/node_modules/tsx/node_modules/esbuild/lib/main.js';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const G = '/home/claude/.npm-global/lib/node_modules';
const out = path.join(root, 'dist-local');
mkdirSync(out, { recursive: true });

await build({
  entryPoints: [path.join(root, 'src/main.tsx')],
  bundle: true,
  minify: true,
  format: 'iife',
  jsx: 'automatic',
  target: 'es2020',
  outfile: path.join(out, 'app.js'),
  nodePaths: [G],
  alias: { 'react-router-dom': path.join(root, 'tools/router-shim.tsx') },
  define: { 'process.env.NODE_ENV': '"production"' },
  loader: { '.css': 'empty' },
  logLevel: 'warning',
});

execFileSync('node', [
  `${G}/@mermaid-js/mermaid-cli/node_modules/tailwindcss/lib/cli.js`,
  '-c', path.join(root, 'tailwind.config.js'),
  '-i', path.join(root, 'src/styles/index.css'),
  '-o', path.join(out, 'app.css'),
  '--minify',
], { cwd: root, stdio: ['ignore', 'ignore', 'inherit'] });

const js = readFileSync(path.join(out, 'app.js'), 'utf8').replace(/<\/script/gi, '<\\/script');
const css = readFileSync(path.join(out, 'app.css'), 'utf8');
const html = `<!doctype html>
<html lang="vi">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>PaceWise</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" />
<style>${css}</style>
</head>
<body>
<div id="root"></div>
<script>${js}</script>
</body>
</html>`;
writeFileSync(path.join(out, 'index.html'), html);
console.log('built', (html.length / 1024).toFixed(0) + ' KB');
