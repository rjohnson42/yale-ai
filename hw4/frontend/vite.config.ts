import fs from "node:fs";
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, type Connect, type Plugin } from "vite";

const dataRoot = path.resolve(import.meta.dirname, "../data");

const imageTypes: Record<string, string> = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
};

/** Serve catalogue photos from hw4/data using the database image paths. */
function catalogueImages(): Plugin {
  const handler: Connect.NextHandleFunction = (req, res, next) => {
    const requestPath = decodeURIComponent((req.url ?? "/").split("?")[0] ?? "/");
    const relative = requestPath.replace(/^\/+/, "");
    const filePath = path.resolve(dataRoot, relative);
    const insideData =
      filePath === dataRoot || filePath.startsWith(`${dataRoot}${path.sep}`);
    if (!insideData || !fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
      next();
      return;
    }
    res.setHeader(
      "Content-Type",
      imageTypes[path.extname(filePath).toLowerCase()] ?? "application/octet-stream",
    );
    fs.createReadStream(filePath).pipe(res);
  };

  return {
    name: "catalogue-images",
    configureServer(server) {
      server.middlewares.use("/media", handler);
    },
    configurePreviewServer(server) {
      server.middlewares.use("/media", handler);
    },
  };
}

export default defineConfig({
  plugins: [react(), catalogueImages()],
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
  },
  preview: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
  },
});
