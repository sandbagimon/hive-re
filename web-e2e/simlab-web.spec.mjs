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

test('frontend opens the built-in viewport shortcut guide', async ({ page }) => {
  await configureApi(page);
  await page.goto('/');

  const guidePromise = page.waitForEvent('popup');
  await page.locator('[data-documentation="viewport-controls"]').click();
  const guide = await guidePromise;

  await expect(guide).toHaveURL(/\/docs\/viewport-controls\.html$/);
  await expect(guide.getByRole('heading', { level: 1, name: 'Viewport 操作与快捷键' }))
    .toBeVisible();
  await expect(guide.locator('body')).toContainText('大型场景建议');
  await expect(guide.locator('body')).toContainText('Ctrl');
  await guide.close();
});

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

test('asset library loads the high-quality Franka robot meshes', async ({ page }) => {
  await configureApi(page);
  let bundleResponses = 0;
  let legacyGeometryResponses = 0;
  page.on('response', (response) => {
    if (!response.ok()) return;
    if (response.url().includes('/geometry/')) legacyGeometryResponses += 1;
    if (
      response.url().includes('/api/v1/artifacts/')
      && response.headers()['content-type']?.includes('application/octet-stream')
    ) bundleResponses += 1;
  });
  await page.goto('/');
  const franka = page.locator('[data-asset-id="openusd_franka_quality_4b35c27245"]');
  await expect(franka).toContainText('Franka Panda (High Quality)', { timeout: 10_000 });

  await franka.click();

  await expect(page.locator('#scene-tree')).toContainText('panda_link7');
  await expect(page.locator('#scene-tree')).toContainText('panda_finger_joint2');
  await expect.poll(() => bundleResponses, { timeout: 20_000 }).toBe(1);
  expect(legacyGeometryResponses).toBe(0);
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(page.locator('#simulation-badge')).toHaveText('Running', {
    timeout: 20_000,
  });
  await page.locator('[data-command="stop"]').click();
  await expect(page.locator('#simulation-badge')).toHaveText('Stopped');
  await page.locator('[data-action="frame"]').click();
  await page.waitForTimeout(500);
});

test('kilometre-scale Houhai asset is clearly framed with authored colors', async ({ page }, testInfo) => {
  await configureApi(page);
  let geometryResponses = 0;
  page.on('response', (response) => {
    if (response.ok() && response.url().includes('/geometry/')) geometryResponses += 1;
  });
  await page.goto('/');
  const houhai = page.locator('[data-asset-id="openusd_houhai_2km_b463d22fff"]');
  await expect(houhai).toContainText('Shenzhen Houhai 2km', { timeout: 10_000 });
  await houhai.click();

  await expect(page.locator('#scene-tree')).toContainText('Shenzhen Houhai 2km');
  await expect.poll(() => geometryResponses, { timeout: 20_000 }).toBe(1);
  await expect(page.locator('#viewport')).toHaveAttribute('data-environment-mode', 'city');
  await expect.poll(async () => page.locator('#viewport').evaluate((canvas) => ({
    radius: Number(canvas.dataset.focusRadius),
    distance: Number(canvas.dataset.cameraDistance),
    far: Number(canvas.dataset.cameraFar),
    fogNear: Number(canvas.dataset.fogNear),
    fogFar: Number(canvas.dataset.fogFar),
  }))).toMatchObject({
    radius: expect.any(Number),
    distance: expect.any(Number),
    far: expect.any(Number),
    fogNear: expect.any(Number),
    fogFar: expect.any(Number),
  });
  const camera = await page.locator('#viewport').evaluate((canvas) => ({
    radius: Number(canvas.dataset.focusRadius),
    distance: Number(canvas.dataset.cameraDistance),
    far: Number(canvas.dataset.cameraFar),
    fogNear: Number(canvas.dataset.fogNear),
    fogFar: Number(canvas.dataset.fogFar),
  }));
  expect(camera.radius).toBeGreaterThan(1_000);
  expect(camera.distance).toBeGreaterThan(camera.radius * 2);
  expect(camera.far).toBeGreaterThan(camera.distance + camera.radius);
  expect(camera.fogNear).toBeGreaterThan(camera.distance + camera.radius);
  await page.locator('#viewport').click({ position: { x: 24, y: 460 } });
  await expect(page.locator('#selection')).toContainText('Selected: None');
  await page.locator('#viewport').screenshot({
    path: testInfo.outputPath('houhai-viewport.png'),
  });

  await page.locator('[data-asset-id="primitive_box"]').click();
  await expect(page.locator('#actor-count')).toHaveText('2');
  await page.waitForTimeout(500);
  const fogAfterAddingAsset = await page.locator('#viewport').evaluate((canvas) => ({
    near: Number(canvas.dataset.fogNear),
    far: Number(canvas.dataset.fogFar),
  }));
  expect(fogAfterAddingAsset.near).toBeCloseTo(camera.fogNear, 3);
  expect(fogAfterAddingAsset.far).toBeCloseTo(camera.fogFar, 3);
  expect(geometryResponses).toBe(1);
  await page.locator('#viewport').screenshot({
    path: testInfo.outputPath('houhai-after-adding-asset.png'),
  });
});

