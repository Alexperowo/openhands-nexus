# OpenHands Mobile LAN PWA

## HOW TO USE

1. **Запустите OpenHands**  
   Запустите `K:\Project\START-OPENHANDS-LOCAL.cmd` на рабочем ПК (или используйте ярлык на рабочем столе).

2. **Откройте адрес в браузере телефона**  
   В Google Chrome на Android (в той же сети Wi-Fi) перейдите по адресу:  
   **`https://192.168.0.14:8443`**  
   *(Вход в доверенной домашней сети происходит сразу напрямую, без ввода паролей).*

3. **При первом входе установите Root CA (при необходимости)**  
   Чтобы Chrome открывал станцию с доверенным замком и разрешал установку PWA, откройте:  
   **`https://192.168.0.14:8443/cert`**  
   Скачайте сертификат (`openhands-ca.crt`) и установите его в настройках Android как Сертификат CA.

4. **Перезапустите Chrome**  
   Закройте и снова откройте вкладку `https://192.168.0.14:8443` в Chrome.

5. **Установите OpenHands как PWA**  
   В меню Chrome (**⋮**) нажмите **«Установить приложение»** (или «Добавить на главный экран»).  
   Приложение появится на рабочем столе смартфона и будет запускаться в полноэкранном режиме.

---

## Verification & Status Truth

- **`SERVER_READY`**: **PASS** (HTTPS Gateway, X.509 Root CA + signed Leaf cert, loopback listener isolation, and PWA asset delivery fully verified).
- **`AUTOMATED_BROWSER_VALIDATION`**: **PASS** (Verified with real Google Chrome: `window.isSecureContext = true`, Service Worker registration active, manifest linked).
- **`ANDROID_MANUAL_TEST_PENDING`**: **PENDING_MANUAL** (Physical installation and touch gesture on an external Android device require a human user with hardware).
- **`HOST_VIA_LAN_IP`**: **PASS** (Gateway reachable over LAN IP `192.168.0.14:8443` through network interface).
- **`EXTERNAL_LAN_CLIENT`**: **PENDING_MANUAL** (Final validation from an external physical phone/tablet on Wi-Fi).

---

## Architecture & Networking

```
+-----------------------------------------------------------------------------------+
| Desktop Workstation (Windows 11)                                                  |
|                                                                                   |
|  [ Inbound Wi-Fi / LAN: 192.168.0.14 ]                                            |
|                                                                                   |
|         | TCP 8443 (HTTPS - Scoped Firewall: Private / LocalSubnet)               |
|         v                                                                         |
|  +-----------------------------------------------------------------------------+  |
|  | OpenHands Mobile LAN PWA Gateway (lan-gateway.mjs, Node.js v24)             |  |
|  | - TLS Signed Leaf Cert (CN=DESKTOP-L0FBHL4, SAN: 192.168.0.14, localhost)   |  |
|  | - Auth Boundary: HttpOnly Cookie / Token Header / Query Param               |  |
|  | - Public Route: /openhands-ca.crt (downloadable Root CA)                     |  |
|  | - Reverse Proxy: httpxy / proxy-utils.mjs                                   |  |
|  +-----------------------------------------------------------------------------+  |
|         |                                      |                                  |
|         | default HTTP & WebSockets            | /voice-api/*                     |
|         v                                      v                                  |
|  +------------------------------------+  +-------------------------------------+  |
|  | Agent Canvas Ingress (Port 8000)   |  | Local Voice Bridge (Port 18002)     |  |
|  | - Strictly bound to 127.0.0.1:8000 |  | - Strictly bound to 127.0.0.1:18002|  |
|  | - Serves UI, PWA manifest, sw.js   |  | - GigaAM v3 STT + Supertonic 3 TTS  |  |
|  | - Proxies /api/* to agent-server   |  +-------------------------------------+  |
|  +------------------------------------+                                           |
|         |                                                                         |
|         v (internal loopback)                                                     |
|  +------------------------------------+  +-------------------------------------+  |
|  | agent-server (Port 18000)          |  | llama-swap Router (Port 8080)       |  |
|  | - Strictly bound to 127.0.0.1:18000|  | - Strictly bound to 127.0.0.1:8080  |  |
|  | - Task execution & workspaces      |  | - Qwen 3.8 Opus / Ornith / Next     |  |
|  +------------------------------------+  +-------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

### Port Assignments & Loopback Isolation

| Port | Service | Protocol | Binding | LAN Accessible? | Purpose |
|---|---|---|---|---|---|
| **8443** | Mobile LAN Gateway | HTTPS / WSS | `0.0.0.0:8443` | **YES (Scoped LAN)** | Single secure entry point with authentication |
| **8000** | Agent Canvas | HTTP | `127.0.0.1:8000` | **NO (Loopback Only)**| Desktop web ingress and frontend static server |
| **8080** | llama-swap | HTTP | `127.0.0.1:8080` | **NO (Loopback Only)**| Model swapping & LLM inference router |
| **18000**| agent-server | HTTP | `127.0.0.1:18000`| **NO (Loopback Only)**| OpenHands agent core API & workspace manager |
| **18001**| automation | HTTP | `127.0.0.1:18001`| **NO (Loopback Only)**| Automation backend |
| **18002**| local-voice | HTTP | `127.0.0.1:18002`| **NO (Loopback Only)**| Neural STT (GigaAM v3) and TTS engine |

All backend services (`8000`, `8080`, `18000`, `18001`, `18002`) remain strictly bound to `127.0.0.1` and cannot be accessed directly from the network.

---

## Security, Certificates & Authentication

1. **LAN Access & Optional Authentication Boundary**
   - **Доверенная домашняя сеть (по умолчанию)**: `lan_auth_enabled: false`. Вход на `https://192.168.0.14:8443` происходит напрямую без ввода паролей.
   - **Ограниченный режим (опционально)**: установите `"lan_auth_enabled": true` в `openhands-pwa/gateway-config.json` (или `OPENHANDS_LAN_AUTH_ENABLED=true`). При включении шлюз требует токен из `openhands-pwa/certs/lan-auth-token.txt` через форму авторизации, cookie или заголовок.
   - Защита сетевого контура: порт 8443 защищен правилом Брандмауэра Windows (профиль Private, подсеть LocalSubnet). Все внутренние службы (`8000`, `8080`, `18000`, `18001`, `18002`) остаются строго на loopback (`127.0.0.1`).
   - Доступ с локального ПК через `http://127.0.0.1:8000` полностью изолирован и не требует авторизации.

