// PatchMon dashboard login + screenshot via Playwright/Chromium.
// Usage: node scripts/screenshot.js [output_path]
// Requires: npm install playwright && npx playwright install chromium
// Env vars: PATCHMON_URL, PATCHMON_USERNAME, PATCHMON_PASSWORD (must already be set)

const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const outPath = process.argv[2] || '/tmp/patchmon_dash.png';
  const url = process.env.PATCHMON_URL || 'https://patchmon.net';
  const user = process.env.PATCHMON_USERNAME;
  const pass = process.env.PATCHMON_PASSWORD;

  if (!user || !pass) {
    console.error('PATCHMON_USERNAME and PATCHMON_PASSWORD must be set');
    process.exit(1);
  }

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.fill('input[placeholder*="Username"], input[name="username"], input[type="text"]', user);
  await page.fill('input[type="password"]', pass);
  await page.click('button:has-text("Sign in")');
  await page.waitForTimeout(3000);
  await page.screenshot({ path: outPath, fullPage: false });
  await browser.close();
  console.log(outPath);
})();
