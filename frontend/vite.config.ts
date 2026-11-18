import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "url";

// Dev: Vite on :5173 proxies /api to FastAPI on :8000. Build: FastAPI serves dist/ at /.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
