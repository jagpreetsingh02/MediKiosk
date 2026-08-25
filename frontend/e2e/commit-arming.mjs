/**
 * Regression suite for the commit arming gate.
 *
 * WHAT BROKE, AND WHY IT NEEDED A BROWSER TO CATCH IT.
 *
 * Commit used to arm from a `scroll` event on the summary column. A scroll event only fires
 * if there is something to scroll, and that one fact produced a class of bug no unit test
 * could see: a physician who had genuinely read the entire summary being permanently unable
 * to commit it. Every case below is a real way to reach that state.
 *
 *   1. SHORT CONTENT   A brief encounter fits the viewport. Nothing scrolls, so under the old
 *                      mechanism the gate never opened. The shorter the consultation, the
 *                      more completely the product broke.
 *   2. 200% ZOOM       Zoom reflows the layout and changes whether a scrollbar exists at all.
 *   3. KEYBOARD-ONLY   `j`/`k` use scrollIntoView({block:'nearest'}), which does nothing when
 *                      the target is already visible. A physician could traverse every line
 *                      to the last one without ever generating a qualifying scroll event.
 *
 * These assert the mechanism, not the styling: that the checkbox arms, that the button
 * follows the checkbox and not the scrollbar, and that the attestation is genuinely required.
 *
 * Run with the stack up:  BASE=http://127.0.0.1:5173 node e2e/commit-arming.mjs
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';

let failures = 0;
function check(label, ok, detail = '') {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures += 1;
}

/** Sign in and open the first queue entry that actually renders a summary. */
async function openASummary(page) {
  await page.goto(`${BASE}/physician`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(600);
  const signIn = page.getByRole('button', { name: /Sign in|Continue|Enter/ }).first();
  if (await signIn.count()) await signIn.click();
  await page.waitForSelector('.queue-item', { timeout: 40000 });

  const total = await page.locator('.queue-item').count();
  for (let i = 0; i < total; i += 1) {
    await page.locator('.queue-item').nth(i).click();
    try {
      await page.waitForSelector('.summary-line', { timeout: 20000 });
      return true;
    } catch {
      /* expired or purged session — try the next one */
    }
  }
  return false;
}

const commitButton = (page) => page.getByRole('button', { name: /Confirm and commit/ });
const attestBox = (page) => page.locator('.phys-attest input[type=checkbox]');

/**
 * Opening a session fires four sequential requests, and `busy` correctly blocks commit until
 * all of them land — on a remote database that is several seconds. Waiting for a fixed
 * interval here made this suite report a bug that did not exist, so it waits for the actual
 * condition instead.
 */
async function waitForCommitEnabled(page, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (!(await commitButton(page).isDisabled())) return true;
    await page.waitForTimeout(250);
  }
  return false;
}

/** The load is finished when the record has settled. Asserting "still disabled" before this
 *  would be asserting against the loading state, not against the gate. */
async function waitUntilLoaded(page, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await attestBox(page).isEnabled()) return true;
    await page.waitForTimeout(250);
  }
  return false;
}

const browser = await chromium.launch();

