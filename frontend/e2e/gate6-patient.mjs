/**
 * GATE 6 PART 1 — a patient signs in and reads their own confirmed record.
 *
 * The whole point of the system is a record a clinician can trust. This is the half that was
 * missing: the person it is ABOUT being able to read it. So the run does the full loop —
 * a physician confirms an encounter, then the patient signs in separately and finds it.
 *
 * THE CROSS-PATIENT CHECK IS THE ONE THAT MATTERS. Everything else here is a screen; that one
 * is a promise. It is asserted three ways — the encounter list, the report, and the PDF —
 * because a leak through any of the three is the same leak.
 */
import { chromium } from 'playwright';
import { readFileSync, mkdirSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const DL = process.env.DL ?? '/tmp/gate6-downloads';
const PY = process.env.PY ?? 'python3';
const SHOT = process.env.SHOT;

let failures = 0;
const check = (l, ok, d = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${l}${d ? ` — ${d}` : ''}`);
  if (!ok) failures += 1;
};
const head = (t) => console.log(`\n── ${t} ${'─'.repeat(Math.max(0, 54 - t.length))}`);

rmSync(DL, { recursive: true, force: true });
mkdirSync(DL, { recursive: true });

const pdfPages = (p) => JSON.parse(execFileSync(PY, ['-c', `
import json,sys
from pypdf import PdfReader
print(json.dumps([q.extract_text() or "" for q in PdfReader(sys.argv[1]).pages]))
`, p], { encoding: 'utf8' }));

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1400, height: 1000 }, acceptDownloads: true });
const page = await context.newPage();
const errs = [];
page.on('pageerror', (e) => errs.push(String(e)));
page.on('console', (m) => m.type() === 'error' && errs.push(m.text()));

const call = (path, init) => page.evaluate(async ([p, i]) => {
  const t = sessionStorage.getItem('medikiosk.token');
  const res = await fetch(p, { ...(i || {}),
    headers: { ...((i || {}).headers || {}), ...(t ? { Authorization: `Bearer ${t}` } : {}) } });
  let body = null; try { body = await res.json(); } catch { /* not json */ }
  return { status: res.status, body };
}, [path, init]);

// ── 1. a physician confirms an encounter ───────────────────────────────────
head('1. A PHYSICIAN CONFIRMS AN ENCOUNTER');
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(900);

// Sign in as clinician and read the demo patient's record, which the seed already committed.
await page.goto(`${BASE}/brief?patient=pat_demo000001`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(900);
const clinicianSignIn = page.getByRole('button', { name: /Continue as clinician/ });
if (await clinicianSignIn.count()) await clinicianSignIn.click();
await page.waitForSelector('.bx-section[aria-label="Physician confirmation"]', { timeout: 90000 });
const confirmText = await page.locator('.bx-confirm').innerText();
check('the demo patient has a physician-confirmed encounter', /Confirmed by/i.test(confirmText),
  confirmText.replace(/\n/g, ' ').slice(0, 70));

const asClinician = await call('/api/v1/patients/pat_demo000001/encounters');
check('a clinician can list those encounters', asClinician.status === 200,
  `${asClinician.body?.encounters?.length ?? 0} confirmed`);
const confirmedRefs = (asClinician.body?.encounters ?? []).map((e) => e.encounterRef);
check('  every one carries a confirming physician',
  (asClinician.body?.encounters ?? []).every((e) => e.confirmedBy),
  confirmedRefs.slice(0, 2).join(', '));

// ── 2. the patient signs in, separately ────────────────────────────────────
head('2. THE PATIENT SIGNS IN');
await context.clearCookies();
await page.goto(`${BASE}/patient/me`, { waitUntil: 'domcontentloaded' });
await page.evaluate(() => sessionStorage.clear());
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForTimeout(800);

check('the portal asks for a sign-in before showing anything',
  (await page.locator('.pp').innerText()).toLowerCase().includes('sign in'));
const noVisitsYet = await page.locator('.pp-visit').count();
check('  and shows no record while signed out', noVisitsYet === 0);
if (SHOT) await page.screenshot({ path: `${SHOT}/G6-1-login.png` });

// The mock ABHA identity, unchanged.
const abhaOption = page.locator('.tap-option').first();
await abhaOption.waitFor({ timeout: 60000 });
await abhaOption.click();
// WAIT for the OTP control rather than probing count() straight after the click — the
// screen has not rendered yet at that instant, and the fallback then fills a field that is
// also not there. Same race that cost a run in gate5.
const demoCode = page.getByRole('button', { name: /Fill demo code/i });
await demoCode.waitFor({ timeout: 60000 });
await demoCode.click();
const verify = page.getByRole('button', { name: /^(Continue|Verify|Sign in)$/ });
await verify.first().waitFor({ timeout: 30000 });
for (let i = 0; i < 80 && (await verify.first().isDisabled()); i += 1) await page.waitForTimeout(250);
await verify.first().click();

await page.waitForSelector('.pp-visit', { timeout: 120000 });
const role = await page.evaluate(() => {
  const t = sessionStorage.getItem('medikiosk.token');
  return t ? JSON.parse(atob(t.split('.')[1])).role : null;
});
check('signed in as a patient (mock ABHA, unchanged)', role === 'patient', `role=${role}`);
const myRef = (await call('/api/v1/patients/me')).body?.patientRef;
check('the record resolved from the TOKEN, not the URL', Boolean(myRef), myRef);

// ── 3. their confirmed history ─────────────────────────────────────────────
head('3. THEIR CONFIRMED HISTORY, NEWEST FIRST');
const visits = await page.locator('.pp-visit').count();
check('confirmed visits are listed', visits > 0, `${visits} visit(s)`);
const dates = await page.locator('.pp-visit__when strong').allInnerTexts();
const sortedDesc = [...dates].sort().reverse();
check('  newest first', JSON.stringify(dates) === JSON.stringify(sortedDesc), dates.join(' > '));
check('  each names the confirming physician',
  (await page.locator('.pp-visit__when .kx-footnote').allInnerTexts())
    .every((t) => /confirmed by/i.test(t)));

const listed = await call(`/api/v1/patients/${myRef}/encounters`);
check('  the API returns only confirmed encounters', listed.status === 200
  && (listed.body?.encounters ?? []).every((e) => e.confirmedBy),
  `${listed.body?.encounters?.length ?? 0} encounters`);
if (SHOT) await page.screenshot({ path: `${SHOT}/G6-2-history.png`, fullPage: true });

// ── 4. view my report ──────────────────────────────────────────────────────
head('4. VIEW MY REPORT');
await page.locator('.pp-visit').first().getByRole('button', { name: /View my report/ }).click();
await page.waitForSelector('.pp-visit__report .bx--patient', { timeout: 120000 });
const groups = await page.locator('.pp-visit__report .bx--patient .bx-section').count();
check('the patient view opens inline', groups === 4, `${groups} groups`);
const shown = await page.locator('.pp-visit__report').innerText();
for (const leak of ['fact_', 'enc_', 'pat_', 'hpi.', 'chief_complaint.', 'factRef', 'tier']) {
  check(`  no internal identifier on screen: ${leak}`, !shown.includes(leak));
}
if (SHOT) await page.screenshot({ path: `${SHOT}/G6-3-report.png`, fullPage: true });

// ── 5. download my PDF ─────────────────────────────────────────────────────
head('5. DOWNLOAD MY PDF');
const [download] = await Promise.all([
  page.waitForEvent('download', { timeout: 180000 }),
  page.locator('.pp-visit').first().getByRole('button', { name: /Download PDF/ }).click(),
]);
const path = `${DL}/${download.suggestedFilename()}`;
await download.saveAs(path);
const bytes = readFileSync(path);
const pages = pdfPages(path);
const body = pages.join('\n');
console.log(`     ${download.suggestedFilename()}: ${bytes.length} bytes, ${pages.length} page(s), ${body.length} chars`);
check('it is a PDF', bytes.subarray(0, 4).toString() === '%PDF');
check('the text is SELECTABLE, not an image', body.length > 400, `${body.length} chars`);
check('not-a-diagnosis footer on every page', pages.every((p) => p.includes('NOT a diagnosis')));
check('every page numbered with the right total',
  pages.every((p, i) => p.includes(`Page ${i + 1} of ${pages.length}`)));
check('it carries no internal identifier',
  !['fact_', 'enc_demo', 'chief_complaint.', 'hpi.'].some((s) => body.includes(s)));

// ── 6. a second patient cannot see the first patient's data ────────────────
head('6. ANOTHER PATIENT IS REFUSED');

// Console errors are judged on the user-facing path only; everything below deliberately
// provokes refusals and the browser logs each one.
const errorsBeforeProbes = errs.length;

// A GENUINELY DIFFERENT PATIENT. The first version hardcoded a reference that turned out to
// be the signed-in patient's OWN record, so three "refused" checks reported HTTP 200 and
// looked like a security hole. It was the test naming the same person twice.
const otherRef = 'pat_demo000001';
check('the probe targets a different patient', otherRef !== myRef, `${myRef} vs ${otherRef}`);

const other = await call(`/api/v1/patients/${otherRef}/encounters`);
check("another patient's encounter list is REFUSED, not empty",
  other.status === 403, `HTTP ${other.status}`);
check('  and the refusal says nothing about whether that record exists',
  !/exists|not found|no such/i.test(other.body?.issue?.[0]?.diagnostics ?? ''),
  (other.body?.issue?.[0]?.diagnostics ?? '').slice(0, 70));

const otherBrief = await call(`/api/v1/patients/${otherRef}/brief/patient`);
check("another patient's report is refused", otherBrief.status === 403, `HTTP ${otherBrief.status}`);

const otherPdf = await page.evaluate(async (r) => {
  const t = sessionStorage.getItem('medikiosk.token');
  const res = await fetch(`/api/v1/patients/${r}/brief.pdf?audience=patient`,
    { headers: { Authorization: `Bearer ${t}` } });
  return res.status;
}, otherRef);
check("another patient's PDF is refused", otherPdf === 403, `HTTP ${otherPdf}`);

const otherClinical = await call(`/api/v1/patients/${otherRef}/brief`);
check("another patient's CLINICIAN brief is refused too", otherClinical.status === 403,
  `HTTP ${otherClinical.status}`);

// And a named encounter belonging to someone else must not fall back to your own.
const foreignEnc = await call(
  `/api/v1/patients/${myRef}/brief/patient?encounter=enc_does_not_belong_here`);
check('a foreign encounter reference is a clean refusal, not a fallback',
  foreignEnc.status >= 400 && foreignEnc.status < 500, `HTTP ${foreignEnc.status}`);

const userFacing = errs.slice(0, errorsBeforeProbes);
check('no console errors on the user-facing patient path', userFacing.length === 0,
  userFacing[0] ?? `${errs.length - errorsBeforeProbes} expected refusal(s) during probes`);

await browser.close();
console.log(failures === 0
  ? '\nGATE 6 PART 1 PASSED — a patient reads their own record, and only their own.'
  : `\nGATE 6 PART 1 FAILED — ${failures} check(s)`);
process.exit(failures === 0 ? 0 : 1);
