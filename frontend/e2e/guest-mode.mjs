/**
 * Guest mode, in a real browser: one button, no account, badge everywhere, reset restores.
 *
 * The reset assertion is the one that matters operationally. A demo is run repeatedly in
 * front of people, and the failure mode is the SECOND run starting from the first run's
 * leftovers — which looks like a working demo right up to the point where a judge asks why
 * there are two identical prescriptions.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const SHOT = process.env.SHOT;

let failures = 0;
const check = (l, ok, d = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${l}${d ? ` — ${d}` : ''}`);
  if (!ok) failures += 1;
};

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1500, height: 1000 } })).newPage();
const errs = [];
page.on('pageerror', (e) => errs.push(String(e)));
page.on('console', (m) => m.type() === 'error' && errs.push(m.text()));

console.log('\n── 1. ONE BUTTON, NO ACCOUNT ─────────────────────────────');
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.hx-cta-secondary', { timeout: 60000 });
check('the hero offers Try demo', true, await page.locator('.hx-cta-secondary').innerText());

// Nothing may be asked for. No form, no ABHA field, no personal detail.
const before = await page.locator('input, select').count();
check('no field is presented before starting', before === 0, `${before} inputs on the hero`);

await page.locator('.hx-cta-secondary').click();
console.log('     … building the synthetic record (real OCR + real ASR, give it time)');
await page.waitForSelector('[data-testid="demo-badge"]', { timeout: 180000 });
check('a demo session started with no account', true);

const ref = await page.evaluate(() => JSON.parse(sessionStorage.getItem('medikiosk.guest') ?? '{}').patientRef);
console.log(`     PATIENT_REF=${ref}`);
check('the record is marked as a guest record', ref.startsWith('pat_guest_'), ref);

console.log('\n── 2. THE BADGE IS ON EVERY SCREEN ───────────────────────');
const badgeText = (await page.locator('[data-testid="demo-badge"]').innerText()).toLowerCase();
check('it says demo and synthetic', badgeText.includes('demo') && badgeText.includes('synthetic'),
  badgeText.split('\n')[1] ?? badgeText.split('\n')[0]);

for (const route of ['/', '/intake', '/physician', '/demo', `/brief?patient=${ref}`,
                     `/brief?patient=${ref}&as=patient`]) {
  await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(900);
  const shown = await page.locator('[data-testid="demo-badge"]').count();
  check(`  badge present on ${route}`, shown === 1);
}
if (SHOT) await page.screenshot({ path: `${SHOT}/G4-badge.png` });

console.log('\n── 3. THE SEEDED HISTORY IS REALLY THERE ─────────────────');
await page.goto(`${BASE}/brief?patient=${ref}`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(700);
const signIn = page.getByRole('button', { name: /Continue as clinician/ });
if (await signIn.count()) await signIn.click();
await page.waitForSelector('.bx-section[aria-label="Current clinical snapshot"]', { timeout: 90000 });

const wc = page.locator('.bx-section[aria-label="What changed?"]');
check('What changed? has a prior encounter to compare against',
  (await wc.locator('.bx-comparedwith').count()) === 1,
  (await wc.locator('.bx-comparedwith').innerText().catch(() => 'absent')).replace(/\n/g, ' '));
const persisting = await wc.locator('.bx-changed__col[data-kind="persisting"] li').count();
check('  and a populated diff', persisting > 0, `persisting=${persisting}`);

const series = await page.locator('.bx-series').count();
check('the lab trajectory has something to chart', series > 0, `${series} analytes`);

const mods = await page.locator('.bx-line[data-modality]').evaluateAll(
  (els) => [...new Set(els.map((e) => e.dataset.modality))]);
check('all four evidence types are present in the demo record',
  ['document', 'voice', 'touch', 'typed'].every((m) => mods.includes(m)), mods.join(', '));
if (SHOT) await page.screenshot({ path: `${SHOT}/G4-brief.png`, fullPage: true });

console.log('\n── 4. RESET RESTORES THE EXACT STARTING STATE ────────────');
// Record the shape before, straight from the API, so the comparison is on data not pixels.
const shapeOf = async (r) => page.evaluate(async (pr) => {
  const t = sessionStorage.getItem('medikiosk.token');
  const res = await fetch(`/api/v1/patients/${pr}/brief`, { headers: { Authorization: `Bearer ${t}` } });
  const b = await res.json();
  return {
    encounters: b.header.encounterCount,
    snapshot: b.snapshot.items.length,
    meds: b.medications.items.length,
    series: b.observations.series.length,
    timeline: b.timeline.items.length,
    persisting: b.whatChanged.persisting.length,
  };
}, r);
const shapeBefore = await shapeOf(ref);
console.log('     before:', JSON.stringify(shapeBefore));

await page.locator('.mk-demobadge__btn').first().click();
await page.getByRole('button', { name: /Yes, reset/ }).click();
console.log('     … rebuilding');
await page.waitForFunction(
  (old) => JSON.parse(sessionStorage.getItem('medikiosk.guest') ?? '{}').patientRef !== old,
  ref, { timeout: 180000 });
const newRef = await page.evaluate(() => JSON.parse(sessionStorage.getItem('medikiosk.guest') ?? '{}').patientRef);
check('reset produced a fresh record', newRef !== ref && newRef.startsWith('pat_guest_'), `${ref} -> ${newRef}`);

await page.goto(`${BASE}/brief?patient=${newRef}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.bx-section[aria-label="Current clinical snapshot"]', { timeout: 90000 });
const shapeAfter = await shapeOf(newRef);
console.log('     after :', JSON.stringify(shapeAfter));
check('the starting state is IDENTICAL, not merely similar',
  JSON.stringify(shapeBefore) === JSON.stringify(shapeAfter));

check('no console errors anywhere in demo mode', errs.length === 0, errs[0] ?? '');
await browser.close();
console.log(failures === 0
  ? '\nGUEST MODE PASSED — one button, badged everywhere, reset restores exactly.'
  : `\nGUEST MODE FAILED — ${failures} check(s)`);
process.exit(failures === 0 ? 0 : 1);
