import test from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
import { answerPresentation, streamedText, retainContext } from "./src/stream-presentation.ts";
import { speechText } from "./src/speech-events.ts";
import { openStreamingSlot, appendStreamingDeltas, handleEventForUI } from "./node_modules/@openhands/agent-canvas/dist/utils/handle-event-for-ui.js";

test("context: preserve the last valid reading across missing/invalid statistics", () => {
  let state = { id: "a", usage: null, stale: false };
  state = retainContext(state, "a", { contextWindow: 262144, perTurnToken: 10000 });
  for (const incoming of [null, { contextWindow: 0, perTurnToken: 0 },
    { contextWindow: NaN, perTurnToken: 0 }, { contextWindow: 262144, perTurnToken: NaN },
    { contextWindow: Infinity, perTurnToken: 0 }, { contextWindow: 262144, perTurnToken: -1 }]) {
    const next = retainContext(state, "a", incoming);
    assert.equal(next.usage, state.usage);
    assert.equal(next.stale, true);
  }
  const compacted = retainContext(state, "a", { contextWindow: 262144, perTurnToken: 500 });
  assert.equal(compacted.usage.perTurnToken, 500, "compaction is allowed to lower the reading");
  assert.equal(compacted.stale, false);
});

test("context: route changes discard previous readings, including the stale store on first render", () => {
  const usage = { contextWindow: 262144, perTurnToken: 12345 };
  const next = retainContext({ id: "a", usage, stale: false }, "b", usage);
  assert.deepEqual(next, { id: "b", usage: null, stale: false });
  assert.deepEqual(retainContext(next, "b", null), next);
  assert.equal(retainContext(next, "b", usage).usage, usage);
});

test("stream: real Canvas frames accumulate reasoning and text; completion replaces the slot", () => {
  let events = openStreamingSlot({ type: "item_started", item_id: "reply", attempt: 1 }, []);
  events = appendStreamingDeltas([
    { type: "delta", item_id: "reply", kind: "reasoning", content: "Сначала ", attempt: 1 },
    { type: "delta", item_id: "reply", kind: "reasoning", content: "проверю.", attempt: 1 },
    { type: "delta", item_id: "reply", kind: "text", content: "Готово.", attempt: 1 },
  ], events);
  assert.deepEqual(streamedText(events[0]), { reasoning: "Сначала проверю.", message: "Готово." });
  assert.equal(speechText(events[0]), "", "streaming deltas never enter TTS");
  events = handleEventForUI({ id: "reply", kind: "MessageEvent", source: "agent",
    llm_message: { role: "assistant", content: [{ type: "text", text: "Готово." }] } }, events);
  assert.equal(events.length, 1);
  assert.equal(events[0].kind, "MessageEvent");
});

test("stream: retries discard the previous attempt, late deltas cannot restore it", () => {
  let events = appendStreamingDeltas([{ item_id: "reply", kind: "reasoning", content: "Старая попытка", attempt: 1 }], []);
  events = openStreamingSlot({ type: "item_started", item_id: "reply", attempt: 2 }, events);
  events = appendStreamingDeltas([
    { item_id: "reply", kind: "reasoning", content: "Новая попытка", attempt: 2 },
    { item_id: "reply", kind: "reasoning", content: "Поздний чанк", attempt: 1 },
  ], events);
  assert.equal(streamedText(events[0]).reasoning, "Новая попытка");
});

test("stream: inline think blocks remain separate from the spoken answer", () => {
  assert.deepEqual(streamedText({ content: "<think>Проверяю" }), { reasoning: "Проверяю", message: "" });
  assert.deepEqual(streamedText({ content: "<think>Проверил</think>Ответ" }), { reasoning: "Проверил", message: "Ответ" });
  assert.equal(streamedText({ thinking_blocks: [{ type: "thinking", thinking: "Размышление" }] }).reasoning, "Размышление");
});

test("reasoning: collapsed while streaming and in history, never a live region", async () => {
  const result = await build({ stdin: { contents: `
    import React from "react";
    import { renderToStaticMarkup } from "react-dom/server";
    import { ReasoningBlock } from "./src/reasoning-block.tsx";
    export const render = (props) => renderToStaticMarkup(React.createElement(ReasoningBlock, props));
  `, resolveDir: process.cwd(), loader: "tsx" }, bundle: true, write: false, platform: "node", format: "esm", packages: "external", jsx: "automatic" });
  // Bare dependencies resolve relative to this file, without generating a bundle on disk.
  const source = result.outputFiles[0].text.replaceAll('from "react"', `from ${JSON.stringify(import.meta.resolve("react"))}`)
    .replaceAll('from "react-dom/server"', `from ${JSON.stringify(import.meta.resolve("react-dom/server"))}`)
    .replaceAll('from "react/jsx-runtime"', `from ${JSON.stringify(import.meta.resolve("react/jsx-runtime"))}`);
  const { render } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
  const streaming = render({ content: "Проверяю <файл>" });
  assert.doesNotMatch(streaming, /open=""/);
  assert.match(streaming, /aria-live="off"/);
  assert.match(streaming, /Проверяю &lt;файл&gt;/);
  assert.doesNotMatch(render({ content: "История" }), /open=""/);
  assert.equal(render({ content: " " }), "");
  assert.deepEqual(answerPresentation({kind: "ActionEvent", action: {kind: "FinishAction", message: "Готово"},
    reasoning_content: "Проверено"}), {message: "Готово", reasoning: "Проверено"});
  assert.deepEqual(answerPresentation({kind: "MessageEvent", llm_message: {content: [{type: "text", text: "<think>Проверено</think>Готово"}]}}),
    {message: "Готово", reasoning: "Проверено"});
});

