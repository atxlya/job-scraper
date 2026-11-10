import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const api = "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": api, "/healthz": api } },
  build: { outDir: "dist", sourcemap: false },
  test: { environment: "jsdom", setupFiles: ["./src/setupTests.ts"] },
});
