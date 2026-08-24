import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';

const preview = spawn('node_modules/.bin/vite', ['preview', '--config', 'frontend/vite.config.mjs'], {
  stdio: 'ignore', detached: true,
});
await new Promise((r) => setTimeout(r, 2500));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('pageerror', (error) => console.error('PAGE ERROR:', error.message));
page.on('console', (message) => {
  if (message.type() === 'error') console.error('CONSOLE ERROR:', message.text());
});
try {
  await page.route('**/beefoundrysim-config.json', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      apiBaseUrl: 'http://127.0.0.1:8876', webSocketBaseUrl: 'ws://127.0.0.1:8876',
      apiVersion: 'v1', projectId: null, accessToken: 'e2e-token',
    }),
  }));
  await page.goto('http://127.0.0.1:4173');
  await page.waitForSelector('#asset-list', { timeout: 10000 });
  await page.locator('[data-asset-id="openusd_franka_quality_4b35c27245"]').click();
  await page.waitForTimeout(2000);
  console.log('scene-tree panda:', await page.locator('#scene-tree').textContent().then((t) => t?.includes('panda_link7')));
  console.log('arm tab count:', await page.locator('[data-bottom-tab="arm-control"]').count());
  console.log('traj tab active:', await page.locator('.dock-tab.active[data-bottom-tab="trajectory-editor"]').count());
  console.log('traj load visible:', await page.locator('[data-trajectory-command="load"]').isVisible());
  console.log('bottom tabs:', await page.locator('[data-leaf-id="center-bottom"] .dock-tab').allTextContents());
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await page.waitForTimeout(3000);
  console.log('badge after run:', await page.locator('#simulation-badge').textContent());
  const state1 = JSON.parse(await page.evaluate(() => window.beefoundrysimEditor.getStateJson()));
  console.log('store status:', state1.simulationStatus, 'sim state status:', state1.simulationState?.status ?? null);
  await page.locator('[data-command="stop"]').click();
  await page.waitForTimeout(2000);
  console.log('badge after stop:', await page.locator('#simulation-badge').textContent());
} catch (error) {
  console.error('FAILED:', error);
} finally {
  await browser.close();
  process.kill(-preview.pid, 'SIGTERM');
}
