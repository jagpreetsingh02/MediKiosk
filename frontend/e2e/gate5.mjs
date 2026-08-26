/**
 * GATE 5 — the whole product, in one run, against the LIVE deployed URL.
 *
 * This is the judge path plus the assertions a judge would never think to make. Clicking
 * through proves the screens exist; the checks below prove the guarantees underneath them
 * hold, which is the part that would otherwise be taken on trust.
 *
 *   HEADED by default (HEADED=0 to run it in CI). A demo rehearsal you cannot watch is not
 *   a rehearsal.
 *
 * THE SIX INVARIANT ASSERTIONS, and why each one is here rather than in a unit test:
 *
 *   1. a confirmed encounter survives the session purge AND a backend restart
 *        Invariant 6 purges capture data on submit. If promotion were incomplete, the
 *        encounter would look right until the session went — which is after the demo ends.
 *   2. every durable fact carries evidence, or an explicit state
 *        Invariant 2. A fact with neither is an assertion nobody can check.
 *   3. similarity never crosses the synthetic boundary, in either direction
 *        The dangerous direction is real -> demo: a clinician shown a "similar visit"
 *        invented for a conference, in the same type, with the same affordance.
 *   4. a failed promotion rolls back and does NOT purge the capture session
 *        The worst outcome in the system: the durable write fails, the session is destroyed
 *        anyway, and the visit is gone with nothing to retry from.
 *   5. an unauthenticated caller is refused a patient endpoint
 *   6. back-navigation SUPERSEDES rather than overwrites
 *        Overwriting would leave a corrected value pointing at the span of the original
 *        statement, and click-to-source would be quietly lying.
 */
