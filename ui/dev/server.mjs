// Local fixture only: never proxies to Nexus, the model or the internet.
import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import { WebSocketServer } from "ws";
import { fileURLToPath } from "node:url";
const timestamp = "2026-10-24T12:00:00Z";
export const answer = "Проверка завершена. Звук работает, сеть подключена.\n\n" + Array.from({length: 9}, (_, i) => `Пункт ${i + 1}. Это записанный пример длинного ответа для проверки плавности. Текст приходит неравномерными пакетами, но место чтения должно сохраняться.`).join("\n\n");
const message = (id, source, text) => ({ id, kind: "MessageEvent", source, timestamp, llm_message: { role: source === "agent" ? "assistant" : "user", content: [{type: "text", text}] } });
const history = Array.from({length: 8}, (_, i) => message(`history-${i}`, i % 2 ? "agent" : "user", i % 2 ? "Предыдущая проверка выполнена. Настройки сохранены.\n\nМожно продолжать работу с компьютером." : "Проверь настройки компьютера и объясни результат."));
export async function startFixture({ root, port = 0 } = {}) {
  let sequence = history.length - 1, runCount = 0, snapshots = 0;
  let events = history.map((event, seq) => ({...event, seq})), status = "idle", offline = false, wsOffline = false, timers = [];
  const requests = [], sockets = new Set();
  const conversation = (id = "replay") => ({ id, title: id === "replay" ? "Проверка компьютера" : "Вторая беседа", created_at: timestamp, updated_at: timestamp, execution_status: status, workspace: {working_dir: "/tmp"}, agent: {kind: "Agent", llm: {model: "fixture"}}, stats: {usage_to_metrics: {}}, sub_conversation_ids: [], available_models: [], sandbox_status: "RUNNING" });
  const send = (frame) => { for (const socket of sockets) if (socket.readyState === 1) socket.send(JSON.stringify(frame)); };
  const durable = event => { event = {...event, seq: ++sequence}; events.push(event); send({type: "durable", seq: event.seq, event}); };
  const statusEvent = () => ({id: `status-${sequence + 1}`, kind: "ConversationStateUpdateEvent", source: "environment", timestamp, key: "execution_status", value: status});
  const schedule = (delay, run) => timers.push(setTimeout(run, delay));
  const run = () => {
    timers.forEach(clearTimeout); timers = []; runCount++;
    const reply = runCount === 1 ? "reply" : `reply-${runCount}`;
    const step = runCount === 1 ? "sound-check" : `sound-check-${runCount}`;
    status = "running"; durable(statusEvent());
    durable(message(`question-${runCount}`, "user", "Проверь звук и сеть. Объясни, что проверяешь, и дай подробный результат."));
    schedule(100, () => durable({id: step, kind: "ActionEvent", source: "agent", timestamp,
      tool_name: "terminal", tool_call_id: "call-sound", llm_response_id: "fixture-response", thought: [{type: "text", text: "Проверяю звук."}],
      action: {kind: "TerminalAction", command: "pactl info", is_input: false}}));
    schedule(700, () => durable({id: `sound-result-${runCount}`, kind: "ObservationEvent", source: "environment", timestamp,
      action_id: step, tool_name: "terminal", tool_call_id: "call-sound", observation: {kind: "TerminalObservation", command: "pactl info", content: [{type: "text", text: "Синтетический результат: звук работает."}], exit_code: 0, metadata: {}}}));
    schedule(900, () => send({type: "item_started", item_id: reply, attempt: 1}));
    schedule(1000, () => send({type: "delta", item_id: reply, attempt: 1, kind: "reasoning", content: "Проверю устройства и подключение. "}));
    schedule(1500, () => send({type: "delta", item_id: reply, attempt: 1, kind: "reasoning", content: "Сначала состояние звука, затем доступность сети. Подготовлю понятный результат."}));
    let offset = 0;
    for (const [index, end] of [90, 380, 430, 820, answer.length].entries()) schedule(1800 + index * 900, () => {
      send({type: "delta", item_id: reply, attempt: 1, kind: "text", content: answer.slice(offset, end)}); offset = end;
    });
    schedule(7000, () => { const event = message(reply, "agent", answer); event.llm_message.reasoning_content = "Проверю устройства и подключение. Сначала состояние звука, затем доступность сети. Подготовлю понятный результат."; durable(event); status = "finished"; durable(statusEvent()); });
    schedule(8500, () => { status = "paused"; durable(statusEvent()); });
  };
  const json = (res, value, code = 200) => { res.writeHead(code, {"Content-Type": "application/json", "Cache-Control": "no-store"}); res.end(JSON.stringify(value)); };
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://fixture.invalid"), p = url.pathname;
    if (p === "/__fixture/reset") {
      timers.forEach(clearTimeout); timers = []; events = history.map((event, seq) => ({...event, seq}));
      sequence = history.length - 1; runCount = 0; status = "idle"; offline = false; wsOffline = false;
      return json(res, {});
    }
    if (p === "/__fixture/start") { run(); return json(res, {}); }
    if (p === "/__fixture/connection") {
      const kind = url.searchParams.get("kind"); offline = kind === "all"; wsOffline = kind !== "online";
      if (wsOffline) for (const socket of sockets) socket.close(1011, "Fixture disconnect");
      return json(res, {});
    }
    if (p === "/__fixture/log") return json(res, requests);
    if (p.startsWith("/api") || p.startsWith("/llm") || p.startsWith("/v1")) {
      requests.push({path: req.url, method: req.method});
      if (offline) return json(res, {detail: "Fixture offline"}, 503);
      if (p === "/llm/running") return json(res, {running: [{model: "fixture", state: "ready"}]});
      if (p === "/llm/model/fixture/health") return json(res, {status: status === "running" ? "no slot available" : "ok", slots_idle: status === "running" ? 0 : 1, slots_processing: status === "running" ? 1 : 0});
      if (p === "/api/settings") return json(res, {language: "ru", enable_sound_notifications: false, is_new_user: false, agent_settings: {llm: {model: "fixture", base_url: "http://127.0.0.1", api_key: "fixture-only"}, tools: []}, conversation_settings: {max_iterations: 100, confirmation_mode: false}, llm_api_key_set: true});
      if (p.endsWith("/events/search")) return json(res, {items: [...events].reverse(), next_page_id: null});
      if (p.endsWith("/events/count")) return json(res, events.length);
      if (p.endsWith("/state")) return json(res, {execution_status: status, stats: {usage_to_metrics: {}}, agent: {llm: {model: "fixture"}}, workspace: {working_dir: "/tmp"}});
      if (p === "/api/conversations/search") return json(res, {items: [conversation(), conversation("second")], next_page_id: null});
      if (p === "/api/conversations") {
        if (req.method === "POST") return json(res, conversation("second"));
        const ids = [...url.searchParams.getAll("ids"), ...url.searchParams.getAll("ids[]")];
        return json(res, (ids.length ? ids : ["replay", "second"]).map(id => conversation(id)));
      }
      if (/^\/api\/conversations\/[^/]+$/.test(p)) return json(res, conversation(p.split("/").at(-1)));
      if (p === "/api/health" || p === "/health") return json(res, {status: "ok"});
      if (/profiles/.test(p)) return json(res, {profiles: [], active_agent_profile_id: null});
      if (/skills|secrets|models/.test(p)) return json(res, {items: [], models: [], skills: [], next_page_id: null});
      if (p === "/v1/audio/speech") {
        const chunks = []; for await (const chunk of req) chunks.push(chunk);
        requests.at(-1).speech = JSON.parse(Buffer.concat(chunks).toString() || "{}").input;
        const wav = Buffer.alloc(44 + 8000 * 2 * 5);
        wav.write("RIFF"); wav.writeUInt32LE(wav.length - 8, 4); wav.write("WAVEfmt ", 8); wav.writeUInt32LE(16, 16);
        wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28);
        wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write("data", 36); wav.writeUInt32LE(wav.length - 44, 40);
        res.writeHead(200, {"Content-Type": "audio/wav"}); return res.end(wav);
      }
      return json(res, {});
    }
    try {
      const file = p.startsWith("/assets/") ? path.join(root, path.basename(p)) : path.join(root, "dev/index.html");
      const actual = p.startsWith("/assets/") ? path.join(root, "assets", path.basename(p)) : file;
      res.setHeader("Content-Type", p.endsWith(".js") ? "text/javascript" : p.endsWith(".css") ? "text/css" : "text/html");
      res.end(await fs.readFile(actual));
    } catch { res.writeHead(404); res.end(); }
  });
  const ws = new WebSocketServer({ noServer: true });
  server.on("upgrade", (req, socket, head) => { if (wsOffline) return socket.destroy(); ws.handleUpgrade(req, socket, head, (client) => ws.emit("connection", client, req)); });
  ws.on("connection", (socket, req) => {
    sockets.add(socket);
    // As agent-server's session socket: sync, the replay after after_seq (none without it), the state snapshot.
    const cursor = new URL(req.url, "http://fixture.invalid").searchParams.get("after_seq");
    const after = cursor === null ? null : Number(cursor);
    socket.send(JSON.stringify({type: "sync", from_seq: after, through_seq: sequence >= 0 ? sequence : null}));
    if (after !== null) for (const event of events) if (event.seq > after) socket.send(JSON.stringify({type: "durable", seq: event.seq, event}));
    socket.send(JSON.stringify({type: "transient", event: {id: `snapshot-${++snapshots}`, kind: "ConversationStateUpdateEvent",
      source: "environment", timestamp, key: "full_state", value: {execution_status: status}}}));
    socket.on("close", () => sockets.delete(socket));
  });
  await new Promise((resolve, reject) => { server.once("error", reject); server.listen(port, "127.0.0.1", resolve); });
  return { origin: `http://127.0.0.1:${server.address().port}`, requests, close: async () => { timers.forEach(clearTimeout); for (const socket of sockets) socket.terminate(); await new Promise(resolve => ws.close(resolve)); await new Promise(resolve => server.close(resolve)); } };
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const fixture = await startFixture({root: path.resolve(process.argv[2] || "/tmp/ohn-ui-replay"), port: Number(process.argv[3] || 4174)});
  console.log(`${fixture.origin}/conversations/replay`);
}
