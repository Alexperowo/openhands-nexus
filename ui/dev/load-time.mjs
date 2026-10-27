// Page load on a fixture build, CPU slowed 4x (closer to the tablet): first with an empty cache, then again.
// node dev/load-time.mjs <fixture build from dev/build.mjs> [runs]
import puppeteer from "puppeteer-core";
import { startFixture } from "./server.mjs";
import { chromeOptions } from "./measure.mjs";
const root = process.argv[2], runs = Number(process.argv[3] || 5);
const fixture = await startFixture({root});
const browser = await puppeteer.launch(chromeOptions);
const rows = [];
try {
  for (let i = 0; i < runs; i++) {
    await fetch(fixture.origin + "/__fixture/reset", {method: "POST"});
    const context = await browser.createBrowserContext();
    const page = await context.newPage();
    await page.setViewport({width: 564, height: 785});
    const cdp = await page.createCDPSession();
    await cdp.send("Performance.enable");
    await cdp.send("Emulation.setCPUThrottlingRate", {rate: 4});
    let bytes = 0;
    page.on("response", async (r) => { try { if (r.url().includes("/assets/")) bytes += (await r.buffer()).length; } catch {} });
    const open = async () => {
      const start = Date.now();
      await page.goto(fixture.origin + "/conversations/replay");
      await page.waitForSelector("[data-testid='chat-input']", {timeout: 60000});
      await page.waitForFunction(() => document.body.innerText.includes("Предыдущая проверка"), {timeout: 60000});
      return Date.now() - start;
    };
    const shown = await open();
    const m = Object.fromEntries((await cdp.send("Performance.getMetrics")).metrics.map((x) => [x.name, x.value]));
    // Opened again: assets from the browser cache, as on the tablet after the first visit.
    const again = await open();
    rows.push({shown, again, script: Math.round(m.ScriptDuration * 1000), heap: Math.round(m.JSHeapUsedSize / 1e6), assets: Math.round(bytes / 1e3)});
    await context.close();
  }
} finally { await browser.close(); fixture.close?.(); }
const median = (k) => rows.map((r) => r[k]).sort((a, b) => a - b)[Math.floor(rows.length / 2)];
console.log(JSON.stringify(rows));
console.log(`median: shown ${median("shown")} ms, again ${median("again")} ms, script ${median("script")} ms, heap ${median("heap")} MB, assets ${median("assets")} kB`);
process.exit(0);
