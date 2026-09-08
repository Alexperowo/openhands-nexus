#!/usr/bin/env node
/**
 * OpenHands Local - HTTPS LAN Gateway with Authentication Boundary
 *
 * Architecture:
 * - LAN Entrance: Port 8443 (HTTPS / WSS)
 * - Authentication: Persistent Token / Cookie boundary for LAN clients
 * - Targets:
 *   - Agent Canvas Ingress: 127.0.0.1:8000
 *   - Local Voice Bridge:   127.0.0.1:18002 (/voice-api/*)
 * - Zero new dependencies: uses built-in Node https/http/tls/fs/crypto and agent-canvas proxy-utils.
 */

import { createServer as createHttpsServer } from "node:https";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL, parse as parseUrl } from "node:url";
import { parse as parseQuery } from "node:querystring";
import process from "node:process";
import { loadWorkingProfiles, getWorkingProfileState, switchWorkingProfile } from "../Config/working_profile_manager.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const CERT_PFX = join(__dirname, "certs", "openhands-lan.pfx");
const CA_CRT = join(__dirname, "certs", "openhands-ca.crt");
const AUTH_TOKEN_FILE = join(__dirname, "certs", "lan-auth-token.txt");
const PFX_PASS = "openhands-pwa-local";
const HTTPS_PORT = parseInt(process.env.OPENHANDS_LAN_PORT || "8443", 10);
const CANVAS_TARGET = "http://127.0.0.1:8000";
const VOICE_TARGET = "http://127.0.0.1:18002";

if (!existsSync(CERT_PFX)) {
  console.error(`[LAN Gateway] Certificate PFX not found at: ${CERT_PFX}`);
  console.error(`[LAN Gateway] Please run generate-ca-and-certs.py first.`);
  process.exit(1);
}

// 1. Read persistent LAN Auth Token & Configuration
const CONFIG_FILE = join(__dirname, "gateway-config.json");
let LAN_AUTH_ENABLED = false; // Default: false (Trusted Home LAN Mode)
if (existsSync(CONFIG_FILE)) {
  try {
    const cfg = JSON.parse(readFileSync(CONFIG_FILE, "utf-8"));
    if (typeof cfg.lan_auth_enabled === "boolean") {
      LAN_AUTH_ENABLED = cfg.lan_auth_enabled;
    }
  } catch (err) {
    console.warn(`[LAN Gateway] Could not parse ${CONFIG_FILE}:`, err.message);
  }
}
if (process.env.OPENHANDS_LAN_AUTH_ENABLED !== undefined) {
  LAN_AUTH_ENABLED = (process.env.OPENHANDS_LAN_AUTH_ENABLED === "true" || process.env.OPENHANDS_LAN_AUTH_ENABLED === "1");
} else if (process.env.LAN_AUTH_ENABLED !== undefined) {
  LAN_AUTH_ENABLED = (process.env.LAN_AUTH_ENABLED === "true" || process.env.LAN_AUTH_ENABLED === "1");
}

let LAN_AUTH_TOKEN = "";
if (existsSync(AUTH_TOKEN_FILE)) {
  LAN_AUTH_TOKEN = readFileSync(AUTH_TOKEN_FILE, "utf-8").trim();
}
if (!LAN_AUTH_TOKEN) {
  LAN_AUTH_TOKEN = process.env.OPENHANDS_LAN_AUTH_TOKEN || "openhands-local-station-pass";
}

// 2. Load proxy handler from agent-canvas installation
let createProxyHandlers;
try {
  const appData = process.env.APPDATA || (process.env.USERPROFILE ? join(process.env.USERPROFILE, "AppData", "Roaming") : "C:\\Users\\User\\AppData\\Roaming");
  const proxyUtilsPath = join(appData, "npm", "node_modules", "@openhands", "agent-canvas", "scripts", "proxy-utils.mjs");
  const proxyUtilsUrl = pathToFileURL(proxyUtilsPath).href;
  const proxyUtils = await import(proxyUtilsUrl);
  createProxyHandlers = proxyUtils.createProxyHandlers;
} catch (err) {
  console.error(`[LAN Gateway] Failed to load agent-canvas proxy-utils: ${err.message}`);
  process.exit(1);
}

