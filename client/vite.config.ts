import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // host: true so the dev server is reachable from outside the container when
    // running under Docker Compose. The API base URL comes from VITE_API_URL —
    // see .env.example for why it must be localhost even there.
    host: true,
    port: 5173,
  },
})
