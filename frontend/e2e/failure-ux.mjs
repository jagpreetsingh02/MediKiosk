/**
 * GATE 2: the failure states, in the real browser, through the real route.
 *
 * Each cause must produce its OWN screen with its OWN most-useful action, and none of them may
 * leak a backend name, a config key or an HTTP status to a patient.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const SC = process.env.SC;

let failures = 0;
function check(label, ok, detail = '') {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures += 1;
}

/** Nothing on a patient's screen may contain any of these, on any branch. */
const FORBIDDEN = [
  'tesseract', 'textlayer', 'pypdfium', 'pillow', 'traceback', 'exception',
  'max_upload_bytes', 'consent_scopes', 'null', 'undefined', 'http 4', 'http 5',
  '403', '413', '422', 'stack', '.py',
];

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

async function reachDocumentStep() {
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
  await page.locator('.kx-records-slot .mk-chip').click();
  await page.waitForSelector('.doc-actions', { timeout: 30000 });
}

await reachDocumentStep();

const cases = [
  ['fail_small.png',  'too_small',        'image', /closer/i],
  ['fail_broken.png', 'unreadable_image', 'image', /camera|photo/i],
  ['fail_blank.png',  'no_text_found',    'image', /handwrit/i],
  ['fail_big.png',    'too_large',        'image', /camera|one page/i],
  ['fail_type.zip',   'unsupported_type', 'pdf',   /photograph|pdf/i],
];

for (const [file, expected, picker, expectedCopy] of cases) {
  const input = page.locator(
    picker === 'image' ? 'input[type=file][accept*="image"]' : 'input[type=file][accept*="pdf"]',
  );
  await input.setInputFiles(`${SC}/${file}`);
  await page.waitForSelector('.kx-failure', { timeout: 180000 });

  const reason = await page.locator('.kx-failure').getAttribute('data-reason');
  const text = (await page.locator('.kx-failure').innerText()).toLowerCase();

  check(`${file} -> ${expected}`, reason === expected, `got "${reason}"`);
  check(`  its copy names the cause`, expectedCopy.test(text));
  check(
    `  three ways forward are offered`,
    (await page.getByRole('button', { name: /Take the photo again/ }).count()) === 1 &&
      (await page.getByRole('button', { name: /Upload a different file/ }).count()) === 1 &&
      (await page.getByRole('button', { name: /Type it in myself/ }).count()) === 1,
  );
  const leak = FORBIDDEN.find((word) => text.includes(word));
  check(`  nothing technical leaks to the patient`, !leak, leak ? `found "${leak}"` : '');

  if (SC && expected === 'no_text_found') {
    await page.screenshot({ path: `${SC}/G2-failure-handwriting.png` });
  }

  // Back to the document step for the next case.
  await page.getByRole('button', { name: /Upload a different file/ }).click();
  await page.waitForTimeout(400);
  const back = page.locator('.doc-actions');
  if (!(await back.count())) {
    await page.locator('.kx-records-slot .mk-chip').click().catch(() => {});
    await page.waitForSelector('.doc-actions', { timeout: 30000 }).catch(() => {});
  }
}

await browser.close();
console.log(
  failures === 0
    ? '\nFAILURE UX PASSED — every cause named, three ways forward, nothing technical leaked.'
    : `\nFAILURE UX FAILED — ${failures} check(s)`,
);
process.exit(failures === 0 ? 0 : 1);
