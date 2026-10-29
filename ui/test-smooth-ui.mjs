// Full real App/Canvas. Fixture owns all HTTP/WS endpoints; never connects to live Nexus.
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { execFileSync } from "node:child_process";
import puppeteer from "puppeteer-core";
import { startFixture } from "./dev/server.mjs";
import { chromeOptions, openPage, pause, replay } from "./dev/measure.mjs";

// A kept fixture build would test old code: without OHN_REPLAY_DIR the current source is built afresh.
const built = process.env.OHN_REPLAY_DIR ? null : await fs.mkdtemp(path.join(os.tmpdir(), "ohn-ui-replay-"));
if (built) execFileSync(process.execPath, ["--import", "./dev/forbid-secrets.mjs", "dev/build.mjs", built], {stdio: "inherit"});
const root = path.resolve(process.env.OHN_REPLAY_DIR || built);
const output = path.resolve(process.env.OHN_UI_EVIDENCE || "dev/evidence");
await fs.mkdir(output, {recursive: true});
let fixture, browser;
const results = [];
try {
  fixture = await startFixture({root});
  browser = await puppeteer.launch(chromeOptions);
  // Prefer the declared dependency; allow the offline cached engine without installing packages.
  let axePath = process.env.AXE_PATH;
  if (!axePath) {
    try { axePath = new URL(import.meta.resolve("axe-core/axe.min.js")); }
    catch (error) {
      if (error.code !== "ERR_MODULE_NOT_FOUND") throw error;
      axePath = "/tmp/ohn-axe/package/axe.min.js";
    }
  }
  const axe = await fs.readFile(axePath, "utf8");
  for (const [width, height] of [[564, 785], [1280, 900]]) for (const fontSize of [18, 28]) for (const reduced of [false, true]) {
    const {page, context, errors, remoteRequests} = await openPage(browser, fixture.origin, {width, height, fontSize, reduced});
    const caseName = `${width}x${height}-${fontSize}px-${reduced ? "reduced" : "normal"}`;
    assert.ok(await page.$eval("[data-testid='chat-input']", node => {
      const style = getComputedStyle(node), placeholder = getComputedStyle(node, "::before");
      return style.fontSize === placeholder.fontSize && node.getBoundingClientRect().height >= parseFloat(style.lineHeight) - 1;
    }), "input and placeholder must follow the selected font without clipping");
    await replay(page); await pause(3000);
    await page.evaluate(() => { window.streamArticle = document.querySelector("[data-testid='nexus-stream'] article"); });
    const scroll = "[data-testid='chat-scroll-container']";
    await page.hover(scroll); await page.mouse.wheel({deltaY: -200}); await pause(100);
    const before = await page.$eval(scroll, node => node.scrollTop);
    await pause(1500);
    const after = await page.$eval(scroll, node => node.scrollTop);
    assert.ok(Math.abs(after - before) <= 3, `reading position moved: ${caseName}, ${before} -> ${after}`);
    await page.waitForSelector("button[aria-label='К новым сообщениям']");
    assert.equal(await page.$eval("[data-testid='scroll-to-bottom']", node => getComputedStyle(node).rotate), "none", "jump label must remain upright");
    await pause(3200);
    assert.ok(Math.abs((await page.$eval(scroll, node => node.scrollTop)) - before) <= 3, "finalization moved the reading position");
    await page.click("button[aria-label='К новым сообщениям']");
    await pause(250);
    assert.ok(await page.$eval(scroll, node => node.scrollHeight - node.clientHeight - node.scrollTop <= 3), "bottom must follow growth");
    // The run ends paused; Canvas's own «Готово» fades out before that and fails contrast mid-fade.
    await page.waitForFunction(() => document.querySelector(".nexus-status-text")?.textContent === "Пауза", {timeout: 10000});
    assert.equal(await page.evaluate(() => window.streamArticle?.isConnected), true, "delta -> final remounted article");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.equal(await page.$$eval("main,[role='main']", nodes => nodes.filter(node => !["presentation", "none"].includes(node.getAttribute("role"))).length), 1, "one main at desktop and tablet widths");
    await page.screenshot({path: path.join(output, `${caseName}.png`)});
    await page.addScriptTag({content: axe});
    const audit = await page.evaluate(async () => await axe.run(document, {rules: {"color-contrast-enhanced": {enabled: true}}}));
    const contrast = audit.passes.find(rule => rule.id === "color-contrast-enhanced");
    const ratios = contrast.nodes.flatMap(node => [...node.any, ...node.all].map(check => check.data?.contrastRatio)).filter(Number.isFinite);
    const minContrast = Math.min(...ratios);
    await fs.writeFile(path.join(output, `${caseName}-axe.json`), JSON.stringify({testEngine: audit.testEngine,
      testEnvironment: audit.testEnvironment, timestamp: audit.timestamp, violations: audit.violations, incomplete: audit.incomplete,
      enhancedContrast: contrast, passes: audit.passes.map(rule => ({id: rule.id, nodes: rule.nodes.length}))}, null, 2) + "\n");
    assert.deepEqual(audit.violations.map(item => ({id: item.id, nodes: item.nodes.map(node => node.target)})), [], caseName);
    assert.ok(ratios.length && minContrast >= 7, `measured text contrast below 7:1: ${minContrast}`);
    // A real keyboard expansion must keep focus on the native summary.
    const summary = ".nexus-reasoning > summary";
    await page.focus(summary); await page.keyboard.press("Enter"); await pause(250);
    assert.equal(await page.$eval(summary, node => document.activeElement === node), true);
    if (reduced) assert.equal(await page.$eval(".nexus-page", node => getComputedStyle(node).animationName), "none");
    assert.deepEqual(errors, []); assert.deepEqual(remoteRequests, []);
    await page.screenshot({path: path.join(output, `${caseName}.png`)});
    results.push({caseName, axeViolations: 0, minMeasuredTextContrast: minContrast, readingPositionDelta: after - before});
    console.log(`PASS ${caseName}: scroll, article, keyboard, axe including enhanced contrast`);
    await context.close();
  }
  // Native setting, keyboard drawer and a single main landmark.
  {
    const {page, context} = await openPage(browser, fixture.origin, {initialPath: "/settings/accessibility"});
    assert.equal(await page.$$eval("main,[role='main']", nodes => nodes.filter(node => node.getClientRects().length).length), 1);
    await page.click(".nexus-settings select"); await page.keyboard.press("End"); await page.keyboard.press("Enter");
    await page.waitForFunction(() => document.documentElement.dataset.nexusMotion === "off");
    assert.equal(await page.$eval(".nexus-page", node => getComputedStyle(node).animationName), "none");
    assert.equal(await page.$eval(".nexus-settings select", node => document.activeElement === node), true);
    await page.click("button[aria-label='Разделы настроек']");
    await page.waitForFunction(() => document.activeElement?.closest("[role='dialog']"));
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => document.activeElement?.getAttribute("aria-label") === "Разделы настроек");
    assert.equal(await page.$eval("button[aria-label='Разделы настроек']", node => document.activeElement === node), true);
    await page.addScriptTag({content: axe});
    const audit = await page.evaluate(async () => await axe.run(document, {rules: {"color-contrast-enhanced": {enabled: true}}}));
    await fs.writeFile(path.join(output, "settings-axe.json"), JSON.stringify({testEngine: audit.testEngine, violations: audit.violations, incomplete: audit.incomplete}, null, 2) + "\n");
    assert.deepEqual(audit.violations.map(item => item.id), []);
    await context.close();
  }
  // Actual socket-only outage: REST stays healthy; one assertive notice per transition.
  {
    const {page, context} = await openPage(browser, fixture.origin, {});
    await page.evaluate(() => {
      window.connectionNotices = [];
      const observer = new MutationObserver(() => {
        const text = document.querySelector(".nexus-status-slot [role='alert']")?.textContent;
        if (text && window.connectionNotices.at(-1) !== text) window.connectionNotices.push(text);
      });
      observer.observe(document.querySelector(".nexus-status-slot"), {subtree: true, childList: true, characterData: true});
    });
    await page.keyboard.press("F8"); await page.click("[data-connection='socket']");
    await page.waitForFunction(() => document.querySelector("[data-nexus-connection='lost']"));
    await pause(3200);
    assert.equal(await page.evaluate(() => window.connectionNotices.filter(text => text.startsWith("Связь потеряна")).length), 1);
    await page.keyboard.press("F8"); await page.click("[data-connection='online']");
    await page.waitForFunction(() => document.querySelector("[data-nexus-connection='online']"), {timeout: 15000});
    await page.waitForFunction(() => window.connectionNotices.includes("Связь восстановлена"));
    assert.equal(await page.evaluate(() => window.connectionNotices.filter(text => text === "Связь восстановлена").length), 1);
    await context.close();
  }
  // A model swap before the first message (the agent idle): the line shows the loading and says it once.
  {
    const {page, context, errors} = await openPage(browser, fixture.origin, {});
    const text = () => document.querySelector(".nexus-status-text")?.textContent.trim();
    await fetch(fixture.origin + "/__fixture/model?state=starting");
    await page.waitForFunction(text => new Function(`return (${text})()`)() === "Модель загружается", {timeout: 8000}, String(text));
    assert.equal(await page.$eval(".nexus-status-slot [role='status']", node => node.textContent), "Модель загружается");
    assert.equal(await page.$eval(".status-bar", node => node.dataset.tone), "work");
    await fetch(fixture.origin + "/__fixture/model?state=ready");
    await page.waitForFunction(text => new Function(`return (${text})()`)() === "", {timeout: 8000}, String(text));
    assert.deepEqual(errors, []); await context.close();
  }
  // Actual controls, not direct service.stop(): both a step and an answer must stop.
  {
    const {page, context, errors} = await openPage(browser, fixture.origin, {autoSpeak: true});
    await page.click("button[aria-label='Включить звук']"); await replay(page);
    await page.waitForFunction(() => window.replay.audio().currentId === "sound-check");
    await page.click("button[aria-label='Остановить озвучку']");
    assert.equal(await page.evaluate(() => window.replay.audio().currentId), null);
    await page.waitForFunction(() => window.replay.audio().currentId === "reply", {timeout: 12000});
    await page.click("button[aria-label='Остановить озвучку']");
    assert.equal(await page.evaluate(() => window.replay.audio().currentId), null);
    assert.equal(await page.$eval("button[aria-label='Остановить озвучку']", node => document.activeElement === node), true);
    assert.deepEqual(errors, []); await context.close();
  }
  // Cancel a stalled transcription through the user's button; read the deferred answer.
  {
    const {page, context} = await openPage(browser, fixture.origin, {autoSpeak: true, stallSTT: true});
    await page.click("button[aria-label='Включить звук']"); await replay(page);
    await page.click("[data-testid='chat-dictation-button']");
    await page.waitForFunction(() => document.querySelector("[data-testid='chat-dictation-button']").getAttribute("aria-pressed") === "true");
    await page.click("[data-testid='chat-dictation-button']");
    await pause(7800);
    assert.equal(await page.evaluate(() => window.replay.audio().isDictating), true);
    await page.click("button[aria-label='Отменить диктовку']");
    await page.waitForFunction(() => window.replay.audio().currentId === "reply");
    assert.equal(await page.evaluate(() => window.replay.audio().isDictating), false);
    await page.click("button[aria-label='Остановить озвучку']");
    await context.close();
  }
  await fs.writeFile(path.join(output, "ui-results.json"), JSON.stringify({status: "passed", browser: await browser.version(), axePath: String(axePath), results,
    additionalChecks: ["settings Off and focus", "drawer keyboard and focus return", "one main", "socket loss/restoration once", "model loading shown while idle", "real Stop for step and answer", "STT Cancel releases hold and reads deferred answer"]}, null, 2) + "\n");
  console.log(`Chrome UI: ${results.length} matrix cases passed; axe=0; real Stop and dictation Cancel passed`);
} catch (error) {
  await fs.writeFile(path.join(output, "ui-results.json"), JSON.stringify({status: error.code === "EPERM" ? "blocked" : "failed", reason: error.message, code: error.code ?? null, results}, null, 2) + "\n");
  throw error;
} finally {
  await browser?.close(); await fixture?.close();
  if (built) await fs.rm(built, {recursive: true, force: true});
}
