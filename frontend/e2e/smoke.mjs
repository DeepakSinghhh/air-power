// End-to-end smoke test of the ops room against a running server (default http://127.0.0.1:8000).
//   npm run e2e              (server must be running: `make serve`)
// Checks sign-in, role gating, filing a snag, approving a plan and actioning its order, importing a
// HUMS download through the data fabric, every board in day and night with zero console errors, and no
// sideways scrolling at phone width. Imports made by the test are removed at the end.
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const BASE = process.env.TATPAR_URL || "http://127.0.0.1:8000";
const SAMPLE = (name) => fileURLToPath(new URL(`../../data/samples/${name}`, import.meta.url));
const BOARDS = ["/", "/planner", "/flow", "/aircraft/HF-114", "/sustainment", "/loss", "/snags", "/proof"];
const fails = [];
const ok = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"}  ${msg}`); if (!cond) fails.push(msg); };
const seen = (loc, timeout = 10000) => loc.first().waitFor({ state: "visible", timeout }).then(() => true, () => false);

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});

async function session(viewport = { width: 1440, height: 900 }) {
  const ctx = await browser.newContext({ viewport });
  const page = await ctx.newPage();
  const errors = [];
  page.on("console", (m) => m.type() === "error" && !/401|403/.test(m.text()) && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  return { ctx, page, errors };
}

async function signIn(page, role, pin) {
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  await page.locator(`[role=radio]:has-text("${role}")`).first().click();
  await page.locator("input[aria-label=PIN]").fill(pin);
  await page.locator("button:has-text('SIGN IN')").click();
  await page.locator(".strip .tabs").waitFor({ state: "attached", timeout: 15000 });
  await page.locator(".boardhead h1").waitFor({ timeout: 20000 });
}

// 1 · sign-in gate and wrong PIN
{
  const { ctx, page } = await session();
  await page.goto(BASE + "/planner", { waitUntil: "networkidle" });
  ok(await seen(page.locator("form[aria-label='Sign in']")), "unauthenticated user sees only the sign-in screen");
  await page.locator("input[aria-label=PIN]").fill("0000");
  await page.locator("button:has-text('SIGN IN')").click();
  ok(await seen(page.locator("text=WRONG ID OR PIN"), 5000), "wrong PIN is refused");
  await ctx.close();
}

// 2 · SENGO: can release the signal and file a snag, cannot approve a readiness plan
{
  const { ctx, page, errors } = await session();
  await signIn(page, "SENGO", "2602");
  await page.locator("button:has-text('RELEASE AS SENGO')").click();
  ok(await seen(page.locator(".stamp:has-text('RELEASED')"), 8000), "SENGO releases the daily signal (stamp shown)");
  await page.goto(BASE + "/planner", { waitUntil: "networkidle" });
  ok(await seen(page.locator("text=ONLY STN CDR MAY APPROVE"), 15000), "SENGO is not offered plan approval");
  await page.goto(BASE + "/snags", { waitUntil: "networkidle" });
  await page.locator("button:has-text('FILE ENTRY')").click();
  ok(await seen(page.locator(".stamp:has-text('FILED TL-')"), 10000), "SENGO files a tech-log entry");
  ok(errors.length === 0, `no console errors as SENGO (${errors.join(" | ")})`);
  await ctx.close();
}

// 3 · STN CDR approves the plan → orders issued; LOG OFFR actions a transfer order
{
  const { ctx, page } = await session();
  await signIn(page, "STN CDR", "2601");
  await page.goto(BASE + "/planner", { waitUntil: "networkidle" });
  await page.locator("button:has-text('APPROVE AS STN CDR')").click();
  ok(await seen(page.locator(".stamp:has-text('ORDERS ISSUED')"), 8000), "STN CDR approval issues orders");
  await ctx.close();
  const s2 = await session();
  await signIn(s2.page, "LOG OFFR", "2603");
  await s2.page.goto(BASE + "/planner", { waitUntil: "networkidle" });
  const row = s2.page.locator("tr:has-text('MOVE'):has(button:has-text('ACTIONED'))").first();
  await row.locator("button:has-text('ACTIONED')").click();
  ok(await seen(s2.page.locator(".stamp:has-text('ACTIONED')"), 8000), "LOG OFFR marks a transfer order actioned");
  await s2.ctx.close();
}

// 4 · data fabric: SENGO imports a HUMS download; the engine's record shows it; AUDITOR cannot import
{
  const { ctx, page, errors } = await session();
  await signIn(page, "SENGO", "2602");
  await page.goto(BASE + "/proof", { waitUntil: "networkidle" });
  await page.locator("[role=tab]:has-text('HUMS')").click();
  await page.locator("input[aria-label='Choose CSV']").setInputFiles(SAMPLE("hums_sample.csv"));
  ok(await seen(page.locator(".stamp:has-text('ACCEPTED')"), 20000), "HUMS download passes its data contract");
  await page.locator("button:has-text('IMPORT')").first().click();
  ok(await seen(page.locator(".stamp:has-text('IMPORTED')"), 30000), "SENGO imports the HUMS download (ledger entry)");
  const tail = (await page.locator("a:has-text('OPEN ')").first().textContent()).match(/[HL]F-\d{3}/)[0];
  await page.goto(BASE + `/aircraft/${tail}`, { waitUntil: "networkidle" });
  ok(await seen(page.locator(".stamp:has-text('UPDATED FROM HUMS DOWNLOAD')"), 20000), `${tail}'s engine record uses the download`);
  ok(errors.length === 0, `no console errors while importing (${errors.join(" | ")})`);
  await ctx.close();
  const s2 = await session();
  await signIn(s2.page, "AUDITOR", "2605");
  await s2.page.goto(BASE + "/proof", { waitUntil: "networkidle" });
  await s2.page.locator("[role=tab]:has-text('STOCK')").click();
  await s2.page.locator("input[aria-label='Choose CSV']").setInputFiles(SAMPLE("stock_sample.csv"));
  ok(await seen(s2.page.locator("text=NEEDS A DIFFERENT AUTHORITY"), 20000), "AUDITOR can validate but is not offered the import");
  await s2.ctx.close();
}

// 5 · every board, day and night, no console errors
for (const theme of ["light", "dark"]) {
  const { ctx, page, errors } = await session();
  await signIn(page, "AUDITOR", "2605");
  await page.evaluate((t) => localStorage.setItem("tatpar-theme", t), theme);
  for (const b of BOARDS) {
    await page.goto(BASE + b, { waitUntil: "networkidle" });
    await page.locator(".boardhead h1").waitFor({ timeout: 20000 });
  }
  ok(errors.length === 0, `all 8 boards render in ${theme} with no console errors (${errors.join(" | ")})`);
  await ctx.close();
}

// 6 · phone width: no sideways scrolling
{
  const { ctx, page } = await session({ width: 390, height: 844 });
  await signIn(page, "STN CDR", "2601");
  for (const b of BOARDS) {
    await page.goto(BASE + b, { waitUntil: "networkidle" });
    await page.locator(".boardhead h1").waitFor({ timeout: 20000 });
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(over <= 1, `no horizontal page scroll at 390 px on ${b} (overflow ${over}px)`);
  }
  await ctx.close();
}

// leave the server as we found it: remove the test's imports
{
  const tok = await (await fetch(BASE + "/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: "stncdr", pin: "2601" }) })).json();
  const r = await fetch(BASE + "/api/ingest/reset", { method: "POST", headers: { Authorization: `Bearer ${tok.token}` } });
  ok(r.ok, "test imports removed");
}

await browser.close();
console.log(fails.length ? `\n${fails.length} FAILED` : "\nALL PASSED");
process.exit(fails.length ? 1 : 0);
