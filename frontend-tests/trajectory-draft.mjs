import assert from 'node:assert/strict';

import {
  captureTrajectoryKeyframe,
  createTrajectoryDraft,
  removeTrajectoryKeyframe,
  setTrajectoryDuration,
  trajectoryDraftFromTrajectory,
  trajectoryFromDraft,
  updateTrajectoryKeyframeTarget,
  updateTrajectoryKeyframeTime,
  validateTrajectoryDraft,
} from '../src/simlab/web_viewport/generated/trajectory-draft.js';

const home = { shoulder: 0, elbow: 0.25 };
let draft = createTrajectoryDraft('robot_001', home, 2);
assert.deepEqual(draft.keyframes.map((item) => item.time), [0, 2]);

draft = setTrajectoryDuration(draft, 4);
assert.deepEqual(draft.keyframes.map((item) => item.time), [0, 4]);

draft = captureTrajectoryKeyframe(draft, 'keyframe-2', 3, {
  shoulder: 0.75,
  elbow: -0.25,
});
draft = updateTrajectoryKeyframeTime(draft, 'keyframe-2', 1.5);
assert.deepEqual(draft.keyframes.map((item) => item.time), [0, 1.5, 4]);

draft = updateTrajectoryKeyframeTarget(draft, 'keyframe-1', 'shoulder', 1);
const trajectory = trajectoryFromDraft(draft);
assert.equal(trajectory.keyframes.at(-1).targets.shoulder, 1);
assert.equal(trajectory.keyframes[1].targets.elbow, -0.25);
assert.equal(trajectory.name, 'Joint Motion');
const restoredDraft = trajectoryDraftFromTrajectory('robot_002', trajectory);
assert.equal(restoredDraft.actorId, 'robot_002');
assert.deepEqual(restoredDraft.keyframes.map((item) => item.id), [
  'keyframe-0',
  'keyframe-1',
  'keyframe-2',
]);
assert.deepEqual(trajectoryFromDraft(restoredDraft), trajectory);

draft = removeTrajectoryKeyframe(draft, 'keyframe-2');
assert.equal(draft.keyframes.length, 2);
assert.throws(
  () => removeTrajectoryKeyframe(draft, 'keyframe-0'),
  /at least two keyframes/,
);

const duplicateTime = updateTrajectoryKeyframeTime(draft, 'keyframe-1', 0);
assert.match(validateTrajectoryDraft(duplicateTime).join('; '), /strictly increasing/);
const missingJoint = structuredClone(draft);
delete missingJoint.keyframes[1].targets.elbow;
assert.match(validateTrajectoryDraft(missingJoint).join('; '), /same joint IDs/);
const invalidTarget = updateTrajectoryKeyframeTarget(draft, 'keyframe-1', 'elbow', NaN);
assert.match(validateTrajectoryDraft(invalidTarget).join('; '), /must be finite/);

console.log('TrajectoryDraft capture/sort/edit/validation: passed');
