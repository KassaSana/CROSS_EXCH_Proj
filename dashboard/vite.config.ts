import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  resolve: {
    alias: mode === "profile" ? [
      { find: /^react-dom\/client$/, replacement: "react-dom/profiling" },
      { find: /^react-dom$/, replacement: "react-dom/profiling" },
    ] : [],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
}));
