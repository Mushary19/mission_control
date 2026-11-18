import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "url";

// Dev: the browser only talks to the Vite dev server (any port: `npm run dev -- --port 5174` works the same);
// Vite proxies /api to the FastAPI backend, so no CORS setup is needed. Point it elsewhere with MC_API.
// Production: `npm run build` writes dist/, and FastAPI serves it at / next to /api.
const API = process.env.MC_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { port: 5173, proxy: { "/api": { target: API, changeOrigin: true } } },
});
