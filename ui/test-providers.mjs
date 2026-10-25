// Guards the vite.config.ts aliases: Canvas hooks that throw without a provider
// the published build no longer contains must all be replaced by host copies.
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import fs from "node:fs";
import { loadConfigFromFile } from "vite";
import path from "node:path";

const dist = "node_modules/@openhands/agent-canvas/dist";
const HOST_COPIES = ["SidebarMobileNavProvider"];

// Read once in Node: provider guards do not need child processes or a system grep.
const sources = (directory) => {
  const result = new Map();
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) for (const pair of sources(file)) result.set(...pair);
    else if (entry.name.endsWith(".js")) result.set(file, readFileSync(file, "utf8"));
  }
  return result;
};
const modules = sources(dist);
const build = [...sources(path.join(process.env.OHN_UI_BUILD_DIR || "dist-next", "assets")).values()];
const grep = (pattern) => [...modules.values()].flatMap((source) => source.match(new RegExp(pattern, "g")) ?? []).join("\n");

test("every dropped Canvas provider has a host copy", () => {
  const required = new Set(grep("must be used within [A-Z][A-Za-z]+Provider").match(/[A-Z][A-Za-z]+Provider/g) ?? []);
  const dropped = [...required].filter((name) => !grep(`(function ${name}\\b|as ${name}\\b)`).trim());
  assert.deepEqual(dropped.sort(), HOST_COPIES.sort());
});

test("navigation context is still the private module the alias replaces", () => {
  assert.match(grep("useNavigation must be used[^\"]*|context/navigation-context\\.js"), /navigation-context/);
});

// vite.config.ts (ADAPTERS) swaps these private modules for host adapters that wrap them.
const ADAPTED = {
  [`${dist}/hooks/chat/use-dictation.js`]: "useDictation",
  [`${dist}/components/conversation-events/chat/event-message.js`]: "EventMessage",
  [`${dist}/ui/dropdown/toggle-button.js`]: "ToggleButton",
  [`${dist}/components/features/chat/components/chat-input-field.js`]: "ChatInputField",
  [`${dist}/components/features/conversation-panel/conversation-card/conversation-card-context-menu.js`]: "ConversationCardContextMenu",
  [`${dist}/components/shared/modals/modal-backdrop.js`]: "ModalBackdrop",
  [`${dist}/themes/syntax-highlighter-themes.js`]: "getSyntaxHighlighterTheme",
  [`${dist}/hooks/use-scroll-to-bottom.js`]: "useScrollToBottom",
};

for (const [module, name] of Object.entries(ADAPTED)) {
  test(`${name} is still the private module and export its adapter wraps`, () => {
    assert.ok(existsSync(module), `${module} is missing`);
    const exports = readFileSync(module, "utf8").match(/^export \{[^}]*\}/gm) ?? [];
    assert.equal(exports.length, 1);
    assert.match(exports[0], new RegExp(`^export \\{ \\w+ as ${name} \\}$`));
  });
}

// The reasoning adapter replaces both exports: the row's button and the overflow menu content.
test("the model picker is still the private module with the two exports its adapter replaces", () => {
  const picker = `${dist}/components/features/chat/components/chat-input-llm-profile-picker.js`;
  const exports = readFileSync(picker, "utf8").match(/^export \{[^}]*\}/gm) ?? [];
  assert.equal(exports.length, 1);
  assert.match(exports[0], /^export \{ \w+ as ChatInputLlmProfileMenuContent, \w+ as ChatInputLlmProfilePicker \}$/);
  assert.match(modules.get(`${dist}/components/features/chat/components/chat-input-actions.js`),
    /import \{ ChatInputLlmProfileMenuContent as \w+, ChatInputLlmProfilePicker as \w+ \} from "\.\/chat-input-llm-profile-picker\.js"/);
  assert.ok(build.some((source) => source.includes("nexus-reasoning-options")), "run `npx vite build --outDir dist-next` first; the reasoning adapter is missing");
});

test("the build includes the read-aloud adapter", () => {
  assert.ok(build.some((source) => source.includes("speak-button")), "run `npx vite build --outDir dist-next` first; the ▶ button is not in dist");
});

