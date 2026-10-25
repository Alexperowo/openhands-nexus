import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { NEW_CONVERSATION_SELECTOR } from "./src/conversation-opening.ts";

const canvas = "./node_modules/@openhands/agent-canvas/dist/";

test("Canvas still renders the native New chat link with our selector and a click navigation", () => {
  const rail = readFileSync(`${canvas}components/features/sidebar/sidebar-rail-body.js`, "utf8");
  const link = readFileSync(`${canvas}components/features/sidebar/sidebar-nav-link.js`, "utf8");
  const navigation = readFileSync(`${canvas}components/shared/navigation-link.js`, "utf8");
  assert.equal(NEW_CONVERSATION_SELECTOR, 'a[data-testid="sidebar-conversations-link"]');
  assert.match(rail, /to: "\/conversations",\s*end: !0,\s*label: [^\n]+SIDEBAR\$NEW_CHAT[^\n]+\s*testId: "sidebar-conversations-link"/);
  assert.match(link, /"data-testid": v/);
  assert.match(navigation, /r\("a",/);
  assert.match(navigation, /onClick: b/);
});

test("init pins Canvas before its consumers: stale selection, URL override and later switches use the shell origin", async (t) => {
  const memory = () => {
    const data = new Map();
    return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, String(value)), removeItem: (key) => data.delete(key) };
  };
  const localStorage = memory(), sessionStorage = memory();
  let url = new URL("https://nexus.invalid:8443/conversations/example?backend=other&org=old&keep=1#answer");
  globalThis.localStorage = localStorage;
  globalThis.window = {
    localStorage, sessionStorage, get location() { return url; },
    history: { state: { marker: 1 }, replaceState(state, title, href) { url = new URL(href, url); assert.deepEqual(state, { marker: 1 }); } },
  };
  t.after(() => { delete globalThis.window; delete globalThis.localStorage; });
  const other = { id: "other", name: "Other", host: "https://other.invalid", apiKey: "", kind: "local" };
  const { SEEDED_DEFAULT_BACKEND_ID: id } = await import(`${canvas}api/backend-registry/default-backend.js`);
  const storage = await import(`${canvas}api/backend-registry/storage.js`);
  storage.writeStoredBackends([other, { id, name: "Local", host: "https://old.invalid", apiKey: "obsolete", kind: "local" }]);
  storage.writeStoredActiveBackend({ backendId: "other", orgId: "old" });
  // Import the actual host entry, not a reimplementation of its initialization.
  await import("./src/init.ts");
  const store = await import(`${canvas}api/backend-registry/active-store.js`);
  const pinned = () => {
    assert.deepEqual(store.getActiveBackend(), {
      backend: { id, name: "Local", host: url.origin, apiKey: "", kind: "local" }, orgId: null,
    });
    assert.deepEqual(storage.readStoredActiveBackend(), { backendId: id, orgId: null });
  };
  pinned();
  assert.equal(url.pathname + url.search + url.hash, "/conversations/example?keep=1#answer");
  store.setActiveSelection({ backendId: "other", orgId: "old" });
  pinned();
  store.setRegisteredBackends([other]);
  pinned();
  store.setRegisteredBackends([other, { id, name: "Local", host: other.host, apiKey: "obsolete", kind: "cloud" }]);
  pinned();
  assert.equal(store.getRegisteredBackends().filter((backend) => backend.id === id).length, 1);
});
