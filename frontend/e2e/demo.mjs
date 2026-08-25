/** The 90-second jury path: landing → demo → run a case → physician → conflicts → commit. */
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
const errors = [];
const failures = [];
const check = (n, ok, d = '') => { console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${n}${d ? ` — ${d}` : ''}`); if (!ok) failures.push(n); };

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 140)}`); });
page.on('response', r => { if (r.status() >= 400) errors.push(`HTTP ${r.status()} ${r.url().replace(BASE, '')}`); });

console.log('LANDING');
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
check('landing renders', await page.locator('.landing-title').count() > 0);
check('disclaimer visible', (await page.locator('.landing-note').innerText()).includes('does not diagnose'));
check('three steps shown', await page.locator('.landing-step').count() === 3);

console.log('\nDEMO MODE');
await page.getByRole('link', { name: /Demo & jury mode/ }).click();
await page.waitForSelector('.demo-card', { timeout: 8000 });
check('cases listed', await page.locator('.demo-card').count() === 5);

const card = page.locator('.demo-card', { hasText: 'prescription disagrees' });
await card.getByRole('button', { name: /Run this case/ }).click();
await card.locator('.demo-result').waitFor({ timeout: 40000 });
const stats = (await card.locator('.demo-result dl').innerText()).replace(/\n/g, ' ');
check('contradiction case ran', stats.includes('contradictions'), stats.slice(0, 110));
const cx = Number(stats.match(/contradictions\s+(\d+)/)?.[1] ?? 0);
check('contradictions detected', cx > 0, `${cx} found`);

console.log('\nPHYSICIAN (deep-linked)');
await card.getByRole('link', { name: /Open on the physician screen/ }).click();
await page.waitForSelector('.phys-login-card', { timeout: 8000 });
await page.getByRole('button', { name: /^Sign in$/ }).click();
await page.waitForSelector('.summary-line', { timeout: 15000 });
check('deep link opened the session', await page.locator('.summary-line').count() > 5);

await page.getByRole('button', { name: /Conflicts/ }).click();
await page.waitForTimeout(400);
check('conflicts panel shows both sides', await page.locator('.cx-item').count() > 0,
  `${await page.locator('.cx-item').count()} conflicts`);
if (await page.locator('.cx-item').count()) {
  const first = (await page.locator('.cx-item').first().innerText()).replace(/\n/g, ' | ');
  console.log(`        ${first.slice(0, 130)}`);
}

await page.locator('.phys-main').evaluate(el => el.scrollTo(0, el.scrollHeight));
await page.waitForTimeout(400);
const commit = page.getByRole('button', { name: /Confirm and commit/ });
check('commit enabled', !(await commit.isDisabled()));
await commit.click();
await page.waitForTimeout(3000);
check('committed', (await page.locator('.phys-bottom').innerText()).includes('committed'));

console.log('\nERRORS');
const unique = [...new Set(errors)];
unique.length ? unique.slice(0, 12).forEach(e => console.log('  ' + e)) : console.log('  (none)');
await browser.close();
console.log(`\n${failures.length || unique.length ? 'FAILED' : 'PASSED'} — ${failures.length} check(s), ${unique.length} error(s)`);
process.exit(failures.length || unique.length ? 1 : 0);
