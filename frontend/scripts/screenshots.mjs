// Opens every screen in Chrome, saves screenshots to docs/screenshots/, and walks the demo path:
// Overview -> "Laptops come after the start date" -> Chiara's case -> laptop step -> Proof -> Confirm -> Feedback page.
// Every screen is shot at 1440px (docs/screenshots/) and 1024px (docs/screenshots/1024/) and run through a layout audit.
// Usage: BASE=http://localhost:5174 CHROME=/usr/bin/google-chrome node scripts/screenshots.mjs
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const BASE = process.env.BASE ?? "http://localhost:5174";
const OUT = fileURLToPath(new URL("../../docs/screenshots/", import.meta.url));
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ executablePath: process.env.CHROME ?? "/usr/bin/google-chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const problems = [];
page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("response", (r) => r.status() >= 400 && problems.push(`HTTP ${r.status()} ${r.url()}`));

// Layout audit run on every screen: text under 12px, text cut off sideways, badges that overflow,
// cards in one grid row with different heights. Line-clamped text (intentional) is not reported.
const audit = () => page.evaluate(() => {
  const out = [];
  const label = (el) => (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 50);
  const visible = (el) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
  for (const el of document.querySelectorAll("main *, aside *, header *")) {
    if (!visible(el)) continue;
    const cs = getComputedStyle(el);
    const ownText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (ownText && parseFloat(cs.fontSize) < 12) out.push(`font ${cs.fontSize}: "${label(el)}"`);
    const clamped = cs.webkitLineClamp && cs.webkitLineClamp !== "none";
    const clipsX = cs.overflowX === "hidden" || cs.textOverflow === "ellipsis";
    if (clipsX && !clamped && el.scrollWidth > el.clientWidth + 1 && ownText) out.push(`cut off: "${label(el)}"`);
    if (el.matches("span.h-6.whitespace-nowrap") && el.scrollWidth > el.clientWidth + 1) out.push(`badge overflow: "${label(el)}"`);
  }
  if (document.documentElement.scrollWidth > innerWidth) out.push(`page scrolls sideways (${document.documentElement.scrollWidth}px > ${innerWidth}px)`);
  for (const box of document.querySelectorAll("main .rounded-lg.border")) {
    if (!visible(box)) continue;
    const r = box.getBoundingClientRect();
    for (const el of box.querySelectorAll("*")) {
      if (!visible(el) || el.closest(".overflow-x-auto, .overflow-auto") !== box.closest(".overflow-x-auto, .overflow-auto")) continue;
      const e = el.getBoundingClientRect();
      if (e.width && e.right > r.right + 1) { out.push(`spills out of its card: "${label(el)}"`); break; }
    }
  }
  for (const grid of document.querySelectorAll("main .grid")) {
    const rows = {};
    for (const c of grid.children) if (visible(c)) (rows[Math.round(c.getBoundingClientRect().top)] ??= []).push(c);
    const card = (c) => (c.matches(".rounded-lg.border") ? c : c.firstElementChild?.matches(".rounded-lg.border") ? c.firstElementChild : null);
    for (const r of Object.values(rows)) {
      if (!r.every(card)) continue; // only rows made of cards (not e.g. timeline + sidebar columns)
      const hs = r.map((c) => Math.round(card(c).getBoundingClientRect().height));
      if (r.length > 1 && Math.max(...hs) - Math.min(...hs) > 1) out.push(`uneven row heights ${hs.join("/")}: "${label(grid).slice(0, 30)}"`);
    }
  }
  return [...new Set(out)];
});
const findings = {};
let dir = OUT;
const shot = async (name, full = true) => {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(250);
  await page.screenshot({ path: `${dir}${name}.png`, fullPage: full });
  const f = await audit();
  if (f.length) findings[`${dir === OUT ? "1440" : "1024"} ${name}`] = f;
  console.log("saved", dir === OUT ? "1440" : "1024", name);
};
const go = async (path, name) => { await page.goto(BASE + path); await shot(name); };

const screens = async () => {
  await go("/", "01-overview");
  await go("/processes/leave", "02-process-leave");
  if (dir === OUT) { // README: just the process map card
    await page.getByText("Process map", { exact: true }).locator("xpath=ancestor::div[contains(@class,'rounded-lg')][1]").screenshot({ path: `${OUT}16-process-map.png` });
    console.log("saved 16-process-map");
  }
  await go("/processes/offboarding", "03-process-offboarding");
  await go("/processes/onboarding", "04-process-onboarding");
  await page.getByRole("button", { name: /Laptop requested/ }).first().click();
  await page.getByText("Example evidence").waitFor();
  await page.waitForTimeout(600);
  await shot("05-process-step-panel", false);
  await page.keyboard.press("Escape");
  await go("/cases", "06-cases");
  await go("/cases?process=onboarding&flagged=yes", "07-cases-filtered");
  await go("/cases/" + encodeURIComponent("offboarding:bram-montague"), "08-case-bram-montague");
  await go("/cases/" + encodeURIComponent("onboarding:vida-faraday"), "09-case-vida-handoff");
  await go("/cases/" + encodeURIComponent("onboarding:luca-bellweather-personal"), "10-case-same-person");
  await go("/insights", "11-insights");
  await go("/questions", "12-questions");
  await go("/how-it-works", "13-how-it-works");
};
await screens();

