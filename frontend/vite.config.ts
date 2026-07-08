import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { accessLogPlugin } from "./plugins/accessLog";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(frontendRoot, "..");

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, projectRoot, "");
  const backendApiHost = env.BACKEND_API_HOST || "localhost";
  const backendApiPort = env.BACKEND_API_PORT || env.BACKEND_PORT || "8080";
  const frontendHost = env.FRONTEND_HOST || "0.0.0.0";
  const frontendPort = Number(env.FRONTEND_PORT || "9001");

  return {
    plugins: [react(), accessLogPlugin(path.join(projectRoot, "logs"))],
    server: {
      host: frontendHost,
      port: frontendPort,
      proxy: {
        "/api": {
          target: `http://${backendApiHost}:${backendApiPort}`,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: frontendHost,
      port: frontendPort,
      proxy: {
        "/api": {
          target: `http://${backendApiHost}:${backendApiPort}`,
          changeOrigin: true,
        },
      },
    },
  };
});
