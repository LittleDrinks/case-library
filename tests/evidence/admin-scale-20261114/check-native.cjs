const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const fixture = require(process.env.PENPOT_CASES || './native-cases.json');

async function main() {
  const browser = await chromium.connectOverCDP(process.env.PENPOT_CDP_URL || 'http://127.0.0.1:9223');
  const context = browser.contexts()[0];
  const viewer = await context.newPage();
  const popups = [];
  const results = [];
  viewer.on('popup', page => popups.push(page));
  try {
    for (const route of fixture.cases) {
      const url = new URL(process.env.PENPOT_PUBLIC_URI || 'http://localhost:9001');
      url.search = new URLSearchParams({
        screen: 'viewer', 'file-id': fixture.fileId, 'page-id': fixture.pageId,
        'frame-id': route.start, section: 'interactions', zoom: 'fit',
      }).toString();
      await viewer.goto(url.href);
      const before = context.pages().length;
      await viewer.locator(`[id*="${route.shapeId}"]`).filter({ visible: true }).first().click({ timeout: 30000 });
      await viewer.locator(`[id*="${route.destination}"]`).filter({ visible: true }).first().waitFor({ timeout: 15000 });
      assert.equal(context.pages().length, before, `${route.name} 新开了标签页`);
      assert.equal(popups.length, 0, `${route.name} 触发了弹出窗口`);
      results.push({ name: route.name, passed: true, addedTabs: 0 });
    }
    require('node:fs').writeFileSync(__dirname+'/'+(process.env.PENPOT_RESULTS || 'native-results.json'), JSON.stringify({passed:results.length,results},null,2));console.log('Native prototype paths passed:',results.length);
  } finally {
    for (const popup of popups) await popup.close();
    await viewer.close();
    await browser.close();
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