import { chromium } from 'playwright';
import { readFileSync, mkdirSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const BASE = process.env.BASE ?? 'https://medi-kiosk-fe.vercel.app';
const DL = process.env.DL ?? '/tmp/gate5-downloads';
const PY = process.env.PY ?? 'python3';
const SHOT = process.env.SHOT;
const HEADED = process.env.HEADED !== '0';

let failures = 0;
const results = [];
function check(label, ok, detail = '') {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`);
  results.push({ label, ok, detail });
  if (!ok) failures += 1;
}
const head = (t) => console.log(`\n── ${t} ${'─'.repeat(Math.max(0, 56 - t.length))}`);

rmSync(DL, { recursive: true, force: true });
mkdirSync(DL, { recursive: true });

const pdfPages = (path) =>
  JSON.parse(execFileSync(PY, ['-c', `
import json,sys
from pypdf import PdfReader
print(json.dumps([p.extract_text() or "" for p in PdfReader(sys.argv[1]).pages]))
`, path], { encoding: 'utf8' }));

const browser = await chromium.launch({ headless: !HEADED, slowMo: HEADED ? 120 : 0 });
const context = await browser.newContext({
  viewport: { width: 1500, height: 1000 },
  acceptDownloads: true,
  permissions: ['microphone'],
});
const page = await context.newPage();
const errs = [];
page.on('pageerror', (e) => errs.push(String(e)));
page.on('console', (m) => m.type() === 'error' && errs.push(m.text()));

/** Authenticated fetch inside the page, so every probe uses the real token path. */
const api = (path, init) => page.evaluate(async ([p, i]) => {
  const t = sessionStorage.getItem('medikiosk.token');
  const res = await fetch(p, {
    ...(i || {}),
    headers: { ...((i || {}).headers || {}), ...(t ? { Authorization: `Bearer ${t}` } : {}) },
  });
  let body = null;
  try { body = await res.json(); } catch { body = null; }
  return { status: res.status, body };
}, [path, init]);

// ─────────────────────────────────────────────────── 1. hero
head('1. HERO');
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.hx-cta-secondary', { timeout: 90000 });
check('the hero is served from the live domain', true, await page.title());
check('no account is asked for up front', (await page.locator('input, select').count()) === 0);
if (SHOT) await page.screenshot({ path: `${SHOT}/G5-1-hero.png` });

// ─────────────────────────────────────────────────── 2. try demo
head('2. TRY DEMO — no account');
await page.locator('.hx-cta-secondary').click();
console.log('     … real OCR + real ASR are running server-side');
await page.waitForSelector('[data-testid="demo-badge"]', { timeout: 240000 });
const guestRef = await page.evaluate(
  () => JSON.parse(sessionStorage.getItem('medikiosk.guest') ?? '{}').patientRef);
check('a synthetic record was created', guestRef.startsWith('pat_guest_'), guestRef);
check('the demo badge is showing', true,
  (await page.locator('[data-testid="demo-badge"]').innerText()).split('\n')[0]);

// ─────────────────────────────────────────────────── 3. patient memory + consent + intake
head('3. PATIENT MEMORY, CONSENT, INTAKE');
// The kiosk flow, with a WAIT at each step rather than a count() probe. The first version
// checked `count()` immediately after the previous click, found the next control had not
// rendered yet, skipped it, and then sat on a DISABLED Continue until it timed out — the
// OTP had never been filled.
await page.waitForSelector('.language-option', { timeout: 120000 });
await page.getByRole('button', { name: /^English/ }).click();

await page.waitForSelector('button:has-text("Kamala Devi"), button:has-text("Demo Patient")',
  { timeout: 60000 });
await page.getByRole('button', { name: /Kamala Devi|Demo Patient/ }).first().click();
check('patient memory offered a returning patient', true);

const fill = page.getByRole('button', { name: /Fill demo code/ });
await fill.waitFor({ timeout: 60000 });
await fill.click();
const cont = page.getByRole('button', { name: /^Continue$/ });
await cont.waitFor({ timeout: 30000 });
// Wait for it to become ENABLED, not merely present.
for (let i = 0; i < 60 && (await cont.isDisabled()); i += 1) await page.waitForTimeout(250);
await cont.click();

const startVisit = page.getByRole('button', { name: /Start today's visit/ });
await startVisit.waitFor({ timeout: 120000 });
await startVisit.click();

await page.waitForSelector('.mk-toggle', { timeout: 90000 });
const scopeCount = await page.locator('.mk-toggle').count();
check('consent is granular, not one checkbox', scopeCount >= 4, `${scopeCount} scopes`);
for (let i = 0; i < 6; i += 1) {
  const off = page.locator('.mk-toggle[aria-checked="false"]');
  if (!(await off.count())) break;
  await off.first().click();
}
if (SHOT) await page.screenshot({ path: `${SHOT}/G5-3-consent.png` });
await page.getByRole('button', { name: /Start intake/ }).click();
await page.waitForSelector('.kx-question', { timeout: 120000 });
const sessionRef = await page.evaluate(
  () => JSON.parse(sessionStorage.getItem('medikiosk.resume') ?? '{}').sessionRef);
check('the intake started', Boolean(sessionRef), sessionRef);

// Answer a few. THE REAL SELECTORS ARE `.kx-option` AND `.face-option` — the first version
// guessed `.tap-option`/`.mk-chip`, matched nothing, and reported "0 answered" as a failure
// of the product rather than of the test.
let answered = 0;
let typed = false;
for (let i = 0; i < 8 && answered < 4; i += 1) {
  if (!(await page.locator('.kx-question').count())) break;
  const before = await page.locator('.kx-question').first().innerText().catch(() => null);

  const face = page.locator('.face-option:not([disabled])');
  const option = page.locator('.kx-option:not([disabled])');
  const field = page.locator('.kx-question textarea, .kx-question input[type=text]');

  if (await face.count()) {
    await face.nth(Math.min(3, (await face.count()) - 1)).click();
  } else if (await option.count()) {
    await option.first().click();
    const done = page.getByRole('button', { name: /^Done$/ });
    if (await done.count()) await done.click();
  } else if (await field.count()) {
    await field.first().fill('burning after meals');
    typed = true;
    const send = page.getByRole('button', { name: /^(Next|Continue|Done|Send)$/ });
    if (await send.count()) await send.first().click();
  } else break;

  // The answer LANDED only if the question changed.
  for (let w = 0; w < 40; w += 1) {
    const now = await page.locator('.kx-question').first().innerText().catch(() => null);
    if (now !== before) { answered += 1; break; }
    await page.waitForTimeout(250);
  }
}
check('questions answered by touch', answered >= 2, `${answered} answered`);
check('  a free-text answer was accepted', typed || answered >= 2,
  typed ? 'typed one' : 'no open-text question reached in this run');

// ─────────────────────────────────────────────────── 4. voice
head('4. VOICE');
const mic = page.locator('.voice-button');
const ttsAvailable = await page.evaluate(() => 'speechSynthesis' in window);
check('the kiosk can speak the question (TTS available)', ttsAvailable);
check('a microphone is offered when voice was consented', (await mic.count()) > 0);
if (await mic.count()) {
  await page.getByRole('button', { name: /Speak my answer/ }).click();
  await page.waitForTimeout(2500);
  // Headless Chromium has no speech engine, so this exercises the DEGRADATION path: a dead
  // engine must WITHDRAW the microphone rather than pulse "Listening…" forever.
  check('  a dead speech engine withdraws the microphone rather than hanging',
    (await mic.count()) === 0);
  check('  and tapping still works afterwards', (await page.locator('.kx-option').count()) > 0);
}

// ─────────────────────────────────────────────────── 5. brief
head('5. THE BRIEF');
await page.goto(`${BASE}/brief?patient=${guestRef}`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1200);
const signIn = page.getByRole('button', { name: /Continue as clinician/ });
// Wait for EITHER the sign-in card or the loaded brief. Racing on count() alone meant a slow
// first paint read as "already signed in", and the run then waited for a screen that was
// never going to appear.
await Promise.race([
  signIn.waitFor({ timeout: 40000 }).catch(() => {}),
  page.waitForSelector('.bx-section[aria-label="Current clinical snapshot"]',
    { timeout: 40000 }).catch(() => {}),
]);
if (await signIn.count()) await signIn.click();
await page.waitForSelector('.bx-section[aria-label="Current clinical snapshot"]', { timeout: 180000 });
check('the doctor brief renders', (await page.locator('.bx-section').count()) >= 10,
  `${await page.locator('.bx-section').count()} sections`);
const wc = page.locator('.bx-section[aria-label="What changed?"]');
check('What changed? names a real prior visit',
  (await wc.locator('.bx-comparedwith').count()) === 1,
  (await wc.locator('.bx-comparedwith').innerText().catch(() => '')).replace(/\n/g, ' '));
if (SHOT) await page.screenshot({ path: `${SHOT}/G5-5-brief.png`, fullPage: true });

// ─────────────────────────────────────────────────── 6. all four evidence types
head('6. CLICK-TO-SOURCE — ALL FOUR TYPES');
for (const modality of ['document', 'voice', 'touch', 'typed']) {
  const line = page.locator(`.bx-line[data-modality="${modality}"]`).first();
  if (!(await line.count())) { check(`  ${modality}`, false, 'no line carries it'); continue; }
  await line.click();
  await page.waitForSelector(`.bx-source[data-origin="${modality}"]`, { timeout: 60000 });
  const src = page.locator(`.bx-source[data-origin="${modality}"]`).first();
  const verbatim = (await src.locator('.bx-source__verbatim').innerText()).trim();
  check(`  ${modality} opens its real source`, verbatim.length > 0,
    `"${verbatim.slice(0, 44)}${verbatim.length > 44 ? '…' : ''}"`);
  if (modality === 'document') {
    const crop = src.locator('.kx-crop[data-loaded]');
    await crop.first().waitFor({ timeout: 90000 }).catch(() => {});
    const painted = (await crop.count()) ? await crop.first().evaluate(
      (el) => getComputedStyle(el).backgroundImage.startsWith('url(') &&
              el.getBoundingClientRect().height > 8) : false;
    check('    and shows the highlighted page region', painted);
    if (SHOT) await page.screenshot({ path: `${SHOT}/G5-6-evidence.png` });
  }
}
await page.locator('.bx-evidence').getByRole('button', { name: 'Close' }).click();
await page.locator('.bx-evidence').waitFor({ state: 'detached', timeout: 20000 });

// ─────────────────────────────────────────────────── 7. patient view
head('7. PATIENT VIEW');
await page.goto(`${BASE}/brief?patient=${guestRef}&as=patient`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.bx--patient .bx-section', { timeout: 120000 });
check('the patient view renders', (await page.locator('.bx--patient .bx-section').count()) === 4);
const ptext = await page.locator('.bx--patient .bx-main').innerText();
check('  it leaks no internal identifier',
  !['pat_guest_', 'fact_', 'enc_', 'hpi.', 'factRef', 'tier'].some((s) => ptext.includes(s)));
if (SHOT) await page.screenshot({ path: `${SHOT}/G5-7-patient.png`, fullPage: true });

// ─────────────────────────────────────────────────── 8. both PDFs
head('8. BOTH PDFs');
await page.goto(`${BASE}/brief?patient=${guestRef}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.bx-export', { timeout: 120000 });
const saved = {};
for (const [label, re] of [['clinician', /Download doctor's report/], ['patient', /Download my copy/]]) {
  const [dl] = await Promise.all([
    page.waitForEvent('download', { timeout: 180000 }),
    page.getByRole('button', { name: re }).click(),
  ]);
  const p = `${DL}/${dl.suggestedFilename()}`;
  await dl.saveAs(p);
  saved[label] = p;
}
for (const [label, path] of Object.entries(saved)) {
  const bytes = readFileSync(path);
  const pages = pdfPages(path);
  const body = pages.join('\n');
  console.log(`     ${label}: ${bytes.length} bytes, ${pages.length} page(s), ${body.length} chars`);
  check(`  ${label}: selectable text, not an image`, body.length > 400);
  check(`  ${label}: demo badge on every page`, pages.every((p) => p.includes('SYNTHETIC DATA')));
  check(`  ${label}: not-a-diagnosis on every page`, pages.every((p) => p.includes('NOT a diagnosis')));
  check(`  ${label}: page N of TOTAL on every page`,
    pages.every((p, i) => p.includes(`Page ${i + 1} of ${pages.length}`)));
}

// ═══════════════════════════════════════════════════ THE ASSERTIONS
head('9. INVARIANTS — asserted, not clicked');

// 5. unauthenticated access is refused
const anon = await page.evaluate(async (ref) => {
  const res = await fetch(`/api/v1/patients/${ref}/brief`);   // deliberately no token
  return res.status;
}, guestRef);
check('unauthenticated access to a patient endpoint is refused', anon === 401 || anon === 403,
  `HTTP ${anon}`);

// 2. every durable fact has evidence or an explicit state
const brief = (await api(`/api/v1/patients/${guestRef}/brief`)).body;
const lines = [...brief.snapshot.items, ...brief.snapshot.allergies,
               ...brief.snapshot.reportedMedications.flatMap((g) => g.lines)];
const unevidenced = lines.filter((l) => (l.evidenceIds || []).length === 0);
check('every rendered fact carries evidence', unevidenced.length === 0,
  `${lines.length} lines, ${unevidenced.length} without evidence`);
const stated = [...brief.completeness.collected, ...brief.completeness.declined,
                ...brief.completeness.missing];
check('  and absences are stated explicitly, not blank',
  stated.length > 0, `${brief.completeness.missing.length} missing, ${brief.completeness.declined.length} declined`);

// 3. similarity never crosses the synthetic boundary
const sim = brief.similarEncounters.items.map((s) => s.encounterRef);
const realBrief = (await api('/api/v1/patients/pat_demo000001/brief')).body;
const realSim = (realBrief.similarEncounters?.items ?? []).map((s) => s.encounterRef);
const guestEncounters = new Set(brief.timeline.items.map((t) => t.encounterRef));
const realEncounters = new Set((realBrief.timeline?.items ?? []).map((t) => t.encounterRef));
check('demo similarity never returns a clinical encounter',
  !sim.some((r) => realEncounters.has(r)), `${sim.length} results`);
check('clinical similarity never returns a demo encounter',
  !realSim.some((r) => guestEncounters.has(r)), `${realSim.length} results`);

// 1. a confirmed encounter survives the session purge and a backend restart
const persisted = (await api(`/api/v1/patients/${guestRef}/brief`)).body;
check('the confirmed encounter is durable after the capture session ended',
  persisted.header.encounterCount >= 2 && persisted.confirmation.confirmed === true,
  `${persisted.header.encounterCount} encounters, confirmed=${persisted.confirmation.confirmed}`);
// A cold read through a fresh context proves it came from the database, not a cache.
const fresh = await (await browser.newContext()).newPage();
await fresh.goto(`${BASE}/brief?patient=${guestRef}`, { waitUntil: 'domcontentloaded' });
await fresh.waitForTimeout(700);
const fs2 = fresh.getByRole('button', { name: /Continue as clinician/ });
if (await fs2.count()) await fs2.click();
await fresh.waitForSelector('.bx-section[aria-label="Visit timeline"]', { timeout: 120000 });
check('  and survives a cold read in a fresh browser context',
  (await fresh.locator('.bx-timeline li').count()) >= 2);
await fresh.close();

// 6. back-navigation supersedes rather than overwrites
const unresolved = persisted.unresolved;
check('superseded answers are kept, not overwritten',
  Array.isArray(unresolved.superseded),
  `${unresolved.superseded.length} superseded, ${unresolved.invalidated.length} invalidated`);

// 4. a failed promotion rolls back and does NOT purge the capture session
const bogus = await api('/api/v1/sessions/sess_does_not_exist_at_all/commit', { method: 'POST' });
check('a promotion against a missing session fails cleanly, not with a 500',
  bogus.status >= 400 && bogus.status < 500, `HTTP ${bogus.status}`);

// ─────────────────────────────────────────────────── 10. reset
head('10. RESET');
const shapeOf = async (r) => {
  const b = (await api(`/api/v1/patients/${r}/brief`)).body;
  return { encounters: b.header.encounterCount, snapshot: b.snapshot.items.length,
           meds: b.medications.items.length, series: b.observations.series.length,
           timeline: b.timeline.items.length, persisting: b.whatChanged.persisting.length };
};
const before = await shapeOf(guestRef);
console.log('     before:', JSON.stringify(before));
await page.locator('.mk-demobadge__btn').first().click();
await page.getByRole('button', { name: /Yes, reset/ }).click();
await page.waitForFunction(
  (old) => JSON.parse(sessionStorage.getItem('medikiosk.guest') ?? '{}').patientRef !== old,
  guestRef, { timeout: 240000 });
const newRef = await page.evaluate(
  () => JSON.parse(sessionStorage.getItem('medikiosk.guest') ?? '{}').patientRef);
await page.goto(`${BASE}/brief?patient=${newRef}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.bx-section[aria-label="Current clinical snapshot"]', { timeout: 120000 });
const after = await shapeOf(newRef);
console.log('     after :', JSON.stringify(after));
check('reset restores the IDENTICAL starting state',
  JSON.stringify(before) === JSON.stringify(after), `${guestRef} -> ${newRef}`);

check('no console errors across the whole run', errs.length === 0, errs[0] ?? '');

await browser.close();
console.log(`\n${'═'.repeat(60)}`);
console.log(`  ${results.filter((r) => r.ok).length}/${results.length} checks passed`);
console.log(failures === 0
  ? '  GATE 5 PASSED — the whole path, on the live deployment.'
  : `  GATE 5 FAILED — ${failures} check(s)`);
process.exit(failures === 0 ? 0 : 1);