test('Iris controller takes off and settles into hover', async ({ page }) => {
  await configureApi(page);
  await page.goto('/');
  const iris = page.locator('[data-asset-id="openusd_iris_09f8390b45"]');
  await expect(iris).toContainText('Pegasus Iris Quadcopter', { timeout: 10_000 });
  await iris.click();

  page.once('dialog', (dialog) => dialog.accept());
  const controllerChooser = page.waitForEvent('filechooser');
  await page.locator('[data-controller-command="load"]').click();
  await (await controllerChooser).setFiles('examples/controllers/iris_hover.py');
  await expect(page.locator('[data-controller-name]')).toHaveText('Iris Takeoff and Hover');

  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(page.locator('#simulation-badge')).toHaveText('Running');
  await expect.poll(async () => {
    const state = JSON.parse(await page.evaluate(() => window.simlabEditor.getStateJson()));
    return state.simulationState?.time ?? 0;
  }, { timeout: 12_000 }).toBeGreaterThan(5.5);

  const runtime = JSON.parse(await page.evaluate(() => window.simlabEditor.getStateJson()));
  const position = runtime.simulationState.actors[0].position;
  expect(position[0]).toBeCloseTo(0, 3);
  expect(position[1]).toBeCloseTo(0, 3);
  expect(position[2]).toBeCloseTo(1.07, 2);
  expect(runtime.simulationState.controller.status).toBe('active');
  expect(runtime.simulationState.controller.step_count).toBeGreaterThan(500);
  await expect(page.locator('[data-rotor-control="actuator_iris_rotor_0"]').last())
    .toHaveValue(/641\./);
});

test('Iris physically picks up and delivers a payload from A to B', async ({ page }, testInfo) => {
  test.setTimeout(65_000);
  await configureApi(page);
  await page.goto('/');
  await expect(page.locator('#asset-list')).toContainText('Pegasus Iris Quadcopter', {
    timeout: 10_000,
  });

  const openChooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Open', exact: true }).click();
  await (await openChooser).setFiles('examples/drone_delivery/scene.json');
  await expect(page.locator('#project-label')).toContainText('Iris A-to-B Physical Delivery');
  await expect(page.locator('#scene-tree')).toContainText('Pickup A');
  await expect(page.locator('#scene-tree')).toContainText('Dropoff B');

  await page.locator('[data-actor-row]').filter({ hasText: 'Pegasus Iris Quadcopter' }).click();
  page.once('dialog', (dialog) => dialog.accept());
  const controllerChooser = page.waitForEvent('filechooser');
  await page.locator('[data-controller-command="load"]').click();
  await (await controllerChooser).setFiles('examples/controllers/iris_payload_delivery.py');
  await expect(page.locator('[data-controller-name]'))
    .toHaveText('Iris Physical Payload Delivery');

  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await page.locator('[data-simulation-speed="2"]').click();
  await expect.poll(async () => {
    const state = JSON.parse(await page.evaluate(() => window.simlabEditor.getStateJson()));
    return state.simulationState?.delivery_tasks?.[0]?.status ?? 'missing';
  }, { timeout: 45_000, intervals: [250, 500, 1000] }).toBe('completed');

  const runtime = JSON.parse(await page.evaluate(() => window.simlabEditor.getStateJson()));
  const payload = runtime.simulationState.actors.find((item) => item.id === 'actor_003');
  expect(runtime.simulationState.attachments[0].active).toBe(false);
  expect(payload.position[0]).toBeCloseTo(4, 1);
  expect(payload.position[1]).toBeCloseTo(3, 1);
  expect(payload.position[2]).toBeCloseTo(0.16, 1);
  await expect(page.locator('#scene-stats')).toContainText('task completed');
  await page.locator('[data-action="frame"]').click();
  await page.waitForTimeout(500);
  await page.locator('#viewport').screenshot({
    path: testInfo.outputPath('drone-delivery-complete.png'),
  });
});

