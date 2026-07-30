import assert from 'node:assert/strict';

import { decodeGeometryBundle } from '../frontend/generated/geometry-bundle.js';

const positions = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]);
const indices = new Uint32Array([0, 1, 2]);
const normals = new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]);
const colors = new Uint8Array([255, 0, 0, 0, 255, 0, 0, 0, 255]);
const payloadLength = positions.byteLength + indices.byteLength + normals.byteLength + colors.byteLength;
const header = new TextEncoder().encode(JSON.stringify({
  format: 'simlab-geometry-bundle',
  version: 1,
  geometries: {
    triangle: {
      positions: [0, positions.length],
      indices: [positions.byteLength, indices.length],
      normals: [positions.byteLength + indices.byteLength, normals.length],
      colors: [positions.byteLength + indices.byteLength + normals.byteLength, colors.length],
      bounds: { min: [0, 0, 0], max: [1, 1, 0], sphere: [0.5, 0.5, 0, 0.707] },
    },
  },
}));
const payloadStart = (12 + header.byteLength + 3) & ~3;
const buffer = new ArrayBuffer(payloadStart + payloadLength);
new Uint8Array(buffer, 0, 8).set(new TextEncoder().encode('SIMGEOM1'));
new DataView(buffer).setUint32(8, header.byteLength, true);
new Uint8Array(buffer, 12, header.byteLength).set(header);
let offset = payloadStart;
for (const view of [positions, indices, normals, colors]) {
  new Uint8Array(buffer, offset, view.byteLength).set(
    new Uint8Array(view.buffer, view.byteOffset, view.byteLength),
  );
  offset += view.byteLength;
}

const bundle = decodeGeometryBundle(buffer);
const triangle = bundle.get('triangle');
assert.ok(triangle);
assert.deepEqual([...triangle.positions], [...positions]);
assert.deepEqual([...triangle.indices], [...indices]);
assert.deepEqual([...triangle.normals], [...normals]);
assert.deepEqual([...triangle.colors], [...colors]);

assert.throws(
  () => decodeGeometryBundle(new TextEncoder().encode('not-a-bundle').buffer),
  /invalid magic/,
);

console.log('geometry-bundle frontend tests passed');
