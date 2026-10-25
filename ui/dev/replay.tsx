// Synthetic, non-personal events; all endpoints are served by dev/server.mjs.
import "../src/main.tsx";
import { audioService } from "../src/audio-service.ts";
const params = new URLSearchParams(location.search);
// Set before React's first commit; preferences are read on module evaluation, so
// the runner seeds localStorage before navigation for each measurement.
(window as any).replay = {
  audio: () => audioService.getStatus(),
  start: () => fetch("/__fixture/start", { method: "POST" }),
  connection: (kind: string) => fetch(`/__fixture/connection?kind=${kind}`, { method: "POST" }),
};
document.documentElement.dataset.replay = params.get("variant") || "current";
const controls = document.createElement("details");
controls.className = "fixture-controls";
controls.innerHTML = `<summary>Стенд</summary><button id="fixture-start">Воспроизвести</button><button data-connection="all">Отключить связь</button><button data-connection="socket">Отключить WebSocket</button><button data-connection="online">Восстановить связь</button>`;
controls.style.cssText = "display:none;position:fixed;right:0;top:0;z-index:1000;background:#111;color:white;border:2px solid #888;padding:4px;font:16px system-ui";
for (const button of controls.querySelectorAll("button")) {
  button.style.cssText = "display:block;min-height:48px;background:#111;color:white;border:1px solid #888;font:inherit;padding:4px 12px";
  button.addEventListener("click", () => {
    controls.open = false; controls.style.display = "none";
    if (button.id === "fixture-start") void (window as any).replay.start();
    else void (window as any).replay.connection((button as HTMLElement).dataset.connection);
    document.querySelector<HTMLElement>("[data-testid='chat-input']")?.focus({preventScroll: true});
  });
}
controls.querySelector("summary")!.style.cssText = "min-height:48px;min-width:48px;cursor:pointer;display:flex;align-items:center";
document.body.append(controls);

document.addEventListener("keydown", event => {
  if (event.key === "F8") {
    event.preventDefault();
    const show = controls.style.display === "none";
    controls.style.display = show ? "block" : "none";
    controls.open = show;
    if (show) controls.querySelector<HTMLButtonElement>("button")?.focus();
    else document.querySelector<HTMLElement>("[data-testid='chat-input']")?.focus({preventScroll: true});
  }
});
if (params.has("controls")) { controls.style.display = "block"; controls.open = true; }
