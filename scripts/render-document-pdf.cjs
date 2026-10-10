const { chromium } = require('@playwright/test');
const { pathToFileURL } = require('node:url');
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => route.request().url().startsWith('file:') ? route.continue() : route.abort());
    await page.goto(pathToFileURL(process.argv[2]).href);
    await page.pdf({ path: process.argv[3], format: 'A4', printBackground: true, preferCSSPageSize: true });
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exit(1); });