const proxy = createProxyHandlers({ label: `lan-gateway:${HTTPS_PORT}` });
const pfxData = readFileSync(CERT_PFX);

function parseCookies(cookieHeader) {
  const list = {};
  if (!cookieHeader) return list;
  cookieHeader.split(";").forEach((cookie) => {
    let [name, ...rest] = cookie.split("=");
    name = name?.trim();
    if (!name) return;
    const val = rest.join("=").trim();
    try {
      list[name] = decodeURIComponent(val);
    } catch {
      list[name] = val;
    }
  });
  return list;
}

function checkAuth(req) {
  if (!LAN_AUTH_ENABLED) {
    return true;
  }

  // Check Cookie
  const cookies = parseCookies(req.headers.cookie);
  if (cookies["openhands_lan_auth"] && cookies["openhands_lan_auth"] === LAN_AUTH_TOKEN) {
    return true;
  }

  // Check Headers
  const authHeader = req.headers["authorization"] || "";
  if (authHeader.startsWith("Bearer ") && authHeader.slice(7).trim() === LAN_AUTH_TOKEN) {
    return true;
  }
  if (req.headers["x-lan-auth"] === LAN_AUTH_TOKEN) {
    return true;
  }

  // Check URL query param ?token=... or ?auth=...
  try {
    const parsed = parseUrl(req.url, true);
    const queryToken = parsed.query?.token || parsed.query?.auth;
    if (queryToken && queryToken === LAN_AUTH_TOKEN) {
      return true;
    }
  } catch (e) {}

  return false;
}

function renderCaInstructionsPage() {
  return `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Установка сертификата — OpenHands Local</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: #09090b;
      color: #f4f4f5;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 1.5rem 1rem;
    }
    .card {
      background-color: #18181b;
      border: 1px solid #27272a;
      border-radius: 1rem;
      padding: 2rem;
      width: 100%;
      max-width: 500px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1.25rem;
    }
    .logo-icon {
      width: 40px;
      height: 40px;
      background: linear-gradient(135deg, #3b82f6, #6366f1);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: bold;
      color: white;
      font-size: 1.25rem;
    }
    h1 { font-size: 1.25rem; font-weight: 600; color: #fff; }
    p.sub { font-size: 0.875rem; color: #a1a1aa; margin-top: 0.25rem; }
    .steps {
      margin: 1.5rem 0;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }
    .step {
      display: flex;
      gap: 0.75rem;
      background: #27272a;
      padding: 0.875rem;
      border-radius: 0.5rem;
      border: 1px solid #3f3f46;
      font-size: 0.875rem;
      line-height: 1.45;
      color: #d4d4d8;
    }
    .step-num {
      background: #3b82f6;
      color: white;
      width: 24px;
      height: 24px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: bold;
      font-size: 0.75rem;
      flex-shrink: 0;
      margin-top: 0.1rem;
    }
    .btn {
      display: block;
      width: 100%;
      padding: 0.85rem;
      background: #2563eb;
      color: white;
      text-align: center;
      text-decoration: none;
      border-radius: 0.5rem;
      font-size: 1rem;
      font-weight: 600;
      transition: background 0.2s;
      margin-top: 1rem;
    }
    .btn:hover { background: #1d4ed8; }
    .btn-secondary {
      display: block;
      width: 100%;
      padding: 0.75rem;
      background: transparent;
      border: 1px solid #3f3f46;
      color: #93c5fd;
      text-align: center;
      text-decoration: none;
      border-radius: 0.5rem;
      font-size: 0.9rem;
      font-weight: 500;
      margin-top: 0.75rem;
    }
    .btn-secondary:hover { background: #27272a; }
    .note {
      font-size: 0.75rem;
      color: #71717a;
      margin-top: 1.25rem;
      line-height: 1.4;
      text-align: center;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">
      <div class="logo-icon">OH</div>
      <div>
        <h1>OpenHands Local</h1>
        <p class="sub">Установка доверенного сертификата CA</p>
      </div>
    </div>

    <p style="font-size: 0.9rem; color: #a1a1aa; line-height: 1.4;">
      Чтобы Chrome на Android открывал OpenHands без предупреждений безопасности и позволял установить приложение (PWA), установите локальный корневой сертификат:
    </p>

    <div class="steps">
      <div class="step">
        <div class="step-num">1</div>
        <div>Нажмите кнопку <b>«Скачать сертификат CA»</b> ниже (файл <code>openhands-ca.crt</code>).</div>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <div>Откройте <b>Настройки Android &rarr; Безопасность (или Защита и конфиденциальность) &rarr; Другие параметры &rarr; Установка из памяти устройства &rarr; Сертификат CA</b> (или нажмите на скачанный файл).</div>
      </div>
      <div class="step">
        <div class="step-num">3</div>
        <div>Подтвердите установку (при запросе выберите «Все равно установить»).</div>
      </div>
      <div class="step">
        <div class="step-num">4</div>
        <div>Перезапустите Chrome и перейдите на главную страницу OpenHands.</div>
      </div>
      <div class="step">
        <div class="step-num">5</div>
        <div>В меню Chrome (⋮) выберите <b>«Установить приложение»</b> или <b>«Добавить на главный экран»</b>.</div>
      </div>
    </div>

    <a class="btn" href="/openhands-ca.crt" download>Скачать сертификат CA (openhands-ca.crt)</a>
    <a class="btn-secondary" href="/">Вернуться в OpenHands</a>

    <div class="note">
      Сертификат выпущен исключительно для вашего локального ПК (<code>192.168.0.14</code>).
    </div>
  </div>
</body>
</html>`;
}

