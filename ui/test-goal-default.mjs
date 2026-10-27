// The real adapter in a real React tree; Canvas modules and the server are offline mocks.
import assert from "node:assert/strict";
import http from "node:http";
import { build } from "esbuild";
import puppeteer from "puppeteer-core";

const mocks = {
  "use-goal-interceptor.js": `export const useGoalInterceptor = () => text => window.calls.push(["canvas", text]);`,
  "conversation-mutation-utils.js": `export const startGoal = async (id, body) => { window.calls.push(["goal", id, body]); return window.goalResult(); };`,
  "use-user-conversation.js": `export const useUserConversation = () => ({data: null});`,
  "use-agent-state.js": `export const useAgentState = () => ({curAgentState: window.agentState});`,
  "conversation-store.js": `export const useConversationStore = select => select({images: window.images, files: [], conversationMode: window.mode});`,
  "custom-toast-handlers.js": `export const displayErrorToast = text => window.calls.push(["toast", text]);`,
  "event-service.api.js": `export default {searchEvents: async () => window.historyPage()};`,
  "use-send-message.js": `export const useSendMessage = () => ({send: async () => {}});`,
  "optimistic-user-message-store.js": `export const useOptimisticUserMessageStore = {getState: () => ({pendingMessages: []})};`,
};
const bundle = await build({
  stdin: {resolveDir: process.cwd(), loader: "tsx", contents: `
    import React from "react";
    import {createRoot} from "react-dom/client";
    import {useGoalInterceptor} from "./src/use-goal-by-default.ts";
    function App({id, version}) {
      window.submit = useGoalInterceptor(id, text => window.calls.push(["next", text]));
      return <div>{id}:{version}</div>;
    }
    const root = createRoot(document.getElementById("root"));
    window.render = (id, version) => root.render(<App id={id} version={version}/>);
  `},
  bundle: true, write: false, platform: "browser", format: "iife", jsx: "automatic",
  plugins: [{name: "offline-canvas", setup(builder) {
    builder.onResolve({filter: /\.js$/}, args => {
      const name = args.path.split("/").at(-1);
      if (mocks[name]) return {path: name, namespace: "offline"};
    });
    builder.onLoad({filter: /.*/, namespace: "offline"}, args => ({contents: mocks[args.path], loader: "js"}));
  }}],
});
const user = text => ({id: "u", source: "user", timestamp: new Date().toISOString(),
  llm_message: {role: "user", content: [{type: "text", text}]}});
const goal = ["goal", "c", {objective: "Создай файл", max_iterations: 3}];
// [name, state, goal start result, history, expected calls]
const scenarios = [
  ["plain request to an idle conversation", {}, "ok", null, [goal]],
  ["command", {text: "/goal Создай файл"}, "ok", null, [["canvas", "/goal Создай файл"]]],
  ["attachment", {images: [1]}, "ok", null, [["canvas", " Создай файл "]]],
  ["agent at work", {agentState: "running"}, "ok", null, [["canvas", " Создай файл "]]],
  ["no conversation yet", {id: null}, "ok", null, [["canvas", " Создай файл "]]],
  ["server refused (409)", {}, "http", null, [goal, ["next", " Создай файл "]]],
  ["no answer, request arrived", {}, "network", [user("Создай файл")], [goal]],
  ["no answer, request lost", {}, "network", [user("Другое")], [goal, ["next", " Создай файл "]]],
  ["no answer, history unreadable", {}, "network", "fail", [goal, ["toast"]]],
];
const server = http.createServer((_req, res) => res.end('<div id="root"></div>'));
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await puppeteer.launch({browser: "firefox", executablePath: "/usr/bin/firefox", headless: true});
  for (const [name, state, result, history, expected] of scenarios) {
    const page = await browser.newPage();
    const pageErrors = [];
    page.on("pageerror", error => pageErrors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.addScriptTag({content: bundle.outputFiles[0].text});
    const calls = await page.evaluate(async ({state, result, history}) => {
      Object.assign(window, {calls: [], images: state.images ?? [], agentState: state.agentState ?? "finished", mode: "code"});
      window.goalResult = () => result === "ok" ? Promise.resolve({}) : Promise.reject(
        result === "http" ? Object.assign(new Error("HTTP 409"), {status: 409}) : new Error("Request timeout after 30000ms"));
      window.historyPage = async () => { if (history === "fail") throw new Error("offline"); return {items: history ?? [], next_page_id: null}; };
      const id = "id" in state ? state.id : "c";
      window.render(id, 1);
      await new Promise(resolve => setTimeout(resolve, 50));
      window.submit(state.text ?? " Создай файл ");
      await new Promise(resolve => setTimeout(resolve, 100));
      return window.calls.map(call => call[0] === "toast" ? ["toast"] : call);
    }, {state, result, history});
    assert.deepEqual(calls, expected, name);
    assert.deepEqual(pageErrors, [], name);
    console.log(`PASS ${name}`);
    await page.close();
  }
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
