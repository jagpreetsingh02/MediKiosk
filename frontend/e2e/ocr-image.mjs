/**
 * GATE 2, first leg: a real image through a real browser upload.
 *
 * No Python calls. `setInputFiles` on the actual file input in the running frontend, which
 * produces a genuine multipart POST to /sessions/{ref}/documents — boundary, Content-Type,
 * Content-Length and all. That is the path the three seeded lab reports never took, and the
 * whole reason "OCR works" was a claim rather than a fact.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const PHOTO = process.env.PHOTO;

let failures = 0;
function check(label, ok, detail = '') {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures += 1;
}

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();

const consoleErrors = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', (e) => consoleErrors.push(String(e)));

// ---- walk to the document step through the real flow ----------------------
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

// Grant every scope, documents included.
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
check('reached the interview', Boolean(sessionRef), sessionRef);

// The records chip is reachable from any question — that is the point of it.
await page.locator('.kx-records-slot .mk-chip').click();
await page.waitForSelector('.doc-actions', { timeout: 30000 });
check('document step reachable mid-interview', true);

// ---- the upload itself ----------------------------------------------------
const input = page.locator('input[type=file][accept*="image"]');
check('an image file input exists', (await input.count()) > 0);
check(
  'the picker accepts HEIC',
  ((await input.getAttribute('accept')) ?? '').toLowerCase().includes('heic'),
);

await input.setInputFiles(PHOTO);
console.log('  … uploading and running OCR (this is the real engine, give it time)');

await page.waitForSelector('.extract-item, .upload-item, .kiosk-error', { timeout: 180000 });

const errorShown = await page.locator('.kiosk-error').count();
if (errorShown) {
  console.log('  error on screen:', await page.locator('.kiosk-error').innerText());
}
const items = await page.locator('.extract-item').count();
check('OCR readback rendered for the photo', items > 0, `${items} extracted items`);

if (items > 0) {
  const readback = (await page.locator('.extract-list').innerText()).toLowerCase();
  const drugs = ['metformin', 'amlodipine', 'atorvastatin', 'omeprazole'];
  const found = drugs.filter((d) => readback.includes(d));
  check('structured entities extracted from the image', found.length > 0, found.join(', '));

  const band = await page.locator('.extract-band').first().innerText();
  check('confidence shown as a word, never a percentage', !band.includes('%'), band.trim());

  // --- the verification lane proper ---------------------------------------
  // The crop is an authenticated fetch of the rendered page, and the render applies the same
  // conditioning OCR used — so it is a real request with real work behind it, not an <img>
  // the browser resolves instantly. Wait for the thing, not for a guess at how long it takes.
  const started = Date.now();
  await page.locator('.kx-crop[data-loaded]').first().waitFor({ timeout: 60000 }).catch(() => {});
  console.log(`  … crop page fetched in ${((Date.now() - started) / 1000).toFixed(1)}s`);

  const crops = await page.locator('.kx-crop[data-loaded]').count();
  check('every row shows the crop it was read from', crops >= items, `${crops} crops`);

  if (crops > 0) {
    // The crop must be a real, loaded image — not a broken one that merely occupies space.
    const painted = await page.locator('.kx-crop[data-loaded]').first().evaluate((el) => {
      const bg = getComputedStyle(el).backgroundImage;
      return bg.startsWith('url(') && el.getBoundingClientRect().height > 8;
    });
    check('the crop is a real page image, not a broken one', painted);
  }

  const first = page.locator('.extract-item').first();
  check('three actions offered, not two',
    (await first.getByRole('button', { name: /^Confirm$/ }).count()) === 1 &&
    (await first.getByRole('button', { name: /^Correct$/ }).count()) === 1 &&
    (await first.getByRole('button', { name: /^Discard$/ }).count()) === 1);

  // Correct opens an editable field carrying the current reading.
  await first.getByRole('button', { name: /^Correct$/ }).click();
  const field = first.locator('.extract-correct input');
  await field.waitFor({ timeout: 10000 });
  check('Correct opens an editable value', (await field.inputValue()).length > 0);
  await first.getByRole('button', { name: /^Cancel$/ }).click();

  // Confirm one row — this is what makes it durable.
  const rowText = (await first.locator('.extract-name').innerText()).trim();
  await first.getByRole('button', { name: /^Confirm$/ }).click();
  await first.locator('.extract-outcome').waitFor({ timeout: 30000 });
  check('a confirmed row is marked confirmed',
    (await first.locator('.extract-outcome').innerText()).toLowerCase().includes('confirmed'),
    rowText);
  console.log(`  CONFIRMED_ROW=${rowText}`);
  console.log(`  SESSION_REF=${sessionRef}`);
}

check('no console errors during upload', consoleErrors.length === 0, consoleErrors[0] ?? '');

if (process.env.SHOT) {
  await page.screenshot({ path: `${process.env.SHOT}/G2-readback.png`, fullPage: false });
  console.log('  screenshot ->', `${process.env.SHOT}/G2-readback.png`);
}

await browser.close();
console.log(
  failures === 0
    ? '\nIMAGE UPLOAD PASSED — a photograph went through the browser and came back as entities.'
    : `\nIMAGE UPLOAD FAILED — ${failures} check(s)`,
);
process.exit(failures === 0 ? 0 : 1);
