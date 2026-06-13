import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Vite dev server runs on 5173. The FastAPI telemetry backend runs on 8800;
// the WebSocket URL is configured via VITE_TELEMETRY_WS (see .env.example).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: true,
    allowedHosts: true,
    proxy: {
      "/ws": {
        target: "ws://127.0.0.1:8800",
        ws: true,
        changeOrigin: true,
      },
      "/api": {
        target: "http://127.0.0.1:8800",
        changeOrigin: true,
      },
    },
  },
});
