/** Sample the hero's REAL rendered colours: the video ground, at several moments. */
import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
await p.goto('http://localhost:5177/', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(3000);

const samples = [];
for (const t of [0, 2, 4, 6, 8, 10]) {
  await p.evaluate((t) => { const v = document.querySelector('.mk-ambient__video'); if (v) v.currentTime = t; }, t);
  await p.waitForTimeout(700);
  const px = await p.evaluate(() => {
    const v = document.querySelector('.mk-ambient__video');
    const c = document.createElement('canvas');
    c.width = 32; c.height = 20;
    const g = c.getContext('2d');
    g.drawImage(v, 0, 0, 32, 20);
    const d = g.getImageData(0, 0, 32, 20).data;
    const out = [];
    for (let i = 0; i < d.length; i += 4) out.push([d[i], d[i+1], d[i+2]]);
    return out;
  });
  samples.push(...px);
}
console.log(JSON.stringify(samples));
await b.close();
