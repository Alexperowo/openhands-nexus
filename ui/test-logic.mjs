import test from "node:test";
import assert from "node:assert/strict";
import { SpeechEvents, forSpeech, speechText, speechChunks, formatPlanCount, clipStepExplanation, actionSpeechPhrase } from "./src/speech-events.ts";
import { getPreferences, setPreferences, stateCuesEnabled } from "./src/preferences.ts";
import { AgentActivity, actionLabel, describeStatus } from "./src/agent-activity.ts";
import { tabBoundary } from "./src/focus.ts";
import { shouldAnnounceStatus } from "./src/status-announcement.ts";
import { createElement } from "react";
import { dialogLabel } from "./src/dialog-label.ts";
import { initialOpening, requestOpening, beginOpening, finishOpening, mayShowOpened, isNewConversationClick } from "./src/conversation-opening.ts";
import { originBackends, isOriginSelection, originLocation } from "./src/backend-origin.ts";
import { shouldFoldSidebar } from "./src/narrow-sidebar.ts";
import { withGuard, guardedBody } from "./src/guard-hooks.ts";

test("opening: one page-load attempt, including StrictMode effect replay; redirects never create a loop", () => {
  for (const path of ["/", "/conversations"]) {
    const initial = initialOpening(path);
    const started = beginOpening(initial, path);
    assert.ok(started.operation);
    assert.equal(initial.opening, null, "transitions do not mutate the input");
    assert.equal(beginOpening(started.state, path).operation, null, "StrictMode cannot duplicate the request");
    const done = finishOpening(started.state, started.operation);
    for (let i = 0; i < 1500; i++) {
      assert.equal(beginOpening(done, "/conversations").operation, null);
      assert.equal(beginOpening(done, "/").operation, null);
    }
  }
  assert.equal(beginOpening(initialOpening("/conversations/missing"), "/conversations").operation, null);
});

test("opening: explicit New chat or Retry works on the same route after failure", () => {
  const started = beginOpening(initialOpening("/conversations"), "/conversations");
  const failed = finishOpening(started.state, started.operation);
  assert.equal(beginOpening(failed, "/conversations").operation, null);
  const retry = beginOpening(requestOpening(failed, "/conversations"), "/conversations");
  assert.ok(retry.operation);
  assert.notEqual(retry.operation.id, started.operation.id);
  assert.equal(beginOpening(finishOpening(retry.state, retry.operation), "/conversations").operation, null);
});

test("opening: repeated clicks during a request do not queue duplicate conversations", () => {
  const started = beginOpening(initialOpening("/conversations"), "/conversations");
  assert.equal(requestOpening(started.state, "/conversations"), started.state);
  assert.equal(beginOpening(started.state, "/conversations").operation, null);
  assert.equal(beginOpening(finishOpening(started.state, started.operation), "/conversations").operation, null);
});

test("opening: New chat during the root lookup waits, and the old result cannot replace it", () => {
  const root = beginOpening(initialOpening("/"), "/");
  const queued = requestOpening(root.state, "/conversations");
  assert.equal(beginOpening(queued, "/conversations").operation, null, "one request at a time");
  assert.equal(mayShowOpened(queued, root.operation, "/"), false);
  const next = beginOpening(finishOpening(queued, root.operation), "/conversations");
  assert.ok(next.operation);
  assert.equal(mayShowOpened(next.state, next.operation, "/settings"), false);
  assert.equal(mayShowOpened(next.state, next.operation, "/conversations"), true);
  assert.equal(finishOpening(next.state, root.operation), next.state, "stale completion cannot unlock a newer request");
});

test("opening: permissions are route-bound; visiting settings does not authorize a conversation", () => {
  const initial = initialOpening("/settings");
  assert.equal(requestOpening(initial, "/settings"), initial);
  assert.equal(beginOpening(initial, "/conversations").operation, null);
  assert.equal(beginOpening(initialOpening("/"), "/conversations").operation, null);
});

test("opening: native link accepts a click from mouse, keyboard or accessibility, without keydown permission", () => {
  const click = { button: 0, metaKey: false, altKey: false, ctrlKey: false, shiftKey: false, defaultPrevented: false };
  const link = { target: "", disabled: false };
  assert.equal(isNewConversationClick(click, link), true, "no pointerType or isTrusted requirement for TalkBack click");
  assert.equal(isNewConversationClick(click, { ...link, target: "_self" }), true);
  for (const field of ["metaKey", "altKey", "ctrlKey", "shiftKey", "defaultPrevented"]) {
    assert.equal(isNewConversationClick({ ...click, [field]: true }, link), false);
  }
  assert.equal(isNewConversationClick({ ...click, button: 1 }, link), false);
  assert.equal(isNewConversationClick(click, { ...link, target: "_blank" }), false);
  assert.equal(isNewConversationClick(click, { ...link, disabled: true }), false);
});

test("backend origin: normalize only the shell backend; keep other entries and correct input unchanged", () => {
  const other = { id: "other", name: "Other", host: "https://other.invalid", kind: "local", apiKey: "" };
  const old = { id: "default-local", name: "Мой ПК", host: "http://old.invalid", kind: "cloud", apiKey: "obsolete", authMode: "cookie" };
  const input = [other, old];
  const normalized = originBackends(input, "https://nexus.invalid:8443", "default-local");
  assert.equal(input[1], old);
  assert.deepEqual(normalized[0], { id: "default-local", name: "Мой ПК", host: "https://nexus.invalid:8443", apiKey: "", kind: "local" });
  assert.equal(normalized[1], other);
  assert.equal(originBackends(normalized, "https://nexus.invalid:8443", "default-local"), normalized);
  assert.equal(originBackends([], "https://nexus.invalid:8443", "default-local").length, 1);
  assert.equal(isOriginSelection({ backend: normalized[0], orgId: null }, "https://nexus.invalid:8443", "default-local"), true);
  assert.equal(isOriginSelection({ backend: other, orgId: null }, "https://nexus.invalid:8443", "default-local"), false);
  assert.equal(isOriginSelection({ backend: normalized[0], orgId: "old-org" }, "https://nexus.invalid:8443", "default-local"), false);
});

test("backend origin: remove Canvas URL selection but preserve conversation path, other parameters and hash", () => {
  assert.equal(originLocation("https://nexus.invalid:8443/conversations/id?backend=other&org=old&keep=1#message"), "/conversations/id?keep=1#message");
  assert.equal(originLocation("https://nexus.invalid:8443/settings/voice"), "/settings/voice");
});

