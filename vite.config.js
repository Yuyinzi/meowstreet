import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  build: {
    lib: {
      entry: resolve(import.meta.dirname, "frontend/src/macro-dashboard/main.js"),
      formats: ["iife"],
      name: "MacroDashboard",
      fileName: () => "macro-dashboard.js",
    },
    outDir: resolve(import.meta.dirname, "static/dist"),
    emptyOutDir: true,
    cssCodeSplit: false,
    minify: false,
    cssMinify: false,
    rollupOptions: {
      output: {
        assetFileNames: "macro-dashboard[extname]",
      },
    },
  },
});
