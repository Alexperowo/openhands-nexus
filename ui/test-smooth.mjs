import test from "node:test";
import assert from "node:assert/strict";
import { StreamBuffer } from "./src/stream-buffer.ts";
import { restoreReadingAnchor, ScrollFollow } from "./src/scroll-follow.ts";
import { resolveMotion } from "./src/motion.ts";
import { connectionPhase, ConnectionAnnouncements } from "./src/connection-state.ts";
import { DictationSession } from "./src/dictation-session.ts";
import { mergeSpeechSnapshot, snapshotForConversation } from "./src/use-conversation-speech.ts";
import { getPreferences, setPreferences } from "./src/preferences.ts";

const settle = () => new Promise(resolve => setImmediate(resolve));
const until = async predicate => {
  const start = Date.now();
  while (!predicate()) { assert.ok(Date.now() - start < 2000, "lifecycle did not settle"); await settle(); }
};

test("stream: a 6400-character burst catches up within 3s, never cuts emoji", () => {
  const buffer = new StreamBuffer(), target = "🙂Проверяю звук. ".repeat(400);
  buffer.targetText(target);
  const sizes = []; let previous = "", now = 0;
  while (!buffer.done && now < 3000) {
    const text = buffer.frame(now); sizes.push(text.length - previous.length);
    assert.ok(text.startsWith(previous)); assert.ok(target.startsWith(text));
    assert.doesNotMatch(text, /[\uD800-\uDBFF]$/);
    previous = text; now += 1000 / 60;
  }
  assert.equal(buffer.shown, target);
  assert.ok(sizes.length > 5); assert.ok(sizes[0] < target.length / 2);
});
test("stream: new bursts accelerate, correction/retry replaces old prefix, reduced/off flush immediately", () => {
  const buffer = new StreamBuffer();
  buffer.targetText("Проверяю "); const first = buffer.frame(0);
  buffer.targetText("Проверяю " + "сеть ".repeat(200));
  assert.ok(buffer.frame(16).length - first.length > 20, "a backlog must accelerate beyond the minimum frame rate");
  buffer.targetText("Новая попытка"); assert.equal(buffer.shown, "Новая попытка");
  buffer.targetText("Новая попытка. Готово", true); assert.equal(buffer.shown, "Новая попытка. Готово");
});
test("stream: partial words never move between lines; idle tails stop frames and flush on final", () => {
  const buffer = new StreamBuffer();
  buffer.targetText("Проверяю устройс", false, false);
  for (let time = 0; !buffer.done && time < 2000; time += 16) {
    const shown = buffer.frame(time);
    assert.ok(!shown || /\s$/.test(shown), "only complete words may enter layout");
  }
  assert.equal(buffer.done, true);
  assert.equal(buffer.shown, "Проверяю ");
  buffer.targetText("Проверяю устройства", false, true);
  for (let time = 2000; !buffer.done && time < 3000; time += 16) buffer.frame(time);
  assert.equal(buffer.shown, "Проверяю устройства");
  buffer.targetText("Проверяю устройства " + "x".repeat(200), false, false);
  buffer.frame(3000);
  buffer.frame(10000);
  assert.equal(buffer.done, true, "unbroken code/URLs must not keep RAF spinning");
  assert.equal(buffer.shown, buffer.target);
});
test("stream: background pause catches up without a delayed animation backlog", () => {
  const buffer = new StreamBuffer(); buffer.targetText("Ответ. ".repeat(100)); buffer.frame(0);
  assert.equal(buffer.frame(10000), buffer.target);
});
test("scroll: follow bottom until user scrolls up; layout cannot turn following back on", () => {
  const scroll = new ScrollFollow(); scroll.target(600); scroll.scroll(600, 1000, 400);
  assert.equal(scroll.following, true);
  scroll.userIntent(true); scroll.scroll(420, 1000, 400);
  scroll.remember("first-visible", 12);
  assert.equal(scroll.correction("first-visible", 72), 60);
  assert.equal(scroll.following, false);
  scroll.target(480); scroll.scroll(480, 1200, 400);
  assert.equal(scroll.following, false, "anchor correction must not follow the arriving answer");
  scroll.latest(); assert.equal(scroll.following, true);
});
test("scroll: returning to bottom resumes following; deleted anchors are ignored", () => {
  const scroll = new ScrollFollow(); scroll.userIntent(true); scroll.remember("gone", 10);
  assert.equal(scroll.correction("other", 200), 0);
  assert.equal(scroll.scroll(598, 1000, 400), true); assert.equal(scroll.following, true);
  const paragraphs = [{tagName: "P", textContent: "Проверяю звук. Первый пункт"}, {tagName: "P", textContent: "Проверяю звук. Второй пункт"}];
  assert.equal(restoreReadingAnchor(paragraphs, {index: 1, tag: "P", prefix: "Проверяю звук."}), paragraphs[1], "final Markdown must preserve the chosen paragraph among repeated prefixes");
});
test("motion: default follows the system, explicit settings win", () => {
  assert.equal(resolveMotion("system", true), "reduced"); assert.equal(resolveMotion("system", false), "full");
  for (const value of ["full", "reduced", "off"]) for (const system of [true, false]) assert.equal(resolveMotion(value, system), value);
});
test("connection: REST and socket must both recover; notices do not repeat across retries", () => {
  const notices = new ConnectionAnnouncements();
  assert.equal(notices.update("online"), null);
  assert.equal(connectionPhase(true, "", {state: "CLOSED", seen: false}), "lost");
  assert.equal(connectionPhase(true, "", {state: "CONNECTING", seen: true}), "lost");
  assert.equal(connectionPhase(true, "HTTP 503", {state: "OPEN", seen: true}), "lost");
  assert.equal(connectionPhase(true, "", {state: "CONNECTING", seen: false, failed: true}), "lost", "initial retries must not hide the outage banner");
  assert.equal(connectionPhase(true, "", {state: "CONNECTING", seen: false}, true), "lost", "missing composer bridge must not connect forever");
  assert.equal(notices.update("lost"), "lost");
  for (let i = 0; i < 10; i++) { assert.equal(notices.update("lost"), null); assert.equal(notices.update("connecting"), null); }
  assert.equal(notices.update("online"), "restored"); assert.equal(notices.update("online"), null);
  assert.equal(notices.update("lost"), "lost");
});
test("poll: unchanged snapshots preserve identity, including fresh identical action arrays", () => {
  const state = {id: "a", status: "running", error: "", ready: true, model: "busy", activity: {actions: ["Чтение файла"], error: ""}};
  for (let i = 0; i < 100; i++) assert.equal(mergeSpeechSnapshot(state, {activity: {actions: ["Чтение файла"], error: ""}, error: "", ready: true}), state);
  assert.notEqual(mergeSpeechSnapshot(state, {model: "idle"}), state);
  assert.notEqual(mergeSpeechSnapshot(state, {activity: {actions: ["Другая команда"], error: ""}}), state);
  assert.equal(snapshotForConversation(state, "a"), state);
  const changed = snapshotForConversation({...state, error: "Old outage"}, "b");
  assert.equal(changed.error, ""); assert.equal(changed.status, ""); assert.equal(changed.ready, false);
});

