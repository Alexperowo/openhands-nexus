// Opt-in check of the installed Nexus. It runs read-only tasks in a temporary conversation.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import puppeteer from "puppeteer-core";

const flag = process.argv[2];
const profilesByFlag = {
  "--nex19": "Nex-19G-2080",
  "--tess": "Tess-27B",
  "--holo": "Holo4-27B",
  "--with-mtp": "Holo4-27B",
};
assert.ok(process.argv.length <= 3 && (flag === undefined || Object.hasOwn(profilesByFlag, flag)),
  "Usage: node ui/test-live-local-models.mjs [--nex19 | --tess | --holo | --with-mtp]");
const startProfile = flag === undefined ? "Nex-25G" : profilesByFlag[flag];
const scenarios = [[startProfile, false], [startProfile, true]];
if (flag === "--with-mtp") {
  scenarios.push(["Holo4-MTP-27B", true], [startProfile, false]);
}

const origin = "https://localhost:8443";
const dir = await mkdtemp(join(tmpdir(), "nexus-live-model-"));
const id = randomUUID();
const conversation = "/api/conversations/" + id;
const picker = "[data-testid='chat-input-llm-profile']";
const moreActions = "button[aria-label='Действия с дополнительным вводом'], button[aria-label='More input actions']";
const input = "[data-testid='chat-input']";
const question = "Посмотри, какая версия драйвера NVIDIA уже установлена на этом компьютере. " +
  "Проверь через nvidia-smi и ответь простым русским языком. Это проверка установленной версии. Сеть и настройки не трогай.";
const recheck = "Перепроверь версию драйвера после переключения модели. Заново запусти " +
  "nvidia-smi --query-gpu=driver_version --format=csv,noheader и сравни с прошлым ответом. " +
  "Сообщи по-русски, совпадает ли версия. Настройки не меняй.";
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let browser, page, created;

const api = (path, method = "GET", body) => page.evaluate(async ({path, method, body}) => {
  const response = await fetch(path, {method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  if (!response.ok) throw new Error(method + " " + path + " returned " + response.status);
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}, {path, method, body});

const events = async () => (await api(conversation + "/events/search?limit=100")).items;

function answers(rows) {
  return rows.filter(row => row.source === "agent").flatMap(row => [
    ...(row.llm_message?.content ?? []).map(part => part.text).filter(Boolean),
    ...(row.tool_name === "finish" && row.action?.message ? [row.action.message] : []),
  ]);
}

function mixedLanguage(text) {
  return /\p{Script=Han}|\p{Script=Hiragana}|\p{Script=Katakana}|\uFFFD/u.test(text) ||
    /(?:[а-яё][a-z]|[a-z][а-яё])/iu.test(text);
}

async function select(profile) {
  await page.waitForSelector(picker);
  if (await page.$eval(picker, node => node.title) === profile) return;
  // Canvas moves the picker into the input actions when the row is too narrow.
  if (await page.$eval(picker, node => node.getClientRects().length > 0)) {
    await page.locator(picker).click();
  } else {
    await page.locator(moreActions).click();
    await page.locator("[data-testid='overflow-model-button']").click();
  }
  const option = `[data-testid="chat-input-llm-profile-option-${profile}"]`;
  await page.locator(option).click();
  await page.waitForFunction((picker, profile) => document.querySelector(picker)?.title === profile, {}, picker, profile);
}

async function ask(prompt, task, installedVersion) {
  const before = new Set((await events()).map(row => row.id));
  await page.waitForSelector(input);
  await page.click(input);
  await page.keyboard.type(prompt);
  await page.keyboard.press("Enter");
  const deadline = Date.now() + (prompt === "Привет." ? 360_000 : 195_000);
  while (Date.now() < deadline) {
    const rows = (await events()).filter(row => !before.has(row.id));
    const status = (await api(conversation)).execution_status;
    assert.notEqual(status, "error", "The agent entered the error state");
    const replies = answers(rows);
    const goal = rows.filter(row => row.key === "goal")
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp)).at(-1)?.value;
    if (task && status === "finished" && replies.length) {
      assert.ok(goal, "Nexus handled the requested check as conversation");
    }
    if (status === "finished" && replies.length && !goal?.active) {
      assert.ok(replies.some(text => /\p{Script=Cyrillic}/u.test(text)), "The answer is missing Russian text");
      assert.ok(!replies.some(mixedLanguage), `Mixed scripts in the answer: ${replies.at(-1)}`);
      assert.ok(!replies.some(text => /\d{32}/u.test(text)), "The answer contains an unexpectedly long number");
      if (task) {
        assert.equal(goal.status, "complete", "The goal check did not confirm completion");
        assert.ok(replies.some(text => text.includes(installedVersion)), "Wrong NVIDIA driver version");
        assert.ok(rows.some(({tool_name, observation}) => tool_name === "terminal" &&
          observation?.command?.includes("nvidia-smi") && observation.exit_code === 0 &&
          observation.content?.some(part => part.text?.includes(installedVersion))),
          "The terminal did not return the real NVIDIA driver version");
        await page.waitForFunction(version => document.querySelector("[data-testid='chat-scroll-container']")
          ?.innerText.includes(version), {}, installedVersion);
      }
      return replies.join("\n");
    }
    await pause(1000);
  }
  assert.fail("The model did not finish within the test limit");
}

