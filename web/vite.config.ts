import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { runnerImport, type Plugin } from "vite";

type Render = typeof import("./src/features/landing/render");

const escapeHtml = (text: string) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/**
 * Fills landing.html with the page the landing feature renders, as plain HTML. The page ships no
 * framework: the build writes the markup, and landing.ts only plays the hero loop. Vite's own runner
 * loads the feature, so the config itself stays free of it.
 */
function landing(): Plugin {
  return {
    name: "landing-html",
    transformIndexHtml: {
      order: "pre",
      async handler(page, context) {
        if (!context.filename.endsWith("landing.html")) return page;
        const { module } = await runnerImport<Render>("./src/features/landing/render.ts");
        return page
          .replace("<!--landing:title-->", escapeHtml(module.TITLE))
          .replace("<!--landing:description-->", escapeHtml(module.DESCRIPTION))
          .replace("<!--landing:body-->", module.body().text);
      },
    },
  };
}

const page = (name: string) => fileURLToPath(new URL(`./${name}`, import.meta.url));
const SERVER = "http://127.0.0.1:8765";

export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss(), landing()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { proxy: { "/v1": SERVER, "/projects": SERVER, "/local": SERVER } },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    modulePreload: { polyfill: false },
    // The landing page's pictures and loops stay files, so the page weighs what its assets weigh.
    assetsInlineLimit: (file) => (file.includes("/features/landing/assets/") ? false : undefined),
    // The landing page is the second entry. It shares no module with the app, so it loads none of its bundle.
    rolldownOptions: { input: { app: page("index.html"), landing: page("landing.html") } },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    testTimeout: 20_000,
  },
});