test("the build includes the named chat input adapter", () => {
  assert.ok(build.some((source) => source.includes("Сообщение агенту")), "run `npx vite build --outDir dist-next` first; the chat input adapter is missing");
});

test("dictation keeps Canvas insert-only text insertion and IME handling", () => {
  const container = modules.get(`${dist}/components/features/chat/components/chat-input-container.js`);
  assert.match(container, /onDictationTranscript: \(\w+\) => \w+\(\w+\.current, \w+\)/);
  const input = readFileSync("src/chat-input-with-label.tsx", "utf8");
  assert.match(input, /<CanvasChatInputField \{\.\.\.props\}/);
  assert.doesNotMatch(input, /onInput|onPaste|onKeyDown|onComposition/);
  const events = modules.get(`${dist}/hooks/chat/use-chat-input-events.js`);
  assert.ok(events.includes("nativeEvent.isComposing"));
});

test("the build uses the host modules instead of the Canvas originals", () => {
  assert.ok(build.every((source) => !source.includes('"aria-label":"Clear selection"')), "Canvas clear-button.js is back in dist");
  assert.ok(build.every((source) => !/`\$\{[a-z]\}mo`/.test(source)), "Canvas format-time-delta.js is back in dist");
});

// Every Canvas element our CSS and scripts reach by test id: collected from the sources,
// so a rule added later is guarded without remembering to list it here.
const hostSources = readdirSync("src").filter((name) => /\.(tsx?|css)$/.test(name))
  .map((name) => readFileSync(path.join("src", name), "utf8")).join("\n");
const referencedIds = new Set([...hostSources.matchAll(/\[data-testid=['"]?([a-z0-9-]+)|testid === "([a-z0-9-]+)"/g)]
  .map((match) => match[1] ?? match[2])
  // Built by Canvas from a template (checked below) or rendered by our own adapters.
  .filter((id) => !/^(action-\w+-button|(agent|user)-message)$/.test(id) && !new RegExp(`(?<!\\[)data-testid="${id}"`).test(hostSources)));

test("Canvas controls used by host visibility and accessibility rules keep their test ids", () => {
  assert.ok(referencedIds.size > 20, "the test id scan found too little; check its pattern");
  for (const id of referencedIds) {
    const literal = grep(`(data-testid"|testId): (\\w+ = )?"${id}"`).trim();
    // Canvas also hoists IDs into local constants (command-menu-trigger).
    // Require the constant and its actual test-id use in the same module.
    const hoisted = [...modules.values()].some(source => [...source.matchAll(new RegExp(`\\b(\\w+) = "${id}"`, "g"))]
      .some(match => new RegExp(`(data-testid"|testId): ${match[1]}\\b`).test(source)));
    assert.ok(literal || hoisted, `${id} disappeared from Canvas`);
  }
  const actions = readFileSync(`${dist}/components/shared/action-tooltip.js`, "utf8");
  assert.match(actions, /"data-testid": `action-\$\{\w+\}-button`/);
  assert.match(actions, /\w+ === "confirm"/);
  const message = readFileSync(`${dist}/components/features/chat/chat-message.js`, "utf8");
  assert.match(message, /"data-testid": `\$\{\w+\}-message`/);
});

// Host replacements with the same exports (agent-canvas-updates by alias, the rest by ADAPTERS).
const REPLACED = {
  "api/agent-canvas-updates.js": "src/no-update-check.ts",
  "utils/format-time-delta.js": "src/relative-time.ts",
  "ui/dropdown/clear-button.js": "src/clear-button.tsx",
  "components/features/chat/components/context-window-meter.js": "src/context-window-meter.tsx",
};

for (const [module, replacement] of Object.entries(REPLACED)) {
  test(`${module} still has exactly the exports ${replacement} provides`, () => {
    const exports = readFileSync(`${dist}/${module}`, "utf8").match(/^export \{([^}]*)\}/m)?.[1] ?? "";
    const names = exports.split(",").map((part) => part.trim().split(/\s+as\s+/).pop()).sort();
    const own = readFileSync(replacement, "utf8").match(/export (?:const|async function|function) (\w+)/g).map((line) => line.split(/\s+/).pop()).sort();
    assert.deepEqual(names, own);
  });
}

// The adapter plugin in vite.config.ts (ADAPTERS) routes these by resolved path; it only looks
// at imports whose file name matches, so every import must name the module file itself.
const ROUTED = [...Object.keys(ADAPTED), `${dist}/utils/format-time-delta.js`, `${dist}/ui/dropdown/clear-button.js`,
  `${dist}/components/features/chat/components/context-window-meter.js`];

for (const module of ROUTED) {
  test(`every import of ${path.basename(module)} uses a path the adapter plugin catches`, () => {
    const target = path.resolve(module);
    const specifiers = [...modules].flatMap(([file, source]) =>
      [...source.matchAll(/from "([^"]+\.js)"/g)].map((match) => ({
        specifier: match[1], resolved: path.resolve(path.dirname(file), match[1]),
      })))
      .filter(({ resolved }) => resolved === target);
    assert.ok(specifiers.length > 0, `nothing imports ${module} any more`);
    for (const { specifier } of specifiers) assert.equal(path.basename(specifier), path.basename(module));
  });
}

