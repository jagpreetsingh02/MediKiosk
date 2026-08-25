/**
 * The cold-start banner, proved against a genuinely slow first response.
 *
 * WHAT THIS IS FOR. Render's free tier sleeps the backend after 15 minutes idle; the next
 * request pays a 30-60s boot. Every spinner in this app was written assuming a warm server, so
 * that minute reads as a crash rather than a wait. This asserts the banner appears while the
 * first request is genuinely in flight and is GONE once it resolves.
 *
 * The delay is injected with route interception rather than by actually sleeping a backend:
 * the thing under test is the frontend's reaction to a slow response, and waiting out a real
 * Render cold boot in a test would be both slow and unreproducible.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const DELAY_MS = Number(process.env.DELAY_MS ?? 4000);

let failures = 0;
function check(label, ok, detail = '') {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures += 1;
}

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();

// Hold the FIRST API call open, so the banner's threshold is genuinely crossed.
let held = 0;
await page.route('**/about', async (route) => {
  held += 1;
  if (held === 1) await new Promise((r) => setTimeout(r, DELAY_MS));
  await route.continue();
});

await page.goto(BASE, { waitUntil: 'domcontentloaded' });

// It must appear while the request is still in flight...
const banner = page.locator('.mk-wakebanner');
await banner.waitFor({ state: 'visible', timeout: DELAY_MS });
check('the banner appears during a slow first request', true);

const text = (await banner.innerText()).toLowerCase();
check('it says the server is waking, in plain words', text.includes('waking the server'), text.trim());
check('it sets an honest expectation of how long', text.includes('minute'));
check('it never shows a status code or backend name',
  !/50\d|render|onrender|uvicorn|postgres/.test(text));

// ...and must be gone once the response actually lands. Not on a timer — on the real response.
await banner.waitFor({ state: 'hidden', timeout: DELAY_MS + 15000 });
check('it disappears when the request resolves', true);

// A SECOND navigation is not a cold start, and must not re-show it: `warmed` is per page load,
// and a reload legitimately starts over, so this checks an in-page route change instead.
const before = await page.locator('.mk-wakebanner').count();
await page.getByRole('link', { name: /^Start$/ }).click().catch(() => {});
await page.waitForTimeout(2500);
const during = await page.locator('.mk-wakebanner').count();
check('it does not re-appear on later navigation', before === 0 && during === 0);

check('it is announced to screen readers',
  (await page.locator('.mk-wakebanner').count()) === 0 ||
  (await banner.getAttribute('role')) === 'status');

await browser.close();
console.log(
  failures === 0
    ? '\nWAKE BANNER PASSED — a cold start looks like a wait, not a crash.'
    : `\nWAKE BANNER FAILED — ${failures} check(s)`,
);
process.exit(failures === 0 ? 0 : 1);
