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

test("socket: history silent, each answer spoken once across reconnects, notices only for real outages, model read only while running", async () => {
  const savedDocument = globalThis.document, savedLocation = globalThis.location, savedSocket = globalThis.WebSocket;
  const savedFetch = globalThis.fetch, savedTimeout = globalThis.setTimeout, savedClear = globalThis.clearTimeout;
  const harness = {state: null, changes: [], timers: [], sockets: [], spoken: [], requests: [], count: () => Promise.resolve(3), cleanup: null};
  globalThis.__socketHarness = harness;
  const result = await build({stdin: {contents: 'export {useConversationSpeech} from "./src/use-conversation-speech.ts";', resolveDir: process.cwd()},
    bundle: true, write: false, platform: "node", format: "esm", plugins: [{name: "hook-environment", setup(builder) {
      builder.onResolve({filter: /^react$/}, () => ({path: "react", namespace: "hook-environment"}));
      builder.onResolve({filter: /\/audio-service\.ts$/}, () => ({path: "audio", namespace: "hook-environment"}));
      builder.onResolve({filter: /\/api\.ts$/}, () => ({path: "api", namespace: "hook-environment"}));
      builder.onResolve({filter: /\/preferences\.ts$/}, () => ({path: "preferences", namespace: "hook-environment"}));
      builder.onLoad({filter: /.*/, namespace: "hook-environment"}, ({path}) => ({contents: {react: `
        export const useCallback = fn => fn;
        export const useRef = value => ({current: value});
        export const useLayoutEffect = effect => {globalThis.__socketHarness.cleanup = effect();};
        export const useState = initial => {
          const h = globalThis.__socketHarness; h.state = initial;
          return [initial, update => {
            const next = typeof update === "function" ? update(h.state) : update;
            if (next !== h.state) h.changes.push(next); h.state = next;
          }];
        };`, api: `
        export const requestJson = path => { globalThis.__socketHarness.requests.push(path);
          return path.endsWith("/events/count") ? globalThis.__socketHarness.count() : Promise.reject(new Error("unexpected " + path)); };
        export const errorMessage = error => error.message;`,
        preferences: "export const getPreferences = () => ({autoSpeak: true, speakSteps: true});",
        audio: "export const audioService = {stop() {}, speak(id) {globalThis.__socketHarness.spoken.push(id);}, speakStep(id) {globalThis.__socketHarness.spoken.push(id);}};",
      }[path]}));
    }}]});
  const settle = () => new Promise(resolve => setImmediate(resolve));
  const until = async (predicate, what) => { const deadline = Date.now() + 2000; while (!predicate()) { assert.ok(Date.now() < deadline, what); await settle(); } };
  const fire = async delay => {
    const index = harness.timers.findIndex(timer => timer.delay === delay);
    assert.ok(index >= 0, `no timer of ${delay} ms`);
    harness.timers.splice(index, 1)[0].callback(); await settle(); await settle();
  };
  const say = (id, text) => ({id, kind: "MessageEvent", source: "agent", llm_message: {role: "assistant", content: [{type: "text", text}]}});
  const user = (id, text) => ({id, kind: "MessageEvent", source: "user", llm_message: {role: "user", content: [{type: "text", text}]}});
  const status = (id, value) => ({id, kind: "ConversationStateUpdateEvent", source: "environment", key: "execution_status", value});
  const snapshot = value => ({type: "transient", event: {id: `snap-${value}`, kind: "ConversationStateUpdateEvent", source: "environment", key: "full_state", value: {execution_status: value}}});
  const socket = () => harness.sockets.at(-1);
  const send = (...frames) => { for (const frame of frames) socket().onmessage({data: JSON.stringify(frame)}); };
  const durable = (seq, event) => ({type: "durable", seq, event});
  try {
    globalThis.document = Object.assign(new EventTarget(), {visibilityState: "visible"});
    globalThis.location = new URL("https://nexus.test:8443/conversations/conversation-a");
    globalThis.WebSocket = class { static OPEN = 1; readyState = 1; closed = false;
      constructor(url) { this.url = new URL(url); harness.sockets.push(this); }
      close() { this.closed = true; this.readyState = 3; } };
    globalThis.fetch = async url => { harness.requests.push(String(url));
      return new Response(JSON.stringify(String(url).endsWith("/running") ? {running: [{model: "m", state: "ready"}]} : {slots_processing: 1})); };
    globalThis.setTimeout = (callback, delay) => { const timer = {callback, delay}; harness.timers.push(timer); return timer; };
    globalThis.clearTimeout = timer => { const index = harness.timers.indexOf(timer); if (index >= 0) harness.timers.splice(index, 1); };
    const module = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`);
    module.useConversationSpeech("conversation-a");
    await until(() => harness.sockets.length === 1, "no socket");
    assert.equal(socket().url.href, "wss://nexus.test:8443/sockets/session/conversation-a?after_seq=-1");

    // Opening: history replays silently; ready only with the server's snapshot.
    send({type: "sync", from_seq: -1, through_seq: 2}, durable(0, user("u0", "привет")), durable(1, say("a1", "Старый ответ")),
      durable(2, user("u2", "сделай")));
    assert.equal(harness.state.ready, false);
    send(snapshot("running"));
    assert.equal(harness.state.ready, true); assert.equal(harness.state.status, "running"); assert.deepEqual(harness.spoken, []);
    await fire(0);
    assert.equal(harness.state.model, "busy", "model read at once while running");
    assert.ok(harness.timers.some(timer => timer.delay === 1500), "and again after 1.5 s");

    // Live: spoken once; a finished run stops the model reads.
    send(durable(3, say("a3", "Готово")), durable(3, say("a3", "Готово")), durable(4, status("s4", "finished")));
    assert.deepEqual(harness.spoken, ["a3"]);
    assert.equal(harness.state.status, "finished", "a reply in words: no «not checked»"); assert.equal(harness.state.model, "unknown");
    const reads = harness.requests.filter(path => path.endsWith("/running")).length;
    await fire(1500);
    assert.equal(harness.requests.filter(path => path.endsWith("/running")).length, reads, "no model read after the run");

    // A dropped socket reconnects quietly from the last seq; what came meanwhile is spoken, repeats are not.
    socket().onclose();
    assert.equal(harness.state.error, "");
    await fire(500);
    assert.equal(socket().url.searchParams.get("after_seq"), "4");
    send({type: "sync", from_seq: 4, through_seq: 6}, durable(3, say("a3", "Готово")), durable(5, user("u5", "ещё")),
      durable(6, say("a6", "Второй ответ")), snapshot("finished"));
    assert.deepEqual(harness.spoken, ["a3", "a6"]);

    // A failed attempt is a real outage: noticed, then cleared by the next connection.
    socket().onclose();
    await fire(500);
    socket().onclose();
    assert.equal(harness.state.error, "Нет связи с сервером");
    await fire(1000);
    assert.equal(socket().url.searchParams.get("after_seq"), "6");
    send({type: "sync", from_seq: 6, through_seq: 6}, snapshot("finished"));
    assert.equal(harness.state.error, ""); assert.equal(harness.state.status, "finished");

    // A silently dead socket: the log grows past it twice in a row and it is replaced.
    harness.count = () => Promise.resolve(9);
    const dead = socket();
    await fire(30000);
    assert.equal(harness.sockets.length, 4, "one check may see an event still on its way");
    await fire(3000);
    assert.ok(dead.closed);
    assert.equal(socket().url.searchParams.get("after_seq"), "6");
    send({type: "sync", from_seq: 6, through_seq: 8}, durable(7, user("u7", "и это")), durable(8, say("a8", "Третий ответ")), snapshot("finished"));
    assert.deepEqual(harness.spoken, ["a3", "a6", "a8"]);
    const idle = harness.requests.length;
    await fire(30000);
    assert.equal(harness.requests.length - idle, 1, "idle: one count request per 30 s");

    harness.cleanup();
    assert.ok(socket().closed);
    assert.deepEqual(harness.timers, []);
  } finally {
    harness.cleanup?.(); globalThis.fetch = savedFetch; globalThis.setTimeout = savedTimeout; globalThis.clearTimeout = savedClear;
    globalThis.WebSocket = savedSocket;
    for (const [key, value] of [["document", savedDocument], ["location", savedLocation]]) {
      if (value === undefined) delete globalThis[key]; else globalThis[key] = value;
    }
    delete globalThis.__socketHarness;
  }
});