function recorderFixture(t, fetchImpl) {
  const original = Object.getOwnPropertyDescriptors(globalThis);
  const tracks = [];
  class Recorder {
    state = "inactive"; mimeType = "audio/webm";
    start() { this.state = "recording"; }
    stop() { this.state = "inactive"; this.ondataavailable?.({data: new Blob(["voice"])}); queueMicrotask(() => this.onstop?.()); }
  }
  Object.defineProperty(globalThis, "navigator", {configurable: true, value: {mediaDevices: {getUserMedia: async () => {
    const track = {stopped: false, stop() {this.stopped = true;}}; tracks.push(track); return {getTracks: () => [track]};
  }}}});
  globalThis.MediaRecorder = Recorder; globalThis.fetch = fetchImpl;
  t.after(() => { for (const key of ["navigator", "MediaRecorder", "fetch"]) {
    if (original[key]) Object.defineProperty(globalThis, key, original[key]); else delete globalThis[key];
  }});
  return tracks;
}
const endpoint = {baseUrl: "http://fixture.invalid/v1", model: "v3_ctc", apiKey: ""};

test("dictation: stalled STT times out, aborts fetch, releases hold once, permits retry", async t => {
  const signals = [], tracks = recorderFixture(t, (_url, options) => { signals.push(options.signal); return new Promise(() => {}); });
  const errors = [], ended = [];
  const session = new DictationSession({onStatus() {}, onTranscript() {assert.fail("no late transcript");}, onError: e => errors.push(e.message), onEnd: value => ended.push(value), requestTimeout: 15});
  session.toggle(endpoint); await until(() => session.status === "recording"); session.toggle(endpoint);
  await until(() => ended.length > 0);
  assert.equal(session.status, "idle"); assert.equal(signals[0].aborted, true);
  assert.equal(tracks[0].stopped, true); assert.deepEqual(ended, [true]); assert.match(errors[0], /вовремя/);
  session.toggle(endpoint); await until(() => session.status === "recording"); session.cancel();
  assert.deepEqual(ended, [true, true]);
});
test("dictation: explicit Cancel aborts request and ignores a late successful transcript", async t => {
  let resolve; const tracks = recorderFixture(t, () => new Promise(r => {resolve = r;})); const ended = [];
  const session = new DictationSession({onStatus() {}, onTranscript() {assert.fail("cancelled transcript inserted");}, onError() {assert.fail("cancel is not an error");}, onEnd: value => ended.push(value)});
  session.toggle(endpoint); await until(() => session.status === "recording"); session.toggle(endpoint);
  await until(() => resolve); session.cancel(); session.cancel();
  resolve(new Response(JSON.stringify({text: "Не вставлять"}))); await settle();
  assert.deepEqual(ended, [true]); assert.ok(tracks.every(track => track.stopped));
});
test("dictation: delayed microphone permission after Cancel closes new tracks", async t => {
  recorderFixture(t, () => assert.fail("no transcription"));
  let resolve; navigator.mediaDevices.getUserMedia = () => new Promise(r => {resolve = r;});
  const session = new DictationSession({onStatus() {}, onTranscript() {}, onError() {}, onEnd() {}});
  session.toggle(endpoint); session.cancel(); let stopped = 0;
  resolve({getTracks: () => [{stop: () => stopped++}]}); await settle(); assert.equal(stopped, 1);
});
test("dictation: successful STT inserts only text and does not classify completion as cancellation", async t => {
  recorderFixture(t, async (_url, options) => {
    assert.equal(options.body.get("model"), "v3_ctc"); assert.ok(options.body.get("file") instanceof Blob); assert.ok(options.signal);
    return new Response(JSON.stringify({text: " Проверить звук "}));
  });
  const text = [], ended = [];
  const session = new DictationSession({onStatus() {}, onTranscript: value => text.push(value), onError() {assert.fail("successful STT");}, onEnd: value => ended.push(value)});
  session.toggle(endpoint); await until(() => session.status === "recording"); session.toggle(endpoint);
  await until(() => text.length); assert.deepEqual(text, ["Проверить звук"]); assert.deepEqual(ended, [false]);
});
test("dictation: a microphone left on stops by itself and what was said is still inserted", async t => {
  recorderFixture(t, async () => new Response(JSON.stringify({text: "Длинная диктовка"})));
  const text = [], ended = [], statuses = [];
  const session = new DictationSession({onStatus: value => statuses.push(value), onTranscript: value => text.push(value),
    onError() {assert.fail("the limit is not an error");}, onEnd: value => ended.push(value), maxRecording: 20});
  session.toggle(endpoint);
  await until(() => text.length);
  assert.deepEqual(text, ["Длинная диктовка"]); assert.deepEqual(ended, [false]);
  assert.ok(statuses.indexOf("recording") < statuses.indexOf("transcribing"));
});
test("dictation: the recognition wait grows with the length of the recording", async t => {
  recorderFixture(t, () => new Promise(() => {}));
  const errors = [], ended = [];
  const session = new DictationSession({onStatus() {}, onTranscript() {}, onError: e => errors.push(e.message),
    onEnd: value => ended.push(value), requestTimeout: 15});
  session.toggle(endpoint); await until(() => session.status === "recording");
  await new Promise(resolve => setTimeout(resolve, 500));
  session.toggle(endpoint);
  await new Promise(resolve => setTimeout(resolve, 60));
  assert.deepEqual(ended, [], "15 ms plus 0.3 of half a second of speech is about 165 ms");
  await until(() => ended.length); assert.match(errors[0], /вовремя/);
});
test("speech: answer arriving during dictation is read once after Cancel, not after ordinary completion", async t => {
  const originalAudio = globalThis.Audio, originalFetch = globalThis.fetch, prefs = {...getPreferences()}; const requests = [];
  class Audio extends EventTarget { src = ""; play() {return Promise.resolve();} pause() {} load() {} removeAttribute() {this.src = "";} }
  globalThis.Audio = Audio;
  globalThis.fetch = async (_url, options) => {requests.push(JSON.parse(options.body).input); return new Response(new Blob(["audio"]));};
  const {audioService} = await import(`./src/audio-service.ts?cancel-replay`);
  t.after(() => {audioService.stop(); globalThis.Audio = originalAudio; globalThis.fetch = originalFetch; setPreferences(prefs);});
  setPreferences({autoSpeak: true}); await audioService.unlockAudio();
  let release = audioService.beginDictation(); audioService.speak("answer-a", "Ответ во время диктовки"); await settle(); assert.equal(requests.length, 0);
  const secondRecorder = audioService.beginDictation();
  release(true); await settle(); assert.equal(requests.length, 0, "another recorder still owns the microphone hold");
  secondRecorder(true); await until(() => requests.length === 1); release(true); audioService.stop();
  release = audioService.beginDictation(); audioService.speak("answer-b", "Ответ при успешной диктовке"); release(false); await settle();
  assert.deepEqual(requests, ["Ответ во время диктовки"]);
});

