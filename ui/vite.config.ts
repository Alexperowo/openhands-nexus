import { defineConfig, type Plugin } from "vite";
import fs from "node:fs";
import react from "@vitejs/plugin-react";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const directory = path.dirname(fileURLToPath(import.meta.url));

// Canvas nests a <main> files panel inside the host's main. HTML forbids even
// role=presentation on <main>. Adapt this one tag at build time, keeping React
// ownership and all panel behavior. Fail loudly if the pinned markup changes.
export function canvasFilesSemantics(): Plugin {
  let seen = false;
  return {
    name: "nexus-files-semantics",
    transform(code, id) {
      if (!id.endsWith("/@openhands/agent-canvas/dist/routes/files-tab.js")) return null;
      const marker = /"main",\s*\{\s*className: "h-full w-full flex flex-col items-stretch",\s*"data-testid": "files-tab"/g;
      if ([...code.matchAll(marker)].length !== 1) this.error("Canvas files-tab markup changed: review its main landmark adapter");
      seen = true;
      return {code: code.replace(marker, match => match.replace('"main"', '"section"')), map: null};
    },
    generateBundle() { if (!seen) this.error("Canvas files-tab adapter was not applied"); },
  };
}

// Canvas ships every string in 16 languages, Russian not among them (ours is src/locales/ru.json);
// only English is read, as the fallback (i18n.ts). The other 15 were a quarter of the bundle.
export function canvasEnglishOnly(): Plugin {
  let seen = false;
  return {
    name: "nexus-canvas-english-only",
    async transform(code, id) {
      if (!id.endsWith("/@openhands/agent-canvas/dist/i18n/translation.js")) return null;
      const strings = (await import(`data:text/javascript,${encodeURIComponent(code)}`)).default;
      const entries = Object.entries(strings ?? {});
      if (!entries.length || entries.some(([, text]: [string, any]) => typeof text?.en !== "string")) {
        this.error("Canvas translation layout changed: review the English-only filter");
      }
      seen = true;
      const english = Object.fromEntries(entries.map(([key, text]: [string, any]) => [key, { en: text.en }]));
      return { code: `export default ${JSON.stringify(english)};`, map: null };
    },
    generateBundle() { if (!seen) this.error("Canvas English-only filter was not applied"); },
  };
}

// Routes Canvas imports of a private module to a host module, matched by resolved path
// (Canvas imports its siblings as "./name.js", which a specifier alias cannot tell apart).
// Adapters wrap the original: EventMessage gets ▶ under answers, the list arrow a spoken name.
// Replacements take its place: English that bypasses the dictionary where Aleksandr sees or hears it.
// Private-module compatibility shims for the pinned version (test-providers.mjs guards them).
export const ADAPTERS = {
  "hooks/chat/use-dictation.js": "src/use-dictation-with-speech.ts",
  "components/conversation-events/chat/event-message.js": "src/event-message-with-speech.tsx",
  "ui/dropdown/toggle-button.js": "src/dropdown-toggle-with-label.tsx",
  "utils/format-time-delta.js": "src/relative-time.ts",
  "ui/dropdown/clear-button.js": "src/clear-button.tsx",
  // Same place in the input row as the original, but it keeps the last reading and reads aloud.
  "components/features/chat/components/context-window-meter.js": "src/context-window-meter.tsx",
  "components/features/chat/components/chat-input-field.js": "src/chat-input-with-label.tsx",
  // Same model button and menu, plus the reasoning level (reasoning.ts).
  "components/features/chat/components/chat-input-llm-profile-picker.js": "src/llm-profile-picker-with-reasoning.tsx",
  "components/features/conversation-panel/conversation-card/conversation-card-context-menu.js": "src/conversation-menu-with-focus.tsx",
  "components/shared/modals/modal-backdrop.js": "src/modal-backdrop-with-label.tsx",
  "themes/syntax-highlighter-themes.js": "src/syntax-theme.ts",
  // Observe actual content sizes; Canvas only follows its private text reveal flag.
  "hooks/use-scroll-to-bottom.js": "src/use-scroll-to-bottom.ts",
  // A plain request between runs goes as a goal: the agent's «done» is checked (nexus_goal.py).
  "hooks/chat/use-goal-interceptor.js": "src/use-goal-by-default.ts",
};

function canvasAdapters(upstreamFixture = false): Plugin {
  const entries = { ...ADAPTERS, ...(upstreamFixture ? {
    "components/conversation-events/chat/event-message.js": "dev/upstream-event-message.tsx",
  } : {}) };
  const routes = new Map(Object.entries(entries).map(([module, adapter]) => [
    fs.realpathSync(path.resolve(directory, "node_modules/@openhands/agent-canvas/dist", module)),
    path.resolve(directory, adapter),
  ]));
  const names = new Set(Object.keys(ADAPTERS).map((module) => path.basename(module)));
  return {
    name: "nexus-canvas-adapters",
    enforce: "pre",
    async resolveId(source, importer, options) {
      if (!importer || !names.has(path.basename(source))) return null;
      const resolved = await this.resolve(source, importer, { ...options, skipSelf: true });
      const adapter = resolved && routes.get(resolved.id);
      // Only an adapter's own import of the module it wraps reaches the original.
      return adapter && adapter !== importer ? adapter : null;
    },
  };
}

// Canvas pulls Outfit and IBM Plex Mono from Google Fonts but never uses them (its text is
// the system stack: Roboto on the tablet, Noto Sans on the PC, both with full Cyrillic).
// The imports are dropped, and the bundle check fails the build if any remote @import or
// url() reaches the CSS by another way (requests from scripts are not covered by this).
function noRemoteCss(): Plugin {
  // The URL is quoted and itself holds ";" (IBM Plex Mono weights), so the match ends at its quote.
  const remoteImport = /@import\s*(?:url\(\s*)?(["'])https?:[^"']*\1\s*\)?[^;]*;/g;
  const remoteUrl = /url\(\s*["']?(?:https?:)?\/\//;
  return {
    name: "nexus-no-remote-css",
    enforce: "pre",
    transform(code, id) {
      if (!/agent-canvas\/dist\/styles\.css$/.test(id.split("?")[0])) return null;
      return { code: code.replace(remoteImport, ""), map: null };
    },
    generateBundle(_options, bundle) {
      for (const file of Object.values(bundle)) {
        if (file.type !== "asset" || !file.fileName.endsWith(".css")) continue;
        const css = String(file.source);
        if (remoteImport.test(css)) this.error(`Remote @import left in ${file.fileName}`);
        remoteImport.lastIndex = 0;
        // Fonts or images by url(): data: URIs are local, an address with // is not.
        if (remoteUrl.test(css)) this.error(`Remote url() in ${file.fileName}`);
      }
    },
  };
}

// Same source as the gateway (launcher/install.sh): the key stays on the proxy side, out of the bundle.
export default defineConfig(({ command, mode }) => {
  // A production/fixture build needs no installed session or local dotenv file.
  let sessionApiKey = "";
  if (command === "serve" && !mode.startsWith("fixture")) {
    const sessionEnv = path.join(os.homedir(), ".config/openhands-nexus/session.env");
    sessionApiKey = fs.existsSync(sessionEnv)
      ? fs.readFileSync(sessionEnv, "utf8").match(/^OHN_SESSION_KEY=(.+)$/m)?.[1] ?? ""
      : "";
  }
  const agentProxy = {
    target: "http://127.0.0.1:18010",
    changeOrigin: true,
    ws: true,
    headers: sessionApiKey ? { "X-Session-API-Key": sessionApiKey } : {},
  };
  // Same routes as gateway/Caddyfile, first match wins (test-providers.mjs compares them).
  const proxy = {
    "/api/automation/": { ...agentProxy, target: "http://127.0.0.1:18011", ws: false },
    "/api": agentProxy,
    "/sockets": agentProxy,
    "^/(server_info|health|ready|alive)$": agentProxy,
    "/v1": { target: "http://127.0.0.1:18020", changeOrigin: true },
    // Only the model health; /slots and the rest of llama-server hold prompt text.
    "^/llm/running$": { target: "http://127.0.0.1:18030", changeOrigin: true, rewrite: () => "/running" },
    "^/llm/model/[A-Za-z0-9._-]+/health$": { target: "http://127.0.0.1:18030", changeOrigin: true,
      rewrite: (url: string) => url.replace(/^\/llm\/model\//, "/upstream/") },
  };
  const listener = { host: "127.0.0.1", port: 3020, strictPort: true,
    proxy: mode.startsWith("fixture") ? {} : proxy };

  return {
    // Vite 6 treats envDir:false as the project root; use an explicitly empty directory.
    envDir: path.join(directory, "dev/no-env"),
    plugins: [canvasAdapters(mode === "fixture-upstream"), canvasFilesSemantics(), canvasEnglishOnly(), noRemoteCss(), react()],
    resolve: {
      // Private Canvas contexts whose providers the published build drops;
      // pinned-version compatibility workaround (test-providers.mjs guards it).
      alias: [
        { find: /.*context\/navigation-context(\.js)?$/, replacement: path.resolve(directory, "src/navigation-context.tsx") },
        { find: /^.*\bsidebar-mobile-nav-context(\.js)?$/, replacement: path.resolve(directory, "src/sidebar-mobile-nav-context.tsx") },
        // No version check against the npm registry (test-providers.mjs guards the exports).
        { find: /^.*\bapi\/agent-canvas-updates(\.js)?$/, replacement: path.resolve(directory, "src/no-update-check.ts") },
      ],
    },
    define: {
      __NEXUS_GUARD__: JSON.stringify(path.resolve(directory, "../guard/guard.py")),
      // Not /tmp: agent-server runs `git init` in the workspace, and tmpfs loses the files at reboot.
      __NEXUS_WORKSPACE__: JSON.stringify(path.join(os.homedir(), "Nexus")),
    },
    build: { target: "esnext" },
    server: listener,
    preview: listener,
  };
});