// ---- demo path
const steps = [];
const check = async (label, fn) => {
  try { await fn(); steps.push(`ok   ${label}`); } catch (e) { steps.push(`FAIL ${label}: ${e.message.split("\n")[0]}`); }
};
await page.goto(BASE + "/");
await check("Overview shows the laptop insight", () => page.getByRole("link", { name: /Laptops come after the start date/ }).waitFor({ timeout: 5000 }));
await check("Click insight -> Insights page", async () => {
  await page.getByRole("link", { name: /Laptops come after the start date/ }).click();
  await page.waitForURL(/\/insights#/);
});
await check("Click Chiara -> case page", async () => {
  await page.locator(`[id="ins:onboarding:laptop_late"]`).getByRole("link", { name: "Chiara Ekwueme" }).click();
  await page.waitForURL(/onboarding%3Achiara-ekwueme/);
  await page.getByRole("heading", { name: "Chiara Ekwueme" }).waitFor();
});
const laptopStep = page.locator("li", { has: page.getByText("Laptop delivered", { exact: true }) }).last();
await check("One-off step shows a 'by' tag, not a handoff", async () => {
  await page.getByText("by Lerato Faraday").first().waitFor({ timeout: 5000 });
  if (await page.getByText(/^Handoff:/).count()) throw new Error("unexpected handoff marker on Chiara's case");
});
await check("Open the laptop step proof", async () => {
  await laptopStep.getByRole("button", { name: "Proof" }).click();
  await laptopStep.getByText("read from the export, unchanged").waitFor({ timeout: 5000 });
  await laptopStep.locator("pre").first().waitFor();
});
await shot("14-demo-proof", false);
await laptopStep.screenshot({ path: `${OUT}17-case-proof.png` }); // README: one step with its raw record
console.log("saved 17-case-proof");
await check("Confirm the laptop step -> toast Saved", async () => {
  await laptopStep.getByRole("button", { name: "Confirm" }).first().click();
  await page.getByText("Saved").waitFor({ timeout: 5000 });
  await laptopStep.getByText(/Confirmed by/).waitFor();
});
await check("Feedback page shows it", async () => {
  await page.getByRole("link", { name: /^Feedback/ }).click();
  await page.waitForURL(/\/feedback$/);
  await page.getByRole("cell", { name: /Chiara Ekwueme · Laptop delivered/ }).first().waitFor({ timeout: 5000 });
});
await shot("15-feedback");
await check("Waiting-for-review count went down", async () => {
  await page.getByRole("link", { name: "Overview" }).click();
  await page.getByText("1 reviewed so far").waitFor({ timeout: 5000 });
});

await check("Vida's case shows the real handoff", async () => {
  await page.goto(BASE + "/cases/" + encodeURIComponent("onboarding:vida-faraday"));
  await page.getByText("Handoff: Hana Pemberton → Lerato Faraday").waitFor({ timeout: 5000 });
});
await check("How it works links open out/ files", async () => {
  await page.goto(BASE + "/how-it-works");
  const href = await page.getByRole("link", { name: "out/3_cases.json" }).getAttribute("href");
  const r = await page.request.get(BASE + href);
  if (r.status() !== 200 || !(await r.json()).cases) throw new Error(`files endpoint ${r.status()}`);
});

// narrower desktop: every screen again at 1024px into docs/screenshots/1024/ (feedback now has the demo entry)
dir = `${OUT}1024/`;
mkdirSync(dir, { recursive: true });
await page.setViewportSize({ width: 1024, height: 800 });
await screens();
await page.goto(BASE + "/cases/" + encodeURIComponent("onboarding:chiara-ekwueme"));
const laptop1024 = page.locator("li", { has: page.getByText("Laptop delivered", { exact: true }) }).last();
await laptop1024.getByRole("button", { name: "Proof" }).click();
await laptop1024.locator("pre").first().waitFor();
await shot("14-demo-proof", false);
await go("/feedback", "15-feedback");

console.log("\nDEMO PATH\n" + steps.join("\n"));
console.log("\nLAYOUT AUDIT\n" + (Object.keys(findings).length ? Object.entries(findings).map(([k, v]) => `${k}\n  ${v.join("\n  ")}`).join("\n") : "none"));
console.log("\nPROBLEMS\n" + (problems.length ? [...new Set(problems)].join("\n") : "none"));
await browser.close();