test("dialog name comes from its nested confirmation title, not the warning or action buttons", () => {
  const Title = () => null;
  const tree = createElement("div", null,
    createElement("span", null, "Это действие необратимо"),
    createElement("section", null, createElement(Title, { title: "Удалить беседу?" })),
    createElement("button", null, "Отмена"));
  assert.equal(dialogLabel(tree, Title), "Удалить беседу?");
  assert.equal(dialogLabel(createElement("div", null, "Нет заголовка"), Title), undefined);
  assert.equal(dialogLabel(null, Title), undefined);
});

test("keyboard: a dialog wraps Tab in both directions, including an empty or escaped scope", () => {
  assert.equal(tabBoundary(3, 2, false), 0);
  assert.equal(tabBoundary(3, 0, true), 2);
  assert.equal(tabBoundary(3, 1, false), null);
  assert.equal(tabBoundary(3, 1, true), null);
  assert.equal(tabBoundary(3, -1, false), 0);
  assert.equal(tabBoundary(3, -1, true), 2);
  assert.equal(tabBoundary(0, -1, false), -1);
  assert.equal(tabBoundary(1, 0, true), 0);
});

test("announcements: opening history is silent, a current confirmation or error is not", () => {
  const empty = { status: "", error: "" };
  for (const status of ["running", "finished", "paused"]) {
    assert.equal(shouldAnnounceStatus(empty, { status, error: "" }), false);
  }
  for (const status of ["awaiting_user_confirmation", "awaiting_user_input", "error", "stuck"]) {
    assert.equal(shouldAnnounceStatus(empty, { status, error: "" }), true);
  }
  assert.equal(shouldAnnounceStatus(empty, { status: "running", error: "Ошибка модели" }), true);
});

test("announcements: unchanged states and cleared errors are silent; new errors and completion speak", () => {
  const running = { status: "running", error: "" };
  assert.equal(shouldAnnounceStatus(running, running), false);
  const failed = { status: "running", error: "Сервис недоступен" };
  assert.equal(shouldAnnounceStatus(running, failed), true);
  assert.equal(shouldAnnounceStatus(failed, failed), false);
  assert.equal(shouldAnnounceStatus(failed, running), false);
  assert.equal(shouldAnnounceStatus(running, { status: "finished", error: "" }), true);
  assert.equal(shouldAnnounceStatus(running, { status: "", error: "" }), false);
});

const message = (id, text, source = "agent") => ({
  id, source, kind: "MessageEvent",
  llm_message: {
    role: source === "agent" ? "assistant" : "user",
    content: [{ type: "text", text }],
    reasoning_content: "Нельзя озвучивать",
  },
});
const finish = (id, text) => ({
  id, source: "agent", kind: "ActionEvent", tool_name: "finish", action: { message: text },
});

function historyReader(history) {
  return async (pageId, limit) => {
    const descending = [...history].reverse();
    const offset = pageId ? descending.findIndex((event) => event.id === pageId) : 0;
    assert.ok(offset >= 0);
    return {
      items: descending.slice(offset, offset + limit),
      next_page_id: descending[offset + limit]?.id ?? null,
    };
  };
}

test("MessageEvent and finish: visible text only, no observations or reasoning", () => {
  const event = message("message", "Ответ");
  event.llm_message.content.push({ type: "thinking", text: "Скрыто" });
  event.extended_content = [{ type: "text", text: "Контекст" }];
  assert.equal(speechText(event), "Ответ");
  assert.equal(speechText(finish("finish", "Готово")), "Готово");
  assert.equal(speechText({ ...finish("observation", "Повтор"), kind: "ObservationEvent" }), "");
  assert.equal(speechText(message("user", "Задание", "user")), "");
  assert.equal(speechText({ ...event, llm_message: { role: "assistant", content: [] } }), "");
});

test("old history stays silent; more than 100 new events arrive in server order exactly once", async () => {
  const history = Array.from({ length: 240 }, (_, i) => message(`old-${i}`, "История"));
  const cursor = new SpeechEvents();
  const read = historyReader(history);
  assert.deepEqual(await cursor.readNew(read), []);
  const incoming = Array.from({ length: 235 }, (_, i) => message(`new-${i}`, `Ответ ${i}`));
  history.push(...incoming);
  assert.deepEqual(await cursor.readNew(read), incoming);
  assert.deepEqual(await cursor.readNew(read), []);
  const reloaded = new SpeechEvents();
  assert.deepEqual(await reloaded.readNew(read), []);
  assert.deepEqual(await reloaded.readNew(read), []);
});

test("deduplicate finish/message in either order, but allow the same answer in a new turn", () => {
  for (const pair of [
    [message("m", "Готово"), finish("f", "Готово")],
    [finish("f", "Готово"), message("m", "Готово")],
  ]) {
    const cursor = new SpeechEvents();
    assert.equal(cursor.takeText(pair[0]), "Готово");
    assert.equal(cursor.takeText(pair[1]), "");
    assert.equal(cursor.takeText(message("u", "Снова", "user")), "");
    assert.equal(cursor.takeText(message("next", "Готово")), "Готово");
  }
});

test("failed pagination does not advance cursor; removed history is an error rather than old speech", async () => {
  const history = [message("old", "История")];
  const read = historyReader(history);
  const cursor = new SpeechEvents();
  await cursor.readNew(read);
  history.push(...Array.from({ length: 110 }, (_, i) => message(`new-${i}`, `Ответ ${i}`)));
  await assert.rejects(cursor.readNew(async (id, limit) => {
    if (id) throw new Error("HTTP 503");
    return read(id, limit);
  }), /503/);
  assert.equal((await cursor.readNew(read)).length, 110);
  history.splice(0, history.length, message("replacement", "Старая чужая история"));
  await assert.rejects(cursor.readNew(read), /История диалога изменилась/);
});

test("an initially empty conversation speaks its first new answer", async () => {
  const history = [];
  const cursor = new SpeechEvents();
  const read = historyReader(history);
  assert.deepEqual(await cursor.readNew(read), []);
  history.push(message("first", "Первый ответ"));
  assert.deepEqual(await cursor.readNew(read), history);
});

