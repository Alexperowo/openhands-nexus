// The fixture exceeds Canvas's virtualization threshold and uses real Chrome touch and keyboard input.
import assert from "node:assert/strict";
import { openPage, pause, replay } from "./dev/measure.mjs";

export async function testLongHistory(browser, fixture) {
  const {page, context, errors} = await openPage(browser, fixture.origin, {touch: true, historyLength: 180});
  const scroll = "[data-testid='chat-scroll-container']";
  const jump = "button[aria-label='К новым сообщениям']";
  await page.waitForSelector("[data-testid='virtualized-message-list'] [data-nexus-event='history-179']");
  await replay(page);
  await page.waitForSelector("[data-nexus-event='reply'] article p");

  const box = await (await page.$(scroll)).boundingBox();
  const x = Math.round(box.x + box.width / 2), y = Math.round(box.y + 70);
  await page.touchscreen.touchStart(x, y);
  for (let i = 1; i <= 8; i++) {
    await page.touchscreen.touchMove(x, y + i * 35);
    await pause(35);
  }
  await pause(150);
  await page.touchscreen.touchEnd();
  await page.waitForSelector(jump);
  await pause(250);
  const readingMark = () => page.$eval(scroll, node => {
    const top = node.getBoundingClientRect().top;
    const item = [...node.querySelectorAll("[data-nexus-event] article p")].find(p => p.getBoundingClientRect().bottom > top + 1);
    return item && {id: item.closest("[data-nexus-event]").dataset.nexusEvent, y: item.getBoundingClientRect().top - top};
  });
  const before = await readingMark();
  assert.match(before?.id, /^history-/);
  await page.waitForFunction(() => document.querySelector(".nexus-status-text")?.textContent === "Пауза");
  const after = await readingMark();
  assert.equal(after?.id, before.id, "the final answer displaced the message being read");
  assert.ok(Math.abs(after.y - before.y) <= 3, `the old message moved from ${before.y} to ${after.y}`);

  const speechId = await page.$eval(scroll, node => {
    const {top, bottom} = node.getBoundingClientRect();
    const button = [...node.querySelectorAll("[data-nexus-event^='history-'] [data-testid='speak-button']")].find(control => {
      const rect = control.getBoundingClientRect();
      return rect.top >= top && rect.bottom <= bottom;
    });
    return button?.closest("[data-nexus-event]").dataset.nexusEvent;
  });
  assert.match(speechId, /^history-/);
  await page.focus(`[data-nexus-event='${speechId}'] [data-testid='speak-button']`);
  await page.keyboard.press("Enter");
  await page.waitForFunction(id => window.replay.audio().currentId === id, {}, speechId);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => window.replay.audio().currentId === null);

  await page.focus(jump);
  await page.keyboard.press("Enter");
  await page.waitForFunction(selector => {
    const node = document.querySelector(selector);
    return node.scrollHeight - node.scrollTop - node.clientHeight <= 3 && !document.querySelector("[data-testid='scroll-to-bottom']");
  }, {}, scroll);
  assert.deepEqual(await page.$eval(scroll, node => [document.activeElement === node, node.getAttribute("aria-label")]),
    [true, "История беседы"], "jumping to the newest messages must leave keyboard focus in the named conversation history");
  await page.keyboard.press("PageUp");
  await page.waitForSelector(jump);
  assert.deepEqual(errors, []);
  await context.close();
  console.log("PASS long history: touch scroll, stable reading, speech and keyboard navigation");
}