function renderLoginPage(errorMsg = "") {
  return `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OpenHands Local — Вход в локальной сети</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: #09090b;
      color: #f4f4f5;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 1rem;
    }
    .card {
      background-color: #18181b;
      border: 1px solid #27272a;
      border-radius: 1rem;
      padding: 2rem;
      width: 100%;
      max-width: 420px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
    }
    .logo-icon {
      width: 36px;
      height: 36px;
      background: linear-gradient(135deg, #3b82f6, #6366f1);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: bold;
      color: white;
      font-size: 1.25rem;
    }
    h1 { font-size: 1.25rem; font-weight: 600; color: #fff; }
    p.sub { font-size: 0.875rem; color: #a1a1aa; margin-top: 0.25rem; }
    .error {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid #ef4444;
      color: #f87171;
      padding: 0.75rem;
      border-radius: 0.5rem;
      font-size: 0.875rem;
      margin-bottom: 1rem;
    }
    label {
      display: block;
      font-size: 0.875rem;
      font-weight: 500;
      color: #d4d4d8;
      margin-bottom: 0.5rem;
    }
    input[type="password"], input[type="text"] {
      width: 100%;
      padding: 0.75rem 1rem;
      background: #27272a;
      border: 1px solid #3f3f46;
      border-radius: 0.5rem;
      color: #fff;
      font-size: 16px;
      margin-bottom: 1.25rem;
    }
    input:focus {
      outline: none;
      border-color: #3b82f6;
      box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
    }
    button {
      width: 100%;
      padding: 0.75rem;
      background: #3b82f6;
      color: white;
      border: none;
      border-radius: 0.5rem;
      font-size: 1rem;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }
    button:hover { background: #2563eb; }
    .info-box {
      margin-top: 1.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid #27272a;
      font-size: 0.75rem;
      color: #71717a;
      line-height: 1.5;
    }
    .info-box a { color: #60a5fa; text-decoration: none; }
    .info-box a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">
      <div class="logo-icon">OH</div>
      <div>
        <h1>OpenHands Local</h1>
        <p class="sub">Шлюз доступа домашней сети</p>
      </div>
    </div>
    ${errorMsg ? `<div class="error">${errorMsg}</div>` : ""}
    <form method="POST" action="/__lan_login">
      <label for="token">Токен доступа / Пароль</label>
      <input type="password" id="token" name="token" placeholder="Введите токен LAN" required autofocus>
      <button type="submit">Подключиться к станции</button>
    </form>
    <div class="info-box">
      <p>Авторизация защищает рабочую станцию от несанкционированного доступа.</p>
      <p style="margin-top:0.5rem;">Токен сохранен на ПК: <code>openhands-pwa/certs/lan-auth-token.txt</code></p>
      <p style="margin-top:0.5rem;"><a href="/cert">Инструкция по сертификату CA</a> &bull; <a href="/openhands-ca.crt" download>Скачать CA сертификат</a></p>
    </div>
  </div>
</body>
</html>`;
}