// Isolated lifecycle tests with fake browser audio/fetch; no services are started.
async function audioFixture(t, fetchImplementation, rejectPlay = false) {
  const originalAudio = globalThis.Audio;
  const originalFetch = globalThis.fetch;
  const elements = [];
  const played = [];
  class AudioElement extends EventTarget {
    constructor() { super(); this.src = ""; elements.push(this); }
    play() {
      if (rejectPlay) return Promise.reject(new DOMException("Blocked", "NotAllowedError"));
      if (this.src.startsWith("blob:")) played.push(this);
      return Promise.resolve();
    }
    pause() {}
    load() {}
    removeAttribute() { this.src = ""; }
  }
  globalThis.Audio = AudioElement;
  globalThis.fetch = fetchImplementation;
  const { audioService } = await import(`./src/audio-service.ts?case=${t.name}`);
  const unsubscribe = audioService.subscribe(() => {});
  t.after(() => {
    audioService.stop();
    unsubscribe();
    globalThis.Audio = originalAudio;
    globalThis.fetch = originalFetch;
  });
  return { audioService, elements, played, get status() { return audioService.getStatus(); } };
}
const settle = () => new Promise((resolve) => setImmediate(resolve));
async function waitFor(predicate) {
  const deadline = Date.now() + 2000;
  while (!predicate()) {
    assert.ok(Date.now() < deadline, "Lifecycle condition timed out");
    await settle();
  }
}

const playing = (fixture) => fixture.status.currentId !== null;

test("TalkBack signals mode stops reading and prefetch, rejects automatic speech, but allows manual reading", async (t) => {
  const saved = { ...getPreferences() };
  t.after(() => setPreferences(saved));
  setPreferences({ autoSpeak: true, cues: false });
  const signals = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    signals.push(options.signal);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speak("old", "Ответ агента. ".repeat(60));
  await waitFor(() => signals.length === 2);
  fixture.audioService.setAutoSpeak(false);
  assert.equal(getPreferences().autoSpeak, false);
  assert.equal(fixture.status.currentId, null);
  assert.ok(signals.every((signal) => signal.aborted));
  assert.equal(stateCuesEnabled(getPreferences()), true, "signals survive an old muted-cues preference");
  fixture.audioService.speak("automatic", "Не читать автоматически");
  await settle();
  assert.equal(signals.length, 2);
  fixture.audioService.playNow("manual", "Читать только по нажатию", true);
  await waitFor(() => signals.length === 3);
  assert.equal(fixture.status.currentId, "manual:full");
  fixture.audioService.stop();
  fixture.audioService.setAutoSpeak(true);
  await settle();
  assert.equal(signals.length, 3, "turning automatic reading back on must not replay a backlog");
  assert.equal(stateCuesEnabled(getPreferences()), false, "the independent cue preference survives returning to automatic speech");
});

test("TalkBack keeps status cues and live announcements independent of automatic answer speech", async () => {
  const { cueForStatus } = await import("./src/status-cues.ts");
  assert.equal(stateCuesEnabled({ autoSpeak: false, cues: false }), true);
  assert.equal(stateCuesEnabled({ autoSpeak: false, cues: true }), true);
  assert.equal(stateCuesEnabled({ autoSpeak: true, cues: false }), false);
  assert.equal(stateCuesEnabled({ autoSpeak: true, cues: true }), true);
  for (const status of ["finished", "awaiting_user_confirmation", "error"]) {
    assert.ok(cueForStatus(status));
    assert.equal(shouldAnnounceStatus({ status: "running", error: "" }, { status, error: "" }), true);
  }
});

test("dictation stops playback and its prefetch; automatic and manual speech stay silent until release", async (t) => {
  const signals = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    signals.push(options.signal);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speak("before-recording", "Длинный ответ. ".repeat(60));
  await waitFor(() => signals.length === 2);
  const release = fixture.audioService.beginDictation();
  assert.equal(fixture.status.isDictating, true);
  assert.equal(playing(fixture), false);
  assert.ok(signals.every((signal) => signal.aborted));
  fixture.audioService.speak("during-recording", "Не читать в микрофон");
  fixture.audioService.playNow("manual", "Не читать и вручную", true);
  await settle();
  assert.equal(signals.length, 2);
  release();
  assert.equal(fixture.status.isDictating, false);
  await settle();
  assert.equal(signals.length, 2, "recording must not leave a speech backlog");
  fixture.audioService.speak("after-recording", "Можно читать");
  await waitFor(() => signals.length === 3);
});

test("dictation release is idempotent and one recorder cannot unlock another", async (t) => {
  const fixture = await audioFixture(t, () => assert.fail("No TTS during recording"));
  const releaseFirst = fixture.audioService.beginDictation();
  const releaseSecond = fixture.audioService.beginDictation();
  releaseFirst();
  releaseFirst();
  fixture.audioService.stop();
  assert.equal(fixture.status.isDictating, true, "Stop is not an end-of-recording signal");
  await fixture.audioService.unlockAudio();
  assert.equal(fixture.elements.length, 0, "even audio unlock waits until recording ends");
  releaseSecond();
  assert.equal(fixture.status.isDictating, false);
  await fixture.audioService.unlockAudio();
  assert.equal(fixture.status.isUnlocked, true);
});

test("a late synthesis response cannot resume speech after microphone acquisition", async (t) => {
  let respond;
  const fixture = await audioFixture(t, () => new Promise((resolve) => { respond = resolve; }));
  await fixture.audioService.unlockAudio();
  fixture.audioService.speak("late", "Поздний ответ сервиса");
  const release = fixture.audioService.beginDictation();
  t.after(release);
  respond(new Response(new Blob(["audio"])));
  await settle();
  assert.equal(fixture.status.currentId, null);
  assert.equal(fixture.elements[0].src, "");
});

test("audio: automatic reading waits for unlock and leaves no hidden backlog", async (t) => {
  let requests = 0;
  const fixture = await audioFixture(t, () => { requests++; throw new Error("Unexpected request"); });
  fixture.audioService.speak("early", "До включения");
  await fixture.audioService.unlockAudio();
  await settle();
  assert.equal(requests, 0);
  assert.equal(fixture.status.isUnlocked, true);
  assert.equal(fixture.elements.length, 2, "two reusable elements: the current part and the preloaded next one");
});

test("audio: rejected unlock stays locked with a visible error and drops the request", async (t) => {
  const fixture = await audioFixture(t, () => assert.fail("No TTS allowed"), true);
  fixture.audioService.playNow("answer", "Ответ");
  await settle();
  assert.equal(fixture.status.isUnlocked, false);
  assert.match(fixture.status.error, /Браузер пока не разрешил звук/);
  fixture.elements[0].play = () => Promise.resolve();
  await fixture.audioService.unlockAudio();
  await settle();
  assert.equal(playing(fixture), false, "a refused ▶ must not play later by surprise");
});

test("audio: ▶ before unlock plays that answer once sound is allowed", async (t) => {
  const bodies = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    bodies.push(JSON.parse(options.body));
    return new Response(new Blob(["audio"]));
  });
  fixture.audioService.playNow("answer", "**Ответ** с `кодом`");
  await waitFor(() => fixture.elements[0].src.startsWith("blob:"));
  assert.equal(fixture.status.currentId, "answer");
  assert.equal(bodies.length, 1);
  assert.equal(bodies[0].input, "Ответ с кодом");
  assert.equal(bodies[0].voice, "xenia");
});

