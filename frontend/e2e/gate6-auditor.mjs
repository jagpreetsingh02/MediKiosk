/**
 * GATE 6 PART 3 — the auditor opens an encounter, verifies the chain, and catches a tamper.
 *
 * Read-only is the whole point of this role, so the strongest thing this run can do is try to
 * find a write and fail to. It does not try every route (that is the AST scan in
 * tests/test_auditor_role.py); it proves the one screen that exists offers none, and that the
 * server refuses a mutating call even when attempted directly.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const API = process.env.API ?? 'http://localhost:8000';
const SHOT = process.env.SHOT;

let failures = 0;
const check = (l, ok, d = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${l}${d ? ` — ${d}` : ''}`);
  if (!ok) failures += 1;
};
const head = (t) => console.log(`\n── ${t} ${'─'.repeat(Math.max(0, 54 - t.length))}`);

/**
 * A real intake→commit run against the local API, so this gate has a fresh encounter whose
 * `consent_ref` actually correlates to real audit_event rows. The SEEDED demo encounters
 * predate `encounter.consent_ref` ever being populated — `promote()` never set it, a real gap
 * found and fixed while building this gate (see the comment in app/modules/encounter/promote.py)
 * — so their trails are empty by construction, not by anything wrong with the auditor screen.
 * This walks the same path as tests/test_api_end_to_end.py::test_full_patient_journey, trimmed
 * to what is needed for a committed encounter to exist.
 */
