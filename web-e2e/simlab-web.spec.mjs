import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const apiBaseUrl = 'http://127.0.0.1:8876';
const accessToken = 'e2e-token';
const authHeaders = { Authorization: `Bearer ${accessToken}` };

async function configureApi(page) {
  await page.route('**/simlab-config.json', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        apiBaseUrl,
        webSocketBaseUrl: 'ws://127.0.0.1:8876',
        apiVersion: 'v1',
        projectId: null,
        accessToken,
      }),
    });
  });
}

test('browser opens, simulates, saves, and exports without Qt', async ({ page }) => {
  await configureApi(page);
  await page.goto('/');
  await expect(page.locator('#viewport')).toBeVisible();
  await expect(page.locator('#asset-list')).toContainText('Box', { timeout: 10_000 });

  const openChooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Open', exact: true }).click();
  await (await openChooser).setFiles('examples/demo_project/scene.json');
  await expect(page.locator('#project-label')).toContainText('Physics Playground');

  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(page.locator('#simulation-badge')).toHaveText('Running');
  await expect(page.locator('#rtf-readout')).not.toHaveText('0.00x', { timeout: 10_000 });

  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await expect(page.locator('#simulation-badge')).toHaveText('Paused');

  const saveDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  expect((await saveDownload).suggestedFilename()).toBe('Physics-Playground.json');

  const exportDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export', exact: true }).click();
  expect((await exportDownload).suggestedFilename()).toBe('scene.xml');
});

test('frontend recovers shared assets when the API starts after the page', async ({ page }) => {
  await configureApi(page);
  const apiPattern = `${apiBaseUrl}/api/v1/**`;
  const unavailable = async (route) => { await route.abort('connectionrefused'); };
  await page.route(apiPattern, unavailable);
  await page.goto('/');
  await expect.poll(() => page.evaluate(() => window.simlabEditorReady)).toBe(true);
  await expect(page.locator('#asset-list')).toContainText('Connecting to shared assets');

  await page.unroute(apiPattern, unavailable);
  await expect(page.locator('#asset-list')).toContainText('Box', { timeout: 10_000 });
  await expect(page.locator('#console-output')).toContainText('Shared assets connected.');
});

test('browser uploads an external OpenUSD robot through the web API', async ({ page }) => {
  await configureApi(page);
  await page.goto('/');
  await expect(page.locator('#asset-list')).toContainText('Box', { timeout: 10_000 });
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Import USD', exact: true }).click();
  await (await chooser).setFiles(
    'tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda',
  );

  await expect(page.locator('#scene-tree')).toContainText('external_two_joint_arm');
  await expect(page.locator('#scene-tree')).toContainText('AxisA');

  await page.locator('[data-trajectory-command="load"]').click();
  await page.locator('[data-trajectory-command="play"]').click();
  await expect(page.locator('#trajectory-status')).toHaveText('completed', {
    timeout: 10_000,
  });

  page.once('dialog', (dialog) => dialog.accept());
  const controllerChooser = page.waitForEvent('filechooser');
  await page.locator('[data-controller-command="load"]').click();
  await (await controllerChooser).setFiles('examples/controllers/two_joint_pd.py');
  await expect(page.locator('[data-controller-name]')).toHaveText('Two Joint PD Example');
  await expect(page.locator('[data-controller-path]')).toHaveText('two_joint_pd.py');

  page.once('dialog', (dialog) => dialog.accept());
  const reloaded = page.waitForResponse((response) => (
    response.url().endsWith('/controller') && response.request().method() === 'POST'
  ));
  await page.locator('[data-controller-command="reload"]').click();
  expect((await reloaded).ok()).toBe(true);

  await page.locator('[data-recording-command="start"]').click();
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(page.locator('#simulation-badge')).toHaveText('Running');
  await expect(page.locator('#recording-status')).toContainText('Rows');
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await page.locator('[data-recording-command="stop"]').click();

  const recordingDownload = page.waitForEvent('download');
  await page.locator('[data-recording-export="json"]').click();
  expect((await recordingDownload).suggestedFilename()).toBe('joint-recording.json');
});