test("audio: the same answer is not read twice, ▶ replaces the current one", async (t) => {
  const inputs = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    inputs.push(JSON.parse(options.body).input);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speak("a", "Первый");
  fixture.audioService.speak("a", "Первый");
  await waitFor(() => fixture.elements[0].src.startsWith("blob:"));
  fixture.audioService.playNow("b", "Второй");
  await waitFor(() => fixture.status.currentId === "b" && fixture.elements[0].src.startsWith("blob:"));
  assert.deepEqual(inputs, ["Первый", "Второй"]);
});

test("audio: an answer finished by ▶ is not read again when the poll reports it", async (t) => {
  const inputs = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    inputs.push(JSON.parse(options.body).input);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.playNow("a", "Ответ");
  await waitFor(() => fixture.elements[0].src.startsWith("blob:"));
  fixture.elements[0].dispatchEvent(new Event("ended"));
  await waitFor(() => !playing(fixture));
  fixture.audioService.speak("a", "Ответ");
  await settle();
  assert.equal(playing(fixture), false);
  fixture.audioService.playNow("a", "Ответ");
  await waitFor(() => inputs.length === 2);
});

test("audio: Stop aborts synthesis and a late response cannot resume speech", async (t) => {
  let resolveFetch;
  let signal;
  const fixture = await audioFixture(t, (_url, options) => {
    signal = options.signal;
    return new Promise((resolve) => { resolveFetch = resolve; });
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speak("stop", "Остановить");
  assert.equal(playing(fixture), true);
  fixture.audioService.stop();
  assert.equal(signal.aborted, true);
  resolveFetch(new Response(new Blob(["audio"])));
  await settle();
  assert.equal(playing(fixture), false);
  assert.equal(fixture.elements[0].src, "");
});

test("audio: HTTP failure clears the queue and reports it; sound stays allowed", async (t) => {
  const fixture = await audioFixture(t, async () => new Response("", { status: 503 }));
  await fixture.audioService.unlockAudio();
  fixture.audioService.speak("a", "Ответ");
  fixture.audioService.speak("b", "Очередь");
  await waitFor(() => !playing(fixture));
  assert.equal(fixture.status.isUnlocked, true);
  assert.match(fixture.status.error, /503/);
});

test("audio: a silent voice service is reported in plain Russian, not as a browser error", async (t) => {
  const fixture = await audioFixture(t, async () => { throw new DOMException("signal timed out", "TimeoutError"); });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speak("a", "Ответ");
  await waitFor(() => fixture.status.error);
  assert.equal(fixture.status.error, "Голосовой сервис не ответил вовремя. Попробуйте ещё раз.");
});

test("audio: playback is serial, Stop cancels playback, every blob URL is released", async (t) => {
  const fixture = await audioFixture(t, async () => new Response(new Blob(["audio"])));
  const revoked = [];
  t.mock.method(URL, "revokeObjectURL", (url) => { revoked.push(url); });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speak("a", "Первый");
  fixture.audioService.speak("b", "Второй");
  await waitFor(() => fixture.elements[0].src.startsWith("blob:"));
  assert.equal(fixture.status.currentId, "a");
  fixture.elements[0].dispatchEvent(new Event("ended"));
  await waitFor(() => fixture.status.currentId === "b" && fixture.elements[0].src.startsWith("blob:"));
  fixture.audioService.stop();
  await settle();
  assert.equal(playing(fixture), false);
  assert.equal(revoked.length, 2);
});

test("audio: a rejected speech play releases its URL and requires a new gesture", async (t) => {
  const fixture = await audioFixture(t, async () => new Response(new Blob(["audio"])));
  const revoked = [];
  t.mock.method(URL, "revokeObjectURL", (url) => { revoked.push(url); });
  await fixture.audioService.unlockAudio();
  fixture.elements[0].play = () => Promise.reject(new DOMException("Playback blocked", "NotAllowedError"));
  fixture.audioService.speak("a", "Ответ");
  await waitFor(() => !playing(fixture));
  assert.equal(fixture.status.isUnlocked, false);
  assert.match(fixture.status.error, /Playback blocked/);
  assert.equal(revoked.length, 1);
});

const LONG = ["Первая фраза ответа звучит сразу.", "Вторая фраза.".padEnd(390, " ещё"), "Третья фраза завершает ответ."].join(" ");

test("audio: a long answer is read part by part, the next part synthesized during the current one", async (t) => {
  const inputs = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    inputs.push(JSON.parse(options.body).input);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speak("long", LONG);
  await waitFor(() => inputs.length === 2);
  assert.equal(playing(fixture), true);
  assert.ok(inputs[0].length <= 150);
  // The next part is already loaded into the second element while the first one sounds.
  await waitFor(() => fixture.elements[1].src.startsWith("blob:"));
  assert.deepEqual(fixture.played, [fixture.elements[0]]);
  const finishPart = async () => {
    const count = fixture.played.length;
    fixture.played.at(-1).dispatchEvent(new Event("ended"));
    await waitFor(() => fixture.played.length > count || !playing(fixture));
  };
  await finishPart();
  assert.equal(fixture.played.at(-1), fixture.elements[1]);
  assert.equal(inputs.length, 3);
  await finishPart();
  assert.equal(fixture.played.at(-1), fixture.elements[0]);
  await finishPart();
  assert.equal(playing(fixture), false);
  assert.equal(fixture.played.length, 3);
  assert.equal(inputs.join(" ").replace(/\s+/g, " "), LONG.replace(/\s+/g, " "));
});

test("audio: Stop between parts aborts the prefetched part and reads nothing more", async (t) => {
  const signals = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    signals.push(options.signal);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speak("long", LONG);
  await waitFor(() => signals.length === 2);
  fixture.audioService.stop();
  assert.ok(signals.every((signal) => signal.aborted));
  await settle();
  assert.equal(playing(fixture), false);
  assert.equal(fixture.elements[0].src, "");
  assert.equal(signals.length, 2);
});

test("audio: volume and speed come from the settings, full reading keeps code and paths", async (t) => {
  const bodies = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    bodies.push(JSON.parse(options.body));
    return new Response(new Blob(["audio"]));
  });
  setPreferences({ volume: 0.5, speed: 1.25 });
  t.after(() => setPreferences({ volume: 1, speed: 1 }));
  await fixture.audioService.unlockAudio();
  fixture.audioService.playNow("a", "Правка в /home/user/app/main.py", true);
  await waitFor(() => fixture.elements[0].src.startsWith("blob:"));
  assert.equal(fixture.status.currentId, "a:full");
  assert.equal(fixture.elements[0].volume, 0.5);
  assert.equal(bodies[0].speed, 1.25);
  assert.equal(bodies[0].input, "Правка в /home/user/app/main.py");
});