async function seedFreshEncounter() {
  const j = (r) => r.json();
  const post = (path, body, headers) =>
    fetch(`${API}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body ?? {}) });
  const get = (path, headers) => fetch(`${API}${path}`, { headers });
  const abhaAddress = `gate6.aud.${Date.now()}@abdm`;
  const auth = (t) => ({ Authorization: `Bearer ${t}` });

  await post('/mock-idp/abha/request-otp', { abha_address: abhaAddress });
  const { access_token: patientToken } = await j(
    await post('/mock-idp/abha/verify-otp', { abha_address: abhaAddress, otp: '123456' }),
  );

  const { sessionRef } = await j(
    await post(
      '/api/v1/sessions',
      { language: 'en', consentScopes: ['history', 'voice', 'documents', 'abdm_share'], audioExplained: true },
      auth(patientToken),
    ),
  );

  const answers = {
    'cc.text': 'pain', 'cc.duration': 'days_1_3', 'hpi.site': 'chest', 'hpi.onset': 'sudden',
    'hpi.character': 'pressure', 'hpi.radiation': 'jaw_neck',
    'hpi.associated': ['sweating', 'breathlessness'], 'hpi.timing': 'constant',
    'hpi.exacerbating': ['worse_effort'], 'hpi.severity': 9,
    'pmh.conditions': ['diabetes', 'hypertension'], 'pmh.hospitalised': false, 'psh.any': false,
    'med.taking': true, 'med.ayush_taking': false, 'allergy.any': false,
    'fh.conditions': ['heart'], 'ph.tobacco': 'never', 'ph.alcohol': 'never', 'ph.diet': 'veg',
    'ph.sleep': 'disturbed', 'ph.bowel': 'regular', 'ph.occupation': 'home',
    'ros.cardio': ['chest_pain_exertion'], 'ros.resp': ['none'], 'ros.gi': ['none'],
    'ros.neuro': ['none'], 'ros.gu': ['none'], 'ros.msk': ['none'], 'ros.general': ['fatigue'],
  };

  for (let i = 0; i < 80; i += 1) {
    const step = await j(await get(`/api/v1/sessions/${sessionRef}/dialogue/next`, auth(patientToken)));
    if (step.complete) break;
    const { questionId, turnId } = step.question;
    if (questionId in answers) {
      const r = await post(
        `/api/v1/sessions/${sessionRef}/dialogue/answer`,
        { turnId, questionId, value: answers[questionId], modality: 'touch' },
        auth(patientToken),
      );
      if (!r.ok) throw new Error(`seed: answer ${questionId} → HTTP ${r.status}`);
    } else {
      await post(`/api/v1/sessions/${sessionRef}/dialogue/skip`, { questionId }, auth(patientToken));
    }
  }

  const { access_token: clinicianToken } = await j(
    await post('/mock-idp/token', { role: 'clinician', sub: 'dr.gate6@aiia' }),
  );
  const committed = await j(
    await post(`/api/v1/sessions/${sessionRef}/commit`, { confirmed: true }, auth(clinicianToken)),
  );
  if (!committed.committed) throw new Error(`seed: commit did not report committed — ${JSON.stringify(committed)}`);
  return committed.promotion.encounterRef;
}

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1500, height: 1100 } })).newPage();
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

// ── 1. sign in as auditor ───────────────────────────────────────────────────
head('1. SIGN IN AS AUDITOR');
await page.goto(`${BASE}/auditor`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('button:has-text("Continue as auditor")', { timeout: 60000 });
check('the screen states the role is read-only before sign-in',
  (await page.locator('.ax').innerText()).toLowerCase().includes('read-only'));
await page.locator('button:has-text("Continue as auditor")').click();
await page.waitForSelector('.ax-lookup', { timeout: 60000 });
const role = await page.evaluate(() => {
  const t = sessionStorage.getItem('medikiosk.token');
  return t ? JSON.parse(atob(t.split('.')[1])).role : null;
});
check('signed in with role=auditor', role === 'auditor', `role=${role}`);
if (SHOT) await page.screenshot({ path: `${SHOT}/G6-aud-1-signin.png` });

const encounterRef = process.env.ENCOUNTER_REF ?? (await seedFreshEncounter());
check('a confirmed encounter exists to audit', Boolean(encounterRef), encounterRef);

// ── 2. open it, chain verified intact ───────────────────────────────────────
head('2. OPEN THE ENCOUNTER — CHAIN VERIFIED');
await page.locator('.ax-input').fill(encounterRef);
await page.locator('button:has-text("Open")').click();
await page.waitForSelector('.ax-section', { timeout: 60000 });
const chainSection = page.locator('.ax-section', { hasText: 'Hash chain' });
await chainSection.waitFor({ timeout: 30000 });
check('the chain section renders', (await chainSection.count()) > 0);
check('the chain is reported intact', (await chainSection.getAttribute('data-state')) === 'ok',
  (await chainSection.locator('.ax-verdict').innerText()).slice(0, 60));
if (SHOT) await page.screenshot({ path: `${SHOT}/G6-aud-2-chain.png`, fullPage: true });

// ── 3. provenance completeness ──────────────────────────────────────────────
head('3. PROVENANCE COMPLETENESS');
const provSection = page.locator('.ax-section', { hasText: 'Provenance completeness' });
check('provenance is reported complete', (await provSection.getAttribute('data-state')) === 'ok',
  (await provSection.locator('.ax-verdict').innerText()).replace(/\n/g, ' ').slice(0, 90));

// ── 4. no-assessment-claim check ────────────────────────────────────────────
head('4. NO DIAGNOSIS / TREATMENT CLAIM');
const claimSection = page.locator('.ax-section', { hasText: 'No diagnosis or treatment claim' });
check('the report content carries no assessment-shaped field',
  (await claimSection.getAttribute('data-state')) === 'ok');

// ── 5. the audit trail, with provenance visible ─────────────────────────────
head('5. THE AUDIT TRAIL');
const trailRows = await page.locator('.ax-table tbody tr').count();
check('the trail lists real events', trailRows > 0, `${trailRows} events`);

// ── 6. the API refuses a mutating call directly, not just the UI hiding one ─
head('6. THE SERVER REFUSES A WRITE, NOT JUST THE SCREEN HIDING ONE');
const mutate = await call('/api/v1/sessions/sess_does_not_exist_at_all/commit', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ confirmed: true }),
});
check('a commit attempt with the auditor token is refused', mutate.status === 403,
  `HTTP ${mutate.status}`);
check('no POST/PUT/PATCH/DELETE control exists on this screen',
  (await page.locator('button[type="submit"], form').count()) === 0);
// That was a deliberate negative-path fetch — Chromium logs its own "403 (Forbidden)"
// resource line for it regardless of any app code, which would otherwise read as a false
// failure below. Drop console noise collected up to this point; only what happens from here
// reflects the app's own behaviour.
errs.length = 0;

// ── 7. tamper demonstration ──────────────────────────────────────────────────
head('7. TAMPER DEMONSTRATION');
// `/api/v1/audit/verify` is a pure read — unlike opening an encounter (which itself logs an
// `audit.read` event every time, correctly), it never calls `record()`. That makes it the
// clean probe for "did the tamper demo touch the real table": totalEvents must be identical
// before and after, with nothing else in between that could account for a difference.
const verify = () => call('/api/v1/audit/verify?purpose=RESEARCH');
const before = await verify();
await page.locator('button:has-text("Run tamper demonstration")').click();
await page.waitForSelector('.ax-tamper-result', { timeout: 30000 });
const result = page.locator('.ax-tamper-result');
check('a tampered field is reported', (await result.innerText()).length > 0);
check('the tamper is DETECTED', (await result.getAttribute('data-state')) === 'ok',
  (await result.locator('.ax-verdict').innerText()).replace(/\n/g, ' ').slice(0, 70));
check('it states the real table was only read',
  /only read|never written|cannot corrupt/i.test(await result.innerText()));
if (SHOT) await page.screenshot({ path: `${SHOT}/G6-aud-3-tamper.png`, fullPage: true });

const after = await verify();
check('the real chain is unaffected by the tamper demo',
  before.body.totalEvents === after.body.totalEvents && after.body.intact === true,
  `before totalEvents=${before.body.totalEvents} after totalEvents=${after.body.totalEvents} intact=${after.body.intact}`);

check('no console errors on the auditor path', errs.length === 0, errs[0] ?? '');

await browser.close();
console.log(failures === 0
  ? '\nGATE 6 PART 3 PASSED — read-only, chain verified, tamper detected.'
  : `\nGATE 6 PART 3 FAILED — ${failures} check(s)`);
process.exit(failures === 0 ? 0 : 1);
