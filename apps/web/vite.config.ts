import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The engine runs on 127.0.0.1:8765. In dev, Vite proxies engine routes so the app uses
// relative URLs; Electron later points VITE_ENGINE_URL at the bundled engine instead.
const ENGINE = process.env.ENGINE_URL ?? "http://127.0.0.1:8765";
const engineRoutes = ["/health", "/mask", "/unmask", "/chat", "/reveal", "/chats", "/vault", "/inspector", "/metrics", "/agent", "/documents", "/images", "/openapi.json"];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@muse-shield/core": path.resolve(__dirname, "../../packages/core/src"),
    },
  },
  base: "./", // relative asset paths, so the build also loads from file:// inside Electron
  server: { port: 5173, proxy: Object.fromEntries(engineRoutes.map((r) => [r, { target: ENGINE, changeOrigin: false }])) },
});