test('obstacle-aware Iris controller initializes and runs in the browser', async ({ page }) => {
  test.setTimeout(75_000);
  await configureApi(page);
  await page.goto('/');
  await expect(page.locator('#asset-list')).toContainText('Pegasus Iris Quadcopter', {
    timeout: 10_000,
  });

  const openChooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Open', exact: true }).click();
  await (await openChooser).setFiles('examples/drone_delivery_obstacles/scene.json');
  await expect(page.locator('#project-label'))
    .toContainText('Iris Obstacle-Aware Payload Delivery');

  await page.locator('[data-actor-row]').filter({ hasText: 'Pegasus Iris Quadcopter' }).click();
  page.once('dialog', (dialog) => dialog.accept());
  const controllerResponse = page.waitForResponse((response) => (
    response.url().endsWith('/controller')
      && response.request().method() === 'POST'
  ));
  const controllerChooser = page.waitForEvent('filechooser');
  await page.locator('[data-controller-command="load"]').click();
  await (await controllerChooser).setFiles('examples/controllers/iris_obstacle_delivery.py');
  const controllerResult = await controllerResponse;
  expect(controllerResult.ok()).toBe(true);
  const controllerPayload = await controllerResult.json();
  expect(controllerPayload.ok, controllerPayload.error).toBe(true);
  await expect(page.locator('[data-controller-name]'))
    .toHaveText('Iris Obstacle-Aware Payload Delivery', { timeout: 20_000 });

  const loaded = JSON.parse(await page.evaluate(() => window.simlabEditor.getStateJson()));
  expect(loaded.simulationState.controller.status).toBe('ready');
  expect(loaded.simulationState.controller.deadline).toBe(0.02);
  expect(loaded.simulationState.controller.reset_deadline).toBe(0.2);
  expect(loaded.simulationState.navigation.status).toBe('idle');
  expect(loaded.simulationState.sensors.filter(
    (sample) => sample.sensor_type === 'rangefinder',
  )).toHaveLength(12);

  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await page.locator('[data-simulation-speed="2"]').click();
  await expect.poll(async () => Number(
    await page.locator('#viewport').getAttribute('data-navigation-replans'),
  ), { timeout: 55_000, intervals: [250, 500, 1000] }).toBeGreaterThan(0);

  const runtime = JSON.parse(await page.evaluate(() => window.simlabEditor.getStateJson()));
  expect(runtime.simulationState.controller.status).toBe('active');
  expect(runtime.simulationState.controller.message).toBeNull();
  expect(runtime.simulationState.controller.step_count).toBeGreaterThan(1_000);
  expect(runtime.simulationState.navigation.replan_count).toBeGreaterThan(0);
  expect(runtime.simulationState.navigation.route_revision).toBeGreaterThan(1);
  expect(runtime.simulationState.navigation.status).toBe('following');
  expect(runtime.simulationState.actors.find((item) => item.id === 'actor_002').position[2])
    .toBeGreaterThan(0.5);
  await expect(page.locator('#scene-stats')).toContainText(/replans [1-9]/);
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

test('editing actor properties keeps the actor selected', async ({ page }) => {
  await configureApi(page);
  await page.goto('/');
  await expect(page.locator('#asset-list')).toContainText('Box', { timeout: 10_000 });

  await page.locator('[data-asset-id="primitive_box"]').click();
  const selectedActor = page.locator('[data-actor-row].selected');
  await expect(selectedActor).toContainText('Box');
  await expect(page.locator('#selection')).toContainText('Selected: Box');

  const friction = page.locator('#property-inspector [data-field="friction"]');
  await friction.fill('1.25');
  await friction.press('Enter');

  await expect(selectedActor).toContainText('Box');
  await expect(page.locator('#property-inspector')).toContainText('Actor');
  await expect(page.locator('#selection')).toContainText('Selected: Box');
  const state = JSON.parse(await page.evaluate(() => window.simlabEditor.getStateJson()));
  expect(state.selectedActorId).toBe('actor_001');
  expect(state.scene.actors[0].properties.physics.friction[0]).toBe(1.25);
});

test('clicking and moving an actor in the viewport keeps it selected', async ({ page }) => {
  await configureApi(page);
  await page.goto('/');
  await expect(page.locator('#asset-list')).toContainText('Box', { timeout: 10_000 });
  await page.locator('[data-asset-id="primitive_box"]').click();

  const viewport = page.locator('#viewport');
  const bounds = await viewport.boundingBox();
  expect(bounds).not.toBeNull();
  await viewport.click({ position: { x: 12, y: 12 } });
  await expect(page.locator('#selection')).toHaveText('Selected: None');

  await viewport.click({
    position: { x: bounds.width / 2, y: bounds.height / 2 },
  });
  await expect(page.locator('[data-actor-row].selected')).toContainText('Box');
  await expect(page.locator('#selection')).toContainText('Selected: Box');

  const gizmoCenter = {
    x: bounds.x + bounds.width / 2,
    y: bounds.y + bounds.height / 2 + 18,
  };
  await page.mouse.move(gizmoCenter.x, gizmoCenter.y);
  await page.mouse.down();
  await page.mouse.move(gizmoCenter.x + 80, gizmoCenter.y, { steps: 8 });
  await page.mouse.up();

  await expect(page.locator('[data-actor-row].selected')).toContainText('Box');
  await expect(page.locator('#selection')).toContainText('Selected: Box');
  await expect.poll(async () => {
    const state = JSON.parse(await page.evaluate(() => window.simlabEditor.getStateJson()));
    return state.scene.actors[0].transform.position;
  }).not.toEqual([0, 0, 0]);
});

test('moving a cached OpenUSD actor does not reload its visual geometry', async ({ page }) => {
  await configureApi(page);
  let geometryRequests = 0;
  page.on('request', (request) => {
    if (request.method() === 'GET' && request.url().includes('/geometry/')) {
      geometryRequests += 1;
    }
  });
  await page.goto('/');
  await expect(page.locator('#asset-list')).toContainText('Vehicle_Hanger_Adjust', {
    timeout: 10_000,
  });

  const initialGeometry = page.waitForResponse((response) => (
    response.request().method() === 'GET' && response.url().includes('/geometry/')
  ));
  await page.locator('[data-asset-id="openusd_vehicle_hanger_adjust_454a0d18a9"]').click();
  expect((await initialGeometry).ok()).toBe(true);
  await expect.poll(() => geometryRequests).toBe(1);

  const positionX = page.locator(
    '#property-inspector [data-vector="position"][data-index="0"]',
  );
  await positionX.fill('1');
  await positionX.press('Enter');

  await expect(page.locator('[data-actor-row].selected')).toContainText('Vehicle_Hanger_Adjust');
  await expect.poll(async () => {
    const state = JSON.parse(await page.evaluate(() => window.simlabEditor.getStateJson()));
    return state.scene.actors[0].transform.position[0];
  }).toBe(1);
  await page.waitForTimeout(500);
  expect(geometryRequests).toBe(1);
});

test('adding an actor does not rebuild existing OpenUSD actors', async ({ page }) => {
  await configureApi(page);
  let geometryRequests = 0;
  const geometryUrls = [];
  page.on('request', (request) => {
    if (request.method() === 'GET' && request.url().includes('/geometry/')) {
      geometryRequests += 1;
      geometryUrls.push(request.url());
    }
  });
  await page.goto('/');
  await expect(page.locator('#asset-list')).toContainText('Vehicle_Hanger_Adjust', {
    timeout: 10_000,
  });

  const initialGeometry = page.waitForResponse((response) => (
    response.request().method() === 'GET' && response.url().includes('/geometry/')
  ));
  await page.locator('[data-asset-id="openusd_vehicle_hanger_adjust_454a0d18a9"]').click();
  expect((await initialGeometry).ok()).toBe(true);
  await expect.poll(() => geometryRequests).toBe(1);

  await page.locator('[data-asset-id="primitive_box"]').click();
  await expect(page.locator('#actor-count')).toHaveText('2');
  await expect(page.locator('#scene-tree')).toContainText('Vehicle_Hanger_Adjust');
  await expect(page.locator('#scene-tree')).toContainText('Box');
  await expect(page.locator('[data-actor-row].selected')).toContainText('Box');
  await page.waitForTimeout(500);

  expect(geometryRequests, geometryUrls.join('\n')).toBe(1);
});

test('scene editing stays independent from a running simulation', async ({ page }) => {
  await configureApi(page);
  const simulationIds = [];
  page.on('response', async (response) => {
    if (
      response.request().method() === 'POST'
      && response.url() === `${apiBaseUrl}/api/v1/simulations`
      && response.ok()
    ) {
      simulationIds.push((await response.json()).id);
    }
  });
  await page.goto('/');
  await expect(page.locator('#asset-list')).toContainText('Box', { timeout: 10_000 });
  await page.locator('[data-asset-id="primitive_box"]').click();
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(page.locator('#simulation-badge')).toHaveText('Running');
  await expect.poll(() => simulationIds.length).toBe(1);

  const sceneUpdate = page.waitForResponse((response) => (
    response.request().method() === 'PUT'
      && response.url().includes('/projects/')
      && response.url().endsWith('/scene')
  ));
  const friction = page.locator('#property-inspector [data-field="friction"]');
  await friction.fill('1.4');
  await friction.press('Enter');
  expect((await sceneUpdate).ok()).toBe(true);
  await page.waitForTimeout(500);
  await expect(page.locator('#simulation-badge')).toHaveText('Running');

  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect.poll(() => simulationIds.length).toBe(2);
  expect(simulationIds[1]).not.toBe(simulationIds[0]);
  await expect(page.locator('#simulation-badge')).toHaveText('Running');
});

test('stop releases the simulation without changing the editor scene', async ({ page }) => {
  await configureApi(page);
  await page.goto('/');
  await expect(page.locator('#asset-list')).toContainText('Box', { timeout: 10_000 });
  await page.locator('[data-asset-id="primitive_box"]').click();
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(page.locator('#simulation-badge')).toHaveText('Running');

  const deleted = page.waitForResponse((response) => (
    response.request().method() === 'DELETE'
      && /\/api\/v1\/simulations\/sim_[^/]+$/.test(response.url())
  ));
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  expect((await deleted).status()).toBe(204);
  await expect(page.locator('#simulation-badge')).toHaveText('Stopped');
  await expect(page.locator('#scene-tree')).toContainText('Box');
  await expect(page.locator('[data-actor-row].selected')).toContainText('Box');
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

test('browser imports an OpenUSD folder with relative composition dependencies', async ({ page }) => {
  await configureApi(page);
  await page.goto('/');
  await expect(page.locator('#asset-list')).toContainText('Box', { timeout: 10_000 });
  const uploadResponse = page.waitForResponse((response) => (
    response.url().endsWith('/assets/openusd')
      && response.request().method() === 'POST'
  ));
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Import USD Folder', exact: true }).click();
  await (await chooser).setFiles('tests/fixtures/openusd/composite');

  const response = await uploadResponse;
  expect(response.status()).toBe(201);
  expect(response.request().headers()['content-type']).toContain('multipart/form-data');
  await expect(page.locator('#scene-tree')).toContainText('root');
  await expect(page.locator('#console-output')).toContainText(
    'No UsdPhysics collision geometry was found',
  );
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
