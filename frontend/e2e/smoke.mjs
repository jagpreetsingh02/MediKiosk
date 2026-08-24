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

// The patient memory screen — the one that says MediKiosk already knows this person. It sits
// between login and consent, so the flow reaches consent through it, not instead of it.
// Wait for the record to arrive, not merely for the panel: the loading state is a
// .kiosk-lead too, and asserting against it raced the fetch.
await page.waitForSelector("button:has-text(\"Start today's visit\")", { timeout: 10000 });
check('patient memory screen reached', await page.locator('.memory-id').count() > 0);
await page.getByRole('button', { name: /Start today's visit/ }).click();

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

// §3: the flow branches, so a question count is a promise it cannot keep. Sections do not
// move; a denominator does.
{
  const rail = await page.locator('.progress-rail').innerText();
  check('progress is by section, not by question count', !/\d+\s*(of|\/)\s*\d+/.test(rail),
    rail.replace(/\n/g, ' ').slice(0, 58));
  check('and one section is marked as where we are',
    await page.locator('.progress-chip.current').count() === 1);
}

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

// The readback. An extraction the patient never saw is an extraction that became true
// without anyone agreeing to it, so the upload goes straight here.
await page.waitForSelector('.extract-row', { timeout: 25000 }).catch(() => {});
const extracted = await page.locator('.extract-row').count();
check('OCR readback shown to the patient', extracted > 0, `${extracted} items`);
check('every item carries a confidence word, not a percentage',
  extracted > 0 && !(await page.locator('.extract-band').first().innerText()).includes('%'));

if (extracted > 0) {
  await page.locator('.extract-row').first().getByRole('button', { name: /^Yes$/ }).click();
  await page.waitForTimeout(400);
  check('confirming an item is recorded', await page.locator('.extract-outcome').count() > 0);
  await page.getByRole('button', { name: /Looks right — continue|Continue — / }).click();
}

await page.waitForFunction(() => document.querySelectorAll('.upload-item').length > 0, null, { timeout: 15000 }).catch(() => {});
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

// A document-derived line must reach the page it came from, not only a box on an outline.
const docLine = doc.locator('.summary-line.traceable').filter({ hasText: /METFORMIN|AMLODIPINE|ATORVASTATIN|OMEPRAZOLE/i }).first();
if (await docLine.count()) {
  await docLine.click();
  await doc.waitForTimeout(300);
  const toOriginal = doc.locator('.phys-side').getByRole('button', { name: /Show the original page/ }).first();
  check('a document-derived claim offers its page', await toOriginal.count() > 0);
  if (await toOriginal.count()) {
    await toOriginal.click();
    await doc.waitForSelector('.evi-frame img', { timeout: 10000 }).catch(() => {});
    check('and the page opens with the region boxed',
      await doc.locator('.evi-box').count() > 0);
    await doc.getByRole('button', { name: /^Close/ }).click();
  }
}

await doc.locator('.phys-side').getByRole('button', { name: /Timeline/ }).click();
await doc.waitForTimeout(500);
check('timeline populated from the document', await doc.locator('.tl-event').count() > 0,
  `${await doc.locator('.tl-event').count()} events`);

// The longitudinal surface is asserted below, on the seeded returning patient. Here it
// is only checked to be present-or-absent honestly: this patient may have no record.
check('patient identity band shown', await doc.locator('.phys-patient').count() > 0);

await doc.locator('.phys-side').getByRole('button', { name: /Source/ }).click();
await doc.locator('.phys-main').evaluate(el => el.scrollTo(0, el.scrollHeight));
await doc.waitForTimeout(400);
const commit = doc.getByRole('button', { name: /Confirm and commit/ });
check('commit enabled after review', !(await commit.isDisabled()));
await commit.click();
await doc.waitForTimeout(3000);
check('commit succeeds', (await doc.locator('.phys-bottom').innerText()).includes('committed'));

// ------------------------------------------------- clinical memory, on a returning patient
//
// The patient above is a first visit by design — that path has to work too, and it is why
// the view nav is absent there. The longitudinal surface needs somebody with a record, so
// this runs the seeded demo patient through the recurrence case and reviews that.
console.log('\nCLINICAL MEMORY (returning patient)');
const api = ctx.request;
await api.post(`${BASE}/mock-idp/abha/request-otp`, { data: { abha_address: 'demo@abdm' } });
const verified = await (await api.post(`${BASE}/mock-idp/abha/verify-otp`,
  { data: { abha_address: 'demo@abdm', otp: '123456' } })).json();
const patientAuth = { Authorization: `Bearer ${verified.access_token}` };
const made = await (await api.post(`${BASE}/api/v1/sessions`, {
  headers: patientAuth,
  data: { language: 'en', consentScopes: ['history', 'voice', 'documents'], audioExplained: true },
})).json();
const loaded = await api.post(`${BASE}/api/v1/demo/cases/recurrence/load`,
  { headers: patientAuth, data: { sessionRef: made.sessionRef } });
check('recurrence demo case loads', loaded.ok());

const mem = await ctx.newPage();
track(mem, 'memory');
await mem.goto(`${BASE}/physician?session=${made.sessionRef}`, { waitUntil: 'networkidle' });
await mem.getByRole('button', { name: /^Sign in$/ }).click();
await mem.waitForSelector('.summary-line', { timeout: 15000 });

check('patient identity band names the record', await mem.locator('.phys-patient').count() > 0,
  (await mem.locator('.phys-patient').innerText().catch(() => '')).replace(/\n/g, ' ').slice(0, 70));
check('reconciliation surfaced across visits', await mem.locator('.phys-rec-row').count() > 0);
check('clinical memory nav present', await mem.locator('.phys-views').count() > 0);

check('today beside history', await mem.locator('.cvh-row').count() > 0,
  `${await mem.locator('.cvh-row').count()} features compared`);
check('shared features are ticked, not scored',
  await mem.locator('.cvh-value.shared').count() > 0 &&
  !(await mem.locator('.cvh').innerText()).includes('%'));

await mem.locator('.phys-views').getByRole('button', { name: /^Timeline/ }).click();
await mem.waitForTimeout(400);
check('longitudinal timeline spans prior visits', await mem.locator('.lt-row').count() > 0,
  `${await mem.locator('.lt-row').count()} events`);
check('timeline groups by year', await mem.locator('.lt-year-label').count() > 1,
  `${await mem.locator('.lt-year-label').count()} years`);

await mem.locator('.phys-views').getByRole('button', { name: /^Medications/ }).click();
await mem.waitForTimeout(400);
check('medication history threads a drug across visits',
  await mem.locator('.med-thread').count() > 0, `${await mem.locator('.med-thread').count()} drugs`);
check('every mention says how it is known', await mem.locator('.med-know').count() > 0);

await mem.locator('.phys-views').getByRole('button', { name: /^Similar visits/ }).click();
await mem.waitForTimeout(400);
check('similar visits list shared features', await mem.locator('.sim-shared li').count() > 0,
  `${await mem.locator('.sim-shared li').count()} shared features`);
check('no percentage anywhere in the similarity view',
  !(await mem.locator('.sim').innerText()).includes('%'));

await mem.locator('.phys-views').getByRole('button', { name: /^Documents/ }).click();
await mem.waitForTimeout(500);
const original = mem.locator('.lt-source').first();
if (await original.count()) {
  await original.click();
  await mem.waitForSelector('.evi', { timeout: 8000 }).catch(() => {});
  check('evidence drawer opens the original', await mem.locator('.evi-quote').count() > 0);

  // The page is fetched with the bearer token and wrapped as a blob, so it arrives after
  // the drawer does. Waiting for the <img> is the point of the check: §12 is explicit that
  // a box drawn on an empty rectangle is not evidence.
  await mem.waitForSelector('.evi-frame img', { timeout: 10000 }).catch(() => {});
  const drawn = await mem.locator('.evi-frame img').evaluate(
    (img) => img.complete && img.naturalWidth > 0,
  ).catch(() => false);
  check('and the page image actually renders', drawn);
  check('with the OCR region boxed on it', await mem.locator('.evi-box').count() > 0);
  await mem.getByRole('button', { name: /^Close/ }).click();
} else {
  check('evidence drawer reachable from a document', false, 'no document rows');
}

// ---------------------------------------------------------------- report
console.log('\nERRORS');
const unique = [...new Set(errors)];
if (!unique.length) console.log('  (none)');
unique.slice(0, 20).forEach(e => console.log('  ' + e));

await browser.close();
const bad = failures.length || unique.length;
console.log(`\n${bad ? 'SMOKE FAILED' : 'SMOKE PASSED'} — ${failures.length} check failure(s), ${unique.length} runtime error(s)`);
process.exit(bad ? 1 : 0);
