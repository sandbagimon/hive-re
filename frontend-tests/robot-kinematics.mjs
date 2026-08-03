import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  advanceRotorAnimation,
  jointLocalPose,
} from '../frontend/generated/robot-kinematics.js';

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

const irisSource = readFileSync(
  'assets/imported/openusd_iris_09f8390b45/robotics.json',
  'utf8',
).replaceAll('-Infinity', 'null').replaceAll('Infinity', 'null');
const iris = JSON.parse(irisSource).articulations[0];
const expectedRotorPositions = [
  [0.137595328, -0.206735339, 0.023],
  [-0.124999969, 0.218694584, 0.023],
  [0.138308804, 0.203219649, 0.023],
  [-0.124502012, -0.221998874, 0.023],
];
iris.joints.forEach((joint, index) => {
  const pose = jointLocalPose(joint);
  const link = iris.links.find((item) => item.id === joint.child_link_id);
  assert.ok(pose);
  assert.ok(link);
  assert.deepEqual(pose.position.map(rounded), expectedRotorPositions[index]);
  assert.deepEqual(pose.position.map(rounded), link.transform.position.map(rounded));
  assert.deepEqual(pose.quaternion.map(rounded), link.transform.quaternion.map(rounded));
});

const initialRotorAnimation = advanceRotorAnimation(undefined, 0, 100, 1);
assert.deepEqual(initialRotorAnimation, { angle: 0, time: 0, angularVelocity: 100 });
const forwardRotorAnimation = advanceRotorAnimation(initialRotorAnimation, 0.1, 100, 1);
assert.equal(rounded(forwardRotorAnimation.angle), 0.8);
const reverseRotorAnimation = advanceRotorAnimation(initialRotorAnimation, 0.1, 100, -1);
assert.equal(rounded(reverseRotorAnimation.angle), rounded((Math.PI * 2) - 0.8));
assert.deepEqual(
  advanceRotorAnimation(forwardRotorAnimation, 0, 100, 1),
  initialRotorAnimation,
);

console.log('Robot dual-frame kinematics: passed');
