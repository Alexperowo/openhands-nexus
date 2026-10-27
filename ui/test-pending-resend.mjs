// Real React effect lifecycle with a delayed offline history service; no Nexus service is used.
import assert from "node:assert/strict";
import http from "node:http";
import { build } from "esbuild";
import puppeteer from "puppeteer-core";

const mocks = {
  "event-service.api.js": `export default {searchEvents: async (id, url, key, options) => {
    window.historyCalls.push({id, options});
    if (window.laterPages) return window.laterPages(options);
    return new Promise(resolve => { window.resolveHistory = resolve; });
  }};`,
  "use-user-conversation.js": `export const useUserConversation = () => ({data: null});`,
  "use-send-message.js": `export const useSendMessage = () => ({send: async message => {window.sent.push(message);}});`,
  "optimistic-user-message-store.js": `export const useOptimisticUserMessageStore = {getState: () => ({
    pendingMessages: window.pending,
    markPendingMessageSending: id => window.sending.push(id),
    markPendingMessageError: id => window.errors.push(id),
  })};`,
};
const bundle = await build({
  stdin: {resolveDir: process.cwd(), loader: "tsx", contents: `
    import React from "react";
    import {createRoot} from "react-dom/client";
    import {usePendingResend} from "./src/pending-resend.ts";
    const originalTimeout = window.setTimeout;
    window.setTimeout = (callback, delay, ...args) => originalTimeout(callback, delay === 3000 ? 20 : delay, ...args);
    function App({id, state}) { usePendingResend(id, state); return <div>{id}:{state}</div>; }
    const root = createRoot(document.getElementById("root"));
    window.render = (id, state) => root.render(<App id={id} state={state}/>);
    window.reset = () => {
      window.sent = []; window.errors = []; window.sending = []; window.historyCalls = []; window.laterPages = null;
      window.pending = [{id:"p", conversationId:"a", content:"Сделай один раз", status:"sending",
        timestamp:"2020-01-01T00:00:00Z", imageUrls:[], fileUrls:[]}];
    };
    window.reset();
  `},
  bundle: true, write: false, platform: "browser", format: "iife", jsx: "automatic",
  plugins: [{name: "offline-services", setup(builder) {
    builder.onResolve({filter: /\.js$/}, args => {
      const name = args.path.split("/").at(-1);
      if (mocks[name]) return {path: name, namespace: "offline"};
    });
    builder.onLoad({filter: /.*/, namespace: "offline"}, args => ({contents: mocks[args.path], loader: "js"}));
  }}],
});
const server = http.createServer((_req, res) => res.end('<div id="root"></div>'));
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await puppeteer.launch({browser:"firefox", executablePath:"/usr/bin/firefox", headless:true});
  // missing: not on the server, resent once; delivered: found on the second page, not resent;
  // incomplete: history longer than the read limit, delivery unknown, retry button instead of a resend.
  for (const scenario of ["missing", "delivered", "incomplete", "navigation", "disconnected"]) {
    const page = await browser.newPage();
    const pageErrors = [];
    page.on("pageerror", error => pageErrors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.addScriptTag({content:bundle.outputFiles[0].text});
    for (const state of ["OPEN", "CLOSED", "OPEN"]) {
      await page.evaluate(state => window.render("a", state), state);
      await page.waitForFunction(state => document.getElementById("root").textContent === `a:${state}`, {}, state);
      // Allow passive effects to run before the next state transition.
      await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 40)));
    }
    await page.waitForFunction(() => window.historyCalls.length === 1);
    if (scenario === "navigation" || scenario === "disconnected") {
      await page.evaluate(scenario => window.render(scenario === "navigation" ? "b" : "a", "CLOSED"), scenario);
      await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 50)));
    }
    await page.evaluate(scenario => {
      if (scenario === "incomplete") window.laterPages = () => ({items:[], next_page_id:"more"});
      if (scenario === "delivered") window.laterPages = () => ({next_page_id:null, items:[{id:"u", source:"user",
        timestamp:"2020-01-01T00:00:01", llm_message:{role:"user", content:[{type:"text", text:"Сделай один раз"}]}}]});
      window.resolveHistory({items:[], next_page_id:scenario === "incomplete" || scenario === "delivered" ? "more" : null});
    }, scenario);
    await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 100)));
    const result = await page.evaluate(() => ({sent:window.sent.length, errors:window.errors.length}));
    assert.deepEqual(result, {sent:scenario === "missing" ? 1 : 0, errors:scenario === "incomplete" ? 1 : 0}, scenario);
    const calls = await page.evaluate(() => window.historyCalls);
    // Read from before the lost message (clock slack), strict paging, and stop at the page limit.
    assert.equal(calls[0].options.timestampGte, "2019-12-31T23:55:00.000Z", scenario);
    assert.equal(calls[0].options.strictPagination, true, scenario);
    if (scenario === "delivered") assert.equal(calls[1].options.pageId, "more");
    if (scenario === "incomplete") assert.equal(calls.length, 10);
    assert.deepEqual(pageErrors, []);
    console.log(`PASS ${scenario}:`, result);
    await page.close();
  }
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
