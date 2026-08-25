/**
 * GATE 2: camera capture in a real browser, and the states where there is no camera.
 *
 * Chromium's `--use-fake-device-for-media-stream` gives a REAL MediaStream from a synthetic
 * device, so getUserMedia, the live preview, the canvas grab and the resulting File are all
 * genuinely exercised — only the photons are fake. The captured JPEG is then uploaded through
 * the ordinary route, which is the part that matters: a capture that cannot be ingested is
 * not a feature.
 *
 * Localhost is a secure context, so getUserMedia is available without a certificate. The
 * phone-over-HTTPS path is documented in docs/DEMO-DAY.md and deliberately not built.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const SC = process.env.SC;

let failures = 0;
function check(label, ok, detail = '') {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures += 1;
}

async function reachDocuments(page) {
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

// ── 1. A GRANTED CAMERA, ALL THE WAY TO AN UPLOAD ──────────────────────────
{
  console.log('CAMERA GRANTED');
  const browser = await chromium.launch({
    args: [
      '--use-fake-ui-for-media-stream',
      '--use-fake-device-for-media-stream',
      '--allow-file-access-from-files',
    ],
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.grantPermissions(['camera'], { origin: BASE });
  const page = await context.newPage();

  await reachDocuments(page);
  await page.getByRole('button', { name: /Take a photo|Use the camera|Photo/i }).first().click();

  await page.waitForSelector('.camera-video', { timeout: 30000 });
  check('the live preview opens', true);

  // A real stream, not a black element.
  await page.waitForFunction(
    () => {
      const v = document.querySelector('.camera-video');
      return v && v.videoWidth > 0 && v.readyState >= 2;
    },
    null,
    { timeout: 30000 },
  );
  const dims = await page.locator('.camera-video').evaluate((v) => `${v.videoWidth}x${v.videoHeight}`);
  check('the stream is live and has frames', true, dims);

  if (SC) await page.screenshot({ path: `${SC}/G2-camera-live.png` });

  await page.getByRole('button', { name: /Take the photo/ }).click();
  await page.waitForSelector('.camera-shot', { timeout: 20000 });
  check('capture produces a still to check', true);
  check('Retake is offered before anything is sent',
    (await page.getByRole('button', { name: /Take it again/ }).count()) === 1);
  check('Use this photo is offered',
    (await page.getByRole('button', { name: /Use this photo/ }).count()) === 1);

  // Retake must reopen a live stream, not strand the patient on the still.
  await page.getByRole('button', { name: /Take it again/ }).click();
  await page.waitForSelector('.camera-video', { timeout: 20000 });
  check('Retake reopens the camera', true);
  await page.waitForFunction(() => {
    const v = document.querySelector('.camera-video');
    return v && v.videoWidth > 0;
  }, null, { timeout: 20000 });
  await page.getByRole('button', { name: /Take the photo/ }).click();
  await page.waitForSelector('.camera-shot', { timeout: 20000 });

  // The whole point: the capture goes through the ordinary upload path.
  await page.getByRole('button', { name: /Use this photo/ }).click();
  await page.waitForSelector('.extract-item, .kx-failure', { timeout: 180000 });
  const failed = await page.locator('.kx-failure').count();
  check('the captured photo was ingested by the real route', true,
    failed ? `readback: ${await page.locator('.kx-failure').getAttribute('data-reason')}` : 'entities returned');
  // The fake device shows a synthetic pattern, not a prescription, so `no_text_found` is the
  // CORRECT outcome. What is being proved is the path, not the recognition.
  if (failed) {
    const reason = await page.locator('.kx-failure').getAttribute('data-reason');
    check('and an empty capture is reported honestly, not faked',
      reason === 'no_text_found' || reason === 'too_small', reason);
  }

  await browser.close();
}

// ── 2. NO CAMERA AT ALL ────────────────────────────────────────────────────
{
  console.log('\nCAMERA UNAVAILABLE');
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  // Remove the API entirely — the "device has no camera" case.
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', { get: () => undefined });
  });

  await reachDocuments(page);
  await page.getByRole('button', { name: /Take a photo|Use the camera|Photo/i }).first().click();
  await page.waitForSelector('.camera--unavailable', { timeout: 20000 });

  const text = (await page.locator('.camera--unavailable').innerText()).toLowerCase();
  check('it is an ordinary state, not an error', (await page.locator('.kiosk-error').count()) === 0);
  check('it does not blame the patient', !/error|denied|failed|invalid|cannot access/.test(text));
  check('choosing a file is offered as the way forward',
    (await page.getByRole('button', { name: /Choose a photo instead/ }).count()) === 1);
  check('going back is still possible',
    (await page.getByRole('button', { name: /Go back/ }).count()) === 1);
  if (SC) await page.screenshot({ path: `${SC}/G2-camera-unavailable.png` });

  // And the encounter is not blocked: the file picker still works.
  await page.getByRole('button', { name: /Choose a photo instead/ }).click();
  await page.waitForTimeout(600);
  check('the file input is reachable with the camera gone',
    (await page.locator('input[type=file][accept*="image"]').count()) > 0);

  await browser.close();
}

console.log(
  failures === 0
    ? '\nCAMERA PASSED — live capture ingested, and no camera is an ordinary state.'
    : `\nCAMERA FAILED — ${failures} check(s)`,
);
process.exit(failures === 0 ? 0 : 1);
