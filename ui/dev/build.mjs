import { build } from "vite";
import path from "node:path";
const outDir = process.argv[2];
if (!outDir || !path.isAbsolute(outDir)) throw new Error("Pass an absolute fixture output directory");
const root = process.cwd();
await build({ root, envFile: false, configFile: path.join(root, "vite.config.ts"), configLoader: "native",
  mode: process.argv[3] === "upstream" ? "fixture-upstream" : "fixture",
  build: { outDir, emptyOutDir: true, rollupOptions: { input: path.join(root, "dev/index.html") } } });