test("connection cue waits for a gesture, keeps latest transition only, is played once", async t => {
  const original = globalThis.AudioContext; let tones = 0;
  class Context {
    state = "suspended"; currentTime = 0; destination = {};
    async resume() {this.state = "running";}
    createOscillator() {return {frequency: {value: 0}, connect(target) {return target;}, start() {tones++;}, stop() {}};}
    createGain() {return {gain: {setValueAtTime() {}, linearRampToValueAtTime() {}}, connect() {}};}
  }
  globalThis.AudioContext = Context; t.after(() => {globalThis.AudioContext = original;});
  const {playConnectionCue, unlockCues} = await import("./src/status-cues.ts?connection-test");
  playConnectionCue("error"); playConnectionCue("done"); assert.equal(tones, 0);
  await unlockCues(); assert.equal(tones, 2); await unlockCues(); assert.equal(tones, 2);
});
test("dictation cleanup releases lifecycle even if recorder stop throws", async t => {
  recorderFixture(t, () => assert.fail("no transcription"));
  MediaRecorder.prototype.stop = () => {throw new Error("already stopping");};
  let ended = false; const session = new DictationSession({onStatus() {}, onTranscript() {}, onError() {}, onEnd() {ended = true;}});
  session.toggle(endpoint); await until(() => session.status === "recording"); session.cancel();
  assert.equal(ended, true); assert.equal(session.status, "idle");
});
