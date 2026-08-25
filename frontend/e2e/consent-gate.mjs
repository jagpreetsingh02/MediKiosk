/**
 * GATE 2: upload is refused without the documents consent, in words a patient can act on.
 *
 * The refusal is exercised through the REAL route with a REAL session whose consent scopes
 * genuinely lack `documents` — not by stubbing the check. Invariant 6 is only meaningful if
 * the running system enforces it.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const API = process.env.API ?? 'http://127.0.0.1:8000';
const PHOTO = process.env.PHOTO;

let failures = 0;
function check(label, ok, detail = '') {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures += 1;
}

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();

// Walk to consent, then DECLINE documents while granting the rest.
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1200);
await page.getByRole('link', { name: /^Start$/ }).click();
await page.waitForSelector('.language-option', { timeout: 40000 });
await page.getByRole('button', { name: /^English/ }).click();
await page.getByRole('button', { name: /Kamala Devi|Demo Patient/ }).first().click();
await page.getByRole('button', { name: /Fill demo code/ }).click();
await page.getByRole('button', { name: /^Continue$/ }).click();
await page.waitForSelector("button:has-text(\"Start today's visit\")", { timeout: 60000 });
await page.getByRole('button', { name: /Start today's visit/ }).click();
await page.waitForSelector('.mk-toggle', { timeout: 40000 });

// Turn on every optional scope EXCEPT the one whose label mentions papers/documents.
const toggles = page.locator('.mk-toggle[role="switch"]');
const total = await toggles.count();
let declined = null;
for (let i = 0; i < total; i += 1) {
  const toggle = toggles.nth(i);
  const label = (await toggle.innerText()).toLowerCase();
  const isDocuments = /paper|prescription|report|document|photo/.test(label);
  const on = (await toggle.getAttribute('aria-checked')) === 'true';
  if (isDocuments) {
    declined = label.split('\n')[0];
    if (on) await toggle.click();          // ensure OFF
  } else if (!on) {
    await toggle.click();                   // ensure ON
  }
}
check('the documents permission was found and declined', Boolean(declined), declined ?? '');

await page.getByRole('button', { name: /Start intake/ }).click();
await page.waitForSelector('.kx-question', { timeout: 60000 });
const sessionRef = await page.evaluate(
  () => JSON.parse(sessionStorage.getItem('medikiosk.resume') ?? '{}').sessionRef,
);
const token = await page.evaluate(() => sessionStorage.getItem('medikiosk.token') ?? null);

// The chip IS still offered, and that is the better design: tapping it asks for this one
// permission in place, at the moment it is needed, rather than hiding a feature the patient
// may well want. Hiding it would leave someone who declined at the consent screen with no
// route back. What must NOT happen is the chip leading to a failure.
const chipVisible = await page.locator('.kx-records-slot .mk-chip').count();
check('the scanning path is still offered', chipVisible > 0);

await page.locator('.kx-records-slot .mk-chip').click();
await page.waitForSelector('.doc-actions, .kiosk-panel', { timeout: 30000 });
const askScreen = (await page.locator('.kiosk-panel').innerText()).toLowerCase();
check('declining leads to an ASK, not a dead end',
  /permission|allow|read your paper|old records/.test(askScreen),
  askScreen.split('\n')[0].slice(0, 60));
check('the ask does not blame the patient', !/error|denied|forbidden|invalid/.test(askScreen));

// Now hit the real route directly with the session's own credentials. This is the invariant.
// Same-origin through the dev proxy, exactly as the app itself calls it — a cross-origin
// fetch would fail on CORS and prove nothing about the gate.
const refusal = await page.evaluate(
  async ({ ref, bearer }) => {
    const body = new FormData();
    body.append(
      'file',
      new File([new Uint8Array([137, 80, 78, 71])], 'x.png', { type: 'image/png' }),
    );
    const headers = {};
    if (bearer) headers.Authorization = `Bearer ${bearer}`;
    const response = await fetch(`/api/v1/sessions/${ref}/documents`, {
      method: 'POST',
      body,
      headers,
    });
    return { status: response.status, text: await response.text() };
  },
  { ref: sessionRef, bearer: token },
);

check('upload is refused', refusal.status === 403, `HTTP ${refusal.status}`);

let message = refusal.text;
try {
  message = JSON.parse(refusal.text)?.issue?.[0]?.diagnostics ?? refusal.text;
} catch { /* not an OperationOutcome */ }

console.log('\n  ── the exact refusal string ──');
console.log(`  "${message}"\n`);

check('it is written for a patient, not about our data model',
  !/scope|session|consent_scopes|invariant|403|forbidden/i.test(message), message.slice(0, 60));
check('it says what it is about', /paper|prescription|report/i.test(message));
check('it offers a way forward', /turn (that|it) on|you can/i.test(message));
check('it does not imply they must', /carry on|say no|if you would like/i.test(message));

await browser.close();
console.log(
  failures === 0
    ? '\nCONSENT GATE PASSED — refused by the real route, in words a patient can act on.'
    : `\nCONSENT GATE FAILED — ${failures} check(s)`,
);
process.exit(failures === 0 ? 0 : 1);
