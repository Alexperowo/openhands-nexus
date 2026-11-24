import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { openPage } from "./dev/measure.mjs";

// Shared by the isolated fixture and the read-only HTTPS acceptance check.
export function settingsLayout() {
  const main = document.querySelector(".settings-page main");
  const overflow = [...main.querySelectorAll("*")].filter(node =>
    node.clientWidth > 0 && node.scrollWidth > node.clientWidth + 1 && !["INPUT", "TEXTAREA"].includes(node.tagName))
    .map(node => ({tag: node.tagName, testId: node.dataset.testid, excess: node.scrollWidth - node.clientWidth}));
  const labelsOutsideField = [...main.querySelectorAll(".grid > div")].flatMap(field => {
    const bounds = field.getBoundingClientRect();
    return [...field.querySelectorAll("label > div:first-child > span")].filter(node => {
      const rect = node.getBoundingClientRect();
      return rect.left < bounds.left - 1 || rect.right > bounds.right + 1;
    }).map(node => node.textContent);
  });
  const title = main.querySelector("[data-testid='title-llm-profile-input']");
  const selectedValues = [...main.querySelectorAll("select")].map(node => {
    const style = getComputedStyle(node), canvas = document.createElement("canvas").getContext("2d");
    canvas.font = style.font;
    const needed = canvas.measureText(node.selectedOptions[0]?.textContent ?? "").width + 20;
    const available = node.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    return {needed, available};
  });
  const heading = main.querySelector("[data-testid='secrets-settings-screen'] h2")?.getBoundingClientRect();
  const add = main.querySelector("[data-testid='add-secret-button']")?.getBoundingClientRect();
  const headerOverlap = !!(heading && add && heading.left < add.right && heading.right > add.left && heading.top < add.bottom && heading.bottom > add.top);
  const navigation = document.querySelector("[data-testid='settings-navbar-desktop']").getBoundingClientRect();
  return {documentOverflow: document.documentElement.scrollWidth > innerWidth, overflow, labelsOutsideField,
    titleClipped: !!title && title.scrollWidth > title.clientWidth + 1, selectedValues, headerOverlap,
    navigationTooTall: navigation.width > innerWidth / 2 && navigation.height > innerHeight * 0.35,
    gridColumns: [...main.querySelectorAll(".grid")].map(node => getComputedStyle(node).gridTemplateColumns)};
}

export function assertSettingsLayout(result, name) {
  assert.equal(result.documentOverflow, false, name);
  assert.deepEqual(result.overflow, [], name);
  assert.deepEqual(result.labelsOutsideField, [], name);
  assert.equal(result.headerOverlap, false, name);
  assert.equal(result.titleClipped, false, name);
  assert.equal(result.navigationTooTall, false, name);
  for (const value of result.selectedValues) assert.ok(value.available >= value.needed - 1, `${name}: selected value clipped`);
}

// Also used by the read-only HTTPS check. Only the status text may ellipsize.
export function inputActionsLayout() {
  const root = document.querySelector(".nexus-input-actions");
  const row = root.firstElementChild;
  const picker = root.querySelector("[data-testid='chat-input-llm-profile']");
  const status = root.querySelector("[data-testid='chat-input-model-status']");
  const plus = root.querySelector("[data-testid='chat-plus-button']");
  const overflow = root.querySelector("button[aria-label='Действия с дополнительным вводом']");
  const right = row.lastElementChild;
  const visible = node => !!node?.getClientRects().length;
  const rect = node => node?.getBoundingClientRect();
  const statusRect = rect(status), plusRect = rect(plus), overflowRect = rect(overflow);
  const controls = [...root.querySelectorAll("[data-testid='chat-plus-button'], [data-testid='chat-dictation-button'], [data-testid='submit-button'], [data-testid='stop-button']")]
    .filter(visible).map(node => ({id: node.dataset.testid, width: rect(node).width, height: rect(node).height}));
  return {
    viewportWidth: innerWidth,
    documentOverflow: document.documentElement.scrollWidth > innerWidth,
    rowOverflow: row.scrollWidth > row.clientWidth + 1,
    pickerVisible: visible(picker), statusVisible: visible(status), text: status?.textContent,
    statusCount: root.querySelectorAll("[data-testid='chat-input-model-status']").length,
    fontSize: getComputedStyle(root).fontSize,
    inlineAfterOverflow: !!overflow && status?.previousElementSibling === overflow &&
      statusRect.left >= overflowRect.right - 1 &&
      Math.abs(statusRect.top + statusRect.height / 2 - overflowRect.top - overflowRect.height / 2) <= 1,
    plusThenOverflow: !!overflow && overflowRect.left >= plusRect.right - 1 && overflowRect.left - plusRect.right <= 8,
    statusWidth: statusRect?.width,
    clearOfRightControls: !!statusRect && statusRect.right <= rect(right).left + 1,
    ellipsis: !!status && getComputedStyle(status).textOverflow === "ellipsis" && getComputedStyle(status).minWidth === "0px",
    controls,
  };
}

