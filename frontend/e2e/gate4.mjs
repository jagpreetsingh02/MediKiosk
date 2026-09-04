/**
 * GATE 4, local, real browser: a guest session start to finish, both PDFs, and a reset.
 *
 *   localhost:5173  →  localhost:8000  →  local demo Postgres (DEMO_LOCAL_DB=true)
 *
 * The PDFs are DOWNLOADED as real files and read back off disk — the text is extracted and
 * asserted, because "a PDF appeared" is exactly what a screenshot-based renderer would also
 * achieve. Production is frozen and untouched.
 */
import { chromium } from 'playwright';
import { readFileSync, mkdirSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const DL = process.env.DL ?? '/tmp/gate4-downloads';
const PY = process.env.PY ?? 'python3';
const SHOT = process.env.SHOT;

let failures = 0;
const check = (l, ok, d = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${l}${d ? ` — ${d}` : ''}`);
  if (!ok) failures += 1;
};

rmSync(DL, { recursive: true, force: true });
mkdirSync(DL, { recursive: true });

/** Extract text per page, so "on every page" can be asserted rather than assumed. */
function pdfPages(path) {
  const out = execFileSync(PY, ['-c', `
import json,sys
from pypdf import PdfReader
r=PdfReader(sys.argv[1])
print(json.dumps([p.extract_text() or "" for p in r.pages]))
`, path], { encoding: 'utf8' });
  return JSON.parse(out);
}

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1500, height: 1000 }, acceptDownloads: true });
const page = await context.newPage();
const errs = [];
page.on('pageerror', (e) => errs.push(String(e)));
page.on('console', (m) => m.type() === 'error' && errs.push(m.text()));

// ── 1. a guest session, with no account ────────────────────────────────────
console.log('\n── 1. GUEST SESSION, NO ACCOUNT ──────────────────────────');
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.hx-cta-secondary', { timeout: 60000 });
check('no field is asked for before starting', (await page.locator('input, select').count()) === 0);
await page.locator('.hx-cta-secondary').click();
console.log('     … building the record (real OCR + real ASR)');
await page.waitForSelector('[data-testid="demo-badge"]', { timeout: 180000 });
const ref = await page.evaluate(() => JSON.parse(sessionStorage.getItem('medikiosk.guest') ?? '{}').patientRef);
check('a demo record exists', ref.startsWith('pat_guest_'), ref);

// ── 2. the whole path is reachable in guest mode ───────────────────────────
console.log('\n── 2. THE PATH WORKS IN GUEST MODE ───────────────────────');
await page.goto(`${BASE}/brief?patient=${ref}`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(700);
const signIn = page.getByRole('button', { name: /Continue as clinician/ });
if (await signIn.count()) await signIn.click();
await page.waitForSelector('.bx-section[aria-label="Current clinical snapshot"]', { timeout: 90000 });
check('the doctor brief renders', (await page.locator('.bx-section').count()) >= 10);
check('What changed? is populated',
  (await page.locator('.bx-section[aria-label="What changed?"] .bx-comparedwith').count()) === 1);

// evidence, by clicking
await page.locator('.bx-line[data-modality="document"]').first().click();
await page.waitForSelector('.bx-source[data-origin="document"]', { timeout: 45000 });
check('evidence opens against the demo record',
  ((await page.locator('.bx-source__verbatim').first().innerText()) || '').trim().length > 0);
await page.locator('.bx-evidence').getByRole('button', { name: 'Close' }).click();
await page.locator('.bx-evidence').waitFor({ state: 'detached', timeout: 15000 });

// ── 3. both PDFs, downloaded and read back ─────────────────────────────────
console.log('\n── 3. BOTH PDFs, DOWNLOADED AND READ BACK ────────────────');
const saved = {};
for (const [label, selector] of [
  ['clinician', /Download doctor's report/],
  ['patient', /Download my copy/],
]) {
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 120000 }),
    page.getByRole('button', { name: selector }).click(),
  ]);
  const path = `${DL}/${download.suggestedFilename()}`;
  await download.saveAs(path);
  saved[label] = path;
  check(`${label} PDF downloaded`, true, download.suggestedFilename());
}

for (const [label, path] of Object.entries(saved)) {
  const bytes = readFileSync(path);
  const pages = pdfPages(path);
  const body = pages.join('\n');
  console.log(`     ${label}: ${bytes.length} bytes, ${pages.length} page(s), ${body.length} chars of text`);

  check(`  ${label}: it is a PDF`, bytes.subarray(0, 4).toString() === '%PDF');
  // The assertion a screenshot renderer cannot pass.
  check(`  ${label}: the text is SELECTABLE, not an image`, body.length > 400,
    `${body.length} extractable characters`);
  check(`  ${label}: clinical content is present as characters`,
    /METFORMIN/i.test(body) && /stomach/i.test(body));
  check(`  ${label}: the demo badge is on EVERY page`,
    pages.every((p) => p.includes('SYNTHETIC DATA')));
  check(`  ${label}: the not-a-diagnosis footer is on EVERY page`,
    pages.every((p) => p.includes('NOT a diagnosis')));
  check(`  ${label}: every page is numbered with the right total`,
    pages.every((p, i) => p.includes(`Page ${i + 1} of ${pages.length}`)));
  check(`  ${label}: the Swastra wordmark is present`, body.includes('Swastra'));
}

// The patient copy must not carry our bookkeeping.
const patientBody = pdfPages(saved.patient).join('\n');
for (const leak of ['pat_guest_', 'fact_', 'enc_demo', 'chief_complaint.', 'hpi.']) {
  check(`  patient PDF leaks nothing: ${leak}`, !patientBody.includes(leak));
}

// ── 4. reset returns identical starting state ──────────────────────────────
console.log('\n── 4. RESET RETURNS THE IDENTICAL STARTING STATE ─────────');
const shapeOf = async (r) => page.evaluate(async (pr) => {
  const t = sessionStorage.getItem('medikiosk.token');
  const res = await fetch(`/api/v1/patients/${pr}/brief`, { headers: { Authorization: `Bearer ${t}` } });
  const b = await res.json();
  return {
    encounters: b.header.encounterCount, snapshot: b.snapshot.items.length,
    meds: b.medications.items.length, series: b.observations.series.length,
    timeline: b.timeline.items.length, persisting: b.whatChanged.persisting.length,
  };
}, r);

const before = await shapeOf(ref);
console.log('     before:', JSON.stringify(before));
await page.locator('.mk-demobadge__btn').first().click();
await page.getByRole('button', { name: /Yes, reset/ }).click();
await page.waitForFunction(
  (old) => JSON.parse(sessionStorage.getItem('medikiosk.guest') ?? '{}').patientRef !== old,
  ref, { timeout: 180000 });
const newRef = await page.evaluate(() => JSON.parse(sessionStorage.getItem('medikiosk.guest') ?? '{}').patientRef);
await page.goto(`${BASE}/brief?patient=${newRef}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.bx-section[aria-label="Current clinical snapshot"]', { timeout: 90000 });
const after = await shapeOf(newRef);
console.log('     after :', JSON.stringify(after));
check('reset restored the IDENTICAL starting state',
  JSON.stringify(before) === JSON.stringify(after), `${ref} -> ${newRef}`);

if (SHOT) await page.screenshot({ path: `${SHOT}/G4-final.png`, fullPage: false });
check('no console errors anywhere', errs.length === 0, errs[0] ?? '');

await browser.close();
console.log(failures === 0
  ? '\nGATE 4 PASSED — guest start to finish, both PDFs selectable and badged, reset exact.'
  : `\nGATE 4 FAILED — ${failures} check(s)`);
process.exit(failures === 0 ? 0 : 1);
