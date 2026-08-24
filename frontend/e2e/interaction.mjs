/**
 * The interaction changes, driven through a real browser. `node e2e/interaction.mjs`.
 *
 * These are the four things that were broken in the running app and could not be caught by a
 * unit test, because each of them is a property of the *rendered* page:
 *
 *   1. a single-choice tap advances with no Continue button anywhere;
 *   2. Back reopens the previous question and shows the answer already given;
 *   3. changing that answer supersedes rather than overwrites;
 *   4. the consent screen presents Required and Optional separately, with one audio control.
 *
 * Speech synthesis is stubbed rather than played: headless Chromium ships no voices, so a
 * real `speak()` would resolve `no-voice` and prove nothing. The stub records what the page
 * *asked* to say, which is the part the application controls — whether a voice exists is the
 * device's business, and the UI is tested for saying so honestly.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'http://127.0.0.1:5173';
const failures = [];
const errors = [];

const check = (name, ok, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
};

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });

// Record every utterance the page requests, and report success so the UI takes the
// "spoken" path. What we are testing is that the app asks; the engine is the device's.
await ctx.addInitScript(() => {
  window.__spoken = [];
  const voice = { name: 'Test Voice', lang: 'en-IN', default: true, localService: true, voiceURI: 'test' };
  // `speechSynthesis` is an accessor on the prototype, so a plain assignment is silently
  // ignored and the real (voiceless, in headless Chromium) engine stays in place. It has to
  // be redefined.
  Object.defineProperty(window, 'speechSynthesis', {
    configurable: true,
    value: {
      speaking: false,
      getVoices: () => [voice],
      addEventListener() {},
      removeEventListener() {},
      cancel() {},
      pause() {},
      resume() {},
      speak(utterance) {
        window.__spoken.push(utterance.text);
        setTimeout(() => {
          utterance.onstart?.();
          utterance.onend?.();
        }, 0);
      },
    },
  });
  window.SpeechSynthesisUtterance = class {
    constructor(text) {
      this.text = text;
      this.lang = '';
      this.rate = 1;
      this.pitch = 1;
      this.volume = 1;
    }
  };
});

const page = await ctx.newPage();
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 160)}`);
});
page.on('response', (r) => {
  if (r.status() >= 400) {
    errors.push(`HTTP ${r.status()} ${r.request().method()} ${r.url().replace(BASE, '')}`);
  }
});

// ------------------------------------------------------------------ login
await page.goto(BASE, { waitUntil: 'networkidle' });
await page.getByRole('link', { name: /^Start$/ }).click();
await page.waitForSelector('.language-option', { timeout: 10000 });
await page.getByRole('button', { name: /^English/ }).click();

await page.getByRole('button', { name: /Kamala Devi/ }).click();
await page.getByRole('button', { name: /Fill demo code/ }).click();
await page.getByRole('button', { name: /^Continue$/ }).click();

// Patient memory screen, then into consent.
await page.waitForSelector("button:has-text(\"Start today's visit\")", { timeout: 10000 });
await page.getByRole('button', { name: /Start today's visit/ }).click();

// ------------------------------------------------------------------ consent
await page.waitForSelector('.mk-toggle', { timeout: 10000 });

check('consent splits required from optional', (await page.locator('.kx-consent-group__head').count()) === 2);
check('exactly one required row', (await page.locator('.kx-consent-required').count()) === 1);
check('optional scopes are switches', (await page.locator('.mk-toggle[role="switch"]').count()) >= 3);
check(
  'one audio control, not one per scope',
  (await page.getByRole('button', { name: /Hear this page/i }).count()) === 1,
);
check(
  'no giant per-scope Read aloud buttons remain',
  (await page.getByRole('button', { name: /^Read aloud$/ }).count()) === 0,
);
check('one clear CTA', (await page.getByRole('button', { name: /Start intake/i }).count()) === 1);

// Turn on the microphone and documents scopes.
const switches = page.locator('.mk-toggle[role="switch"]');
await switches.nth(0).click();
await switches.nth(1).click();

await page.getByRole('button', { name: /Hear this page/i }).click();
await page.waitForTimeout(400);
const consentSpoken = await page.evaluate(() => window.__spoken.length);
check('consent page requests audio', consentSpoken > 0, `${consentSpoken} utterance(s)`);

await page.getByRole('button', { name: /Start intake/i }).click();

// ------------------------------------------------------------------ interview
await page.waitForSelector('.kx-question', { timeout: 10000 });

// The prompt is spoken from an effect, and speakTts() waits ~60ms for the cancel/speak
// race before it reaches the engine. Poll rather than sampling once.
await page
  .waitForFunction(
    (before) => window.__spoken.length > before,
    consentSpoken,
    { timeout: 5000 },
  )
  .catch(() => undefined);
const spokenNow = await page.evaluate(() => window.__spoken);
check(
  'question is read aloud without any tap',
  spokenNow.length > consentSpoken,
  spokenNow[spokenNow.length - 1]?.slice(0, 46),
);
check(
  'no "Continue" button on a single-choice question',
  (await page.getByRole('button', { name: /^Continue$/ }).count()) === 0,
);
check('Back is present', (await page.getByRole('button', { name: /go back to the previous question/i }).count()) === 1);
check('Back is disabled on the first question', await page.getByRole('button', { name: /go back to the previous question/i }).isDisabled());

const firstPrompt = await page.locator('.kx-question').textContent();
const firstOption = page.locator('.kx-option').first();
const firstLabel = (await firstOption.textContent())?.trim();
await firstOption.click();

await page.waitForFunction(
  (previous) => document.querySelector('.kx-question')?.textContent !== previous,
  firstPrompt,
  { timeout: 10000 },
);
check('one tap advances to the next question', true, `answered "${firstLabel}"`);

const secondPrompt = await page.locator('.kx-question').textContent();
check('Back becomes enabled once something is answered', !(await page.getByRole('button', { name: /go back to the previous question/i }).isDisabled()));

// ------------------------------------------------------------------ back
await page.getByRole('button', { name: /go back to the previous question/i }).click();
await page.waitForSelector('.reopened-note', { timeout: 10000 });

const backPrompt = await page.locator('.kx-question').textContent();
check('Back reopens the previous question', backPrompt === firstPrompt, backPrompt?.slice(0, 48));
check(
  'the previous answer is shown',
  (await page.locator('.reopened-note').textContent())?.includes(firstLabel ?? '~'),
);
check(
  'the previous answer is shown as selected',
  (await page.locator('.kx-option[aria-checked="true"]').count()) === 1,
);

// Change it to a different option.
const options = page.locator('.kx-option');
const optionCount = await options.count();
let changed = firstLabel;
for (let i = 0; i < optionCount; i += 1) {
  const label = (await options.nth(i).textContent())?.trim();
  if (label && label !== firstLabel) {
    changed = label;
    await options.nth(i).click();
    break;
  }
}
await page.waitForFunction(
  (previous) => document.querySelector('.kx-question')?.textContent !== previous,
  backPrompt,
  { timeout: 10000 },
);
check('a changed answer submits on one tap and moves on', true, `changed to "${changed}"`);
check(
  'the interview continues from the corrected answer',
  (await page.locator('.kx-question').textContent()) !== backPrompt,
);

// ------------------------------------------------------------------ documents
check(
  'documents are reachable from inside the interview',
  (await page.locator('.kx-records-slot .mk-chip').count()) === 1,
);
await page.locator('.kx-records-slot .mk-chip').click();
await page.waitForSelector('.doc-actions', { timeout: 10000 });

for (const label of ['Take Photo', 'Upload Image', 'Upload PDF', 'Skip']) {
  check(`document screen offers ${label}`, (await page.getByRole('button', { name: label }).count()) === 1);
}
const bodyText = (await page.locator('body').textContent()) ?? '';
check('no OCR_BACKEND instruction anywhere on screen', !bodyText.includes('OCR_BACKEND'));
check('no tesseract jargon on screen', !/tesseract/i.test(bodyText));

console.log('');
if (errors.length) {
  console.log('PAGE ERRORS');
  for (const e of [...new Set(errors)]) console.log(`  ${e}`);
}
console.log(
  failures.length ? `FAILED: ${failures.join(', ')}` : `All ${'checks'} passed.`,
);

await browser.close();
process.exit(failures.length || errors.length ? 1 : 0);