test("production config never reads session.env and has no proxy key", async () => {
  const original = fs.readFileSync;
  let secretReads = 0;
  fs.readFileSync = (file, ...args) => {
    if (/(^|\/)(session\.env|\.env)$/.test(String(file))) { secretReads++; throw new Error("Secret read forbidden in build"); }
    return original(file, ...args);
  };
  try {
    const loaded = await loadConfigFromFile({command: "build", mode: "production"}, "vite.config.ts", undefined, "silent", undefined, "native");
    assert.equal(path.basename(loaded.config.envDir), "no-env");
    assert.deepEqual(loaded.config.server.proxy["/api"].headers, {});
    assert.equal(secretReads, 0);
  } finally { fs.readFileSync = original; }
});

test("files landmark adapter changes only the root tag and rejects upstream drift", async () => {
  const {canvasFilesSemantics} = await import("./vite.config.ts");
  const plugin = canvasFilesSemantics();
  const context = {error(message) { throw new Error(message); }};
  const id = path.resolve(dist, "routes/files-tab.js");
  const source = readFileSync(id, "utf8");
  assert.throws(() => plugin.generateBundle.call(context), /not applied/);
  const result = plugin.transform.call(context, source, id);
  assert.equal(result.code.replace(/"section",(\s*\{\s*className: "h-full w-full flex flex-col items-stretch")/, '"main",$1'), source);
  plugin.generateBundle.call(context);
  assert.throws(() => plugin.transform.call(context, source.replace('"data-testid": "files-tab"', '"data-testid": "changed"'), id), /markup changed/);
  assert.equal(plugin.transform.call(context, source, "/another-module.js"), null);
});

test("the build contains no npm registry update-check URL", () => {
  assert.ok(build.every((source) => !source.includes("registry.npmjs.org")), "the update check is back in dist");
});

// Canvas ships no Russian; a key missing from our file shows up as English on screen.
test("every Canvas string has a Russian translation", () => {
  const en = JSON.parse(readFileSync(`${dist}/locales/en/openhands.json`, "utf8"));
  const ru = JSON.parse(readFileSync("src/locales/ru.json", "utf8"));
  assert.deepEqual(Object.keys(en).filter((key) => !ru[key]?.trim()), []);
});

test("Russian strings keep the placeholders and plural forms of the original", () => {
  const en = JSON.parse(readFileSync(`${dist}/locales/en/openhands.json`, "utf8"));
  const ru = JSON.parse(readFileSync("src/locales/ru.json", "utf8"));
  const placeholders = (text) => [...String(text).matchAll(/{{\s*([\w.]+)[^}]*}}/g)].map((m) => m[1]).sort().join();
  assert.deepEqual(Object.keys(en).filter((key) => ru[key] && placeholders(en[key]) !== placeholders(ru[key])), []);
  // i18next picks the suffix from Intl.PluralRules: Russian needs one/few/many (1, 2, 5 files).
  const forms = new Intl.PluralRules("ru").resolvedOptions().pluralCategories;
  const plurals = new Set(Object.keys(en).filter((key) => key.endsWith("_one")).map((key) => key.slice(0, -4)));
  const missing = [...plurals].flatMap((base) => forms.filter((form) => !ru[`${base}_${form}`]).map((form) => `${base}_${form}`));
  assert.deepEqual(missing, []);
});
