import assert from 'node:assert/strict';

async function loadRuntimeConfig(label) {
  const config = (await import(`../frontend/vite.config.mjs?runtime-config-${label}`)).default;
  let routePath;
  let routeHandler;
  config.plugins[0].configureServer({
    middlewares: {
      use(path, handler) {
        routePath = path;
        routeHandler = handler;
      },
    },
  });

  let responseBody = '';
  const headers = new Map();
  routeHandler({}, {
    set statusCode(value) {
      assert.equal(value, 200);
    },
    setHeader(name, value) {
      headers.set(name.toLowerCase(), value);
    },
    end(value) {
      responseBody = value;
    },
  });

  assert.equal(routePath, '/simlab-config.json');
  assert.equal(headers.get('cache-control'), 'no-store');
  return JSON.parse(responseBody);
}

process.env.SIMLAB_API_TOKEN = 'backend-development-token';
delete process.env.SIMLAB_FRONTEND_ACCESS_TOKEN;
assert.deepEqual(await loadRuntimeConfig('fallback'), {
  apiBaseUrl: 'same-origin',
  webSocketBaseUrl: 'same-origin',
  apiVersion: 'v1',
  projectId: null,
  accessToken: 'backend-development-token',
});

process.env.SIMLAB_FRONTEND_ACCESS_TOKEN = 'frontend-development-token';
assert.deepEqual(await loadRuntimeConfig('override'), {
  apiBaseUrl: 'same-origin',
  webSocketBaseUrl: 'same-origin',
  apiVersion: 'v1',
  projectId: null,
  accessToken: 'frontend-development-token',
});

console.log('Vite authenticated runtime config: passed');
