import assert from 'node:assert/strict';

import {
  playbackRateForSpeed,
  selectIdleClipName,
  selectLocomotionClipName,
} from '../frontend/generated/actor-animation.js';

const available = ['Idle_A', 'Walk', 'Bicycle_Ride', 'Delivery_Stop'];
const walking = {
  locomotion: 'walking',
  clips: { idle: 'idle_a', walking: 'walk' },
  reference_speed: 1.25,
};
const cycling = {
  locomotion: 'cycling',
  clips: { idle: 'Idle_A', cycling: 'Bicycle_Ride' },
  reference_speed: 4,
  min_playback_rate: 0.5,
  max_playback_rate: 1.8,
  stop_speed: 0.05,
};

assert.equal(selectIdleClipName(available, walking), 'Idle_A');
assert.equal(selectLocomotionClipName(available, walking), 'Walk');
assert.equal(selectLocomotionClipName(available, cycling), 'Bicycle_Ride');
assert.equal(selectLocomotionClipName(['Courier Bike Loop'], {
  ...cycling,
  clips: {},
}), 'Courier Bike Loop');
assert.equal(playbackRateForSpeed(0.01, walking), 0);
assert.equal(playbackRateForSpeed(1.25, walking), 1);
assert.equal(playbackRateForSpeed(0.2, walking), 0.55);
assert.equal(playbackRateForSpeed(20, cycling), 1.8);

console.log('Actor glTF locomotion animation: passed');