const httpsServer = createHttpsServer(
  {
    pfx: pfxData,
    passphrase: PFX_PASS,
    minVersion: "TLSv1.2",
  },
  (req, res) => {
    const parsed = parseUrl(req.url, true);
    const pathname = parsed.pathname || "/";

    // 1. Root CA Certificate instructions and download
    if (pathname === "/cert" || pathname === "/ca") {
      res.writeHead(200, {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "public, max-age=3600",
      });
      res.end(renderCaInstructionsPage());
      return;
    }

    if (pathname === "/openhands-ca.crt") {
      if (existsSync(CA_CRT)) {
        const certBytes = readFileSync(CA_CRT);
        res.writeHead(200, {
          "Content-Type": "application/x-x509-ca-cert",
          "Content-Disposition": 'attachment; filename="openhands-ca.crt"',
          "Content-Length": certBytes.length,
          "Cache-Control": "public, max-age=86400",
        });
        res.end(certBytes);
        return;
      }
    }

    // 2. Form login POST endpoint
    if (pathname === "/__lan_login" && req.method === "POST") {
      let body = "";
      req.on("data", (chunk) => { body += chunk; });
      req.on("end", () => {
        const form = parseQuery(body);
        const submittedToken = (form.token || form.password || "").trim();
        if (submittedToken === LAN_AUTH_TOKEN) {
          // Set 1-year persistent secure HttpOnly cookie
          res.writeHead(302, {
            "Set-Cookie": `openhands_lan_auth=${LAN_AUTH_TOKEN}; Path=/; HttpOnly; SameSite=Lax; Secure; Max-Age=31536000`,
            "Location": "/",
          });
          res.end();
        } else {
          res.writeHead(401, { "Content-Type": "text/html; charset=utf-8" });
          res.end(renderLoginPage("Неверный токен доступа. Проверьте lan-auth-token.txt на компьютере."));
        }
      });
      return;
    }

    // 3. Query param authentication hook (?token=... or ?auth=...)
    // If present in query and matches, set cookie and redirect to clean URL
    const queryToken = parsed.query?.token || parsed.query?.auth;
    if (queryToken && queryToken === LAN_AUTH_TOKEN) {
      delete parsed.query.token;
      delete parsed.query.auth;
      delete parsed.search;
      const cleanUrl = parsed.pathname + (Object.keys(parsed.query).length ? `?${new URLSearchParams(parsed.query).toString()}` : "") + (parsed.hash || "");
      res.writeHead(302, {
        "Set-Cookie": `openhands_lan_auth=${LAN_AUTH_TOKEN}; Path=/; HttpOnly; SameSite=Lax; Secure; Max-Age=31536000`,
        "Location": cleanUrl || "/",
      });
      res.end();
      return;
    }

    // 4. Authenticate request
    const isAuthed = checkAuth(req);

    if (!isAuthed) {
      // API / Voice API / server_info requests return 401 JSON
      if (pathname.startsWith("/api") || pathname.startsWith("/voice-api") || pathname.startsWith("/server_info") || pathname.startsWith("/sockets")) {
        res.writeHead(401, { "Content-Type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ error: "Требуется авторизация", message: "Для доступа к шлюзу OpenHands LAN требуется токен авторизации" }));
        return;
      }

      // Browser navigation gets login page
      res.writeHead(401, { "Content-Type": "text/html; charset=utf-8" });
      res.end(renderLoginPage());
      return;
    }

    // 4b. Working Profiles API Endpoint (Shared between Desktop & Mobile)
    if (pathname === "/api/working-profiles") {
      if (req.method === "GET") {
        try {
          const profiles = loadWorkingProfiles();
          const state = getWorkingProfileState();
          res.writeHead(200, {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-cache, no-store, must-revalidate",
          });
          res.end(JSON.stringify({ profiles, state }, null, 2));
          return;
        } catch (err) {
          res.writeHead(500, { "Content-Type": "application/json; charset=utf-8" });
          res.end(JSON.stringify({ error: err.message }));
          return;
        }
      } else if (req.method === "POST") {
        let body = "";
        req.on("data", (chunk) => { body += chunk; });
        req.on("end", async () => {
          try {
            const data = JSON.parse(body || "{}");
            const result = await switchWorkingProfile(
              data.working_profile_id,
              data.reasoning_mode_id,
              "lan_mobile"
            );
            res.writeHead(200, {
              "Content-Type": "application/json; charset=utf-8",
              "Cache-Control": "no-cache",
            });
            res.end(JSON.stringify(result));
          } catch (err) {
            res.writeHead(400, { "Content-Type": "application/json; charset=utf-8" });
            res.end(JSON.stringify({ error: err.message }));
          }
        });
        return;
      }
    }

    // 5. Authenticated requests: Proxy to upstream services
    // Route /voice-api/* to Voice Bridge (127.0.0.1:18002)
    if (pathname.startsWith("/voice-api/")) {
      req.url = req.url.slice("/voice-api".length) || "/";
      proxy.proxyHttp(req, res, VOICE_TARGET);
      return;
    }

    // All other HTTP requests route to Agent Canvas Ingress (127.0.0.1:8000)
    proxy.proxyHttp(req, res, CANVAS_TARGET);
  }
);

// Handle WebSocket upgrades (Agent Canvas /sockets)
httpsServer.on("upgrade", (req, socket, head) => {
  if (!checkAuth(req)) {
    socket.end(
      "HTTP/1.1 401 Unauthorized\r\n" +
      "Content-Type: text/plain; charset=utf-8\r\n" +
      "Connection: close\r\n" +
      "\r\n" +
      "Требуется авторизация\r\n"
    );
    return;
  }
  proxy.proxyWebSocket(req, socket, head, CANVAS_TARGET);
});

httpsServer.on("clientError", (err, socket) => {
  if (socket.writable) {
    socket.end("HTTP/1.1 400 Bad Request\r\n\r\n");
  } else {
    socket.destroy();
  }
});

httpsServer.listen(HTTPS_PORT, "0.0.0.0", () => {
  console.log(`=====================================================================`);
  console.log(` OpenHands Mobile LAN PWA Gateway ONLINE on port ${HTTPS_PORT}`);
  console.log(` Target Canvas Ingress: ${CANVAS_TARGET}`);
  console.log(` Target Voice Bridge:   ${VOICE_TARGET}`);
  console.log(` Authentication:        ${LAN_AUTH_ENABLED ? "ВКЛЮЧЕНА (Режим ограниченного доступа)" : "ОТКЛЮЧЕНА (Доверенная домашняя сеть / Прямой вход)"}`);
  console.log(` CA Instructions:       /cert or /ca`);
  console.log(` Public Root CA:        /openhands-ca.crt (downloadable)`);
  console.log(`=====================================================================`);
});

// Clean shutdown signals
process.on("SIGINT", () => { httpsServer.close(); process.exit(0); });
process.on("SIGTERM", () => { httpsServer.close(); process.exit(0); });
