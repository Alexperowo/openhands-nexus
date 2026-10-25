import type { Backend, ResolvedActiveBackend } from "../node_modules/@openhands/agent-canvas/dist/api/backend-registry/types.js";

export function originBackends(backends: Backend[], origin: string, id: string): Backend[] {
  const current = backends.find((backend) => backend.id === id);
  if (current?.host === origin && current.apiKey === "" && current.kind === "local") return backends;
  const local: Backend = { id, name: current?.name || "Local", host: origin, apiKey: "", kind: "local" };
  return [local, ...backends.filter((backend) => backend.id !== id)];
}

export function isOriginSelection(active: ResolvedActiveBackend, origin: string, id: string) {
  return active.backend.id === id && active.backend.host === origin && active.backend.kind === "local" &&
    active.backend.apiKey === "" && active.orgId === null;
}

export function originLocation(href: string) {
  const url = new URL(href);
  url.searchParams.delete("backend");
  url.searchParams.delete("org");
  return url.pathname + url.search + url.hash;
}
