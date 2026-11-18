// Opens every screen in Chrome, saves screenshots to docs/screenshots/, and walks the demo path:
// Overview -> "Laptops come after the start date" -> Chiara's case -> laptop step -> Proof -> Confirm -> Feedback page.
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

const shot = async (name, full = true) => {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(250);
  await page.screenshot({ path: `${OUT}${name}.png`, fullPage: full });
  console.log("saved", name);
};
const go = async (path, name) => { await page.goto(BASE + path); await shot(name); };

await go("/", "01-overview");
await go("/processes/leave", "02-process-leave");
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
await check("Open the laptop step proof", async () => {
  await laptopStep.getByRole("button", { name: "Proof" }).click();
  await laptopStep.getByText("read from the export, unchanged").waitFor({ timeout: 5000 });
  await laptopStep.locator("pre").first().waitFor();
});
await shot("14-demo-proof", false);
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

// narrower desktop
await page.setViewportSize({ width: 1024, height: 800 });
await go("/cases/" + encodeURIComponent("onboarding:chiara-ekwueme"), "16-case-chiara-1024");

console.log("\nDEMO PATH\n" + steps.join("\n"));
console.log("\nPROBLEMS\n" + (problems.length ? [...new Set(problems)].join("\n") : "none"));
await browser.close();
