import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    // Vitest: globals enables @testing-library/react's automatic afterEach
    // cleanup (so portal-rendered dialogs don't leak across component tests).
    test: {
        globals: true,
        // Node 25+ stubs global.localStorage without .clear(); patch it with
        // the real jsdom Storage in all jsdom-environment tests.
        // Global setupFiles: the shim self-guards on `typeof window`, so it only
        // patches storage in jsdom-environment tests; node-env tests are untouched.
        setupFiles: ['./src/setupTests.ts'],
    },
    css: {
        postcss: {
            plugins: [
                tailwindcss,
                autoprefixer,
            ],
        },
    },
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
        },
    },
    server: {
        proxy: {
            '/api': {
                // Keep the Windows dev server pointed at the real WSL runtime.
                // Frontend clients use relative /api paths so auth and all
                // operational data share the Docker Admin API session/store.
                target: 'http://127.0.0.1:3003',
                changeOrigin: true,
            }
        }
    }
})