test("audio: an answer read in full is not read again by the poll", async (t) => {
  const inputs = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    inputs.push(JSON.parse(options.body).input);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.playNow("a", "Код в /srv/app.py", true);
  await waitFor(() => fixture.elements[0].src.startsWith("blob:"));
  fixture.audioService.speak("a", "Код в /srv/app.py");
  fixture.elements[0].dispatchEvent(new Event("ended"));
  await waitFor(() => !playing(fixture));
  assert.deepEqual(inputs, ["Код в /srv/app.py"]);
});

test("audio: a refused play cancels the part being prefetched", async (t) => {
  const signals = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    signals.push(options.signal);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.elements[0].play = () => Promise.reject(new DOMException("Playback blocked", "NotAllowedError"));
  fixture.audioService.speak("long", LONG);
  await waitFor(() => !playing(fixture));
  assert.equal(signals.length, 2);
  assert.ok(signals[1].aborted);
});

test("speech text: thinking is never read, markdown is read as words", () => {
  const event = message("think", "<think>скрытое</think>Ответ");
  assert.equal(speechText(event), "Ответ");
  assert.equal(speechText(finish("open", "Итог<think>обрыв")), "Итог");
  assert.equal(forSpeech("## Шаги\n- **один**\n- [ссылка](http://x)\n```js\ncode()\n```"), "Шаги\nодин\nссылка\n Блок кода.");
  assert.equal(forSpeech("**Причина** в __двух словах__"), "Причина в двух словах");
});

const tool = (id, tool_name, action, tool_call_id = `call-${id}`) =>
  ({ id, source: "agent", kind: "ActionEvent", tool_name, tool_call_id, action });
const observed = (id, action_id) =>
  ({ id, source: "environment", kind: "ObservationEvent", action_id, tool_call_id: `call-${action_id}` });
const failed = (id, code, kind, detail = "/home/user/secret/path stack trace") =>
  ({ id, source: "environment", kind: "ConversationErrorEvent", code, detail, classification: { kind, retryable: true } });

test("activity: neutral labels, file name and program name only", () => {
  assert.equal(actionLabel(tool("a", "file_editor", { command: "view", path: "/home/user/work/hello.txt" })), "Чтение файла: hello.txt");
  assert.equal(actionLabel(tool("a", "file_editor", { command: "create", path: "/tmp/new.md" })), "Создание файла: new.md");
  assert.equal(actionLabel(tool("a", "file_editor", { command: "str_replace", path: "/tmp/a.py" })), "Изменение файла: a.py");
  assert.equal(actionLabel(tool("a", "terminal", { command: "/usr/bin/python3 -c 'print(1)' --token=x" })), "Выполнение команды: python3");
  assert.equal(actionLabel(tool("a", "terminal", { command: "y", is_input: true })), "Ввод в терминал");
  assert.equal(actionLabel(tool("a", "delegate", {})), "Ожидание исполнителя");
  assert.equal(actionLabel(tool("a", "browser_navigate", {})), "Работа в браузере");
});

test("activity: an action runs until its result; parallel actions are counted; think/finish never run", () => {
  const activity = new AgentActivity();
  activity.apply([tool("t", "think", { thought: "…" }), tool("a", "terminal", { command: "ls" }),
    tool("b", "glob", { pattern: "*" })]);
  assert.deepEqual(activity.snapshot().actions, ["Выполнение команды: ls", "Поиск файлов"]);
  assert.equal(describeStatus("running", activity.snapshot(), "idle").text, "Выполнение команды: ls и ещё 1");
  activity.apply([observed("o1", "a"),
    { id: "e", source: "agent", kind: "AgentErrorEvent", tool_name: "glob", tool_call_id: "call-b", error: "x" }]);
  activity.apply([tool("f", "finish", { message: "Готово" })]);
  assert.deepEqual(activity.snapshot().actions, []);
});

test("activity: an error names the cause without raw detail, stops actions, clears on recovery", () => {
  const activity = new AgentActivity();
  activity.apply([tool("a", "terminal", { command: "ls" }), failed("x", "LLMServiceUnavailableError", "transient")]);
  const line = describeStatus("error", activity.snapshot(), "offline");
  assert.equal(line.text, "Ошибка: Модель недоступна");
  assert.ok(!line.text.includes("/home"));
  assert.deepEqual(activity.snapshot().actions, []);
  activity.apply([failed("y", "SomethingNew", "rate_limit")]);
  assert.equal(activity.snapshot().error, "Слишком много запросов к модели");
  activity.apply([tool("b", "glob", {})]);
  assert.equal(activity.snapshot().error, "");
});

test("status: only proven stages; finished beats a stale action; model faults come first", () => {
  const none = { actions: [], error: "" };
  const busyTool = { actions: ["Чтение файла: a.txt"], error: "" };
  assert.equal(describeStatus("running", none, "offline").text, "Агент ждёт модель");
  assert.equal(describeStatus("running", busyTool, "loading").text, "Модель загружается");
  assert.equal(describeStatus("running", none, "busy").text, "Модель генерирует ответ");
  assert.match(describeStatus("running", none, "idle").text, /вероятно/);
  assert.equal(describeStatus("running", none, "unknown").text, "Агент работает");
  assert.equal(describeStatus("finished", busyTool, "idle").text, "Готово");
  assert.equal(describeStatus("awaiting_user_confirmation", { actions: ["Выполнение команды: rm"], error: "" }, "idle").text,
    "Нужно ваше подтверждение: Выполнение команды: rm");
  assert.equal(describeStatus("idle", busyTool, "idle"), null);
});

test("opening mid-action: recent history restores the step silently, speech stays at the head", async () => {
  const history = [message("m1", "сделай", "user"), tool("a", "terminal", { command: "npm test" })];
  const speech = new SpeechEvents();
  const activity = new AgentActivity();
  const fresh = await speech.readNew(historyReader(history), (events) => activity.apply(events));
  assert.deepEqual(fresh, []);
  assert.deepEqual(activity.snapshot().actions, ["Выполнение команды: npm"]);
  history.push(observed("o", "a"));
  activity.apply(await speech.readNew(historyReader(history)));
  assert.deepEqual(activity.snapshot().actions, []);
});

