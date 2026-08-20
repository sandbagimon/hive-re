import assert from 'node:assert/strict';

import {
  categoryForAsset,
  groupAssets,
} from '../frontend/generated/asset-catalog.js';

const assets = [
  { id: 'primitive_box', name: 'Box', type: 'object', primitive: 'box' },
  { id: 'robot_arm', name: 'Robot Arm', type: 'robot', source_format: 'openusd' },
  { id: 'crate', name: 'Crate', type: 'object', source_format: 'openusd' },
  {
    id: 'city',
    name: 'City',
    type: 'object',
    category: 'environment',
    source_format: 'openusd',
  },
];

assert.equal(categoryForAsset(assets[0]), 'primitive');
assert.equal(categoryForAsset(assets[1]), 'robot');
assert.equal(categoryForAsset(assets[2]), 'prop');
assert.equal(categoryForAsset(assets[3]), 'environment');

assert.deepEqual(
  groupAssets(assets).map((group) => [group.category, group.assets.map((asset) => asset.id)]),
  [
    ['robot', ['robot_arm']],
    ['primitive', ['primitive_box']],
    ['prop', ['crate']],
    ['environment', ['city']],
  ],
);
assert.deepEqual(groupAssets(assets, 'environment')[0].assets, [assets[3]]);
assert.deepEqual(groupAssets(assets, 'usd').flatMap((group) => group.assets), assets.slice(1));

console.log('Asset catalog categories: passed');