// ── 1. SHORT CONTENT THAT NEVER SCROLLS ────────────────────────────────────
// The case that motivated the rewrite. The column is forced tall enough to hold the whole
// summary, so no scroll event can ever fire; the gate must still open.
{
  console.log('SHORT CONTENT (nothing to scroll)');
  const page = await (await browser.newContext({ viewport: { width: 1600, height: 1000 } })).newPage();
  if (!(await openASummary(page))) {
    check('a summary could be opened', false, 'no live session in the queue');
  } else {
    // Make the column taller than its content, reproducing a brief encounter. Measured twice:
    // the summary grows after first paint as images and late sections land, so a height fixed
    // from the first measurement is stale by the time it is asserted on.
    const fit = async () => {
      await page.locator('.phys-main').evaluate((el) => {
        el.style.height = 'auto';
        el.style.maxHeight = 'none';
        el.style.overflowY = 'auto';
        el.style.height = `${el.scrollHeight + 600}px`;
      });
      await page.waitForTimeout(800);
    };
    await fit();
    await fit();

    const metrics = await page.locator('.phys-main').evaluate((el) => ({
      scrollHeight: el.scrollHeight,
      clientHeight: el.clientHeight,
      scrollable: el.scrollHeight > el.clientHeight + 1,
    }));
    check('the column genuinely cannot scroll', !metrics.scrollable,
      `${metrics.scrollHeight} content vs ${metrics.clientHeight} viewport`);

    check('attestation checkbox is enabled without any scroll', await waitUntilLoaded(page));
    check('commit is still blocked before attesting', await commitButton(page).isDisabled());

    await attestBox(page).check();
    check('commit arms once attested', await waitForCommitEnabled(page));

    await attestBox(page).uncheck();
    await page.waitForTimeout(300);
    check('un-attesting disarms commit again', await commitButton(page).isDisabled());
  }
  await page.close();
}

// ── 2. 200% BROWSER ZOOM ───────────────────────────────────────────────────
// Zoom reflows everything and changes whether a scrollbar exists. deviceScaleFactor is not
// zoom; the honest reproduction is a viewport half the size at double the CSS pixel ratio.
{
  console.log('200% BROWSER ZOOM');
  const context = await browser.newContext({
    viewport: { width: 800, height: 500 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  if (!(await openASummary(page))) {
    check('a summary could be opened at 200%', false, 'no live session in the queue');
  } else {
    await page.waitForTimeout(600);
    check('the bar is still reachable at 200%', await commitButton(page).count() > 0);

    // Scroll the column to the end the way a physician would at this zoom level.
    await page.locator('.phys-main').evaluate((el) => {
      el.style.scrollBehavior = 'auto';
      el.scrollTo(0, el.scrollHeight);
    });
    check('attestation arms after reaching the end at 200%', await waitUntilLoaded(page));

    await attestBox(page).check();
    check('commit arms at 200% zoom', await waitForCommitEnabled(page));
  }
  await page.close();
  await context.close();
}

// ── 3. KEYBOARD-ONLY TRAVERSAL ─────────────────────────────────────────────
// No pointer events at all: `j` to the last line, Tab to the checkbox, Space to tick it.
{
  console.log('KEYBOARD-ONLY TRAVERSAL');
  const page = await (await browser.newContext({ viewport: { width: 1600, height: 1000 } })).newPage();
  if (!(await openASummary(page))) {
    check('a summary could be opened for keyboard traversal', false, 'no live session');
  } else {
    const lines = await page.locator('.summary-line').count();
    for (let i = 0; i < lines + 4; i += 1) {
      await page.keyboard.press('j');
      await page.waitForTimeout(40);
    }
    check('reaching the last line by keyboard arms the attestation',
      await waitUntilLoaded(page), `${lines} lines traversed`);

    // Reach the checkbox with Tab alone and toggle it with the keyboard.
    let reached = false;
    for (let i = 0; i < 60 && !reached; i += 1) {
      await page.keyboard.press('Tab');
      reached = await page.evaluate(
        () => document.activeElement?.matches('.phys-attest input[type=checkbox]') ?? false,
      );
    }
    check('the attestation is reachable by Tab alone', reached);

    if (reached) {
      await page.keyboard.press('Space');
      await page.waitForTimeout(300);
      check('Space ticks the attestation', await attestBox(page).isChecked());
      check('commit arms from keyboard only', await waitForCommitEnabled(page));
    }
  }
  await page.close();
}

await browser.close();

console.log(
  failures === 0
    ? '\nCOMMIT ARMING PASSED — the gate opens by observation, and only an attestation commits.'
    : `\nCOMMIT ARMING FAILED — ${failures} check(s)`,
);
process.exit(failures === 0 ? 0 : 1);
