import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build lands inside the Python package so `pip install whatitdid` ships a working
// `serve` with no npm anywhere in the user's path.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "../src/whatitdid/static", emptyOutDir: true, assetsDir: "assets" },
  server: { proxy: { "/api": "http://127.0.0.1:8321" } },
});
