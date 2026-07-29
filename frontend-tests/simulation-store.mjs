import assert from 'node:assert/strict';

import { SimulationStore } from '../frontend/generated/simulation-store.js';

const store = new SimulationStore();
assert.equal(store.current.simulationStatus, 'stopped');
assert.equal(store.current.simulationState, null);
assert.deepEqual(store.current.validationIssues, []);

const frame = { time: 0.25, actors: [], links: [], joints: [], actuators: [], sensors: [] };
store.setSimulation('running', frame);
assert.equal(store.current.simulationStatus, 'running');
assert.equal(store.current.simulationState, frame);

const issue = { severity: 'warning', code: 'test.warning', message: 'Test warning' };
store.setValidationIssues([issue]);
assert.deepEqual(store.current.validationIssues, [issue]);
assert.equal(store.current.simulationStatus, 'running');

const nextFrame = { ...frame, time: 0.5 };
store.setSimulationState(nextFrame);
assert.equal(store.current.simulationState, nextFrame);
assert.equal(store.current.simulationStatus, 'running');

store.reset();
assert.equal(store.current.simulationStatus, 'stopped');
assert.equal(store.current.simulationState, null);
assert.deepEqual(store.current.validationIssues, []);

console.log('SimulationStore runtime/validation/reset isolation: passed');
