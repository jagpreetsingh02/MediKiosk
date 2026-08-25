/**
 * GATE 2, end to end, real browser only.
 *
 *   1. a scanned PDF with NO text layer, uploaded through the browser
 *   2. a lab-report PHOTOGRAPH uploaded through the browser  (the honest reseed)
 *   3. the HbA1c row confirmed in the verification lane
 *   4. the physician commits, which is what makes it durable
 *
 * The database read and the medication-history screenshot happen after this, against the row
 * this run produced. Nothing here is a Python call into the pipeline.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const SC = process.env.SC;
const LAB_PHOTO = `${SC}/lab_2026_photo.jpg`;
const SCANNED_PDF = `${SC}/scanned_no_textlayer.pdf`;

let failures = 0;
function check(label, ok, detail = '') {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures += 1;
}

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();

await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1100);
await page.getByRole('link', { name: /^Start$/ }).click();
await page.waitForSelector('.language-option', { timeout: 40000 });
await page.getByRole('button', { name: /^English/ }).click();
await page.getByRole('button', { name: /Kamala Devi|Demo Patient/ }).first().click();
await page.getByRole('button', { name: /Fill demo code/ }).click();
await page.getByRole('button', { name: /^Continue$/ }).click();
await page.waitForSelector("button:has-text(\"Start today's visit\")", { timeout: 60000 });
await page.getByRole('button', { name: /Start today's visit/ }).click();
await page.waitForSelector('.mk-toggle', { timeout: 40000 });
for (let i = 0; i < 6; i += 1) {
  const off = page.locator('.mk-toggle[aria-checked="false"]');
  if (!(await off.count())) break;
  await off.first().click();
}
await page.getByRole('button', { name: /Start intake/ }).click();
await page.waitForSelector('.kx-question', { timeout: 60000 });
const sessionRef = await page.evaluate(
  () => JSON.parse(sessionStorage.getItem('medikiosk.resume') ?? '{}').sessionRef,
);
console.log(`  SESSION_REF=${sessionRef}`);

async function openDocuments() {
  if (!(await page.locator('.doc-actions').count())) {
    await page.locator('.kx-records-slot .mk-chip').click();
    await page.waitForSelector('.doc-actions', { timeout: 30000 });
  }
}

// ── 1. SCANNED PDF WITH NO TEXT LAYER ──────────────────────────────────────
await openDocuments();
await page.locator('input[type=file][accept*="pdf"]').setInputFiles(SCANNED_PDF);
await page.waitForSelector('.extract-item, .kx-failure', { timeout: 180000 });
const pdfFailed = await page.locator('.kx-failure').count();
check('a scanned PDF with no text layer is read', pdfFailed === 0,
  pdfFailed ? await page.locator('.kx-failure').getAttribute('data-reason') : 'entities returned');
if (!pdfFailed) {
  const text = (await page.locator('.extract-list').innerText()).toLowerCase();
  check('  and its entities came back', /metformin|amlodipine|polyclinic|diabetes/.test(text));
  if (SC) await page.screenshot({ path: `${SC}/G2-scanned-pdf.png` });
  await page.getByRole('button', { name: /^Done$/ }).click();
  await page.waitForTimeout(800);
}

// ── 2. THE LAB REPORT PHOTOGRAPH (the honest reseed) ───────────────────────
await openDocuments();
await page.locator('input[type=file][accept*="image"]').setInputFiles(LAB_PHOTO);
await page.waitForSelector('.extract-item, .kx-failure', { timeout: 180000 });
check('the lab-report photograph is read', (await page.locator('.kx-failure').count()) === 0);

const readback = (await page.locator('.extract-list').innerText());
check('HbA1c is among the readings', /hba1c/i.test(readback), readback.split('\n')[0]);

// ── 3. CONFIRM THE HbA1c ROW ───────────────────────────────────────────────
const rows = page.locator('.extract-item');
const count = await rows.count();
let confirmed = null;
for (let i = 0; i < count; i += 1) {
  const row = rows.nth(i);
  const name = (await row.locator('.extract-name').innerText()).trim();
  if (/hba1c/i.test(name)) {
    await row.getByRole('button', { name: /^Confirm$/ }).click();
    await row.locator('.extract-outcome').waitFor({ timeout: 30000 });
    confirmed = name;
    break;
  }
}
check('the HbA1c row was confirmed by a human', Boolean(confirmed), confirmed ?? 'not found');
console.log(`  CONFIRMED_ROW=${confirmed}`);
if (SC) await page.screenshot({ path: `${SC}/G2-lab-readback.png` });

await page.getByRole('button', { name: /^Done$/ }).click();
await page.waitForTimeout(1000);

// ── 4. PHYSICIAN COMMITS — what makes it durable ───────────────────────────
const doc = await (await browser.newContext({ viewport: { width: 1600, height: 1000 } })).newPage();
await doc.goto(`${BASE}/physician?session=${sessionRef}`, { waitUntil: 'domcontentloaded' });
await doc.waitForTimeout(900);
const signIn = doc.getByRole('button', { name: /Sign in|Continue|Enter/ }).first();
if (await signIn.count()) await signIn.click();
await doc.waitForSelector('.summary-line', { timeout: 90000 });

await doc.locator('.phys-main').evaluate((el) => {
  el.style.scrollBehavior = 'auto';
  el.scrollTo(0, el.scrollHeight);
});
const attest = doc.locator('.phys-attest input[type=checkbox]');
for (let i = 0; i < 80 && !(await attest.isEnabled()); i += 1) await doc.waitForTimeout(250);
await attest.check();
const commit = doc.getByRole('button', { name: /Confirm and commit/ });
for (let i = 0; i < 80 && (await commit.isDisabled()); i += 1) await doc.waitForTimeout(250);
await commit.click();
await doc.waitForFunction(
  () => (document.querySelector('.phys-bottom')?.textContent ?? '').includes('committed'),
  null,
  { timeout: 120000 },
);
check('the physician committed the encounter', true,
  (await doc.locator('.phys-bottom').innerText()).replace(/\n/g, ' ').slice(0, 80));

await browser.close();
console.log(
  failures === 0 ? '\nGATE 2 BROWSER LEGS PASSED' : `\nGATE 2 FAILED — ${failures} check(s)`,
);
process.exit(failures === 0 ? 0 : 1);
