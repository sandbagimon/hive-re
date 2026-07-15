import assert from 'node:assert/strict';

import { EditorStore } from '../src/simlab/web_viewport/generated/store.js';

const store = new EditorStore();
const box = {
  id: 'primitive_box',
  name: 'Box',
  type: 'object',
  primitive: 'box',
  default_properties: {
    primitive: 'box',
    size: [0.5, 0.5, 0.5],
    physics: { dynamic: true, mass: 1 },
  },
};

assert.equal(store.current.dirty, false);
assert.equal(store.current.scene.actors.length, 0);

store.setAssets([box]);
store.addAsset(box);
assert.equal(store.current.scene.actors.length, 1);
assert.equal(store.current.selectedActorId, 'actor_001');
assert.equal(store.current.dirty, true);
assert.equal(store.current.canUndo, true);

store.undo();
assert.equal(store.current.scene.actors.length, 0);
assert.equal(store.current.dirty, false);
assert.equal(store.current.canRedo, true);

store.redo();
assert.equal(store.current.scene.actors.length, 1);
store.markSaved('/tmp/scene.json');
assert.equal(store.current.dirty, false);

store.updateActorName('actor_001', 'Renamed Box');
assert.equal(store.current.scene.actors[0].name, 'Renamed Box');
assert.equal(store.current.dirty, true);

store.selectActor(null);
assert.equal(store.current.selectedActorId, null);
assert.equal(store.current.dirty, true);

const robot = {
  id: 'external_arm', name: 'Arm', type: 'robot',
  default_properties: { articulation_ids: ['arm_001'] },
};
const robotics = {
  version: '1.0',
  articulations: [{
    id: 'arm_001', name: 'Arm', root_link_id: 'base', fixed_base: true,
    links: [], joints: [], actuators: [], sensors: [],
  }],
};
store.addAsset(robot, robotics);
assert.equal(store.current.scene.actors.at(-1).type, 'robot');
assert.equal(store.current.scene.robotics.articulations[0].id, 'arm_001');
store.deleteActor(store.current.scene.actors.at(-1).id);
assert.equal(store.current.scene.robotics, undefined);

console.log('EditorStore add/undo/redo/dirty/selection: passed');
