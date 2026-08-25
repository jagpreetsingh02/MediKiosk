/**
 * What the patient sees when the backend is not there.
 *
 * This exists because it actually happened: the API was stopped, the dev server kept
 * serving the app, and the kiosk showed "Request failed". That is precisely the
 * console-like text the product rules forbid on a clinical screen — it tells a
 * patient nothing, and it tells them nothing in the vocabulary of a stack trace.
 *
 * Three separate faults produced it, and each one failed in its own way:
 *   - a dead API rejects `fetch` with a bare TypeError, which escaped uncaught;
 *   - a proxy error page is not JSON, so `JSON.parse` threw a SyntaxError;
 *   - an error response with no OperationOutcome fell back to "Request failed (500)".
 *
 * `node e2e/offline.mjs` with the frontend running. The backend may be up or down —
 * this suite blocks the API itself.
 */
/**
 * NAVIGATION WAITS ON THE DOM, NOT ON AN IDLE NETWORK.
 *
 * Every `goto` here used `waitUntil: 'networkidle'`. That stopped working the moment the
 * product grew a shared ambient background: the hero's video is a looping stream mounted for
 * the whole application, so there is always an open connection and the network is never idle.
 * The suite hung on the first navigation rather than failing on an assertion.
 *
 * `domcontentloaded` is the correct condition now, and it costs nothing in coverage: every
 * navigation below is already followed by an explicit `waitForSelector` for the thing being
 * tested, which is a stronger guarantee than "no requests for 500ms" ever was. The console
 * error and failed request listeners are untouched.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const failures = [];

const check = (name, ok, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
};

//: Anything that reads as a developer talking to another developer.
const JARGON =
  /Request failed|Failed to fetch|TypeError|SyntaxError|NetworkError|ECONNREFUSED|HTTP \d{3}|Traceback|\[object Object\]|\bundefined\b/i;

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

const uncaught = [];
page.on('pageerror', (e) => uncaught.push(e.message));

// The backend is unreachable. Not slow — gone.
await ctx.route('**/api/v1/**', (r) => r.abort('connectionrefused'));
await ctx.route('**/mock-idp/**', (r) => r.abort('connectionrefused'));

console.log('KIOSK WITH NO BACKEND');
await page.goto(`${BASE}/intake`, { waitUntil: 'domcontentloaded' });
await page.getByRole('button', { name: /^English/ }).click();
await page.waitForTimeout(1200);
await page.locator('button', { hasText: /Demo Patient/ }).first().click();
await page.waitForTimeout(2500);

const body = await page.locator('body').innerText();

check('the patient is told something in plain words', /cannot reach|ask a staff member/i.test(body));
check('no developer jargon on screen', !JARGON.test(body), JARGON.exec(body)?.[0] ?? '');
check('nothing escapes uncaught', uncaught.length === 0, uncaught[0] ?? '');
check('the screen still works', (await page.locator('button').count()) > 3);

// A 500 with no OperationOutcome must not surface its status code either.
await ctx.unroute('**/api/v1/**');
await ctx.route('**/api/v1/**', (r) =>
  r.fulfill({ status: 500, contentType: 'text/html', body: '<html>502 Bad Gateway</html>' }),
);
await page.reload({ waitUntil: 'domcontentloaded' });
await page.getByRole('button', { name: /^English/ }).click();
await page.waitForTimeout(1000);
await page.locator('button', { hasText: /Demo Patient/ }).first().click();
await page.waitForTimeout(2000);

const body2 = await page.locator('body').innerText();
check('an HTML error page does not leak either', !JARGON.test(body2), JARGON.exec(body2)?.[0] ?? '');
check('and it still says something useful', /went wrong|staff member|try again/i.test(body2));

await browser.close();

console.log('');
if (failures.length) {
  console.error(`OFFLINE SUITE FAILED — ${failures.length}: ${failures.join(', ')}`);
  process.exit(1);
}
console.log('OFFLINE SUITE PASSED — the patient never sees a stack trace.');
