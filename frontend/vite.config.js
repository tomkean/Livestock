import { defineConfig } from 'vite';
import { resolve } from 'path';

const backend = 'http://localhost:8100';

export default defineConfig({
    build: {
        // Build output lives outside the repo, beside it.
        outDir: resolve(__dirname, '../../build/frontend'),
        emptyOutDir: true
    },
    server: {
        proxy: {
            '/api': backend,
            '/media': backend,
            '/ws': { target: backend, ws: true }
        }
    }
});