test("speech: paths are reduced to filename, Windows paths untouched", () => {
  assert.equal(forSpeech("Файл в /home/user/a/b/file.py изменён."), "Файл в file.py изменён.");
  assert.equal(forSpeech("Конфиг ~/x/y.txt обновлён"), "Конфиг y.txt обновлён");
  assert.equal(forSpeech("Смотри ./src/app.ts и ../parent/test.js"), "Смотри app.ts и test.js");
  assert.equal(forSpeech("Путь C:\\dir\\f.txt не менять"), "Путь C:\\dir\\f.txt не менять");
  assert.equal(forSpeech("В `/home/user/deep/path/to/script.sh` найдена ошибка"), "В script.sh найдена ошибка");
});

test("speech: URLs are read as their domain without www, markdown links keep only text", () => {
  assert.equal(forSpeech("Перейдите на https://www.google.com/search?q=test."), "Перейдите на google.com.");
  assert.equal(forSpeech("Локальный адрес: http://localhost:8080/api"), "Локальный адрес: localhost");
  assert.equal(forSpeech("Открой [документацию](https://openhands.ai/docs)"), "Открой документацию");
  assert.equal(forSpeech("См. https://example.org/docs,затем дальше"), "См. example.org,затем дальше");
});

test("speech: inline code reads simple text, replaces complex/long code with 'код'", () => {
  assert.equal(forSpeech("Команда `npm test` выполнена"), "Команда npm test выполнена");
  assert.equal(forSpeech("Выражение `const x = 1;` заменено"), "Выражение код заменено");
  assert.equal(forSpeech("Вызов `foo()` вернул результат"), "Вызов код вернул результат");
  assert.equal(forSpeech("Тег `<div>` и условие `a < b`"), "Тег код и условие код");
  assert.equal(forSpeech("Длинная строка `one two three four five six seven eight nine ten`"), "Длинная строка код");
});

test("speech: full=true reads code and paths as is without markdown markup", () => {
  const full = forSpeech("## Заголовок\nФайл: /home/user/a.py\n```python\ndef test():\n    return 42\n```\nКод `x = y;` и [ссылка](http://example.com)", true);
  assert.equal(full, "Заголовок\nФайл: /home/user/a.py\ndef test():\n    return 42\n\nКод x = y; и ссылка http://example.com");
});

test("speechChunks: empty input returns empty array, preserves empty strings", () => {
  assert.deepEqual(speechChunks(""), []);
  assert.deepEqual(speechChunks("   "), []);
  assert.equal(forSpeech(""), "");
  assert.equal(forSpeech("   "), "");
});

test("speechChunks: respects first and rest limits, does not break words, preserves text", () => {
  const s1 = "Первое короткое предложение.";
  const s2 = "Второе предложение, содержащее достаточно слов для проверки распределения.";
  const s3 = "Третье предложение тоже достаточно длинное, чтобы проверить лимиты частей синтеза.";
  const text = `${s1} ${s2} ${s3}`;

  const chunks = speechChunks(text, 50, 100);
  assert.ok(chunks.length >= 2);
  assert.ok(chunks[0].length <= 50, `first chunk length ${chunks[0].length} > 50`);
  for (let i = 1; i < chunks.length; i++) {
    assert.ok(chunks[i].length <= 100, `chunk ${i} length ${chunks[i].length} > 100`);
  }

  // No words broken: text split by space equals joined chunks split by space
  const wordsOriginal = text.split(/\s+/).filter(Boolean);
  const wordsChunks = chunks.join(" ").split(/\s+/).filter(Boolean);
  assert.deepEqual(wordsChunks, wordsOriginal);

  // Long sentence split by space without splitting words
  const longSentence = "Слово1 Слово2 Слово3 Слово4 Слово5 Слово6 Слово7 Слово8 Слово9 Слово10";
  const cutChunks = speechChunks(longSentence, 25, 25);
  for (const c of cutChunks) {
    assert.ok(c.length <= 25, `chunk length ${c.length} > 25`);
    assert.ok(!c.includes("  "));
  }
  assert.deepEqual(cutChunks.join(" ").split(/\s+/), longSentence.split(/\s+/));
});

test("speechChunks: cuts long sentences at clause boundaries before spaces", () => {
  const sentence = "Файл app.ts обычно содержит точку входа приложения: инициализацию состояния, подключение компонентов или маршрутов, а также настройку глобальных сервисов.";
  const clauseChunks = speechChunks(sentence, 150, 400);
  assert.ok(clauseChunks[0].endsWith("маршрутов,"));
  assert.equal(clauseChunks[0], "Файл app.ts обычно содержит точку входа приложения: инициализацию состояния, подключение компонентов или маршрутов,");
  assert.equal(clauseChunks[1], "а также настройку глобальных сервисов.");

  // Case with dash: dash goes to the beginning of the next chunk
  const dashSentence = "Главный модуль системы управления задачами — центральный компонент всей инфраструктуры проекта.";
  const dashChunks = speechChunks(dashSentence, 50, 100);
  assert.equal(dashChunks[0], "Главный модуль системы управления задачами");
  assert.equal(dashChunks[1], "— центральный компонент всей инфраструктуры проекта.");

  // Case without punctuation: falls back to last space
  const noPunctSentence = "ПервоеСлово ВтороеСлово ТретьеСлово ЧетвертоеСлово ПятоеСлово ШестоеСлово";
  const spaceChunks = speechChunks(noPunctSentence, 30, 50);
  assert.equal(spaceChunks[0], "ПервоеСлово ВтороеСлово");
  assert.equal(spaceChunks[1], "ТретьеСлово ЧетвертоеСлово ПятоеСлово ШестоеСлово");
});

test("card times are durations in words of the page language", async (t) => {
  const page = { documentElement: { lang: "ru" } };
  globalThis.document = page;
  t.after(() => { delete globalThis.document; });
  const { formatTimeDelta } = await import("./src/relative-time.ts");
  const ago = (seconds) => new Date(Date.now() - seconds * 1000);
  assert.equal(formatTimeDelta(ago(47 * 60 + 5)), "47 минут");
  assert.equal(formatTimeDelta(ago(2 * 3600)), "2 часа");
  assert.equal(formatTimeDelta(ago(0)), "0 секунд");
  assert.equal(formatTimeDelta("not a date"), "");
  page.documentElement.lang = "en";
  assert.equal(formatTimeDelta(ago(86400)), "1 day");
});

