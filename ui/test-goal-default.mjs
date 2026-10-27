// The real adapter in a real React tree; Canvas modules and the server are offline mocks.
import assert from "node:assert/strict";
import http from "node:http";
import { build } from "esbuild";
import puppeteer from "puppeteer-core";

const mocks = {
  "use-goal-interceptor.js": `export const useGoalInterceptor = () => text => window.calls.push(["canvas", text]);`,
  "conversation-mutation-utils.js": `export const startGoal = async (id, body) => { window.calls.push(["goal", id, {...body}]); return window.goalResult(); };`,
  "use-agent-state.js": `export const useAgentState = () => ({curAgentState: window.agentState});`,
  "conversation-store.js": `export const useConversationStore = select => select({images: window.images, files: [], conversationMode: window.mode});`,
  "custom-toast-handlers.js": `export const displayErrorToast = text => window.calls.push(["toast", text]);`,
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
    window.unmount = () => root.render(<div/>);
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
const goal = (attempt) => ["goal", "c", {objective: "Создай файл", max_iterations: 3, attempt}];
// [name, state, goal start answers in order, expected calls]; attempts are shown as A1, A2… in order
// of appearance. Waits of a second and more (the repeats, GOAL_RETRY_MS) pass at once, except
// when the conversation changes during the first one.
const scenarios = [
  ["plain request to an idle conversation", {}, ["ok"], [goal("A1")]],
  ["command", {text: "/goal Создай файл"}, [], [["canvas", "/goal Создай файл"]]],
  ["attachment", {images: [1]}, [], [["canvas", " Создай файл "]]],
  ["agent at work", {agentState: "running"}, [], [["canvas", " Создай файл "]]],
  ["no conversation yet", {id: null}, [], [["canvas", " Создай файл "]]],
  ["server refused (409)", {}, [409], [goal("A1"), ["next", " Создай файл "]]],
  ["accepted, the gateway lost the answer (502)", {}, [502, "ok"], [goal("A1"), goal("A1")]],
  ["no answer, then refused", {}, ["network", 409], [goal("A1"), goal("A1"), ["next", " Создай файл "]]],
  ["refused after the conversation changed", {switchTo: "d"}, ["network", 409], [goal("A1"), goal("A1"), ["toast"]]],
  ["refused after the page closed", {switchTo: null}, ["network", 409], [goal("A1"), goal("A1"), ["toast"]]],
  ["the same text sent twice", {twice: true}, ["ok", "ok"], [goal("A1"), goal("A2")]],
  ["no answer to any repeat", {}, Array(8).fill(504), [...Array(8).fill(goal("A1")), ["toast"]]],
];
const server = http.createServer((_req, res) => res.end('<div id="root"></div>'));
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await puppeteer.launch({browser: "firefox", executablePath: "/usr/bin/firefox", headless: true});
  for (const [name, state, answers, expected] of scenarios) {
    const page = await browser.newPage();
    const pageErrors = [];
    page.on("pageerror", error => pageErrors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.addScriptTag({content: bundle.outputFiles[0].text});
    const calls = await page.evaluate(async ({state, answers}) => {
      Object.assign(window, {calls: [], images: state.images ?? [], agentState: state.agentState ?? "finished", mode: "code"});
      window.goalResult = () => {
        const answer = answers.shift();
        if (answer === "ok") return Promise.resolve({});
        return Promise.reject(answer === "network" ? new Error("Request timeout after 30000ms")
          : Object.assign(new Error(`HTTP ${answer}`), {status: answer}));
      };
      const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
      const wait = window.setTimeout;
      if (!("switchTo" in state)) window.setTimeout = (callback, ms, ...rest) => wait(callback, ms >= 1000 ? 1 : ms, ...rest);
      const id = "id" in state ? state.id : "c";
      window.render(id, 1);
      await pause(50);
      window.submit(state.text ?? " Создай файл ");
      if (state.twice) window.submit(state.text ?? " Создай файл ");
      await pause(100);
      if ("switchTo" in state) {
        if (state.switchTo) window.render(state.switchTo, 2); else window.unmount();
        await pause(50);
      }
      await pause("switchTo" in state ? 1100 : 100);
      const attempts = [];
      return window.calls.map(call => {
        if (call[0] === "toast") return ["toast"];
        if (call[0] !== "goal") return call;
        if (!attempts.includes(call[2].attempt)) attempts.push(call[2].attempt);
        return [...call.slice(0, 2), {...call[2], attempt: `A${attempts.indexOf(call[2].attempt) + 1}`}];
      });
    }, {state, answers});
    assert.deepEqual(calls, expected, name);
    assert.deepEqual(pageErrors, [], name);
    console.log(`PASS ${name}`);
    await page.close();
  }
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
