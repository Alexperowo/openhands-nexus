// Offline component check. Only the server-backed hooks supply fixture data; no live conversation is opened.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import http from "node:http";
import { build } from "esbuild";
import puppeteer from "puppeteer-core";

const bundle = await build({
  stdin: { resolveDir: process.cwd(), loader: "tsx", contents: `
    import React from "react";
    import { createRoot } from "react-dom/client";
    import { NavigationProvider } from "./src/navigation-context.tsx";
    import { ChatInputField } from "./src/chat-input-with-label.tsx";
    import { ReasoningBlock } from "./src/reasoning-block.tsx";
    // In the app the meter replaces Canvas's own in the input actions row (vite ADAPTERS).
    import { ContextWindowMeter } from "./src/context-window-meter.tsx";
    import { useEventStore } from "./node_modules/@openhands/agent-canvas/dist/stores/use-event-store.js";
    useEventStore.getState().clearEventsForConversation("a");
    const root = createRoot(document.getElementById("root"));
    const input = React.createRef();
    window.sample = null;
    window.render = (content = "Проверяю файл") => root.render(
      <React.StrictMode><NavigationProvider value={{ conversationId: "a", currentPath: "/conversations/a", navigate() {}, isNavigating: false }}>
        <ReasoningBlock content={content} />
        <ChatInputField chatInputRef={input} onInput={() => {}} onPaste={() => {}} onKeyDown={() => {}} onFocus={() => {}} onBlur={() => {}} />
        <ContextWindowMeter />
      </NavigationProvider></React.StrictMode>);
    window.render();
  ` },
  bundle: true, write: false, platform: "browser", format: "iife", jsx: "automatic",
  plugins: [{ name: "offline-data", setup(builder) {
    builder.onResolve({ filter: /\/hooks\/use-(context-window-usage|compact-context-action|select-conversation-tab)\.js$/ }, ({ path }) => ({ path, namespace: "offline-data" }));
    builder.onLoad({ filter: /.*/, namespace: "offline-data" }, ({ path }) => ({ contents:
      path.includes("context-window-usage") ? "export const useContextWindowUsage = () => window.sample;" :
      path.includes("compact-context-action") ? "export const useCompactContextAction = () => ({ handleCompact() {}, isDisabled: true, isCompacting: false });" :
      "export const useSelectConversationTab = () => ({ navigateToTab() {} });",
    }));
  } }],
});

// Canvas stores backend selection in localStorage. about:blank has an opaque
// origin in Firefox and fails before React mounts; use a real isolated origin.
const server = http.createServer((_request, response) => response.end('<html lang="ru"><body><div id="root" data-agent-server-ui></div></body></html>'));
await new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await puppeteer.launch({ browser: "firefox", executablePath: "/usr/bin/firefox", headless: true, timeout: 20000 });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => { errors.push(error.message); console.error(error.stack); });
  await page.setRequestInterception(true);
  page.on("request", (request) => request.url() === origin + "/" ? request.continue() : request.abort());
  await page.setViewport({ width: 564, height: 785 });
  const canvasCss = readFileSync("node_modules/@openhands/agent-canvas/dist/styles.css", "utf8")
    .replace(/@import\s*(?:url\(\s*)?(["'])https?:[^"']*\1\s*\)?[^;]*;/g, "");
  await page.goto(origin);
  await page.addStyleTag({content: `${canvasCss}\n${readFileSync("src/index.css", "utf8")}\n${readFileSync("src/motion.css", "utf8")}`});
  await page.addScriptTag({ content: bundle.outputFiles[0].text });
  const meter = ".nexus-context > summary";
  await page.waitForSelector(meter);
  assert.equal(await page.$eval(meter, (node) => node.getAttribute("aria-label")), "Контекст: данных пока нет");
  await page.evaluate(() => { window.sample = { contextWindow: 1000, perTurnToken: 250 }; window.render(); });
  await page.waitForFunction(() => document.querySelector(".nexus-context > summary").getAttribute("aria-label") === "Контекст: 25%");
  await page.focus(meter);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector(".nexus-context").open);
  await page.keyboard.press("Escape");
  assert.equal(await page.$eval(".nexus-context", (node) => node.open), false);
  await page.evaluate(() => { window.sample = null; window.render("Проверяю файл дальше"); });
  await page.waitForFunction(() => document.querySelector(".nexus-context > summary").getAttribute("aria-label").includes("последнее известное"));
  assert.equal(await page.evaluate(() => document.activeElement === document.querySelector(".nexus-context > summary")), true);
  assert.equal(await page.$eval(".nexus-reasoning", (node) => node.open), false, "reasoning starts collapsed, streaming included");
  await page.focus(".nexus-reasoning > summary");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector(".nexus-reasoning").open);
  await page.evaluate(() => window.render("Следующий чанк"));
  assert.equal(await page.$eval(".nexus-reasoning", (node) => node.open), true, "updates must not close a user-opened block");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !document.querySelector(".nexus-reasoning").open);
  assert.equal(await page.$eval(".nexus-reasoning", (node) => node.getAttribute("aria-live")), "off");
  await page.focus('[data-testid="chat-input"]');
  await page.keyboard.type("Привет");
  assert.equal(await page.$eval('[data-testid="chat-input"]', (node) => node.textContent), "Привет");
  const size = await page.$eval(meter, (node) => { const r = node.getBoundingClientRect(); return [r.width, r.height]; });
  assert.ok(size.every((value) => value >= 48));
  assert.deepEqual(errors, []);
  console.log("PASS: offline Firefox 564×785; unknown/valid/missing metrics, retained focus, Enter/Escape, reasoning collapsed + toggle, live=off, native text input, 48px; no page errors");
} finally { await browser?.close(); await new Promise(resolve => server.close(resolve)); }