test("poll: partial REST success must not announce a recovery before conversation status succeeds", async () => {
  const savedDocument = globalThis.document;
  const savedFetch = globalThis.fetch, savedTimeout = globalThis.setTimeout, savedClear = globalThis.clearTimeout;
  const harness = {state: null, changes: [], timers: [], cleanup: null, status: () => Promise.reject(new Error("metadata unavailable"))};
  globalThis.__pollHarness = harness;
  const result = await build({stdin: {contents: 'export {useConversationSpeech} from "./src/use-conversation-speech.ts";', resolveDir: process.cwd()},
    bundle: true, write: false, platform: "node", format: "esm", plugins: [{name: "hook-environment", setup(builder) {
      builder.onResolve({filter: /^react$/}, () => ({path: "react", namespace: "hook-environment"}));
      builder.onResolve({filter: /\/audio-service\.ts$/}, () => ({path: "audio", namespace: "hook-environment"}));
      builder.onResolve({filter: /\/api\.ts$/}, () => ({path: "api", namespace: "hook-environment"}));
      builder.onLoad({filter: /.*/, namespace: "hook-environment"}, ({path}) => ({contents: path === "react" ? `
        export const useCallback = fn => fn;
        export const useRef = value => ({current: value});
        export const useSyncExternalStore = (_subscribe, snapshot) => snapshot();
        export const useLayoutEffect = effect => {globalThis.__pollHarness.cleanup = effect();};
        export const useState = initial => {
          const h = globalThis.__pollHarness; h.state = initial;
          return [initial, update => {
            const next = typeof update === "function" ? update(h.state) : update;
            if (next !== h.state) h.changes.push(next); h.state = next;
          }];
        };` : path === "api" ? `
        export const requestJson = path => path.includes("/events/search") ? Promise.resolve({items: []}) : globalThis.__pollHarness.status();
        export const errorMessage = error => error.message;` :
        'export const audioService = {stop() {}, speak() {}, speakStep() {}};'}));
    }}]});
  const settle = () => new Promise(resolve => setImmediate(resolve));
  const until = async predicate => { const deadline = Date.now() + 2000; while (!predicate()) { assert.ok(Date.now() < deadline, "poll stalled"); await settle(); } };
  try {
    globalThis.document = Object.assign(new EventTarget(), {visibilityState: "visible"});
    globalThis.fetch = async url => new Response(JSON.stringify(String(url).endsWith("/running") ? {running: [{model: "m", state: "ready"}]} : {slots_processing: 0}));
    globalThis.setTimeout = (callback, delay, ...args) => {
      if (delay !== 1500) return savedTimeout(callback, delay, ...args);
      const timer = {callback}; harness.timers.push(timer); return timer;
    };
    globalThis.clearTimeout = timer => { if (!harness.timers.includes(timer)) savedClear(timer); };
    const module = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`);
    module.useConversationSpeech("conversation-a");
    await until(() => harness.timers.length === 1);
    assert.equal(harness.state.error, "metadata unavailable");
    harness.changes = [];
    let rejectStatus;
    harness.status = () => new Promise((_resolve, reject) => {rejectStatus = reject;});
    harness.timers.shift().callback(); await until(() => rejectStatus);
    assert.equal(harness.state.error, "metadata unavailable", "event success cleared an unresolved status error");
    assert.equal(harness.changes.length, 0);
    rejectStatus(new Error("metadata unavailable")); await until(() => harness.timers.length === 1);
    assert.equal(harness.changes.length, 0, "retry emitted a spurious state transition");
    harness.status = () => Promise.resolve({execution_status: "running"});
    harness.timers.shift().callback(); await until(() => harness.timers.length === 1);
    assert.equal(harness.state.error, ""); assert.equal(harness.state.ready, true);
    assert.equal(harness.changes.length, 1, "only a complete successful poll restores the connection");
  } finally {
    harness.cleanup?.(); globalThis.fetch = savedFetch; globalThis.setTimeout = savedTimeout; globalThis.clearTimeout = savedClear;
    if (savedDocument === undefined) delete globalThis.document; else globalThis.document = savedDocument;
    delete globalThis.__pollHarness;
  }
});