try {
  const installedVersion = execFileSync("nvidia-smi", ["--query-gpu=driver_version", "--format=csv,noheader"],
    {encoding: "utf8", timeout: 10_000}).trim().split("\n")[0];
  assert.match(installedVersion, /^\d+\.\d+/);
  browser = await puppeteer.launch({
    executablePath: "/usr/bin/google-chrome", headless: true, acceptInsecureCerts: true, args: ["--no-proxy-server"],
  });
  page = await browser.newPage();
  await page.setViewport({width: 564, height: 785, hasTouch: true, isMobile: true});
  const pageErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.goto(origin, {waitUntil: "domcontentloaded"});
  const running = (await api("/api/conversations/search?limit=100")).items;
  assert.ok(!running.some(row => ["running", "waiting_for_confirmation"].includes(row.execution_status)),
    "Another conversation is working");
  const profiles = await api("/api/profiles");
  const {agent_settings} = await api("/api/settings");
  assert.equal(new URL(agent_settings.llm.base_url).origin, "http://127.0.0.1:18030");
  agent_settings.llm.api_key = "not-needed";
  await api("/api/conversations", "POST", {
    conversation_id: id, workspace: {working_dir: dir}, agent_settings, autotitle: false, max_iterations: 10,
  });
  created = true;
  await page.goto(origin + "/conversations/" + id, {waitUntil: "domcontentloaded"});
  for (const [profile, task] of scenarios) {
    await select(profile);
    const prompt = task ? (profile === "Holo4-MTP-27B" ? recheck : question) : "Привет.";
    await ask(prompt, task, installedVersion);
    console.log("PASS", profile, task ? "driver query and goal completion" : "greeting");
  }
  if (flag === "--tess") {
    const answer = await ask("Сколько процентов видеопамяти займут 4 ГиБ из 16 ГиБ? " +
      "Напиши ответ знаком % и коротко поясни расчёт по-русски.", false, installedVersion);
    assert.match(answer, /\b25(?:[.,]0+)?\s*%/u);
    console.log("PASS", "Tess-27B", "short answer with a verified calculation");
  }
  assert.equal((await api("/api/profiles")).active_profile, profiles.active_profile);
  assert.deepEqual(pageErrors, []);
} finally {
  try {
    if (created) {
      await api(conversation + "/goal/stop", "POST", {}).catch(() => {});
      await api(conversation + "/pause", "POST", {}).catch(() => {});
      await api(conversation, "DELETE");
    }
  } finally {
    await browser?.close();
    await rm(dir, {recursive: true, force: true});
  }
}
