import { defineConfig } from "tsup"

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm"],
  target: "es2020",
  platform: "browser",
  dts: true,
  clean: true,
  treeshake: true,
  external: ["vue", "qrcode"],
})