2. **Genuine 2-Tier Certificate Architecture (Root CA + Signed Leaf)**
   - Generated via Python cryptography (`K:\Project\openhands-pwa\generate-ca-and-certs.py`).
   - **Root CA** (`openhands-ca.crt`): `CN=OpenHands Local Root CA`, `is_ca=True`, KeyUsage `keyCertSign, cRLSign`. Valid 10 years.
   - **Leaf Certificate** (`openhands-lan.crt` / `.pfx`): `CN=DESKTOP-L0FBHL4`, `is_ca=False`, signed by Root CA. SANs: `DESKTOP-L0FBHL4`, `192.168.0.14`, `localhost`, `127.0.0.1`.
   - Private keys and PFX archives are strictly protected by `.gitignore` and never committed or logged.

3. **Installing Root CA on Android for Green Lock**
   If you want to remove Chrome's security prompt permanently on your phone:
   1. Download the Root CA certificate: tap the download link on the gateway login page or visit `https://192.168.0.14:8443/openhands-ca.crt`.
   2. On your Android device, navigate to:  
      **Settings** -> **Security & Privacy** -> **More Security Settings** -> **Encryption & credentials** -> **Install a certificate** -> **CA certificate**.  
      *(Note: Select CA certificate, NOT user/VPN certificate).*
   3. Choose `openhands-ca.crt` and tap **Install Anyway**. Chrome on Android will now trust connections to `https://192.168.0.14:8443` with a green lock!

---

## Progressive Web App (PWA) Specifications

- **Manifest**: Located at `/manifest.webmanifest`.
  - Name: `OpenHands`
  - Display: `standalone` (removes browser navigation chrome, status bar color matching)
  - Theme Color: `#18181b`
  - Background Color: `#09090b`
  - Icons: High-resolution 192x192 PNG, 512x512 PNG, and SVG vector icon.
- **Service Worker (`sw.js`)**:
  - Strategy: **Network-First** for shell assets with offline fallback.
  - API Safety: Strictly **NEVER** caches `/api/*`, `/sockets/*`, `/voice-api/*`, or `/server_info` requests. This guarantees that agent streaming responses and live tool state are never stale.
  - Lifecycle: `skipWaiting()` and `clients.claim()` are called immediately to ensure any updates to the frontend are applied on the next page load.
- **Mobile Responsive Enhancements (`mobile-pwa.css`)**:
  - Safe Area Insets: Dynamic padding for phone notches and home gesture bars (`env(safe-area-inset-*)`).
  - Auto-Zoom Prevention: Sets `16px` font size on mobile form inputs to stop iOS/Android browser viewport auto-zooming on focus.
  - Touch Targets: Buttons and interactive controls have minimum 38px–44px touch areas.
  - Overflow Protection: Wide code blocks, markdown tables, and output panes are wrapped in touch-scrollable horizontal containers to prevent breaking mobile page width.
  - Voice Button: Sized to 44x44px and positioned comfortably within reach of the mobile composer.

---

## Station Lifecycle & Updater Integration

- **Canonical Start**:  
  `START-OPENHANDS-LOCAL.cmd` automatically launches the PWA Gateway on port 8443 alongside the model router, voice bridge, and agent canvas.
- **Canonical Stop**:  
  `STOP-OPENHANDS-LOCAL.cmd` terminates the gateway process and ensures all 6 ports (8000, 8080, 8443, 18000, 18001, 18002) are fully released with 0 orphan processes.
- **Update Survivability**:  
  The update script (`K:\Project\OpenHands-Update\scripts\update-openhands.ps1`) integrates `patch-agent-canvas-pwa.ps1` into its automated post-build pipeline. If Agent Canvas is reinstalled or updated, PWA assets (`manifest.webmanifest`, `sw.js`, `mobile-pwa.css`, and `index.html` tags) are automatically restored and validated before station launch.

---

## Troubleshooting

- **Phone cannot reach `https://192.168.0.14:8443`**:
  - Check that the PC and mobile device are connected to the same Wi-Fi router.
  - Check Windows network settings: ensure your active Wi-Fi connection profile is set to **Private network**, not Public.
  - Verify OpenHands is running by checking `START-OPENHANDS-LOCAL.cmd` output.
- **Voice input not responding**:
  - Ensure you accessed the app via `https://` (microphone access is blocked by browsers on insecure `http://` LAN connections).
  - Check that Chrome was granted microphone permission in Android app settings.
- **IP Address Changed**:
  - If your workstation's LAN IP changes after a router restart, you can reserve a static IP for `DESKTOP-L0FBHL4` in your router's DHCP settings, or run `K:\Project\openhands-pwa\generate-certs.ps1` to regenerate certificates for the new IP.