export function assertInputActionsLayout(result, name) {
  assert.equal(result.documentOverflow, false, name);
  assert.equal(result.rowOverflow, false, name);
  assert.ok(result.statusCount <= 1, name);
  assert.equal(result.statusVisible, !result.pickerVisible, `${name}: exactly one model indicator`);
  if (result.statusVisible) {
    assert.equal(result.inlineAfterOverflow, true, `${name}: status immediately after overflow in the same row`);
    assert.equal(result.plusThenOverflow, true, `${name}: compact plus/overflow order`);
    assert.equal(result.clearOfRightControls, true, `${name}: status overlaps right controls`);
    assert.equal(result.ellipsis, true, name);
    assert.ok(result.statusWidth >= 48, `${name}: status must have readable space, got ${result.statusWidth}px`);
  }
  for (const control of result.controls) {
    // Canvas permits the desktop send button to flex down to its 48px minimum.
    const fullSize = control.id === "chat-dictation-button" ||
      (control.id === "submit-button" && result.viewportWidth <= 767);
    const expected = fullSize ? Math.max(48, parseFloat(result.fontSize) * 2) : 48;
    assert.ok(control.width >= expected && control.height >= expected, `${name}: unchanged touch target ${control.id}`);
  }
}

export async function testSettingsLayout(browser, fixture, output) {
  const results = [];
  for (const width of [564, 1280]) for (const fontSize of [18, 28]) {
    for (const route of ["/settings", "/settings/llm", "/settings/secrets", "/settings/voice"]) {
      const {page, context, errors, remoteRequests} = await openPage(browser, fixture.origin, {width, height: 900, fontSize, initialPath: route});
      if (route === "/settings/llm") await page.waitForSelector("[data-testid='sdk-settings-llm.num_retries']");
      if (route === "/settings/secrets") await page.waitForSelector("[data-testid='secret-item']");
      const name = `${route}-${width}-${fontSize}`;
      const result = await page.evaluate(settingsLayout);
      assertSettingsLayout(result, name);
      assert.deepEqual(errors, [], name);
      assert.deepEqual(remoteRequests, [], name);
      results.push({name, ...result});
      await context.close();
    }
  }
  await fs.writeFile(path.join(output, "settings-layout.json"), JSON.stringify({status: "passed", results}, null, 2) + "\n");
  console.log("PASS settings layout: four pages at 564/1280 × 18/28px, full selected values, labels and secrets table");
}

export async function testInputMenu(page) {
  const picker = "[data-testid='chat-input-llm-profile']";
  const inline = await page.$eval(picker, node => !!node.getClientRects().length);
  if (inline) await page.click(picker);
  else {
    await page.click("button[aria-label='Действия с дополнительным вводом']");
    await page.click("[data-testid='overflow-model-button']");
  }
  const menu = inline ? "[data-testid='chat-input-llm-profile-popover']" : "[data-testid='overflow-model-submenu']";
  await page.waitForSelector(menu, {visible: true});
  await page.waitForFunction(selector => getComputedStyle(document.querySelector(selector).parentElement).opacity === "1", {}, menu);
  const result = await page.$eval(menu, node => {
    const rect = node.getBoundingClientRect(), style = getComputedStyle(node);
    const button = node.querySelector("[data-testid^='chat-input-llm-profile-option-']");
    const viewport = (node.closest("[data-testid='chat-input-overflow-menu']") ?? node).getBoundingClientRect();
    const firstProfile = button.getBoundingClientRect();
    return {background: style.backgroundColor, display: getComputedStyle(button).display,
      inViewport: viewport.top >= 0 && viewport.bottom <= innerHeight + 1,
      profileVisible: firstProfile.top >= viewport.top && firstProfile.bottom <= viewport.bottom,
      fits: rect.left >= 0 && rect.right <= innerWidth + 1, overflow: node.scrollWidth > node.clientWidth + 1};
  });
  assert.notEqual(result.background, "rgba(0, 0, 0, 0)");
  assert.ok(result.display.includes("flex"), "profile menu buttons must receive Canvas styles");
  assert.equal(result.fits, true);
  assert.equal(result.overflow, false);
  assert.equal(result.inViewport, true, "model menu must stay within the viewport");
  assert.equal(result.profileVisible, true, "profile choices must be visible inside the menu");
  await page.mouse.click(1, 1);
  await page.waitForSelector(menu, {hidden: true});
}
