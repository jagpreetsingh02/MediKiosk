/**
 * End-to-end smoke test. `node e2e/smoke.mjs` with the stack running (`make demo`).
 *
 * This exists because the unit tests cannot see a CSS grid place the clinical summary in the
 * wrong column, and that is exactly the class of bug that makes a demo look broken while
 * every test passes. It walks both surfaces and fails on any console error, failed request,
 * or missing element.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const failures = [];
const errors = [];

const check = (name, ok, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
};

const track = (p, tag) => {
  p.on('pageerror', e => errors.push(`${tag} pageerror: ${e.message}`));
  p.on('console', m => { if (m.type() === 'error') errors.push(`${tag} console: ${m.text().slice(0, 140)}`); });
  p.on('response', r => {
    if (r.status() >= 400) errors.push(`${tag} HTTP ${r.status()} ${r.request().method()} ${r.url().replace(BASE, '')}`);
  });
};

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });

// ---------------------------------------------------------------- kiosk
console.log('KIOSK');
const page = await ctx.newPage();
track(page, 'kiosk');
await page.goto(BASE, { waitUntil: 'networkidle' });
check('landing renders', await page.locator('.landing-title').count() > 0);
await page.getByRole('link', { name: /^Start$/ }).click();
await page.waitForSelector('.language-option', { timeout: 8000 });

await page.getByRole('button', { name: /^English/ }).click();
check('language picker advances', await page.locator('text=Your ABHA number').count() > 0);

await page.getByRole('button', { name: /Kamala Devi/ }).click();
await page.getByRole('button', { name: /Fill demo code/ }).click();
await page.getByRole('button', { name: /^Continue$/ }).click();
await page.waitForSelector('text=Before we begin', { timeout: 8000 });
check('consent screen reached', true);

for (let i = 0; i < 6; i++) {
  const off = page.locator('.consent-toggle:not(.on):not([disabled])');
  if (!(await off.count())) break;
  await off.first().click();
}
await page.getByRole('button', { name: /I agree — start/ }).click();
await page.waitForSelector('.kiosk-prompt', { timeout: 12000 });
const sessionRef = (await page.locator('.kiosk-top').innerText()).match(/sess_\w+/)?.[0];
check('interview started', Boolean(sessionRef), sessionRef);
check('microphone offered when voice consented', await page.locator('.voice-button').count() > 0);

// A dead speech engine must withdraw the microphone rather than pulse "Listening…" forever.
// Chromium (and Brave, Electron, most kiosk browsers) construct webkitSpeechRecognition
// successfully and then never call back — this is the exact failure that watchdog covers.
if (await page.locator('.voice-button').count()) {
  await page.getByRole('button', { name: /Speak my answer/ }).click();
  await page.waitForTimeout(7500);
  check('dead speech engine withdraws the microphone', await page.locator('.voice-button').count() === 0);
  check('and tells the patient why',
    (await page.locator('.kiosk-error').first().innerText()).includes('not available'));
  check('and tapping still works', await page.locator('.tap-option').count() > 0);
}

let asked = 0;
for (; asked < 90; asked++) {
  if (await page.locator('.upload-drop').count()) break;
  if (!(await page.locator('.kiosk-prompt').count())) break;
  if (await page.locator('.face-option').count()) {
    await page.locator('.face-option').nth(3).click();
  } else if (await page.locator('.tap-option').count()) {
    await page.locator('.tap-option').first().click();
    const cont = page.getByRole('button', { name: /^Continue$|^Continue with/ });
    if (await cont.count()) await cont.first().click();
  } else {
    const box = page.locator('.typed-answer textarea').first();
    if (!(await box.count())) break;
    await box.fill('free text answer');
    await page.getByRole('button', { name: /Send what I typed/ }).click();
  }
  await page.waitForTimeout(140);
}
check('interview completes', asked > 20, `${asked} questions`);

// A kiosk browser reloads. Losing the sessionRef used to send the patient back to the
// language picker with their answers apparently gone.
{
  const beforeReload = await page.locator('.upload-drop').count();
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  const stillHere =
    (await page.locator('.upload-drop').count()) > 0 ||
    (await page.locator('.kiosk-prompt').count()) > 0 ||
    (await page.locator('.review-row').count()) > 0;
  check('refresh resumes the session', stillHere,
    beforeReload ? 'was at the document step' : 'was mid-interview');
  if (!(await page.locator('.upload-drop').count())) {
    await page.waitForSelector('.upload-drop', { timeout: 15000 }).catch(() => {});
  }
}
check('document stage offered', await page.locator('.upload-drop').count() > 0);

await page.locator('input[type=file]').setInputFiles('../data/fixtures/documents/prescription.pdf');
await page.waitForFunction(() => document.querySelectorAll('.upload-item').length > 0, null, { timeout: 25000 }).catch(() => {});
check('document uploaded and read', await page.locator('.upload-item').count() > 0);

await page.getByRole('button', { name: /Done — continue|I have no papers/ }).click();
await page.waitForSelector('.review-row', { timeout: 10000 });
check('patient review screen reached', await page.locator('.review-row').count() > 5,
  `${await page.locator('.review-row').count()} answers read back`);

// Correcting one answer must re-present that question and return to review, not restart.
const firstQuestion = await page.locator('.review-row .review-q').first().innerText();
await page.locator('.review-row').first().getByRole('button', { name: /Change this/ }).click();
await page.waitForSelector('.kiosk-prompt', { timeout: 8000 });
check('correction re-presents that question',
  (await page.locator('.kiosk-prompt').innerText()).trim() === firstQuestion.trim(),
  firstQuestion.slice(0, 46));
if (await page.locator('.tap-option').count()) {
  await page.locator('.tap-option').nth(1).click();
  const cont = page.getByRole('button', { name: /^Continue$|^Continue with/ });
  if (await cont.count()) await cont.first().click();
} else {
  await page.locator('.typed-answer textarea').first().fill('corrected answer');
  await page.getByRole('button', { name: /Send what I typed/ }).click();
}
await page.waitForSelector('.review-row', { timeout: 10000 });
check('correction returns to review, not to documents', await page.locator('.review-row').count() > 5);

await page.getByRole('button', { name: /Yes, this is right/ }).click();
await page.waitForSelector('text=What happens now', { timeout: 8000 });
check('done screen reached', true);

// ---------------------------------------------------------------- physician
console.log('\nPHYSICIAN');
const doc = await ctx.newPage();
track(doc, 'physician');
await doc.goto(`${BASE}/physician`, { waitUntil: 'networkidle' });
await doc.getByRole('button', { name: /^Sign in$/ }).click();
await doc.waitForSelector('.queue-item', { timeout: 10000 });
check('queue loads', await doc.locator('.queue-item').count() > 0);

await doc.locator('.queue-item', { hasText: sessionRef }).first().click();
await doc.waitForSelector('.summary-line', { timeout: 12000 });
check('summary renders', await doc.locator('.summary-line').count() > 5);

// Layout: the clinical summary must be in the centre column, not the right rail.
const layout = await doc.evaluate(() => {
  const main = document.querySelector('.phys-main')?.getBoundingClientRect();
  const side = document.querySelector('.phys-side')?.getBoundingClientRect();
  return main && side ? { mainX: main.x, mainW: main.width, sideX: side.x, sideW: side.width } : null;
});
check('summary is the widest, centre column', Boolean(layout) && layout.mainX < layout.sideX && layout.mainW > layout.sideW,
  layout ? `main ${Math.round(layout.mainW)}px @${Math.round(layout.mainX)}, side ${Math.round(layout.sideW)}px @${Math.round(layout.sideX)}` : 'not found');
check('escalation shown once', await doc.locator('.flag-banner').count() === 1);

await doc.locator('.summary-line.traceable').first().click();
await doc.waitForSelector('.source-verbatim', { timeout: 6000 });
check('click-to-source resolves', (await doc.locator('.source-verbatim').first().innerText()).length > 2);

await doc.getByRole('button', { name: /Timeline/ }).click();
await doc.waitForTimeout(500);
check('timeline populated from the document', await doc.locator('.tl-event').count() > 0,
  `${await doc.locator('.tl-event').count()} events`);

await doc.getByRole('button', { name: /Source/ }).click();
await doc.locator('.phys-main').evaluate(el => el.scrollTo(0, el.scrollHeight));
await doc.waitForTimeout(400);
const commit = doc.getByRole('button', { name: /Confirm and commit/ });
check('commit enabled after review', !(await commit.isDisabled()));
await commit.click();
await doc.waitForTimeout(3000);
check('commit succeeds', (await doc.locator('.phys-bottom').innerText()).includes('committed'));

// ---------------------------------------------------------------- report
console.log('\nERRORS');
const unique = [...new Set(errors)];
if (!unique.length) console.log('  (none)');
unique.slice(0, 20).forEach(e => console.log('  ' + e));

await browser.close();
const bad = failures.length || unique.length;
console.log(`\n${bad ? 'SMOKE FAILED' : 'SMOKE PASSED'} — ${failures.length} check failure(s), ${unique.length} runtime error(s)`);
process.exit(bad ? 1 : 0);
