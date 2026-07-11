import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // dev: the api service from deploy/docker-compose.yml
      "/api": "http://localhost:8101",
      // public-dashboard data calls live outside /api (issue #41)
      "^/public/[^/]+/query$": "http://localhost:8101",
    },
  },
});
