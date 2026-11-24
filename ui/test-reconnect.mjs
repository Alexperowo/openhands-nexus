import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { openPage, pause } from "./dev/measure.mjs";

export async function testReconnect(browser, fixture, output, axe) {
  const { page, context, errors, remoteRequests } = await openPage(browser, fixture.origin, { fontSize: 28 });
  const online = "[data-nexus-connection='online']";
  const button = "[data-testid='reconnect-button']";
  const input = "[data-testid='chat-input']";
  const draft = "Проверь связь после возвращения в приложение";
  const cdp = await page.createCDPSession();
  await cdp.send("Network.enable");
  let handshakes = 0;
  cdp.on("Network.webSocketHandshakeResponseReceived", ({ response }) => {
    if (response.status === 101) handshakes++;
  });
  const restored = async previousHandshakes => {
    const deadline = Date.now() + 5000;
    // A stale OPEN render must not count as recovery: require a new wire handshake.
    while (handshakes <= previousHandshakes && Date.now() < deadline) await pause(25);
    assert.ok(handshakes > previousHandshakes, "a new WebSocket must open");
    await page.waitForSelector(online, { timeout: Math.max(1, deadline - Date.now()) });
  };
  const results = [];
  const requestCount = fixture.requests.length;
  try {
    await page.waitForSelector(online);
    await page.type(input, draft);
    // Real short suspension reproduces resume arriving before the queued close event.
    // The 120-second counterpart is also run against live Nexus before release.
    const beforeFreeze = handshakes;
    await cdp.send("Page.setWebLifecycleState", { state: "frozen" });
    await pause(10000);
    const resumed = Date.now();
    await cdp.send("Page.setWebLifecycleState", { state: "active" });
    await restored(beforeFreeze);
    results.push({ scenario: "CDP freeze 10s", recoveryMs: Date.now() - resumed });
    // CDP active resumes JS but leaves visibility hidden. Restore the foreground
    // before pointer/keyboard tests, whose viewport checks use animation frames.
    await cdp.send("Emulation.setFocusEmulationEnabled", { enabled: true });
    assert.equal(await page.evaluate(() => document.visibilityState), "visible");
    assert.equal(await page.$eval(input, node => node.innerText), draft);

    // A clean freeze disconnect disables Canvas's retry timer. Keep JS running
    // without resume so only the user's explicit action can restore the socket.
    for (const activation of ["Enter", "Space", "click"]) {
      await page.evaluate(() => document.dispatchEvent(new Event("freeze")));
      await page.waitForSelector(button, { visible: true });
      assert.ok(await page.$eval(button, node => node.tagName === "BUTTON" && node.type === "button" && node.tabIndex === 0));
      await page.focus(button);
      if (activation === "Enter") {
        await page.screenshot({ path: path.join(output, "reconnect-lost.png") });
        await page.addScriptTag({ content: axe });
        const audit = await page.evaluate(async () => await axe.run(document, {rules: {"color-contrast-enhanced": {enabled: true}}}));
        await fs.writeFile(path.join(output, "reconnect-axe.json"), JSON.stringify(audit.violations, null, 2) + "\n");
        assert.deepEqual(audit.violations.map(item => item.id), [], "lost banner must be accessible");
      }
      const beforeManual = handshakes;
      const started = Date.now();
      if (activation === "click") await page.click(button);
      else await page.keyboard.press(activation);
      await restored(beforeManual);
      assert.equal(await page.$(button), null);
      assert.equal(await page.$eval(input, node => node.innerText), draft);
      await page.waitForFunction(() => document.activeElement === document.querySelector(".nexus-status-slot"), {polling:100,timeout:3000});
      results.push({ scenario: `manual ${activation}`, recoveryMs: Date.now() - started });
    }
    await cdp.send("Emulation.setFocusEmulationEnabled", { enabled: false });
    await page.setUserAgent("Mozilla/5.0 (Linux; Android 14; SM-X916B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36");
    const beforeMobileFreeze = handshakes;
    await cdp.send("Page.setWebLifecycleState", { state: "frozen" });
    await pause(10000);
    const mobileResumed = Date.now();
    await cdp.send("Page.setWebLifecycleState", { state: "active" });
    await restored(beforeMobileFreeze);
    results.push({ scenario: "Android CDP freeze 10s", recoveryMs: Date.now() - mobileResumed });
    assert.equal(await page.$eval(input, node => node.innerText), draft);
    await cdp.send("Emulation.setFocusEmulationEnabled", { enabled: true });
    await page.screenshot({ path: path.join(output, "reconnect-restored.png") });
    // Chrome reports sockets closed by forced BFCache entry in its console.
    // Every other browser/React error remains a failure.
    const frozenSocketError = /^WebSocket connection to '[^']+' failed: Page entered Back-Forward Cache\.$/;
    assert.deepEqual(errors.filter(message => !frozenSocketError.test(message)), []);
    assert.deepEqual(remoteRequests, []);
    assert.equal(fixture.requests.slice(requestCount).filter(entry => entry.method === "POST" && /\/(events|goal)$/.test(entry.path)).length, 0,
      "reconnection must preserve the draft without sending it");
    await fs.writeFile(path.join(output, "reconnect-results.json"), JSON.stringify({ status: "passed", results, expectedFrozenSocketClosures: errors.filter(message => frozenSocketError.test(message)).length }, null, 2) + "\n");
    console.log("PASS CDP freeze/resume, manual reconnect by Enter/Space/click, draft, focus and axe");
  } finally {
    await context.close();
  }
}
