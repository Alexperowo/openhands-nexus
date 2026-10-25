import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";
import { startFixture } from "./server.mjs";

export const chromeOptions = {
  executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true, pipe: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking", "--disable-gpu", "--mute-audio",
    "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
};
export const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
export async function openPage(browser, origin, {width = 564, height = 785, fontSize = 28, reduced = false, autoSpeak = false, motion = "system", stallSTT = false, initialPath = "/conversations/replay"} = {}) {
  // Fixture setup precedes page navigation; each viewport receives identical history.
  await fetch(origin + "/__fixture/reset", {method: "POST"});
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setViewport({width, height});
  await page.emulateMediaFeatures([{name: "prefers-reduced-motion", value: reduced ? "reduce" : "no-preference"}]);
  const errors = [], remoteRequests = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", entry => { if (entry.type() === "error" && !entry.text().includes("503")) errors.push(entry.text()); });
  await page.setRequestInterception(true);
  page.on("request", request => {
    const url = request.url();
    if (stallSTT && url.endsWith("/audio/transcriptions")) return;
    if (url.startsWith(origin + "/") || /^(data|blob):/.test(url)) request.continue();
    else { remoteRequests.push(url); request.abort(); }
  });
  await page.evaluateOnNewDocument(({fontSize, autoSpeak, motion}) => {
    localStorage.setItem("nexus-preferences", JSON.stringify({fontSize, autoSpeak, motion, speakSteps: true}));
    const shifts = [], gaps = [], longFrames = [], textFrames = [];
    let previous = 0, observing = false;
    let textLength = 0, article = null, articleChanges = 0;
    const loop = time => {
      if (observing) {
        if (previous) gaps.push(time - previous);
        const node = [...document.querySelectorAll("article[data-testid='agent-message']")].findLast(node => node.textContent.startsWith("Проверка завершена."));
        if (node) {
          if (article && article !== node) articleChanges++;
          article = node;
          const length = node.querySelector(".whitespace-normal")?.textContent.length ?? 0;
          if (length !== textLength) { textFrames.push({time, length, delta: length - textLength}); textLength = length; }
        }
      }
      previous = time; requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
    new PerformanceObserver(list => { if (observing) for (const item of list.getEntries()) shifts.push({value: item.value, time: item.startTime, recentInput: item.hadRecentInput,
      sources: item.sources?.map(source => ({node: source.node?.getAttribute?.("data-testid") ?? source.node?.className ?? source.node?.parentElement?.outerHTML.slice(0, 240), previous: source.previousRect.toJSON(), current: source.currentRect.toJSON()}))}); })
      .observe({type: "layout-shift", buffered: true});
    if (PerformanceObserver.supportedEntryTypes.includes("long-animation-frame")) new PerformanceObserver(list => { if (observing) for (const item of list.getEntries()) longFrames.push(item.duration); }).observe({type: "long-animation-frame"});
    window.beginMeasurement = () => { shifts.length = gaps.length = longFrames.length = textFrames.length = 0; previous = textLength = articleChanges = 0; article = null; observing = true; };
    window.endMeasurement = () => { observing = false; return {shifts, gaps, longFrames, textFrames, articleChanges}; };
  }, {fontSize, autoSpeak, motion});
  await page.goto(origin + initialPath, {waitUntil: "networkidle0"});
  await page.waitForSelector(initialPath.startsWith("/settings") ? ".nexus-settings" : "[data-testid='chat-input']", {timeout: 15000});
  return {page, context, errors, remoteRequests};
}
export async function replay(page) {
  await page.keyboard.press("F8");
  await page.click("#fixture-start");
}
export function summarize({shifts, gaps, longFrames, textFrames, articleChanges}) {
  // Web Vitals CLS: maximum session window, <=1s gaps and <=5s total duration.
  let cls = 0, sum = 0, start = 0, last = -Infinity;
  for (const shift of shifts.filter(item => !item.recentInput)) {
    if (shift.time - last > 1000 || shift.time - start > 5000) { sum = 0; start = shift.time; }
    sum += shift.value; last = shift.time; cls = Math.max(cls, sum);
  }
  return {cls, rawLayoutShiftSum: shifts.reduce((sum, item) => sum + item.value, 0),
    rafGapsOver50ms: gaps.filter(value => value > 50).length, maxRafGapMs: Math.max(0, ...gaps),
    longAnimationFrames: longFrames.length, maxLongAnimationFrameMs: Math.max(0, ...longFrames), samples: gaps.length,
    textUpdates: textFrames.length, maxCharactersPerFrame: Math.max(0, ...textFrames.map(frame => frame.delta)), articleChanges, shifts, textFrames};
}
export async function measure(root, output, {caseFilter} = {}) {
  const results = [];
  let fixture, browser;
  try {
    fixture = await startFixture({root});
    browser = await puppeteer.launch(chromeOptions);
    for (const [width, height] of [[564, 785], [1280, 900]]) for (const fontSize of [18, 28]) for (const reduced of [false, true]) {
      const caseName = `${width}x${height}-${fontSize}px-${reduced ? "reduced" : "normal"}`;
      if (caseFilter && caseName !== caseFilter) continue;
      const {page, context, errors, remoteRequests} = await openPage(browser, fixture.origin, {width, height, fontSize, reduced});
      await replay(page); await pause(600); await page.evaluate(() => window.beginMeasurement());
      // Trace captures actual main-thread work; screenshots are actual browser frames.
      const capture = width === 564 && fontSize === 28 && !reduced;
      if (capture) await page.tracing.start({path: output.replace(/\.json$/, ".trace.json"), screenshots: true, categories: ["devtools.timeline"]});
      for (let frame = 0; frame < 4; frame++) {
        await pause(1800);
        if (frame === 0) await page.evaluate(() => {
          window.streamArticle = [...document.querySelectorAll("article[data-testid='agent-message']")].findLast(node => node.textContent.startsWith("Проверка завершена."));
        });
        if (capture) await page.screenshot({path: output.replace(/\.json$/, `-frame-${frame}.png`)});
      }
      if (capture) await page.tracing.stop();
      const performance = summarize(await page.evaluate(() => window.endMeasurement()));
      const articlePreserved = await page.evaluate(() => window.streamArticle?.isConnected ?? null);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      const fonts = await page.evaluate(() => ({status: document.fonts.status, externalFaces: [...document.fonts].map(font => font.family)}));
      results.push({caseName, ...performance, articlePreserved, overflow, fonts, errors, remoteRequests});
      const {shifts, textFrames, ...summary} = results.at(-1);
      console.log(JSON.stringify(summary));
      await context.close();
    }
    await fs.writeFile(output, JSON.stringify({status: "measured", browser: await browser.version(), results}, null, 2) + "\n");
    return results;
  } catch (error) {
    await fs.writeFile(output, JSON.stringify({status: "blocked", reason: error.message, code: error.code ?? null,
      cls: null, longFrames: null, screenshots: [], results}, null, 2) + "\n");
    throw error;
  } finally { await browser?.close(); await fixture?.close(); }
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = path.resolve(process.argv[2] || "/tmp/ohn-ui-after");
  const output = path.resolve(process.argv[3] || "dev/evidence/after.json");
  await fs.mkdir(path.dirname(output), {recursive: true});
  await measure(root, output).catch(error => {console.error(error.message); process.exitCode = 1;});
}
