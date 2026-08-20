import assert from 'node:assert/strict';

import {
  createDefaultLayout,
  findLeafById,
  removePanel,
} from '../frontend/generated/dock-tree.js';

function splitById(node, id) {
  if (node.type === 'leaf') return null;
  if (node.id === id) return node;
  for (const child of node.children) {
    const found = splitById(child, id);
    if (found) return found;
  }
  return null;
}

function assertSizesClose(actual, expected) {
  assert.equal(actual.length, expected.length);
  actual.forEach((value, index) => {
    assert.ok(Math.abs(value - expected[index]) < 1e-12);
  });
}

const initial = createDefaultLayout();
const rootSizes = [...initial.sizes];
const centerSizes = [...splitById(initial, 'center-col').sizes];

// The 1440 x 900 non-browser fallback mirrors the former fixed workspace:
// a 918 px centre region and a 735 px viewport leaf before dock chrome.
assert.ok(Math.abs(rootSizes[1] * 1426 - 918) < 0.01);
assert.ok(Math.abs(centerSizes[0] * 825 - 735) < 0.01);
assert.ok(findLeafById(initial, 'right-bottom').panels.includes('agent'));

let changed = initial;
for (const panel of ['console', 'validation', 'recording']) {
  changed = removePanel(changed, panel);
  assert.ok(changed);
}

// Closing every diagnostics tab keeps the named slot and, critically, does
// not renormalize the centre split to 50 / 50.
assertSizesClose(splitById(changed, 'root').sizes, rootSizes);
assertSizesClose(splitById(changed, 'center-col').sizes, centerSizes);
assert.deepEqual(findLeafById(changed, 'center-bottom').panels, []);

changed = removePanel(changed, 'scene-tree');
assert.ok(changed);
assertSizesClose(splitById(changed, 'root').sizes, rootSizes);
assert.deepEqual(findLeafById(changed, 'left-top').panels, []);

console.log('Dock tree stable-slot geometry: passed');
