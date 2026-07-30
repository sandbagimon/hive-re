import assert from 'node:assert/strict';

import { jointLocalPose } from '../frontend/generated/robot-kinematics.js';

const identity = [0, 0, 0, 1];
const rounded = (value) => (
  Math.abs(value) < 1e-9 ? 0 : Math.round(value * 1e9) / 1e9
);
const rotatedChildFrame = {
  id: 'joint_test',
  name: 'Test Joint',
  type: 'revolute',
  parent_link_id: 'parent',
  child_link_id: 'child',
  origin: { position: [0, 0, 0.2], quaternion: identity },
  parent_frame: { position: [0, 0, 0.2], quaternion: identity },
  child_frame: {
    position: [0.1, 0, 0],
    quaternion: [Math.SQRT1_2, 0, 0, Math.SQRT1_2],
  },
  axis: [0, 1, 0],
  limits: null,
  initial_position: 0,
};

const zeroPose = jointLocalPose(rotatedChildFrame);
assert.ok(zeroPose);
assert.deepEqual(
  zeroPose.position.map(rounded),
  [-0.1, 0, 0.2],
);

const quarterTurn = jointLocalPose({
  ...rotatedChildFrame,
  initial_position: Math.PI / 2,
});
assert.ok(quarterTurn);
assert.deepEqual(
  quarterTurn.position.map(rounded),
  [0, 0, 0.3],
);

assert.equal(jointLocalPose({
  ...rotatedChildFrame,
  parent_frame: undefined,
  child_frame: undefined,
}), null);

console.log('Robot dual-frame kinematics: passed');
