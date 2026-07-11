import { defineConfig } from 'vite'
import { resolve } from 'path'

// Path B: Vite as asset bundler.
// Keeps Jinja2 SSR untouched. Vite compiles SCSS -> app/api/static/style.css
// and bundles ES modules -> app/api/static/main.js.
// Built assets are committed to the repo (Option 1) — no CI change needed.

export default defineConfig({
  root: resolve(__dirname, 'src'),
  base: '/static/',
  publicDir: resolve(__dirname, 'public'),
  build: {
    outDir: resolve(__dirname, '../app/api/static'),
    emptyOutDir: false, // keep sw.js, manifest.json, icons/ untouched
    assetsDir: '.',
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'src/main.js'),
        styles: resolve(__dirname, 'src/main.scss'),
      },
      output: {
        entryFileNames: '[name].js',
        assetFileNames: 'style.css',
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy all non-asset requests to the running FastAPI dev server
      '^/(?!static/).*': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