test('independent browser clients keep projects and simulations isolated', async ({ browser }) => {
  const context = await browser.newContext();
  const first = await context.newPage();
  const second = await context.newPage();
  await Promise.all([configureApi(first), configureApi(second)]);

  const projectResponses = [];
  const simulationResponses = [];
  for (const page of [first, second]) {
    page.on('response', async (response) => {
      if (response.request().method() !== 'POST') return;
      if (response.url() === `${apiBaseUrl}/api/v1/projects`) {
        projectResponses.push((await response.json()).id);
      } else if (response.url() === `${apiBaseUrl}/api/v1/simulations`) {
        simulationResponses.push((await response.json()).id);
      }
    });
  }

  await Promise.all([first.goto('/'), second.goto('/')]);
  await Promise.all([
    expect(first.locator('#asset-list')).toContainText('Box'),
    expect(second.locator('#asset-list')).toContainText('Box'),
  ]);
  expect(new Set(projectResponses).size).toBe(2);
  expect(first.url()).toMatch(/^http:\/\/127\.0\.0\.1:4173/);

  const firstChooser = first.waitForEvent('filechooser');
  await first.getByRole('button', { name: 'Open', exact: true }).click();
  await (await firstChooser).setFiles('examples/demo_project/scene.json');
  const secondChooser = second.waitForEvent('filechooser');
  await second.getByRole('button', { name: 'Open', exact: true }).click();
  await (await secondChooser).setFiles('examples/demo_project/scene.json');

  await first.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(first.locator('#simulation-badge')).toHaveText('Running');
  await expect(second.locator('#simulation-badge')).toHaveText('Stopped');
  await second.getByRole('button', { name: 'Step', exact: true }).click();
  await expect(second.locator('#simulation-badge')).toHaveText('Paused');
  await expect(first.locator('#simulation-badge')).toHaveText('Running');
  expect(new Set(simulationResponses).size).toBe(2);

  await context.close();
});

test('websocket reconnect resumes from the last event sequence', async ({ page, request }) => {
  const denied = await request.post(`${apiBaseUrl}/api/v1/projects`, {
    data: { name: 'Denied' },
  });
  expect(denied.status()).toBe(401);
  const unauthorizedSocketCode = await page.evaluate(() => new Promise((resolve) => {
    const socket = new WebSocket('ws://127.0.0.1:8876/api/v1/simulations/missing/events');
    socket.addEventListener('close', (event) => resolve(event.code), { once: true });
  }));
  expect(unauthorizedSocketCode).toBe(4401);

  const project = await request.post(`${apiBaseUrl}/api/v1/projects`, {
    headers: authHeaders,
    data: { name: 'Resume Project' },
  });
  const projectId = (await project.json()).id;
  const scene = JSON.parse(await readFile('examples/demo_project/scene.json', 'utf8'));
  await request.put(`${apiBaseUrl}/api/v1/projects/${projectId}/scene`, {
    headers: authHeaders,
    data: scene,
  });
  const simulation = await request.post(`${apiBaseUrl}/api/v1/simulations`, {
    headers: authHeaders,
    data: { project_id: projectId },
  });
  const simulationId = (await simulation.json()).id;
  await request.post(`${apiBaseUrl}/api/v1/simulations/${simulationId}/step`, {
    headers: authHeaders,
  });

  const receiveOne = async (afterSequence) => await page.evaluate(
    ({ id, sequence, token }) => new Promise((resolve, reject) => {
      const socket = new WebSocket(
        `ws://127.0.0.1:8876/api/v1/simulations/${id}/events`
        + `?after_sequence=${sequence}&token=${encodeURIComponent(token)}`,
      );
      const timer = window.setTimeout(() => {
        socket.close();
        reject(new Error('WebSocket event timeout'));
      }, 5000);
      socket.addEventListener('message', (message) => {
        window.clearTimeout(timer);
        const event = JSON.parse(String(message.data));
        socket.close();
        resolve(event);
      }, { once: true });
      socket.addEventListener('error', () => reject(new Error('WebSocket connection failed')));
    }),
    { id: simulationId, sequence: afterSequence, token: accessToken },
  );

  const snapshot = await receiveOne(0);
  expect(snapshot.type).toBe('snapshot');
  expect(snapshot.simulation_id).toBe(simulationId);
  expect(snapshot.sequence).toBeGreaterThan(0);

  await request.post(`${apiBaseUrl}/api/v1/simulations/${simulationId}/step`, {
    headers: authHeaders,
  });
  const replayed = await receiveOne(snapshot.sequence);
  expect(replayed.type).not.toBe('snapshot');
  expect(replayed.simulation_id).toBe(simulationId);
  expect(replayed.sequence).toBeGreaterThan(snapshot.sequence);
});
