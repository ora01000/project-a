import fs from "node:fs";
import path from "node:path";
import type { Connect } from "vite";
import type { Plugin } from "vite";

function appendAccessLog(logPath: string, line: string): void {
  fs.mkdirSync(path.dirname(logPath), { recursive: true });
  fs.appendFile(logPath, line, () => undefined);
}

function createAccessLogger(logPath: string): Connect.NextHandleFunction {
  return (req, res, next) => {
    const startedAt = Date.now();

    res.on("finish", () => {
      const remoteAddress = req.socket.remoteAddress ?? "-";
      const durationMs = Date.now() - startedAt;
      const line = `${new Date().toISOString()} ${req.method ?? "-"} ${req.url ?? "-"} ${res.statusCode} ${durationMs}ms ${remoteAddress}\n`;
      appendAccessLog(logPath, line);
    });

    next();
  };
}

export function accessLogPlugin(logsDir: string): Plugin {
  const logPath = path.resolve(logsDir, "frontend-access.log");

  const attachMiddleware = (middlewares: Connect.Server) => {
    middlewares.use(createAccessLogger(logPath));
  };

  return {
    name: "frontend-access-log",
    configureServer(server) {
      attachMiddleware(server.middlewares);
    },
    configurePreviewServer(server) {
      attachMiddleware(server.middlewares);
    },
  };
}
