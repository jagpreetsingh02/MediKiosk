/**
 * GATE 3, end to end, real browser, local stack only.
 *
 *   localhost:5173  →  localhost:8000  →  local demo Postgres (DEMO_LOCAL_DB=true)
 *
 * Production is frozen and is deliberately not touched: the Vercel preview rewrites /api to
 * the live Render backend, which runs main's code against Supabase and has neither the
 * Session 3 endpoints nor the 3A schema. Proving Gate 3 there is impossible by construction,
 * so it is proved here, against the database the migration actually ran on.
 *
 * WHAT MUST BE TRUE:
 *   1. the doctor brief renders every section from stored rows
 *   2. What Changed? is populated against a REAL prior encounter
 *   3. all FOUR evidence types open by clicking — document+bbox, touch, typed, voice
 *   4. the patient view of the SAME encounter renders, leaking no internal identifier
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const PATIENT = process.env.PATIENT ?? 'pat_demo000001';
const SHOT = process.env.SHOT;

let failures = 0;
function check(label, ok, detail = '') {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures += 1;
}

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1600, height: 1100 } })).newPage();

const consoleErrors = [];
page.on('console', (m) => m.type() === 'error' && consoleErrors.push(m.text()));
page.on('pageerror', (e) => consoleErrors.push(String(e)));

// ── sign in and open the doctor brief ──────────────────────────────────────
await page.goto(`${BASE}/brief?patient=${PATIENT}`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(900);
const signIn = page.getByRole('button', { name: /Continue as clinician/ });
if (await signIn.count()) await signIn.click();
// NOT `.bx-section` — the sign-in card is one too, so that matched before the brief had
// loaded and every section assertion then failed against an empty page. Wait for a marker
// only the loaded brief has.
await page.waitForSelector('.bx-section[aria-label="Current clinical snapshot"]', {
  timeout: 60000,
});

console.log('\n── 1. THE DOCTOR BRIEF ───────────────────────────────────');
const sections = await page.locator('.bx-section').count();
check('the brief rendered its sections', sections >= 10, `${sections} sections`);

for (const title of [
  'Escalations',
  'What changed?',
  'Current clinical snapshot',
  'Laboratory values',
  'Medication history',
  'Visit timeline',
  'Similar earlier visits',
  'Contradictions',
  'Unresolved and changed',
  'Intake completeness',
  'Physician confirmation',
]) {
  const found = await page.locator(`.bx-section[aria-label="${title}"]`).count();
  check(`  section present: ${title}`, found === 1);
}

// Empty sections must EXPLAIN themselves rather than sitting blank.
const empties = await page.locator('.bx-empty').allInnerTexts();
check(
  'every empty section states a reason',
  empties.every((t) => t.trim().length > 15),
  `${empties.length} empty section(s)`,
);

// ── 2. WHAT CHANGED, against a real prior encounter ────────────────────────
console.log('\n── 2. WHAT CHANGED ───────────────────────────────────────');
const changed = page.locator('.bx-section[aria-label="What changed?"]');
const comparedWith = await changed.locator('.bx-comparedwith').count();
check('it names the visit it compared against', comparedWith === 1,
  comparedWith ? (await changed.locator('.bx-comparedwith').innerText()).replace(/\n/g, ' ') : 'absent');

const counts = {};
for (const kind of ['new', 'resolved', 'persisting']) {
  counts[kind] = await changed.locator(`.bx-changed__col[data-kind="${kind}"] li`).count();
}
console.log(`     new=${counts.new}  resolved=${counts.resolved}  persisting=${counts.persisting}`);
check('the diff is populated', counts.new + counts.resolved + counts.persisting > 0);
check('persisting features are shown, not only differences', counts.persisting > 0,
  'a complaint in its second visit is the point of a follow-up screen');

// ── 3. ALL FOUR EVIDENCE TYPES, OPENED BY CLICKING ─────────────────────────
console.log('\n── 3. CLICK-TO-SOURCE, ALL FOUR TYPES ────────────────────');

// Ask the payload which line carries which modality, then click those exact lines.
const plan = await page.evaluate(async (patientRef) => {
  const token = sessionStorage.getItem('medikiosk.token');
  const res = await fetch(`/api/v1/patients/${patientRef}/brief`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const brief = await res.json();
  const lines = [...brief.snapshot.items, ...brief.snapshot.allergies];
  for (const g of brief.snapshot.reportedMedications) lines.push(...g.lines);
  const byModality = {};
  for (const l of lines) {
    const m = l.evidenceModalities[0] ?? l.evidenceKinds[0];
    if (m && !byModality[m]) byModality[m] = { factRef: l.factRef, label: l.label };
  }
  return byModality;
}, PATIENT);

console.log('     modalities available on brief lines:', Object.keys(plan).join(', '));

for (const modality of ['document', 'voice', 'touch', 'typed']) {
  const target = plan[modality];
  if (!target) {
    check(`  ${modality}: a line exists to click`, false, 'no line carries this modality');
    continue;
  }

  // Click the real line in the real DOM — not a fetch.
  const line = page.locator(`.bx-line[data-modality="${modality}"]`).first();
  if (!(await line.count())) {
    check(`  ${modality}: line is present in the DOM`, false);
    continue;
  }
  await line.click();
  await page.waitForSelector(`.bx-source[data-origin="${modality}"]`, { timeout: 30000 });

  const source = page.locator(`.bx-source[data-origin="${modality}"]`).first();
  const verbatim = (await source.locator('.bx-source__verbatim').innerText()).trim();
  check(`  ${modality}: opens its real source`, verbatim.length > 0,
    `"${verbatim.slice(0, 46)}${verbatim.length > 46 ? '…' : ''}"`);

  if (modality === 'document') {
    // The cropped page region has to be a REAL loaded image, not a box holding space.
    const crop = source.locator('.kx-crop[data-loaded]');
    await crop.first().waitFor({ timeout: 40000 }).catch(() => {});
    const painted = (await crop.count())
      ? await crop.first().evaluate(
          (el) =>
            getComputedStyle(el).backgroundImage.startsWith('url(') &&
            el.getBoundingClientRect().height > 8,
        )
      : false;
    check('    and shows the highlighted page region', painted);
  }

  if (modality === 'voice') {
    const meta = await source.locator('.bx-source__meta').innerText();
    const hasScore = /Recognition confidence/i.test(meta);
    check('    and shows the ASR confidence', hasScore, meta.replace(/\n/g, ' ').slice(0, 60));
    // An unmeasured score must read as "not measured", never as 0.
    const unmeasured = await source.locator('.bx-unmeasured').count();
    const shows0 = /\b0\.00\b/.test(meta);
    check('    an unmeasured score is never rendered as zero', !(unmeasured && shows0));
  }

  if (SHOT) await page.screenshot({ path: `${SHOT}/G3-evidence-${modality}.png` });
  // Deliberately NOT closing between types: clicking the next line swaps the panel in
  // place, which is what a physician actually does, and closing first raced the exit
  // animation (the button is mid-flight and Playwright rightly refuses to click it).

}

await page.locator('.bx-evidence').getByRole('button', { name: 'Close' }).click();
await page.locator('.bx-evidence').waitFor({ state: 'detached', timeout: 15000 });
check('the evidence panel closes', true);

if (SHOT) await page.screenshot({ path: `${SHOT}/G3-doctor.png`, fullPage: true });

// ── 4. THE PATIENT VIEW OF THE SAME ENCOUNTER ──────────────────────────────
console.log('\n── 4. THE PATIENT VIEW ───────────────────────────────────');
await page.goto(`${BASE}/brief?patient=${PATIENT}&as=patient`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.bx--patient .bx-section', { timeout: 60000 });

const groups = await page.locator('.bx--patient .bx-section').count();
check('the patient view rendered', groups === 4, `${groups} groups`);
for (const title of [
  'What you told us',
  'What came from your documents',
  'What comes from your previous visits',
  'Items still waiting for doctor verification',
]) {
  check(`  group present: ${title}`, (await page.locator(`.bx-section[aria-label="${title}"]`).count()) === 1);
}

// THE RENDERED TEXT, not the payload — the payload was already proved clean in pytest.
const shown = await page.locator('.bx--patient .bx-main').innerText();
for (const leak of ['fact_', 'enc_', 'pat_', 'hpi.', 'chief_complaint.', 'drug_allergy.',
                    'factRef', 'evidenceIds', 'confidence', 'tier', 'FHIR', 'document tier']) {
  check(`  no leak on screen: ${leak}`, !shown.includes(leak));
}
check('the density is the calm one',
  (await page.locator('.bx[data-density="patient"]').count()) === 1);

if (SHOT) await page.screenshot({ path: `${SHOT}/G3-patient.png`, fullPage: true });

check('no console errors anywhere', consoleErrors.length === 0, consoleErrors[0] ?? '');

await browser.close();
console.log(
  failures === 0
    ? '\nGATE 3 PASSED — both views from stored data, four evidence types, no leaks.'
    : `\nGATE 3 FAILED — ${failures} check(s)`,
);
process.exit(failures === 0 ? 0 : 1);