test("code blocks: every token colour of the dark theme is at least 7:1, at full size, upright", async () => {
  const { getSyntaxHighlighterTheme } = await import("./src/syntax-theme.ts");
  const theme = getSyntaxHighlighterTheme("openhands-neutral");
  const luminance = (hex) => {
    const [r, g, b] = hex.match(/\w\w/g).map((part) => {
      const c = parseInt(part, 16) / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const ratio = (a, b) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
  const styles = Object.values(theme);
  const colours = styles.map((style) => style.color).filter(Boolean);
  assert.ok(colours.length > 10);
  for (const colour of colours) assert.ok(ratio(colour, "#1e1e1e") >= 7, `${colour} is ${ratio(colour, "#1e1e1e").toFixed(2)}:1`);
  assert.ok(styles.every((style) => !style.fontSize || style.fontSize === "1rem"));
  assert.ok(styles.every((style) => !style.Opacity && style.fontStyle !== "italic"));
  assert.ok(styles.every((style) => style.whiteSpace !== "pre"), "long lines wrap instead of scrolling sideways");
  assert.equal(getSyntaxHighlighterTheme("openhands-neutral"), theme, "derived once, not on every render");
});

test("step phrases: action without explanation produces short Russian action phrase", () => {
  const cursor = new SpeechEvents();
  assert.equal(cursor.takeStep(tool("1", "terminal", { command: "python3 test.py" })), "Выполняю команду");
  assert.equal(cursor.takeStep(tool("2", "file_editor", { command: "view", path: "/srv/app/server.ts" })), "Читаю файл server.ts");
  assert.equal(cursor.takeStep(tool("3", "file_editor", { command: "str_replace", path: "/srv/app/server.ts" })), "Правлю файл server.ts");
  assert.equal(cursor.takeStep(tool("4", "apply_patch", {})), "Правлю файлы");
  assert.equal(cursor.takeStep(tool("5", "glob", {})), "Поиск файлов");
  assert.equal(cursor.takeStep(tool("6", "grep", {})), "Поиск в файлах");
  assert.equal(cursor.takeStep(tool("7", "finish", { message: "Ответ" })), "");
  assert.equal(cursor.takeStep(tool("8", "think", {})), "");
});

test("step phrases: plan updates track task tracker and announce count or completed task", () => {
  const cursor = new SpeechEvents();
  assert.equal(formatPlanCount(1), "План: 1 задача");
  assert.equal(formatPlanCount(3), "План: 3 задачи");
  assert.equal(formatPlanCount(5), "План: 5 задач");
  assert.equal(formatPlanCount(21), "План: 21 задача");

  const initialPlan = {
    command: "plan",
    task_list: [
      { title: "Найти скрипт в /home/user/app.py", status: "in_progress" },
      { title: "Исправить задержку", status: "todo" },
      { title: "Запустить тесты", status: "todo" },
    ],
  };
  const phrase1 = cursor.takeStep(tool("plan-1", "task_tracker", initialPlan));
  assert.equal(phrase1, "План: 3 задачи");

  const updatedPlan = {
    command: "plan",
    task_list: [
      { title: "Найти скрипт в /home/user/app.py", status: "done" },
      { title: "Исправить задержку", status: "in_progress" },
      { title: "Запустить тесты", status: "todo" },
    ],
  };
  const phrase2 = cursor.takeStep(tool("plan-2", "task_tracker", updatedPlan));
  assert.equal(phrase2, "Готово: Найти скрипт в app.py");
});

test("step phrases: explanation is clipped to first sentence under 150 chars with speech filters", () => {
  const cursor = new SpeechEvents();
  const event = {
    ...tool("step-1", "terminal", { command: "ls" }),
    thought: [
      { type: "text", text: "Проверяю конфиг в /etc/app/config.json на `{port: 8080}`. Второе предложение не должно звучать." }
    ],
  };
  assert.equal(cursor.takeStep(event), "Проверяю конфиг в config.json на код.");

  const longSentence = "Это невероятно длинное предложение, которое содержит огромное количество подробных пояснений по поводу каждого отдельного шага работы агента, чтобы превысить лимит.";
  const clipped = clipStepExplanation(longSentence);
  assert.ok(clipped.length <= 150);
  assert.ok(longSentence.startsWith(clipped));
});

test("intermediate speech: disabled by default and speaks nothing", async (t) => {
  const saved = { ...getPreferences() };
  t.after(() => setPreferences(saved));
  setPreferences({ autoSpeak: true, speakSteps: false });
  const inputs = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    inputs.push(JSON.parse(options.body).input);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speakStep("s1", "Выполняю команду");
  await settle();
  assert.equal(inputs.length, 0);
  assert.equal(playing(fixture), false);
});

test("intermediate speech: enabled speaks action, plan, and explanation phrases", async (t) => {
  const saved = { ...getPreferences() };
  t.after(() => setPreferences(saved));
  setPreferences({ autoSpeak: true, speakSteps: true });
  const inputs = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    inputs.push(JSON.parse(options.body).input);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speakStep("s1", "Выполняю команду");
  await waitFor(() => fixture.elements[0].src.startsWith("blob:"));
  assert.equal(inputs[0], "Выполняю команду");
  fixture.elements[0].dispatchEvent(new Event("ended"));
  await waitFor(() => !playing(fixture));

  fixture.audioService.speakStep("s2", "План: 3 задачи");
  await waitFor(() => fixture.elements[0].src.startsWith("blob:"));
  assert.equal(inputs[1], "План: 3 задачи");
  fixture.elements[0].dispatchEvent(new Event("ended"));
  await waitFor(() => !playing(fixture));

  fixture.audioService.speakStep("s3", "Готово: Исправить ошибку");
  await waitFor(() => fixture.elements[0].src.startsWith("blob:"));
  assert.equal(inputs[2], "Готово: Исправить ошибку");
  fixture.elements[0].dispatchEvent(new Event("ended"));
  await waitFor(() => !playing(fixture));
  assert.equal(inputs.length, 3);
});

test("intermediate speech: new step replaces waiting step without accumulating in queue", async (t) => {
  const saved = { ...getPreferences() };
  t.after(() => setPreferences(saved));
  setPreferences({ autoSpeak: true, speakSteps: true });
  const inputs = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    inputs.push(JSON.parse(options.body).input);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speakStep("step-1", "Первый шаг выполняется долго");
  await waitFor(() => fixture.elements[0].src.startsWith("blob:"));
  assert.equal(inputs.length, 1);
  assert.equal(inputs[0], "Первый шаг выполняется долго");

  // While step-1 is still sounding, step-2 arrives, then step-3 replaces step-2
  fixture.audioService.speakStep("step-2", "Второй шаг устарел");
  fixture.audioService.speakStep("step-3", "Третий шаг актуальный");
  await settle();
  assert.equal(inputs.length, 1);

  // Finish step-1
  fixture.elements[0].dispatchEvent(new Event("ended"));
  await waitFor(() => inputs.length === 2 && fixture.elements[0].src.startsWith("blob:"));
  assert.equal(inputs[1], "Третий шаг актуальный");
  fixture.elements[0].dispatchEvent(new Event("ended"));
  await waitFor(() => !playing(fixture));

  // step-2 was never synthesized or played!
  assert.deepEqual(inputs, ["Первый шаг выполняется долго", "Третий шаг актуальный"]);
});

test("intermediate speech: final answer interrupts playing intermediate phrase immediately", async (t) => {
  const saved = { ...getPreferences() };
  t.after(() => setPreferences(saved));
  setPreferences({ autoSpeak: true, speakSteps: true });
  const inputs = [];
  let stepSignal;
  const fixture = await audioFixture(t, async (_url, options) => {
    const body = JSON.parse(options.body);
    inputs.push(body.input);
    if (body.input.startsWith("Длинный шаг")) {
      stepSignal = options.signal;
    }
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speakStep("step-1", "Длинный шаг агента выполняется");
  await waitFor(() => fixture.elements[0].src.startsWith("blob:"));
  assert.equal(inputs.length, 1);
  assert.equal(playing(fixture), true);

  // Waiting step queued
  fixture.audioService.speakStep("step-2", "Ожидающий шаг");

  // Final answer arrives
  fixture.audioService.speak("answer-1", "Итоговый ответ готов");
  await waitFor(() => inputs.length === 2 && fixture.elements[0].src.startsWith("blob:"));
  assert.equal(inputs[1], "Итоговый ответ готов");
  assert.equal(fixture.status.currentId, "answer-1");
  assert.equal(stepSignal?.aborted, true, "playing step synthesis/playback was aborted");

  fixture.elements[0].dispatchEvent(new Event("ended"));
  await waitFor(() => !playing(fixture));

  // Waiting step-2 was discarded when answer arrived
  assert.deepEqual(inputs, ["Длинный шаг агента выполняется", "Итоговый ответ готов"]);
});

test("intermediate speech: TalkBack signals mode keeps intermediate steps silent", async (t) => {
  const saved = { ...getPreferences() };
  t.after(() => setPreferences(saved));
  setPreferences({ autoSpeak: false, speakSteps: true });
  const inputs = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    inputs.push(JSON.parse(options.body).input);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speakStep("step-1", "Выполняю команду");
  await settle();
  assert.equal(inputs.length, 0);
  assert.equal(playing(fixture), false);
});

test("intermediate speech: history on open remains silent and seeds plan state", async () => {
  const history = [
    tool("h1", "terminal", { command: "pwd" }),
    tool("h2", "task_tracker", {
      command: "plan",
      task_list: [
        { title: "Задача 1", status: "done" },
        { title: "Задача 2", status: "todo" },
      ],
    }),
  ];
  const cursor = new SpeechEvents();
  const read = historyReader(history);
  const initial = await cursor.readNew(read);
  assert.deepEqual(initial, [], "history read returns empty array for speech");

  // Now a new event arrives where Задача 2 becomes done
  history.push(tool("new1", "task_tracker", {
    command: "plan",
    task_list: [
      { title: "Задача 1", status: "done" },
      { title: "Задача 2", status: "done" },
    ],
  }));
  const fresh = await cursor.readNew(read);
  assert.equal(fresh.length, 1);
  const step = cursor.takeStep(fresh[0]);
  assert.equal(step, "Готово: Задача 2", "seeds history so Задача 1 is not re-announced as done");
});

test("intermediate speech: service stop aborts playing and waiting intermediate phrases", async (t) => {
  const saved = { ...getPreferences() };
  t.after(() => setPreferences(saved));
  setPreferences({ autoSpeak: true, speakSteps: true });
  const signals = [];
  const fixture = await audioFixture(t, async (_url, options) => {
    signals.push(options.signal);
    return new Response(new Blob(["audio"]));
  });
  await fixture.audioService.unlockAudio();
  fixture.audioService.speakStep("s1", "Выполняю долгий шаг");
  await waitFor(() => fixture.elements[0].src.startsWith("blob:"));
  fixture.audioService.speakStep("s2", "Ожидающий шаг");
  fixture.audioService.stop();
  assert.equal(playing(fixture), false);
  assert.ok(signals.every((s) => s.aborted));
  await settle();
  assert.equal(playing(fixture), false);
});

test("sidebar folds where its rem width would squeeze the chat, not on phones or wide screens", () => {
  assert.equal(shouldFoldSidebar(800, 28), true, "tablet portrait, 28 px: 525 of 800 px");
  assert.equal(shouldFoldSidebar(1280, 28), false, "tablet landscape keeps 755 px for the chat");
  assert.equal(shouldFoldSidebar(1280, 18), false);
  assert.equal(shouldFoldSidebar(800, 18), true);
  assert.equal(shouldFoldSidebar(600, 28), false, "below 768 px Canvas uses its drawer");
});

test("guard: every conversation start gets the guard first, other requests stay untouched", () => {
  const command = "/usr/bin/python3 -I '/x/guard.py'";
  const origin = "https://pc:8443";
  const project = { pre_tool_use: [{ matcher: "terminal", hooks: [{ type: "command", command: "lint" }] }], stop: [{ hooks: [] }] };
  const started = JSON.parse(guardedBody(`${origin}/api/conversations`, "post", JSON.stringify({ a: 1, hook_config: project }), origin, command));
  assert.equal(started.a, 1);
  assert.equal(started.hook_config.pre_tool_use[0].hooks[0].command, command);
  assert.equal(started.hook_config.pre_tool_use[1].hooks[0].command, "lint", "workspace hooks are kept");
  assert.deepEqual(started.hook_config.stop, project.stop);
  const relative = JSON.parse(guardedBody("/api/conversations", "POST", "{}", origin, command));
  assert.equal(relative.hook_config.pre_tool_use.length, 1);
  const twice = withGuard(withGuard(null, command), command);
  assert.equal(twice.pre_tool_use.length, 1, "no duplicate guard");
  const legacy = withGuard({ hooks: { PreToolUse: [{ hooks: [{ command: "lint" }] }] } }, command);
  assert.deepEqual(Object.keys(legacy), ["pre_tool_use"]);
  assert.equal(legacy.pre_tool_use.length, 2);
  for (const [url, method] of [["/api/conversations", "GET"], ["/api/conversations/abc/events", "POST"], ["/api/settings", "PATCH"]]) {
    assert.equal(guardedBody(url, method, "{}", origin, command), "{}");
  }
  assert.throws(() => guardedBody("/api/conversations", "POST", new Blob(["{}"]), origin, command), /Страж Nexus/);
  assert.throws(() => guardedBody("/api/conversations", "POST", "not json", origin, command));
});
