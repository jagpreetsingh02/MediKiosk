/**
 * The front door is two doors, and each opens onto its own workflow.
 * `node e2e/two-doors.mjs` with the stack running (`make demo`).
 *
 * `tests/test_role_separation.py` proves the import graph is separated and that the routes
 * exist. It cannot prove that the two doors are actually on the screen, that they are
 * reachable with a click, or that neither workspace paints the other's chrome. That is what
 * this walks.
 *
 * WHAT IT ASSERTS, AND WHY EACH ONE:
 *
 *   both doors are visible on the first screen — the split is worthless if the doctor's half
 *   of the product is still a link in a corner
 *
 *   the patient door leads to a patient sign-in and NOT to a queue — the single most likely
 *   regression here is a route swap, and it is silent
 *
 *   the doctor door leads to staff sign-in, and the workspace opens by naming who is next
 *   rather than telling the doctor to pick somebody
 *
 *   neither screen carries the other's controls — a text scan for the words that belong to
 *   exactly one role. Crude on purpose: it keeps working when the components are rewritten.
 *
 * Navigation waits on the DOM rather than an idle network, for the reason smoke.mjs gives at
 * length: the ambient background video means the network is never idle.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const failures = [];

const check = (name, ok, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
};

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

// ── the front door ─────────────────────────────────────────────────────────
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.hx-doors', { timeout: 60000 });

const doors = await page.locator('.hx-door').allInnerTexts();
check('the front door offers two doors', doors.length === 2, `${doors.length} found`);
check(
  'one door is the patient',
  doors.some((t) => /patient/i.test(t)),
  doors.join(' | '),
);
check(
  'one door is the doctor',
  doors.some((t) => /doctor/i.test(t)),
  doors.join(' | '),
);

// Invariant 1 has not moved off the first screen.
check(
  'the no-diagnosis line is still above the fold',
  /does not diagnose/i.test(await page.locator('.hx-badge').innerText()),
);

// ── the patient door ───────────────────────────────────────────────────────
await page.locator('.hx-door', { hasText: /patient/i }).first().click();
await page.waitForURL('**/patient', { timeout: 30000 });
await page.waitForSelector('.pp', { timeout: 30000 });

const patientText = await page.locator('.pp').innerText();
check('the patient door opens the patient surface', /your records/i.test(patientText));
check(
  'the patient surface carries no queue',
  !/queue|waiting/i.test(patientText),
  patientText.slice(0, 120),
);
check(
  'the patient surface carries no commit control',
  !/commit|attest/i.test(patientText),
);

// ── the doctor door ────────────────────────────────────────────────────────
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.hx-doors', { timeout: 60000 });
await page.locator('.hx-door', { hasText: /doctor/i }).first().click();
await page.waitForURL('**/doctor', { timeout: 30000 });
await page.waitForSelector('.phys-login-card', { timeout: 30000 });

const loginText = await page.locator('.phys-login-card').innerText();
check('the doctor door opens staff sign-in', /clinician/i.test(loginText));

// Signed in, the workspace must say who is next rather than "select a patient".
await page.locator('.phys-login-card button', { hasText: /^Sign in$/ }).click();
await page.waitForSelector('.phys-next', { timeout: 30000 });
const nextText = await page.locator('.phys-next').innerText();
check(
  'the workspace names the next patient, or says nobody is waiting',
  /next to assess|nobody is waiting/i.test(nextText),
  nextText.slice(0, 120),
);

const doctorText = await page.locator('.phys').innerText();
check(
  "the doctor's workspace carries no patient-portal controls",
  !/sign out|download pdf|my papers/i.test(doctorText),
);

await browser.close();

console.log('');
if (failures.length) {
  console.error(`FAILED: ${failures.join(', ')}`);
  process.exit(1);
}
console.log('two-doors: all checks passed');
