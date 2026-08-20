import { EditorBridgeClient } from './bridge.js';
import { groupAssets } from './asset-catalog.js';
import { SimulationStore } from './simulation-store.js';
import { EditorStore } from './store.js';
import { captureTrajectoryKeyframe, createTrajectoryDraft, removeTrajectoryKeyframe, setTrajectoryDuration, trajectoryDraftFromTrajectory, trajectoryDuration, trajectoryFromDraft, updateTrajectoryKeyframeTarget, updateTrajectoryKeyframeTime, } from './trajectory-draft.js';
import { applySimulationState, configureViewport, selectViewportActor, selectViewportLink, setViewportScene, updateViewportTransforms, } from './viewport.js';
import { setViewportFeature } from './viewport.js';
import { DockManager } from './dock-manager.js';
const materialPresets = {
    default: { density: 1000, friction: [0.8, 0.005, 0.0001], solref: [0.02, 1], solimp: [0.9, 0.95, 0.001, 0.5, 2], roughness: 0.55, metalness: 0.04 },
    rubber: { density: 1100, friction: [1.2, 0.01, 0.0002], solref: [0.03, 1], solimp: [0.88, 0.96, 0.002, 0.5, 2], roughness: 0.86, metalness: 0 },
    wood: { density: 700, friction: [0.6, 0.004, 0.0001], solref: [0.015, 1], solimp: [0.9, 0.95, 0.001, 0.5, 2], roughness: 0.72, metalness: 0 },
    metal: { density: 7800, friction: [0.35, 0.003, 0.0001], solref: [0.008, 1], solimp: [0.92, 0.97, 0.0005, 0.5, 2], roughness: 0.24, metalness: 0.82 },
    ice: { density: 917, friction: [0.03, 0.001, 0.00005], solref: [0.01, 1], solimp: [0.92, 0.98, 0.0005, 0.5, 2], roughness: 0.12, metalness: 0.08 },
};
const store = new EditorStore();
const simulationStore = new SimulationStore();
const trajectoryDrafts = new Map();
const recordingDrafts = new Map();
let bridge = new EditorBridgeClient(null);
let previousSceneJson = '';
let previousViewportStructure = '';
let previousSelectedActorId = null;
let previousSelectedJointId = null;
let previousSelectedSensorId = null;
let previousSimulationState = null;
let syncSnapshot = '';
let renderSnapshot = '';
let assetFilter = '';
const element = (id) => {
    const value = document.getElementById(id);
    if (!value)
        throw new Error(`Missing editor element: #${id}`);
    return value;
};
const escapeHtml = (value) => String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
function showToast(message, error = false) {
    const toast = element('toast');
    toast.textContent = message;
    toast.classList.toggle('error', error);
    toast.hidden = false;
    window.setTimeout(() => { toast.hidden = true; }, 3200);
}
const workspace = new DockManager();
function articulationsForActor(actor, scene) {
    const articulationIds = actor.properties.articulation_ids;
    return scene.robotics?.articulations.filter((item) => articulationIds?.includes(item.id)) ?? [];
}
function renderAssets(assets) {
    const list = element('asset-list');
    const groups = groupAssets(assets, assetFilter);
    list.innerHTML = groups.length ? groups.map((group) => `
    <section class="asset-group" data-asset-category="${group.category}" aria-labelledby="asset-group-${group.category}">
      <header class="asset-group-header">
        <h3 id="asset-group-${group.category}">${group.label}</h3>
        <span class="asset-group-count">${group.assets.length}</span>
      </header>
      <div class="asset-group-items">${group.assets.map((asset) => {
        const rgba = asset.default_properties?.rgba ?? [0.55, 0.62, 0.7, 1];
        const color = `rgb(${rgba.slice(0, 3).map((part) => Math.round(part * 255)).join(',')})`;
        return `<button class="asset-item" type="button" data-asset-id="${escapeHtml(asset.id)}" title="Add ${escapeHtml(asset.name)} to the scene">
          <span class="asset-swatch" style="background:${color}"></span>
          <span class="item-label">${escapeHtml(asset.name)}</span>
          <span class="item-meta">${escapeHtml(asset.primitive ?? asset.source_format ?? asset.type)}</span>
        </button>`;
    }).join('')}</div>
    </section>`).join('')
        : `<div class="empty-state">${assets.length ? `No assets match “${escapeHtml(assetFilter.trim())}”` : 'No assets'}</div>`;
    for (const button of list.querySelectorAll('[data-asset-id]')) {
        button.addEventListener('click', () => {
            const asset = store.current.assets.find((item) => item.id === button.dataset.assetId);
            if (asset)
                store.addAsset(asset, asset.robotics);
        });
    }
}
function renderSceneTree(scene, selectedActorId, selectedJointId, selectedSensorId) {
    element('actor-count').textContent = String(scene.actors.length);
    const tree = element('scene-tree');
    tree.innerHTML = scene.actors.length ? scene.actors.map((actor) => {
        const articulationIds = actor.properties.articulation_ids;
        const articulations = scene.robotics?.articulations.filter((item) => articulationIds?.includes(item.id)) ?? [];
        const robotRows = articulations.map((articulation) => `
      <div class="robot-tree" data-robot-id="${escapeHtml(articulation.id)}">
        ${articulation.links.map((link) => `
          <div class="tree-subitem link" title="${escapeHtml(link.id)}">
            <span class="item-icon"></span><span class="item-label">${escapeHtml(link.name)}</span>
          </div>`).join('')}
        ${articulation.joints.map((joint) => `
          <button class="tree-subitem joint ${joint.id === selectedJointId ? 'selected' : ''}" type="button" title="${escapeHtml(joint.id)}" data-joint-id="${escapeHtml(joint.id)}" data-owner-actor-id="${escapeHtml(actor.id)}">
            <span class="item-icon"></span><span class="item-label">${escapeHtml(joint.name)}</span>
          </button>`).join('')}
        ${articulation.sensors.map((sensor) => `
          <button class="tree-subitem sensor ${sensor.id === selectedSensorId ? 'selected' : ''}" type="button" title="${escapeHtml(sensor.id)}" data-sensor-id="${escapeHtml(sensor.id)}" data-owner-actor-id="${escapeHtml(actor.id)}">
            <span class="item-icon"></span><span class="item-label">${escapeHtml(sensor.name)}</span>
          </button>`).join('')}
      </div>`).join('');
        return `
    <button class="tree-item ${actor.id === selectedActorId && selectedJointId === null && selectedSensorId === null ? 'selected' : ''}" type="button" data-actor-row data-actor-id="${escapeHtml(actor.id)}">
      <span class="item-icon"></span>
      <span class="item-label">${escapeHtml(actor.name)}</span>
      <span class="delete-actor" data-delete-id="${escapeHtml(actor.id)}" title="Delete">×</span>
    </button>${robotRows}`;
    }).join('') : '<div class="empty-state">Scene is empty</div>';
    for (const button of tree.querySelectorAll('[data-actor-row]')) {
        button.addEventListener('click', (event) => {
            const deleteTarget = event.target.closest('[data-delete-id]');
            if (deleteTarget?.dataset.deleteId)
                store.deleteActor(deleteTarget.dataset.deleteId);
            else
                store.selectActor(button.dataset.actorId ?? null);
        });
    }
    for (const button of tree.querySelectorAll('[data-joint-id]')) {
        button.addEventListener('click', () => {
            const actorId = button.dataset.ownerActorId;
            const jointId = button.dataset.jointId;
            if (actorId && jointId)
                store.selectJoint(actorId, jointId);
        });
    }
    for (const button of tree.querySelectorAll('[data-sensor-id]')) {
        button.addEventListener('click', () => {
            const actorId = button.dataset.ownerActorId;
            const sensorId = button.dataset.sensorId;
            if (actorId && sensorId)
                store.selectSensor(actorId, sensorId);
        });
    }
}
function numberInput(label, field, value, options = '') {
    return `<div class="property-row"><label>${label}</label><input type="number" step="0.01" value="${value}" data-field="${field}" ${options}></div>`;
}
function vectorInput(label, field, values) {
    return `<div class="property-row"><label>${label}</label><div class="vector-row">${values.map((value, index) => `<input type="number" step="0.01" value="${value}" data-vector="${field}" data-index="${index}">`).join('')}</div></div>`;
}
function renderProperties(actor, scene, selectedJointId, selectedSensorId) {
    const inspector = element('property-inspector');
    if (!actor) {
        inspector.innerHTML = `<div class="empty-state rich-empty-state">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"></path><circle cx="9" cy="6" r="1.5"></circle><circle cx="15" cy="12" r="1.5"></circle><circle cx="7" cy="18" r="1.5"></circle></svg>
      <strong>Nothing selected</strong>
      <span>Pick an actor in the viewport or scene tree to edit its transform and physics.</span>
    </div>`;
        return;
    }
    const physics = actor.properties.physics ?? { dynamic: true };
    const friction = physics.friction ?? [0.8, 0.005, 0.0001];
    const geometry = actor.properties.geometry;
    const articulations = articulationsForActor(actor, scene);
    const selectedJoint = articulations.flatMap((item) => item.joints)
        .find((item) => item.id === selectedJointId);
    const selectedSensor = articulations.flatMap((item) => item.sensors)
        .find((item) => item.id === selectedSensorId);
    const simulationState = simulationStore.current.simulationState;
    const selectedSensorSample = simulationState?.sensors.find((item) => item.id === selectedSensorId);
    const jointStates = new Map((simulationState?.joints ?? []).map((item) => [item.id, item]));
    const sourceSection = geometry ? `
    <section class="property-group"><h3>Imported Geometry</h3>
      <div class="property-row"><label>Format</label><input type="text" value="OpenUSD" disabled></div>
      <div class="property-row"><label>Source</label><input type="text" value="${escapeHtml(geometry.source)}" title="${escapeHtml(geometry.source)}" disabled></div>
      <div class="property-row"><label>Collider</label><input type="text" value="Mesh" disabled></div>
    </section>` : '';
    const selectedJointState = selectedJoint ? jointStates.get(selectedJoint.id) : undefined;
    const selectedArticulation = selectedJoint
        ? articulations.find((item) => item.joints.some((joint) => joint.id === selectedJoint.id))
        : undefined;
    const parentLink = selectedArticulation?.links.find((item) => item.id === selectedJoint?.parent_link_id);
    const childLink = selectedArticulation?.links.find((item) => item.id === selectedJoint?.child_link_id);
    const sensorJoint = selectedSensor
        ? articulations.flatMap((item) => item.joints)
            .find((item) => item.id === selectedSensor.joint_id)
        : undefined;
    const sensorArticulation = selectedSensor
        ? articulations.find((item) => item.sensors.some((sensor) => sensor.id === selectedSensor.id))
        : undefined;
    const sensorLink = selectedSensor
        ? sensorArticulation?.links
            .find((item) => item.id === selectedSensor.link_id)
        : undefined;
    const sensorColliderLink = selectedSensor?.collider_id
        ? sensorArticulation?.links.find((link) => link.colliders.some((collider) => collider.id === selectedSensor.collider_id))
        : undefined;
    const sensorCollider = sensorColliderLink?.colliders.find((collider) => collider.id === selectedSensor?.collider_id);
    const selectedJointSensorSample = selectedSensorSample?.sensor_type === 'joint_state'
        ? selectedSensorSample
        : undefined;
    const selectedImuSample = selectedSensorSample?.sensor_type === 'imu'
        ? selectedSensorSample
        : undefined;
    const selectedContactSample = selectedSensorSample?.sensor_type === 'contact'
        ? selectedSensorSample
        : undefined;
    const selectedRangefinderSample = selectedSensorSample?.sensor_type === 'rangefinder'
        ? selectedSensorSample
        : undefined;
    const sensorPayloadFields = selectedSensor?.sensor_type === 'rangefinder' ? `
      <div class="property-row"><label>Sequence</label><input type="text" value="${selectedRangefinderSample?.sequence ?? '—'}" disabled data-sensor-field="sequence" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Time</label><input type="text" value="${selectedRangefinderSample?.time.toFixed(3) ?? '—'}" disabled data-sensor-field="time" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Distance</label><input type="text" value="${selectedRangefinderSample?.distance.toFixed(3) ?? '—'} m" disabled data-sensor-field="distance" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Hit</label><input type="text" value="${selectedRangefinderSample ? (selectedRangefinderSample.hit ? 'yes' : 'no') : '—'}" disabled data-sensor-field="hit" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Max Range</label><input type="text" value="${selectedSensor.max_distance?.toFixed(2) ?? '—'} m" disabled></div>` : selectedSensor?.sensor_type === 'contact' ? `
      <div class="property-row"><label>Sequence</label><input type="text" value="${selectedContactSample?.sequence ?? '—'}" disabled data-sensor-field="sequence" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Time</label><input type="text" value="${selectedContactSample?.time.toFixed(3) ?? '—'}" disabled data-sensor-field="time" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Count</label><input type="text" value="${selectedContactSample?.contact_count ?? '—'}" disabled data-sensor-field="contact_count" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Normal Force</label><input type="text" value="${selectedContactSample?.normal_force.toFixed(3) ?? '—'}" disabled data-sensor-field="normal_force" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Impulse</label><input type="text" value="${selectedContactSample?.normal_impulse.toFixed(4) ?? '—'}" disabled data-sensor-field="normal_impulse" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Tangent</label><input type="text" value="${selectedContactSample?.tangent_force.map((value) => value.toFixed(3)).join(', ') ?? '—'}" disabled data-sensor-field="tangent_force" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>First Point</label><input type="text" value="${selectedContactSample?.points[0]?.map((value) => value.toFixed(3)).join(', ') ?? '—'}" disabled data-sensor-field="first_point" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>First Normal</label><input type="text" value="${selectedContactSample?.normals[0]?.map((value) => value.toFixed(3)).join(', ') ?? '—'}" disabled data-sensor-field="first_normal" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>` : selectedSensor?.sensor_type === 'imu' ? `
      <div class="property-row"><label>Sequence</label><input type="text" value="${selectedImuSample?.sequence ?? '—'}" disabled data-sensor-field="sequence" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Time</label><input type="text" value="${selectedImuSample?.time.toFixed(3) ?? '—'}" disabled data-sensor-field="time" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Orientation</label><input type="text" value="${selectedImuSample?.orientation.map((value) => value.toFixed(3)).join(', ') ?? '—'}" disabled data-sensor-field="orientation" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Angular Vel.</label><input type="text" value="${selectedImuSample?.angular_velocity.map((value) => value.toFixed(3)).join(', ') ?? '—'}" disabled data-sensor-field="angular_velocity" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>
      <div class="property-row"><label>Linear Accel.</label><input type="text" value="${selectedImuSample?.linear_acceleration.map((value) => value.toFixed(3)).join(', ') ?? '—'}" disabled data-sensor-field="linear_acceleration" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>` : `
      <div class="property-row"><label>Sequence</label><input type="text" value="${selectedJointSensorSample?.sequence ?? '—'}" disabled data-sensor-field="sequence" data-runtime-sensor-id="${escapeHtml(selectedSensor?.id ?? '')}"></div>
      <div class="property-row"><label>Time</label><input type="text" value="${selectedJointSensorSample?.time.toFixed(3) ?? '—'}" disabled data-sensor-field="time" data-runtime-sensor-id="${escapeHtml(selectedSensor?.id ?? '')}"></div>
      <div class="property-row"><label>Position</label><input type="text" value="${selectedJointSensorSample?.qpos.toFixed(3) ?? '—'}" disabled data-sensor-field="qpos" data-runtime-sensor-id="${escapeHtml(selectedSensor?.id ?? '')}"></div>
      <div class="property-row"><label>Velocity</label><input type="text" value="${selectedJointSensorSample?.qvel.toFixed(3) ?? '—'}" disabled data-sensor-field="qvel" data-runtime-sensor-id="${escapeHtml(selectedSensor?.id ?? '')}"></div>`;
    const identitySections = selectedSensor ? `
    <section class="property-group"><h3>Sensor</h3>
      <div class="property-row"><label>Name</label><input type="text" value="${escapeHtml(selectedSensor.name)}" disabled></div>
      <div class="property-row"><label>Type</label><input type="text" value="${escapeHtml(selectedSensor.sensor_type)}" disabled></div>
      <div class="property-row"><label>${selectedSensor.sensor_type === 'contact' ? 'Scope' : ['imu', 'rangefinder'].includes(selectedSensor.sensor_type) ? 'Link' : 'Joint'}</label><input type="text" value="${escapeHtml(selectedSensor.sensor_type === 'contact' ? sensorCollider?.name ?? sensorLink?.name ?? selectedSensor.collider_id ?? selectedSensor.link_id ?? '—' : ['imu', 'rangefinder'].includes(selectedSensor.sensor_type) ? sensorLink?.name ?? selectedSensor.link_id ?? '—' : sensorJoint?.name ?? selectedSensor.joint_id ?? '—')}" disabled data-sensor-scope></div>
      <div class="property-row"><label>Rate</label><input type="text" value="${selectedSensor.update_rate_hz === null ? 'Physics rate' : `${selectedSensor.update_rate_hz} Hz`}" disabled></div>
      ${sensorPayloadFields}
    </section>` : selectedJoint ? `
    <section class="property-group"><h3>Joint</h3>
      <div class="property-row"><label>Name</label><input type="text" value="${escapeHtml(selectedJoint.name)}" disabled></div>
      <div class="property-row"><label>Type</label><input type="text" value="${escapeHtml(selectedJoint.type)}" disabled></div>
      <div class="property-row"><label>Parent</label><input type="text" value="${escapeHtml(parentLink?.name ?? selectedJoint.parent_link_id)}" disabled></div>
      <div class="property-row"><label>Child</label><input type="text" value="${escapeHtml(childLink?.name ?? selectedJoint.child_link_id)}" disabled></div>
      <div class="property-row"><label>Axis</label><input type="text" value="${selectedJoint.axis.join(', ')}" disabled></div>
      <div class="property-row"><label>Range</label><input type="text" value="${selectedJoint.limits?.lower?.toFixed(3) ?? '—'} to ${selectedJoint.limits?.upper?.toFixed(3) ?? '—'}" disabled></div>
      <div class="property-row"><label>Position</label><input type="text" value="${selectedJointState?.qpos.toFixed(3) ?? selectedJoint.initial_position}" disabled data-joint-position-field="${escapeHtml(selectedJoint.id)}"></div>
    </section>` : `
    <section class="property-group"><h3>Actor</h3>
      <div class="property-row"><label>Name</label><input type="text" value="${escapeHtml(actor.name)}" data-field="name"></div>
      <div class="property-row"><label>Type</label><input type="text" value="${escapeHtml(actor.type)}" disabled></div>
      <div class="property-row"><label>Asset</label><input type="text" value="${escapeHtml(actor.asset_id)}" disabled></div>
    </section>
    <section class="property-group"><h3>Transform</h3>
      ${vectorInput('Position', 'position', actor.transform.position)}
      ${vectorInput('Rotation', 'rotation', actor.transform.rotation)}
      ${vectorInput('Scale', 'scale', actor.transform.scale)}
    </section>
    ${sourceSection}`;
    const physicsSection = selectedJoint || selectedSensor ? '' : `
    <section class="property-group"><h3>Physics</h3>
      <div class="property-row"><label>Dynamic</label><input type="checkbox" data-field="dynamic" ${physics.dynamic ? 'checked' : ''}></div>
      <div class="property-row"><label>Material</label><select data-field="material">${Object.keys(materialPresets).map((id) => `<option value="${id}" ${physics.material === id ? 'selected' : ''}>${id[0].toUpperCase()}${id.slice(1)}</option>`).join('')}</select></div>
      <div class="property-row"><label>Mass Mode</label><select data-field="mass_mode"><option value="mass" ${physics.mass_mode !== 'density' ? 'selected' : ''}>Explicit Mass</option><option value="density" ${physics.mass_mode === 'density' ? 'selected' : ''}>Material Density</option></select></div>
      ${numberInput('Mass', 'mass', physics.mass ?? actor.properties.mass ?? 1, physics.mass_mode === 'density' ? 'disabled' : '')}
      ${numberInput('Density', 'density', physics.density ?? 1000, physics.mass_mode !== 'density' ? 'disabled' : '')}
      ${numberInput('Friction', 'friction', friction[0], 'min="0"')}
    </section>`;
    inspector.innerHTML = `
    ${identitySections}
    ${physicsSection}`;
    const actorId = actor.id;
    for (const input of inspector.querySelectorAll('[data-field]')) {
        input.addEventListener('change', () => updateProperty(actorId, input));
    }
    for (const input of inspector.querySelectorAll('[data-vector]')) {
        input.addEventListener('change', () => {
            const current = store.current.scene.actors.find((item) => item.id === actorId);
            if (!current)
                return;
            const transform = structuredClone(current.transform);
            const vector = transform[input.dataset.vector];
            vector[Number(input.dataset.index)] = Number(input.value);
            store.updateActorTransform(actorId, transform);
        });
    }
}
function renderArmControl(actor, scene, selectedJointId) {
    const body = element('arm-control-body');
    if (!actor || actor.type !== 'robot') {
        body.innerHTML = '<div class="empty-state">Select a robot actor</div>';
        return;
    }
    const articulations = articulationsForActor(actor, scene);
    const simulationState = simulationStore.current.simulationState;
    const jointStates = new Map((simulationState?.joints ?? []).map((item) => [item.id, item]));
    const actuatorStates = new Map((simulationState?.actuators ?? []).map((item) => [item.id, item]));
    const jointControls = articulations.flatMap((articulation) => articulation.actuators
        .filter((item) => item.control_type === 'position')
        .filter((item) => selectedJointId === null || item.joint_id === selectedJointId)
        .map((actuator) => {
        const joint = articulation.joints.find((item) => item.id === actuator.joint_id);
        if (!joint)
            return '';
        const state = jointStates.get(joint.id);
        const target = actuatorStates.get(actuator.id)?.ctrl ?? joint.initial_position;
        return `<div class="joint-control">
        <div class="joint-header"><label>${escapeHtml(joint.name)}</label><span data-joint-position="${escapeHtml(joint.id)}">${state?.qpos.toFixed(3) ?? '—'} rad</span></div>
        <div class="joint-target-row">
          <button type="button" class="joint-jog-button" title="Jog negative" data-joint-jog="${escapeHtml(joint.id)}" data-direction="-1">-</button>
          <input type="range" min="${actuator.control_range[0]}" max="${actuator.control_range[1]}" step="0.05" value="${target}" data-joint-target="${escapeHtml(joint.id)}" data-actuator-id="${escapeHtml(actuator.id)}">
          <button type="button" class="joint-jog-button" title="Jog positive" data-joint-jog="${escapeHtml(joint.id)}" data-direction="1">+</button>
          <input type="number" min="${actuator.control_range[0]}" max="${actuator.control_range[1]}" step="0.05" value="${target.toFixed(3)}" data-joint-target="${escapeHtml(joint.id)}" data-actuator-id="${escapeHtml(actuator.id)}">
        </div>
        <div class="joint-state"><span data-joint-qpos="${escapeHtml(joint.id)}">qpos ${state?.qpos.toFixed(3) ?? '—'}</span><span data-joint-qvel="${escapeHtml(joint.id)}">qvel ${state?.qvel.toFixed(3) ?? '—'}</span></div>
      </div>`;
    })).join('');
    if (!jointControls) {
        body.innerHTML = '<div class="empty-state">No position joints</div>';
        return;
    }
    body.innerHTML = `
    <section class="property-group"><div class="group-heading"><h3>Joint Control</h3><div class="joint-tools"><label>Step <input type="number" min="0.001" max="1" step="0.01" value="0.05" data-joint-step></label><button type="button" data-joint-home>Home</button></div></div>
      ${jointControls}
    </section>`;
    for (const input of body.querySelectorAll('[data-joint-target]')) {
        input.addEventListener('change', () => {
            const jointId = input.dataset.jointTarget;
            if (jointId)
                void sendJointTargets({ [jointId]: Number(input.value) });
        });
    }
    body.querySelector('[data-joint-step]')?.addEventListener('change', (event) => {
        const value = Number(event.currentTarget.value);
        if (!Number.isFinite(value) || value <= 0)
            return;
        for (const input of body.querySelectorAll('[data-joint-target]')) {
            input.step = String(value);
        }
    });
    for (const button of body.querySelectorAll('[data-joint-jog]')) {
        button.addEventListener('click', () => {
            const jointId = button.dataset.jointJog;
            const direction = Number(button.dataset.direction);
            const step = Number(body.querySelector('[data-joint-step]')?.value);
            const targetInput = Array.from(body.querySelectorAll('input[type="number"][data-joint-target]')).find((input) => input.dataset.jointTarget === jointId);
            const target = Number(targetInput?.value);
            if (!jointId || !Number.isFinite(step) || step <= 0
                || Math.abs(direction) !== 1 || !Number.isFinite(target)) {
                showToast('Joint jog requires a positive step and finite target', true);
                return;
            }
            void sendJointTargets({ [jointId]: target + direction * step });
        });
    }
    body.querySelector('[data-joint-home]')?.addEventListener('click', () => {
        const targets = Object.fromEntries(articulations.flatMap((articulation) => articulation.actuators.filter((actuator) => actuator.control_type === 'position')
            .filter((actuator) => selectedJointId === null || actuator.joint_id === selectedJointId)
            .map((actuator) => articulation.joints.find((joint) => joint.id === actuator.joint_id))
            .filter((joint) => joint !== undefined)
            .map((joint) => [joint.id, joint.initial_position])));
        void sendJointTargets(targets);
    });
}
function renderDroneControl(actor, scene) {
    const body = element('drone-control-body');
    const propulsion = actor?.properties.propulsion;
    if (!actor || propulsion?.type !== 'quadrotor') {
        body.innerHTML = '<div class="empty-state">Select a quadrotor actor</div>';
        return;
    }
    const articulations = articulationsForActor(actor, scene);
    const actuatorStates = new Map((simulationStore.current.simulationState?.actuators ?? []).map((item) => [item.id, item]));
    const robotActuators = new Map(articulations.flatMap((item) => item.actuators).map((item) => [item.id, item]));
    const rotorControls = propulsion.rotors.map((rotor) => {
        const actuator = robotActuators.get(rotor.actuator_id);
        if (!actuator)
            return '';
        const target = actuatorStates.get(actuator.id)?.ctrl ?? 0;
        return `<div class="joint-control">
      <div class="joint-header"><label>${escapeHtml(rotor.id)}</label><span>${target.toFixed(1)} rad/s</span></div>
      <div class="joint-target-row">
        <input type="range" min="${rotor.min_angular_velocity}" max="${rotor.max_angular_velocity}" step="1" value="${target}" data-rotor-control="${escapeHtml(actuator.id)}" data-actuator-id="${escapeHtml(actuator.id)}">
        <input type="number" min="${rotor.min_angular_velocity}" max="${rotor.max_angular_velocity}" step="1" value="${target.toFixed(1)}" data-rotor-control="${escapeHtml(actuator.id)}" data-actuator-id="${escapeHtml(actuator.id)}">
      </div>
    </div>`;
    }).join('');
    body.innerHTML = `
    <section class="property-group"><div class="group-heading"><h3>Rotor Control</h3><div class="joint-tools"><button type="button" data-rotor-stop>Stop Rotors</button></div></div>
      ${rotorControls}
    </section>
    <p class="window-hint">实际推力仍由 MuJoCo 四旋翼模型产生。</p>`;
    for (const input of body.querySelectorAll('[data-rotor-control]')) {
        input.addEventListener('change', () => {
            const actuatorId = input.dataset.rotorControl;
            if (actuatorId)
                void sendActuatorControls({ [actuatorId]: Number(input.value) });
        });
    }
    body.querySelector('[data-rotor-stop]')?.addEventListener('click', () => {
        void sendActuatorControls(Object.fromEntries(propulsion.rotors.map((rotor) => [rotor.actuator_id, 0])));
    });
}
function renderSensorView(actor, scene, selectedSensorId) {
    const body = element('sensor-view-body');
    const articulations = actor ? articulationsForActor(actor, scene) : [];
    const selectedSensor = articulations.flatMap((item) => item.sensors)
        .find((item) => item.id === selectedSensorId);
    if (!selectedSensor) {
        body.innerHTML = '<div class="empty-state">Select a sensor in the scene tree</div>';
        return;
    }
    const simulationState = simulationStore.current.simulationState;
    const sample = simulationState?.sensors.find((item) => item.id === selectedSensor.id);
    const sensorArticulation = articulations.find((item) => item.sensors.some((sensor) => sensor.id === selectedSensor.id));
    const sensorJoint = articulations.flatMap((item) => item.joints)
        .find((item) => item.id === selectedSensor.joint_id);
    const sensorLink = sensorArticulation?.links.find((item) => item.id === selectedSensor.link_id);
    const sensorColliderLink = selectedSensor.collider_id
        ? sensorArticulation?.links.find((link) => link.colliders.some((collider) => collider.id === selectedSensor.collider_id))
        : undefined;
    const sensorCollider = sensorColliderLink?.colliders.find((collider) => collider.id === selectedSensor.collider_id);
    const scopeLabel = selectedSensor.sensor_type === 'contact'
        ? 'Scope'
        : ['imu', 'rangefinder'].includes(selectedSensor.sensor_type) ? 'Link' : 'Joint';
    const scopeValue = selectedSensor.sensor_type === 'contact'
        ? sensorCollider?.name ?? sensorLink?.name ?? selectedSensor.collider_id ?? selectedSensor.link_id ?? '—'
        : ['imu', 'rangefinder'].includes(selectedSensor.sensor_type)
            ? sensorLink?.name ?? selectedSensor.link_id ?? '—'
            : sensorJoint?.name ?? selectedSensor.joint_id ?? '—';
    const field = (label, value, name) => `<div class="property-row"><label>${label}</label><input type="text" value="${escapeHtml(value)}" disabled data-sensor-field="${name}" data-runtime-sensor-id="${escapeHtml(selectedSensor.id)}"></div>`;
    let payloadFields = '';
    if (selectedSensor.sensor_type === 'rangefinder') {
        const typed = sample?.sensor_type === 'rangefinder' ? sample : undefined;
        payloadFields = field('Sequence', String(typed?.sequence ?? '—'), 'sequence')
            + field('Time', typed?.time.toFixed(3) ?? '—', 'time')
            + field('Distance', typed ? `${typed.distance.toFixed(3)} m` : '—', 'distance')
            + field('Hit', typed ? (typed.hit ? 'yes' : 'no') : '—', 'hit')
            + `<div class="property-row"><label>Max Range</label><input type="text" value="${selectedSensor.max_distance?.toFixed(2) ?? '—'} m" disabled></div>`;
    }
    else if (selectedSensor.sensor_type === 'contact') {
        const typed = sample?.sensor_type === 'contact' ? sample : undefined;
        payloadFields = field('Sequence', String(typed?.sequence ?? '—'), 'sequence')
            + field('Time', typed?.time.toFixed(3) ?? '—', 'time')
            + field('Count', String(typed?.contact_count ?? '—'), 'contact_count')
            + field('Normal Force', typed?.normal_force.toFixed(3) ?? '—', 'normal_force')
            + field('Impulse', typed?.normal_impulse.toFixed(4) ?? '—', 'normal_impulse')
            + field('Tangent', typed?.tangent_force.map((v) => v.toFixed(3)).join(', ') ?? '—', 'tangent_force')
            + field('First Point', typed?.points[0]?.map((v) => v.toFixed(3)).join(', ') ?? '—', 'first_point')
            + field('First Normal', typed?.normals[0]?.map((v) => v.toFixed(3)).join(', ') ?? '—', 'first_normal');
    }
    else if (selectedSensor.sensor_type === 'imu') {
        const typed = sample?.sensor_type === 'imu' ? sample : undefined;
        payloadFields = field('Sequence', String(typed?.sequence ?? '—'), 'sequence')
            + field('Time', typed?.time.toFixed(3) ?? '—', 'time')
            + field('Orientation', typed?.orientation.map((v) => v.toFixed(3)).join(', ') ?? '—', 'orientation')
            + field('Angular Vel.', typed?.angular_velocity.map((v) => v.toFixed(3)).join(', ') ?? '—', 'angular_velocity')
            + field('Linear Accel.', typed?.linear_acceleration.map((v) => v.toFixed(3)).join(', ') ?? '—', 'linear_acceleration');
    }
    else {
        const typed = sample?.sensor_type === 'joint_state' ? sample : undefined;
        payloadFields = field('Sequence', String(typed?.sequence ?? '—'), 'sequence')
            + field('Time', typed?.time.toFixed(3) ?? '—', 'time')
            + field('Position', typed?.qpos.toFixed(3) ?? '—', 'qpos')
            + field('Velocity', typed?.qvel.toFixed(3) ?? '—', 'qvel');
    }
    body.innerHTML = `
    <section class="property-group"><h3>${escapeHtml(selectedSensor.name)}</h3>
      <div class="property-row"><label>Type</label><input type="text" value="${escapeHtml(selectedSensor.sensor_type)}" disabled></div>
      <div class="property-row"><label>${scopeLabel}</label><input type="text" value="${escapeHtml(scopeValue)}" disabled></div>
      <div class="property-row"><label>Rate</label><input type="text" value="${selectedSensor.update_rate_hz === null ? 'Physics rate' : `${selectedSensor.update_rate_hz} Hz`}" disabled></div>
      ${payloadFields}
    </section>`;
}
function updateRuntimeInspector(simulationState) {
    if (!simulationState)
        return;
    const controller = document.querySelector('[data-controller-status]');
    if (controller) {
        controller.dataset.controllerStatus = simulationState.controller.status;
        const label = controller.querySelector('[data-controller-status-label]');
        const message = controller.querySelector('[data-controller-message]');
        if (label)
            label.textContent = simulationState.controller.status.replace('_', ' ');
        if (message)
            message.textContent = simulationState.controller.message ?? '';
    }
    for (const joint of simulationState.joints) {
        for (const item of document.querySelectorAll('[data-joint-position]')) {
            if (item.dataset.jointPosition === joint.id)
                item.textContent = `${joint.qpos.toFixed(3)} rad`;
        }
        for (const item of document.querySelectorAll('[data-joint-qpos]')) {
            if (item.dataset.jointQpos === joint.id)
                item.textContent = `qpos ${joint.qpos.toFixed(3)}`;
        }
        for (const item of document.querySelectorAll('[data-joint-qvel]')) {
            if (item.dataset.jointQvel === joint.id)
                item.textContent = `qvel ${joint.qvel.toFixed(3)}`;
        }
        for (const input of document.querySelectorAll('[data-joint-position-field]')) {
            if (input.dataset.jointPositionField === joint.id)
                input.value = joint.qpos.toFixed(3);
        }
    }
    for (const actuator of simulationState.actuators) {
        for (const input of document.querySelectorAll('[data-actuator-id]')) {
            if (input.dataset.actuatorId === actuator.id && document.activeElement !== input) {
                input.value = input.type === 'number' ? actuator.ctrl.toFixed(3) : String(actuator.ctrl);
            }
        }
    }
    for (const sensor of simulationState.sensors) {
        for (const input of document.querySelectorAll('[data-runtime-sensor-id]')) {
            if (input.dataset.runtimeSensorId !== sensor.id)
                continue;
            const field = input.dataset.sensorField;
            if (field === 'sequence')
                input.value = String(sensor.sequence);
            else if (field === 'time')
                input.value = sensor.time.toFixed(3);
            else if (sensor.sensor_type === 'joint_state' && field === 'qpos') {
                input.value = sensor.qpos.toFixed(3);
            }
            else if (sensor.sensor_type === 'joint_state' && field === 'qvel') {
                input.value = sensor.qvel.toFixed(3);
            }
            else if (sensor.sensor_type === 'imu' && field === 'orientation') {
                input.value = sensor.orientation.map((value) => value.toFixed(3)).join(', ');
            }
            else if (sensor.sensor_type === 'imu' && field === 'angular_velocity') {
                input.value = sensor.angular_velocity.map((value) => value.toFixed(3)).join(', ');
            }
            else if (sensor.sensor_type === 'imu' && field === 'linear_acceleration') {
                input.value = sensor.linear_acceleration.map((value) => value.toFixed(3)).join(', ');
            }
            else if (sensor.sensor_type === 'contact' && field === 'contact_count') {
                input.value = String(sensor.contact_count);
            }
            else if (sensor.sensor_type === 'contact' && field === 'normal_force') {
                input.value = sensor.normal_force.toFixed(3);
            }
            else if (sensor.sensor_type === 'contact' && field === 'normal_impulse') {
                input.value = sensor.normal_impulse.toFixed(4);
            }
            else if (sensor.sensor_type === 'contact' && field === 'tangent_force') {
                input.value = sensor.tangent_force.map((value) => value.toFixed(3)).join(', ');
            }
            else if (sensor.sensor_type === 'contact' && field === 'first_point') {
                input.value = sensor.points[0]?.map((value) => value.toFixed(3)).join(', ') ?? '—';
            }
            else if (sensor.sensor_type === 'contact' && field === 'first_normal') {
                input.value = sensor.normals[0]?.map((value) => value.toFixed(3)).join(', ') ?? '—';
            }
            else if (sensor.sensor_type === 'rangefinder' && field === 'distance') {
                input.value = `${sensor.distance.toFixed(3)} m`;
            }
            else if (sensor.sensor_type === 'rangefinder' && field === 'hit') {
                input.value = sensor.hit ? 'yes' : 'no';
            }
        }
    }
}
async function sendJointTargets(targets) {
    const result = await bridge.call('setJointTargets', JSON.stringify(store.current.scene), JSON.stringify(targets));
    if (!result.ok || !result.data) {
        if (result.data?.state)
            simulationStore.setSimulation('paused', result.data.state);
        showToast(result.error ?? 'Joint control failed', true);
        return;
    }
    const status = simulationStore.current.simulationStatus === 'running' ? 'running' : 'paused';
    simulationStore.setSimulation(status, result.data.state);
}
async function sendActuatorControls(controls) {
    const result = await bridge.call('setActuatorControls', JSON.stringify(store.current.scene), JSON.stringify(controls));
    if (!result.ok || !result.data) {
        if (result.data?.state)
            simulationStore.setSimulation('paused', result.data.state);
        showToast(result.error ?? 'Actuator control failed', true);
        return;
    }
    const status = simulationStore.current.simulationStatus === 'running' ? 'running' : 'paused';
    simulationStore.setSimulation(status, result.data.state);
}
function updateProperty(actorId, input) {
    const actor = store.current.scene.actors.find((item) => item.id === actorId);
    if (!actor)
        return;
    const field = input.dataset.field;
    if (field === 'name') {
        store.updateActorName(actorId, input.value);
        return;
    }
    const physics = structuredClone(actor.properties.physics ?? { dynamic: true });
    if (field === 'dynamic')
        physics.dynamic = input.checked;
    else if (field === 'material') {
        physics.material = input.value;
        Object.assign(physics, structuredClone(materialPresets[input.value]));
    }
    else if (field === 'mass_mode')
        physics.mass_mode = input.value;
    else if (field === 'mass')
        physics.mass = Number(input.value);
    else if (field === 'density')
        physics.density = Number(input.value);
    else if (field === 'friction') {
        const friction = [...(physics.friction ?? [0.8, 0.005, 0.0001])];
        friction[0] = Number(input.value);
        physics.friction = friction;
    }
    store.updateActorProperties(actorId, { physics, mass: physics.mass });
}
function renderValidation(issues) {
    const count = document.getElementById('validation-count');
    if (count)
        count.textContent = String(issues.length);
    const badge = document.querySelector('[data-tab-badge="validation"]');
    if (badge) {
        badge.textContent = String(issues.length);
        badge.hidden = issues.length === 0;
    }
    workspace.autoOpen('validation', issues.length > 0);
    const list = element('validation-list');
    list.innerHTML = issues.length ? issues.map((issue, index) => `
    <button type="button" class="validation-item ${issue.severity}" data-issue-index="${index}">
      <span class="validation-code">${escapeHtml(issue.code)}</span>
      <span class="validation-message">${escapeHtml(issue.actor_name ?? issue.actor_id ?? 'Scene')}: ${escapeHtml(issue.message)}</span>
    </button>`).join('') : '<div class="empty-state">No issues · Run a Preflight to check the scene</div>';
    for (const button of list.querySelectorAll('[data-issue-index]')) {
        button.addEventListener('click', () => {
            const issue = issues[Number(button.dataset.issueIndex)];
            if (issue.actor_id)
                store.selectActor(issue.actor_id);
        });
    }
}
function renderConsole(logs) {
    const output = element('console-output');
    output.innerHTML = logs.map((line) => `<div class="console-line">${escapeHtml(line)}</div>`).join('');
    output.scrollTop = output.scrollHeight;
}
function renderTrajectoryWindows(actor, scene) {
    const editorBody = element('trajectory-editor-body');
    const playerBody = element('trajectory-player-body');
    if (!actor || actor.type !== 'robot') {
        editorBody.innerHTML = '<div class="empty-state">Select a robot actor</div>';
        playerBody.innerHTML = '<div class="empty-state">Select a robot actor</div>';
        return;
    }
    const draftState = ensureTrajectoryDraft(actor, scene);
    if (!draftState) {
        editorBody.innerHTML = '<div class="empty-state">No position joints</div>';
        playerBody.innerHTML = '<div class="empty-state">No position joints</div>';
        return;
    }
    const { draft } = draftState;
    const bindings = positionJointBindings(actor, scene);
    const clips = scene.trajectories?.filter((item) => item.actor_id === actor.id) ?? [];
    const activeClip = clips.find((item) => item.id === draftState.clipId);
    const controls = editorBody;
    editorBody.innerHTML = `
    <div class="trajectory-library-controls">
      <select data-trajectory-clip title="Saved trajectory">
        <option value="" ${activeClip ? '' : 'selected'}>New Clip</option>
        ${clips.map((clip) => `<option value="${escapeHtml(clip.id)}" ${clip.id === activeClip?.id ? 'selected' : ''}>${escapeHtml(clip.trajectory.name)}</option>`).join('')}
      </select>
      <button type="button" data-trajectory-save title="Save clip">Save</button>
      <button type="button" class="icon-button" data-trajectory-delete title="Delete clip" ${activeClip ? '' : 'disabled'}>×</button>
    </div>
    <div class="trajectory-fields">
      <input type="text" value="${escapeHtml(draft.name)}" data-trajectory-name title="Trajectory name">
      <input type="number" min="0.05" step="0.1" value="${trajectoryDuration(draft)}" data-trajectory-duration title="Duration in seconds">
      <label><input type="checkbox" data-trajectory-loop ${draft.loop ? 'checked' : ''}>Loop</label>
    </div>
    <div class="keyframe-toolbar">
      <span>${draft.keyframes.length} Keyframes</span>
      <button type="button" data-keyframe-add>Add Current</button>
    </div>
    <div class="keyframe-list">
      ${draft.keyframes.map((keyframe, index) => `
        <div class="keyframe-row" data-keyframe-id="${escapeHtml(keyframe.id)}">
          <div class="keyframe-header">
            <strong>#${index + 1}</strong>
            <label>Time <input type="number" min="0" step="0.05" value="${keyframe.time}" data-keyframe-time ${index === 0 ? 'disabled' : ''}></label>
            <button type="button" class="icon-button" data-keyframe-delete title="Delete keyframe" ${index === 0 || draft.keyframes.length <= 2 ? 'disabled' : ''}>×</button>
          </div>
          <div class="keyframe-targets">
            ${bindings.map(({ joint, actuator }) => `
              <label title="${escapeHtml(joint.id)}">
                <span>${escapeHtml(joint.name)}</span>
                <input type="number" min="${actuator.control_range[0]}" max="${actuator.control_range[1]}" step="0.01" value="${keyframe.targets[joint.id]}" data-keyframe-target="${escapeHtml(joint.id)}">
              </label>`).join('')}
          </div>
        </div>`).join('')}
    </div>`;
    playerBody.innerHTML = `
    <progress class="trajectory-progress" value="0" max="1" data-trajectory-progress></progress>
    <div class="trajectory-time" data-trajectory-time>0.00 / 0.00 s</div>
    <div class="trajectory-actions">
      <button type="button" data-trajectory-command="load">Load</button>
      <button type="button" class="icon-button" data-trajectory-command="play" title="Play">▶</button>
      <button type="button" class="icon-button" data-trajectory-command="pause" title="Pause">Ⅱ</button>
      <button type="button" class="icon-button" data-trajectory-command="stop" title="Stop">■</button>
    </div>`;
    controls.querySelector('[data-trajectory-clip]')?.addEventListener('change', (event) => {
        setTrajectoryDraftClip(actor, scene, event.currentTarget.value || null);
        renderTrajectoryWindows(actor, scene);
    });
    controls.querySelector('[data-trajectory-save]')?.addEventListener('click', () => {
        try {
            const trajectory = trajectoryFromDraft(draftState.draft);
            const clipId = store.upsertTrajectory(actor.id, trajectory, draftState.clipId ?? undefined);
            if (!clipId)
                throw new Error('Trajectory owner must be a robot actor');
            draftState.clipId = clipId;
            draftState.sourceSignature = JSON.stringify([clipId, trajectory]);
            draftState.targetsTouched = true;
            showToast('Trajectory clip saved');
            renderTrajectoryWindows(actor, store.current.scene);
        }
        catch (error) {
            showToast(error instanceof Error ? error.message : String(error), true);
        }
    });
    controls.querySelector('[data-trajectory-delete]')?.addEventListener('click', () => {
        if (!activeClip)
            return;
        const homeTargets = Object.fromEntries(bindings.map(({ joint }) => [
            joint.id,
            joint.initial_position,
        ]));
        const placeholder = createTrajectoryDraftState(actor.id, homeTargets);
        placeholder.clipId = activeClip.id;
        placeholder.sourceSignature = `missing:${activeClip.id}:${placeholder.homeSignature}`;
        trajectoryDrafts.set(actor.id, placeholder);
        store.removeTrajectory(activeClip.id);
        showToast('Trajectory clip deleted');
    });
    controls.querySelector('[data-trajectory-name]')?.addEventListener('change', (event) => { draft.name = event.currentTarget.value; });
    controls.querySelector('[data-trajectory-duration]')?.addEventListener('change', (event) => {
        try {
            draftState.draft = setTrajectoryDuration(draftState.draft, Number(event.currentTarget.value));
            renderTrajectoryWindows(actor, scene);
        }
        catch (error) {
            showToast(error instanceof Error ? error.message : String(error), true);
        }
    });
    controls.querySelector('[data-trajectory-loop]')?.addEventListener('change', (event) => { draft.loop = event.currentTarget.checked; });
    for (const button of playerBody.querySelectorAll('[data-trajectory-command]')) {
        button.addEventListener('click', () => {
            void handleTrajectoryCommand(button.dataset.trajectoryCommand ?? '', actor, scene);
        });
    }
    controls.querySelector('[data-keyframe-add]')?.addEventListener('click', () => {
        draftState.draft = captureTrajectoryKeyframe(draftState.draft, `keyframe-${draftState.nextKeyframeId++}`, trajectoryDuration(draftState.draft) + 0.5, currentRobotTargets(actor, scene));
        draftState.targetsTouched = true;
        renderTrajectoryWindows(actor, scene);
    });
    for (const row of controls.querySelectorAll('[data-keyframe-id]')) {
        const keyframeId = row.dataset.keyframeId ?? '';
        row.querySelector('[data-keyframe-time]')?.addEventListener('change', (event) => {
            draftState.draft = updateTrajectoryKeyframeTime(draftState.draft, keyframeId, Number(event.currentTarget.value));
            draftState.targetsTouched = true;
            renderTrajectoryWindows(actor, scene);
        });
        for (const input of row.querySelectorAll('[data-keyframe-target]')) {
            input.addEventListener('change', () => {
                draftState.draft = updateTrajectoryKeyframeTarget(draftState.draft, keyframeId, input.dataset.keyframeTarget ?? '', Number(input.value));
                draftState.targetsTouched = true;
            });
        }
        row.querySelector('[data-keyframe-delete]')?.addEventListener('click', () => {
            try {
                draftState.draft = removeTrajectoryKeyframe(draftState.draft, keyframeId);
                draftState.targetsTouched = true;
                renderTrajectoryWindows(actor, scene);
            }
            catch (error) {
                showToast(error instanceof Error ? error.message : String(error), true);
            }
        });
    }
    updateTrajectoryRuntime(simulationStore.current.simulationState);
}
function positionJointBindings(actor, scene) {
    const articulationIds = actor.properties.articulation_ids;
    const articulations = scene.robotics?.articulations.filter((item) => articulationIds?.includes(item.id)) ?? [];
    const bindings = [];
    for (const articulation of articulations) {
        for (const actuator of articulation.actuators) {
            if (actuator.control_type !== 'position')
                continue;
            const joint = articulation.joints.find((item) => item.id === actuator.joint_id);
            if (!joint)
                continue;
            bindings.push({ joint, actuator });
        }
    }
    return bindings;
}
function robotSensors(actor, scene) {
    const articulationIds = actor.properties.articulation_ids;
    return scene.robotics?.articulations
        .filter((item) => articulationIds?.includes(item.id))
        .flatMap((item) => item.sensors) ?? [];
}
function currentRobotTargets(actor, scene) {
    const actuatorStates = new Map((simulationStore.current.simulationState?.actuators ?? []).map((item) => [item.id, item.ctrl]));
    return Object.fromEntries(positionJointBindings(actor, scene).map(({ joint, actuator }) => [
        joint.id,
        actuatorStates.get(actuator.id) ?? joint.initial_position,
    ]));
}
function createTrajectoryDraftState(actorId, homeTargets, clip) {
    const draft = clip
        ? trajectoryDraftFromTrajectory(actorId, clip.trajectory)
        : createTrajectoryDraft(actorId, homeTargets);
    return {
        draft,
        homeSignature: JSON.stringify(homeTargets),
        sourceSignature: clip
            ? JSON.stringify([clip.id, clip.trajectory])
            : `new:${JSON.stringify(homeTargets)}`,
        clipId: clip?.id ?? null,
        targetsTouched: Boolean(clip),
        nextKeyframeId: draft.keyframes.length,
    };
}
function setTrajectoryDraftClip(actor, scene, clipId) {
    const homeTargets = Object.fromEntries(positionJointBindings(actor, scene).map(({ joint }) => [
        joint.id,
        joint.initial_position,
    ]));
    const clip = scene.trajectories?.find((item) => item.actor_id === actor.id && item.id === clipId);
    trajectoryDrafts.set(actor.id, createTrajectoryDraftState(actor.id, homeTargets, clip));
}
function ensureTrajectoryDraft(actor, scene) {
    const homeTargets = Object.fromEntries(positionJointBindings(actor, scene).map(({ joint }) => [
        joint.id,
        joint.initial_position,
    ]));
    if (Object.keys(homeTargets).length === 0)
        return null;
    const homeSignature = JSON.stringify(homeTargets);
    const existing = trajectoryDrafts.get(actor.id);
    const clips = scene.trajectories?.filter((item) => item.actor_id === actor.id) ?? [];
    if (existing?.homeSignature === homeSignature) {
        if (existing.clipId) {
            const clip = clips.find((item) => item.id === existing.clipId);
            const sourceSignature = clip
                ? JSON.stringify([clip.id, clip.trajectory])
                : `missing:${existing.clipId}:${homeSignature}`;
            if (sourceSignature !== existing.sourceSignature) {
                const restored = createTrajectoryDraftState(actor.id, homeTargets, clip);
                restored.clipId = existing.clipId;
                restored.sourceSignature = sourceSignature;
                trajectoryDrafts.set(actor.id, restored);
                return restored;
            }
        }
        return existing;
    }
    const created = createTrajectoryDraftState(actor.id, homeTargets, clips[0]);
    trajectoryDrafts.set(actor.id, created);
    return created;
}
async function handleTrajectoryCommand(command, actor, scene) {
    let result;
    if (command === 'load') {
        const draftState = ensureTrajectoryDraft(actor, scene);
        if (!draftState) {
            showToast('Robot has no position joints', true);
            return;
        }
        if (!draftState.targetsTouched) {
            const finalKeyframe = draftState.draft.keyframes.at(-1);
            if (finalKeyframe) {
                for (const [jointId, target] of Object.entries(currentRobotTargets(actor, scene))) {
                    draftState.draft = updateTrajectoryKeyframeTarget(draftState.draft, finalKeyframe.id, jointId, target);
                }
            }
        }
        let trajectory;
        try {
            trajectory = trajectoryFromDraft(draftState.draft);
        }
        catch (error) {
            showToast(error instanceof Error ? error.message : String(error), true);
            return;
        }
        result = await bridge.call('loadTrajectory', JSON.stringify(scene), JSON.stringify(trajectory));
        simulationStore.setValidationIssues(result.data?.issues ?? []);
    }
    else if (command === 'play')
        result = await bridge.call('playTrajectory');
    else if (command === 'pause')
        result = await bridge.call('pauseTrajectory');
    else if (command === 'stop')
        result = await bridge.call('stopTrajectory');
    else
        return;
    if (!result.ok || !result.data) {
        showToast(result.error ?? `Trajectory ${command} failed`, true);
        return;
    }
    const status = command === 'play' ? 'running' : 'paused';
    simulationStore.setSimulation(status, result.data.state);
}
function updateTrajectoryRuntime(simulationState) {
    const trajectory = simulationState?.trajectory;
    const status = trajectory?.status ?? 'stopped';
    const time = trajectory?.time ?? 0;
    const duration = trajectory?.duration ?? 0;
    element('trajectory-status').textContent = status.replace('_', ' ');
    const progress = document.querySelector('[data-trajectory-progress]');
    if (progress) {
        progress.max = Math.max(duration, 0.001);
        progress.value = Math.min(time, progress.max);
    }
    const timeLabel = document.querySelector('[data-trajectory-time]');
    if (timeLabel)
        timeLabel.textContent = `${time.toFixed(2)} / ${duration.toFixed(2)} s`;
    const loaded = trajectory?.name !== null && trajectory?.name !== undefined;
    const play = document.querySelector('[data-trajectory-command="play"]');
    const pause = document.querySelector('[data-trajectory-command="pause"]');
    const stop = document.querySelector('[data-trajectory-command="stop"]');
    if (play)
        play.disabled = !loaded || status === 'playing';
    if (pause)
        pause.disabled = status !== 'playing';
    if (stop)
        stop.disabled = !loaded;
}
function ensureRecordingDraft(actor, scene) {
    const bindings = positionJointBindings(actor, scene);
    const sensors = robotSensors(actor, scene).filter((sensor) => ['joint_state', 'imu', 'contact', 'rangefinder'].includes(sensor.sensor_type));
    const signature = JSON.stringify([
        bindings.map(({ joint }) => joint.id),
        sensors.map((sensor) => sensor.id),
    ]);
    const existing = recordingDrafts.get(actor.id);
    if (existing?.signature === signature)
        return existing;
    const created = {
        signature,
        name: 'Joint Recording',
        selectedJointIds: new Set(bindings.map(({ joint }) => joint.id)),
        selectedSensorIds: new Set(),
    };
    recordingDrafts.set(actor.id, created);
    return created;
}
function sensorsForRecording(actor, scene, draft) {
    return robotSensors(actor, scene)
        .filter((sensor) => ['joint_state', 'imu', 'contact', 'rangefinder'].includes(sensor.sensor_type))
        .filter((sensor) => draft.selectedSensorIds.has(sensor.id))
        .map((sensor) => sensor.id);
}
function renderRecordingPanel(actor, scene) {
    const controls = element('recording-controls');
    if (!actor || actor.type !== 'robot') {
        controls.innerHTML = '<div class="empty-state">Select a robot actor</div>';
        return;
    }
    const draft = ensureRecordingDraft(actor, scene);
    const bindings = positionJointBindings(actor, scene);
    const sensors = robotSensors(actor, scene).filter((sensor) => ['joint_state', 'imu', 'contact', 'rangefinder'].includes(sensor.sensor_type));
    controls.innerHTML = `
    <input class="recording-name" type="text" value="${escapeHtml(draft.name)}" data-recording-name title="Recording name">
    <div class="recording-source-title">Joints</div>
    <div class="recording-sources">
      ${bindings.map(({ joint }) => `
        <label title="${escapeHtml(joint.id)}">
          <input type="checkbox" data-recording-joint="${escapeHtml(joint.id)}" ${draft.selectedJointIds.has(joint.id) ? 'checked' : ''}>
          <span>${escapeHtml(joint.name)}</span>
        </label>`).join('')}
    </div>
    ${sensors.length ? `
      <div class="recording-source-title">Sensors</div>
      <div class="recording-sources">
        ${sensors.map((sensor) => `
          <label title="${escapeHtml(sensor.id)}">
            <input type="checkbox" data-recording-sensor="${escapeHtml(sensor.id)}" ${draft.selectedSensorIds.has(sensor.id) ? 'checked' : ''}>
            <span>${escapeHtml(sensor.name)}</span>
          </label>`).join('')}
      </div>` : ''}
    <div class="recording-actions">
      <button type="button" data-recording-command="start">Start</button>
      <button type="button" data-recording-command="stop">Stop</button>
      <button type="button" data-recording-export="json">Export JSON</button>
      <button type="button" data-recording-export="csv">Export CSV</button>
    </div>`;
    controls.querySelector('[data-recording-name]')?.addEventListener('change', (event) => { draft.name = event.currentTarget.value; });
    for (const checkbox of controls.querySelectorAll('[data-recording-joint]')) {
        checkbox.addEventListener('change', () => {
            const jointId = checkbox.dataset.recordingJoint ?? '';
            if (checkbox.checked)
                draft.selectedJointIds.add(jointId);
            else
                draft.selectedJointIds.delete(jointId);
        });
    }
    for (const checkbox of controls.querySelectorAll('[data-recording-sensor]')) {
        checkbox.addEventListener('change', () => {
            const sensorId = checkbox.dataset.recordingSensor ?? '';
            if (checkbox.checked)
                draft.selectedSensorIds.add(sensorId);
            else
                draft.selectedSensorIds.delete(sensorId);
        });
    }
    for (const button of controls.querySelectorAll('[data-recording-command]')) {
        button.addEventListener('click', () => {
            void handleRecordingCommand(button.dataset.recordingCommand ?? '', actor, scene, draft);
        });
    }
    for (const button of controls.querySelectorAll('[data-recording-export]')) {
        button.addEventListener('click', () => {
            void exportRecording(button.dataset.recordingExport ?? 'json');
        });
    }
    updateRecordingRuntime(simulationStore.current.simulationState);
}
async function handleRecordingCommand(command, actor, scene, draft) {
    let result;
    if (command === 'start') {
        const bindings = positionJointBindings(actor, scene).filter(({ joint }) => draft.selectedJointIds.has(joint.id));
        const sensorIds = sensorsForRecording(actor, scene, draft);
        if (bindings.length === 0 && sensorIds.length === 0) {
            showToast('Select at least one joint or sensor to record', true);
            return;
        }
        result = await bridge.call('startRecording', JSON.stringify(scene), JSON.stringify({
            name: draft.name,
            joint_ids: bindings.map(({ joint }) => joint.id),
            actuator_ids: bindings.map(({ actuator }) => actuator.id),
            sensor_ids: sensorIds,
        }));
    }
    else if (command === 'stop') {
        result = await bridge.call('stopRecording');
    }
    else
        return;
    if (!result.ok || !result.data) {
        showToast(result.error ?? `Recording ${command} failed`, true);
        return;
    }
    const status = simulationStore.current.simulationStatus === 'running' ? 'running' : 'paused';
    simulationStore.setSimulation(status, result.data.state);
}
async function exportRecording(formatName) {
    const result = await bridge.call('exportRecordingDialog', formatName);
    if (!result.ok || !result.data) {
        if (result.error !== 'Cancelled')
            showToast(result.error ?? 'Recording export failed', true);
        return;
    }
    store.appendLog(`Exported recording: ${result.data.path}`);
    showToast(`Exported ${result.data.sample_count} samples`);
}
function updateRecordingRuntime(simulationState) {
    const recording = simulationState?.recording;
    const active = recording?.active ?? false;
    const sampleCount = recording?.sample_count ?? 0;
    const sensorEventCount = recording?.sensor_event_count ?? 0;
    const limitReached = recording?.limit_reached ?? false;
    const status = element('recording-status');
    status.textContent = limitReached
        ? `${sampleCount} · Limit`
        : active
            ? `${sampleCount} Rows · ${sensorEventCount} Events`
            : sampleCount ? `${sampleCount} Rows · ${sensorEventCount} Events` : 'Idle';
    status.classList.toggle('limit', limitReached);
    const start = document.querySelector('[data-recording-command="start"]');
    const stop = document.querySelector('[data-recording-command="stop"]');
    if (start)
        start.disabled = active;
    if (stop)
        stop.disabled = !active;
    for (const button of document.querySelectorAll('[data-recording-export]')) {
        button.disabled = active || sampleCount === 0;
    }
}
let loadedController = null;
function renderControllerPanel(actor, simulationState) {
    const controls = element('controller-controls');
    if (!actor || actor.type !== 'robot') {
        controls.innerHTML = '<div class="empty-state">Select a robot actor</div>';
        return;
    }
    const runtime = simulationState?.controller;
    const attached = runtime?.mode === 'python';
    const metadata = loadedController?.actorId === actor.id ? loadedController : null;
    const name = runtime?.name ?? metadata?.name ?? 'No controller loaded';
    const path = metadata?.path ?? '';
    const controllerStatus = `<div class="controller-status" data-controller-status="${runtime?.status ?? 'ready'}">
    <span data-controller-status-label>${(runtime?.status ?? 'ready').replace('_', ' ')}</span>
    <small data-controller-message>${runtime?.message ? escapeHtml(runtime.message) : ''}</small>
  </div>`;
    controls.innerHTML = `
    ${controllerStatus}
    <div class="controller-identity">
      <div class="controller-name" data-controller-name>${escapeHtml(name)}</div>
      <div class="controller-path" data-controller-path title="${escapeHtml(path)}">${escapeHtml(path || '—')}</div>
    </div>
    <div class="controller-metrics">
      <span data-controller-steps>0 Steps</span>
      <span data-controller-duration>—</span>
    </div>
    <div class="controller-actions">
      <button type="button" data-controller-command="load">Load Python</button>
      <button type="button" class="icon-button" data-controller-command="reload" title="Reload controller" ${path ? '' : 'disabled'}>↻</button>
      <button type="button" class="icon-button" data-controller-command="detach" title="Detach controller" ${attached ? '' : 'disabled'}>×</button>
    </div>`;
    for (const button of controls.querySelectorAll('[data-controller-command]')) {
        button.addEventListener('click', () => {
            void handleControllerCommand(button.dataset.controllerCommand ?? '', actor);
        });
    }
    updateControllerRuntime(simulationState);
}
async function handleControllerCommand(command, actor) {
    if (command === 'detach') {
        const result = await bridge.call('detachController');
        if (!result.ok || !result.data) {
            showToast(result.error ?? 'Controller detach failed', true);
            return;
        }
        loadedController = null;
        simulationStore.setSimulation('paused', result.data.state);
        renderControllerPanel(actor, result.data.state);
        store.appendLog('Detached Python controller.');
        return;
    }
    if (command !== 'load' && command !== 'reload')
        return;
    if (!window.confirm('Run trusted Python controller code from this project?'))
        return;
    await loadProjectController(command === 'reload', actor);
}
async function loadProjectController(reload, actor) {
    const result = await bridge.call(reload ? 'reloadController' : 'loadController', JSON.stringify(store.current.scene));
    if (!result.ok || !result.data) {
        if (result.error !== 'Cancelled')
            showToast(result.error ?? 'Controller load failed', true);
        return result;
    }
    loadedController = {
        actorId: actor.id,
        path: result.data.controller.path,
        name: result.data.controller.name,
    };
    simulationStore.setSimulation('paused', result.data.state);
    renderControllerPanel(actor, result.data.state);
    store.appendLog(`Loaded Python controller: ${result.data.controller.name}`);
    return result;
}
function updateControllerRuntime(simulationState) {
    const controller = simulationState?.controller;
    const attached = controller?.mode === 'python';
    const status = element('controller-panel-status');
    status.textContent = attached ? controller.status : 'Detached';
    status.classList.toggle('fault', controller?.status === 'fault');
    const name = document.querySelector('[data-controller-name]');
    if (name && attached && controller.name)
        name.textContent = controller.name;
    const steps = document.querySelector('[data-controller-steps]');
    if (steps)
        steps.textContent = `${controller?.step_count ?? 0} Steps`;
    const duration = document.querySelector('[data-controller-duration]');
    if (duration) {
        duration.textContent = controller?.last_duration === null || controller?.last_duration === undefined
            ? '—'
            : `${(controller.last_duration * 1000).toFixed(2)} ms`;
    }
    const detach = document.querySelector('[data-controller-command="detach"]');
    if (detach)
        detach.disabled = !attached;
    for (const control of document.querySelectorAll('[data-joint-jog], [data-joint-target], [data-joint-home]'))
        control.disabled = attached;
    const play = document.querySelector('[data-trajectory-command="play"]');
    if (play && attached)
        play.disabled = true;
}
let targetRealtimeFactor = 1;
function updateSimulationClock(simulationState) {
    if (simulationState)
        targetRealtimeFactor = simulationState.clock.target_rtf;
    for (const button of document.querySelectorAll('[data-simulation-speed]')) {
        const factor = Number(button.dataset.simulationSpeed);
        const active = factor === targetRealtimeFactor;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', String(active));
    }
    for (const button of document.querySelectorAll('[data-panel-speed]')) {
        const factor = Number(button.dataset.panelSpeed);
        button.classList.toggle('active', factor === targetRealtimeFactor);
    }
    const actual = simulationState?.clock.actual_rtf ?? 0;
    element('rtf-readout').textContent = `${actual.toFixed(2)}x`;
    const panelReadout = document.getElementById('panel-rtf-readout');
    if (panelReadout)
        panelReadout.textContent = `${actual.toFixed(2)}x`;
    const panelSimRtf = document.getElementById('panel-sim-rtf');
    if (panelSimRtf)
        panelSimRtf.textContent = `${actual.toFixed(2)}x`;
    const panelSimTime = document.getElementById('panel-sim-time');
    if (panelSimTime)
        panelSimTime.textContent = `${(simulationState?.time ?? 0).toFixed(2)}s`;
    const targetReadout = document.getElementById('panel-target-speed');
    if (targetReadout)
        targetReadout.textContent = `${targetRealtimeFactor}x`;
    const running = simulationStore.current.simulationStatus === 'running';
    const ratio = running && targetRealtimeFactor > 0
        ? Math.max(0, Math.min(1, actual / targetRealtimeFactor))
        : 0;
    const meter = document.querySelector('.throughput-meter');
    const meterFill = document.getElementById('throughput-meter-fill');
    const lagging = running && ratio < 0.9;
    if (meter) {
        meter.setAttribute('aria-valuenow', String(Math.round(ratio * 100)));
        meter.classList.toggle('lagging', lagging);
    }
    if (meterFill)
        meterFill.style.width = `${ratio * 100}%`;
    const throughputHint = document.getElementById('throughput-hint');
    if (throughputHint) {
        throughputHint.textContent = !running
            ? 'RTF is measured while the simulation runs.'
            : lagging
                ? `Solver throughput is ${actual.toFixed(2)}x of the requested ${targetRealtimeFactor}x.`
                : 'The solver is keeping up with the requested time scale.';
    }
}
async function setSimulationSpeed(factor) {
    const previous = targetRealtimeFactor;
    targetRealtimeFactor = factor;
    updateSimulationClock(null);
    const result = await bridge.call('setSimulationSpeed', factor);
    if (result.ok && result.data) {
        targetRealtimeFactor = result.data.target_rtf;
        if (result.data.state)
            simulationStore.setSimulationState(result.data.state);
        else
            updateSimulationClock(null);
        return result;
    }
    targetRealtimeFactor = previous;
    updateSimulationClock(simulationStore.current.simulationState);
    showToast(result.error ?? 'Simulation speed update failed', true);
    return result;
}
function render() {
    const state = store.current;
    const simulation = simulationStore.current;
    element('project-label').textContent = `${state.dirty ? '* ' : ''}${state.scene.name}`;
    document.title = `${state.dirty ? '* ' : ''}${state.scene.name}`;
    const projectPanelName = document.getElementById('project-panel-name');
    if (projectPanelName)
        projectPanelName.textContent = state.scene.name;
    const projectPanelState = document.getElementById('project-panel-state');
    if (projectPanelState) {
        projectPanelState.textContent = state.dirty ? 'unsaved' : 'saved';
        projectPanelState.classList.toggle('unsaved', state.dirty);
    }
    const actorCount = state.scene.actors.length;
    const articulationCount = state.scene.robotics?.articulations.length ?? 0;
    const projectSummary = document.getElementById('project-panel-summary');
    if (projectSummary) {
        projectSummary.textContent = `${actorCount} actor${actorCount === 1 ? '' : 's'} in scene`;
    }
    const projectActorCount = document.getElementById('project-actor-count');
    if (projectActorCount)
        projectActorCount.textContent = String(actorCount);
    const projectRobotCount = document.getElementById('project-robot-count');
    if (projectRobotCount)
        projectRobotCount.textContent = String(articulationCount);
    const badge = element('simulation-badge');
    badge.textContent = simulation.simulationStatus[0].toUpperCase()
        + simulation.simulationStatus.slice(1);
    badge.dataset.status = simulation.simulationStatus;
    const runToggle = element('run-toggle-button');
    const runToggleLabel = element('run-toggle-label');
    const running = simulation.simulationStatus === 'running';
    runToggle.dataset.command = running ? 'pause' : 'run';
    runToggle.title = running ? 'Pause simulation' : 'Run simulation';
    runToggle.classList.toggle('primary', !running);
    runToggle.classList.toggle('active', running);
    runToggleLabel.textContent = running
        ? 'Pause'
        : simulation.simulationStatus === 'paused' ? 'Resume' : 'Run';
    const playIcon = runToggle.querySelector('.run-icon-play');
    const pauseIcon = runToggle.querySelector('.run-icon-pause');
    if (playIcon)
        playIcon.toggleAttribute('hidden', running);
    if (pauseIcon)
        pauseIcon.toggleAttribute('hidden', !running);
    element('sim-stop-button').disabled = simulation.simulationStatus === 'stopped';
    const panelRunToggle = element('panel-run-toggle');
    panelRunToggle.dataset.menuCommand = running ? 'pause' : 'run';
    const panelRunLabel = running
        ? 'Pause'
        : simulation.simulationStatus === 'paused' ? 'Resume' : 'Run';
    panelRunToggle.textContent = panelRunLabel;
    panelRunToggle.setAttribute('aria-label', `${panelRunLabel} simulation from panel`);
    panelRunToggle.classList.toggle('primary', !running);
    const panelStop = document.querySelector('[data-panel="sim-control"] [data-menu-command="stop"]');
    if (panelStop)
        panelStop.disabled = simulation.simulationStatus === 'stopped';
    const panelSimBadge = document.getElementById('panel-sim-badge');
    if (panelSimBadge) {
        panelSimBadge.textContent = simulation.simulationStatus;
        panelSimBadge.dataset.status = simulation.simulationStatus;
    }
    const panelSimDetail = document.getElementById('panel-sim-detail');
    if (panelSimDetail) {
        panelSimDetail.textContent = {
            stopped: 'Physics idle at the initial state',
            running: 'Stepping the MuJoCo model in real time',
            paused: 'State held — Step advances one frame',
            fault: 'Blocked by a preflight error',
        }[simulation.simulationStatus];
    }
    updateSimulationClock(simulation.simulationState);
    element('undo-button').disabled = !state.canUndo;
    element('redo-button').disabled = !state.canRedo;
    renderAssets(state.assets);
    renderSceneTree(state.scene, state.selectedActorId, state.selectedJointId, state.selectedSensorId);
    const selectedActor = state.scene.actors.find((actor) => actor.id === state.selectedActorId);
    renderProperties(selectedActor, state.scene, state.selectedJointId, state.selectedSensorId);
    renderArmControl(selectedActor, state.scene, state.selectedJointId);
    renderDroneControl(selectedActor, state.scene);
    renderSensorView(selectedActor, state.scene, state.selectedSensorId);
    renderTrajectoryWindows(selectedActor, state.scene);
    renderRecordingPanel(selectedActor, state.scene);
    renderControllerPanel(selectedActor, simulation.simulationState);
    renderValidation(simulation.validationIssues);
    renderConsole(state.logs);
    // Open feature windows automatically when their content becomes relevant, while
    // respecting windows the user closed explicitly during this session.
    const hasPositionJoints = selectedActor?.type === 'robot'
        && positionJointBindings(selectedActor, state.scene).length > 0;
    workspace.autoOpen('arm-control', hasPositionJoints);
    workspace.autoOpen('drone-control', selectedActor?.properties.propulsion?.type === 'quadrotor');
    workspace.autoOpen('trajectory-editor', hasPositionJoints, { focus: true });
    // Selecting a robot with position joints should reveal the Trajectory tab once,
    // on the relevance transition only.
    if (hasPositionJoints && hasPositionJoints !== previousRobotJointContext) {
        workspace.activateBottomTab('trajectory-editor');
    }
    previousRobotJointContext = hasPositionJoints;
    workspace.autoOpen('recording', selectedActor?.type === 'robot');
    workspace.autoOpen('controller', selectedActor?.type === 'robot');
    workspace.autoOpen('sensors', state.selectedSensorId !== null, { focus: true });
    // Selecting a sensor in the scene tree should also reveal the Sensors tab once,
    // on the selection transition only.
    const sensorSelected = state.selectedSensorId !== null;
    if (sensorSelected && sensorSelected !== previousSensorSelected) {
        workspace.activateBottomTab('sensors');
    }
    previousSensorSelected = sensorSelected;
    updateStatusBar();
}
let previousSensorSelected = false;
let previousRobotJointContext = false;
function updateStatusBar() {
    const state = store.current;
    const simulation = simulationStore.current;
    const simState = simulation.simulationState;
    const setStatus = (id, text) => {
        const el = document.getElementById(id);
        if (el)
            el.textContent = text;
    };
    const dot = document.getElementById('status-sim-dot');
    if (dot) {
        dot.className = `status-dot ${simulation.simulationStatus === 'running' ? 'ok'
            : simulation.simulationStatus === 'paused' ? 'warn'
                : simulation.simulationStatus === 'fault' ? 'bad' : ''}`;
    }
    setStatus('status-sim-state', simulation.simulationStatus);
    setStatus('status-time', `t ${(simState?.time ?? 0).toFixed(2)}s`);
    setStatus('status-rtf', `rtf ${(simState?.clock.actual_rtf ?? 0).toFixed(2)}x`);
    const controllerEl = document.getElementById('status-controller');
    if (controllerEl) {
        const attached = simState?.controller.mode === 'python';
        controllerEl.hidden = !attached;
        if (attached) {
            controllerEl.textContent = `controller ${(simState?.controller.step_count ?? 0).toLocaleString()} steps`;
        }
    }
    const recEl = document.getElementById('status-rec');
    if (recEl) {
        const recording = simState?.recording;
        recEl.hidden = !recording?.active;
        if (recording?.active)
            recEl.textContent = `● rec ${(recording.sample_count ?? 0).toLocaleString()} rows`;
    }
    const errorsEl = document.getElementById('status-errors');
    if (errorsEl) {
        const errors = simulation.validationIssues.filter((issue) => issue.severity === 'error').length;
        errorsEl.hidden = errors === 0;
        if (errors > 0)
            errorsEl.textContent = `${errors} preflight error(s)`;
    }
    setStatus('status-actors', `${state.scene.actors.length} actors`);
    setStatus('status-windows', `${document.querySelectorAll('.dock-tab').length} windows`);
}
async function saveProject(saveAs = false) {
    const result = await bridge.call('saveProject', JSON.stringify(store.current.scene), saveAs);
    if (!result.ok || !result.data) {
        if (result.error !== 'Cancelled')
            showToast(result.error ?? 'Save failed', true);
        return false;
    }
    store.markSaved(result.data.path);
    store.appendLog(`Saved scene: ${result.data.path}`);
    return true;
}
function allowDiscard() {
    return !store.current.dirty || window.confirm('Discard unsaved scene changes?');
}
async function handleCommand(command) {
    if (command === 'new' && allowDiscard()) {
        trajectoryDrafts.clear();
        recordingDrafts.clear();
        loadedController = null;
        await bridge.call('discardSimulation');
        store.newScene();
        simulationStore.reset();
    }
    else if (command === 'open' && allowDiscard()) {
        const result = await bridge.call('openProject');
        if (result.ok && result.data) {
            trajectoryDrafts.clear();
            recordingDrafts.clear();
            loadedController = null;
            await bridge.call('discardSimulation');
            store.loadScene(result.data.scene, result.data.path);
            simulationStore.reset();
            store.appendLog(`Opened scene: ${result.data.path}`);
        }
        else if (result.error !== 'Cancelled')
            showToast(result.error ?? 'Open failed', true);
    }
    else if (command === 'save')
        await saveProject(false);
    else if (command === 'save-as')
        await saveProject(true);
    else if (command === 'import-openusd')
        await importOpenUsd('file');
    else if (command === 'import-openusd-folder')
        await importOpenUsd('folder');
    else if (command === 'undo')
        store.undo();
    else if (command === 'redo')
        store.redo();
    else if (command === 'clear-console')
        store.clearLogs();
    else if (command === 'export') {
        const result = await bridge.call('exportMjcf', JSON.stringify(store.current.scene));
        simulationStore.setValidationIssues(result.data?.issues ?? []);
        if (result.ok && result.data) {
            store.appendLog(`Exported MJCF: ${result.data.path}`);
            showToast('MJCF exported');
        }
        else
            showToast(result.error ?? 'Export failed', true);
    }
    else if (command === 'run') {
        const result = await bridge.call('runSimulation', JSON.stringify(store.current.scene));
        simulationStore.setValidationIssues(result.data?.issues ?? []);
        if (result.ok && result.data) {
            simulationStore.setSimulation('running', result.data.state);
        }
        else
            showToast(result.error ?? 'Simulation failed', true);
    }
    else if (command === 'pause') {
        const result = await bridge.call('pauseSimulation');
        if (result.ok) {
            simulationStore.setSimulation('paused', simulationStore.current.simulationState);
        }
    }
    else if (command === 'stop') {
        const result = await bridge.call('discardSimulation');
        if (result.ok) {
            loadedController = null;
            simulationStore.reset();
        }
        else
            showToast(result.error ?? 'Simulation stop failed', true);
    }
    else if (command === 'step') {
        const result = await bridge.call('stepSimulation', JSON.stringify(store.current.scene));
        simulationStore.setValidationIssues(result.data?.issues ?? []);
        if (result.ok && result.data)
            simulationStore.setSimulation('paused', result.data.state);
        else
            showToast(result.error ?? 'Simulation step failed', true);
    }
    else if (command === 'reset') {
        const result = await bridge.call('resetSimulation');
        if (result.ok && result.data?.state) {
            simulationStore.setSimulation('paused', result.data.state);
        }
        else if (result.ok) {
            simulationStore.setSimulation('stopped', null);
        }
        else {
            showToast(result.error ?? 'Simulation reset failed', true);
        }
    }
}
async function importOpenUsd(mode) {
    const method = mode === 'folder' ? 'importOpenUsdFolder' : 'importOpenUsd';
    showToast(mode === 'folder' ? 'Uploading OpenUSD folder…' : 'Uploading OpenUSD asset…');
    const result = await bridge.call(method);
    if (result.ok && result.data) {
        store.upsertAsset(result.data.asset);
        store.addAsset(result.data.asset, result.data.robotics);
        for (const warning of result.data.warnings)
            store.appendLog(`USD: ${warning}`);
        showToast(`Imported ${result.data.asset.name}`);
    }
    else if (result.error !== 'Cancelled') {
        const report = result.data;
        for (const issue of report?.issues ?? []) {
            const field = issue.field ? ` (${issue.field})` : '';
            store.appendLog(`USD ${issue.severity ?? 'error'}: ${issue.message ?? result.error}${field}`);
        }
        showToast(result.error ?? 'OpenUSD import failed', true);
    }
    return result;
}
for (const button of document.querySelectorAll('[data-command]')) {
    button.addEventListener('click', () => void handleCommand(button.dataset.command ?? ''));
}
for (const button of document.querySelectorAll('[data-simulation-speed]')) {
    button.addEventListener('click', () => {
        void setSimulationSpeed(Number(button.dataset.simulationSpeed));
    });
}
element('asset-filter-input').addEventListener('input', (event) => {
    assetFilter = event.currentTarget.value;
    renderAssets(store.current.assets);
});
for (const button of document.querySelectorAll('[data-material-preset]')) {
    button.addEventListener('click', () => {
        const actorId = store.current.selectedActorId;
        const actor = store.current.scene.actors.find((item) => item.id === actorId);
        if (!actor) {
            showToast('Select an actor before applying a material preset', true);
            return;
        }
        const preset = button.dataset.materialPreset ?? 'default';
        const physics = structuredClone(actor.properties.physics ?? { dynamic: true });
        physics.material = preset;
        Object.assign(physics, structuredClone(materialPresets[preset]));
        store.updateActorProperties(actor.id, { physics, mass: physics.mass });
        showToast(`Material preset applied: ${preset[0].toUpperCase()}${preset.slice(1)}`);
    });
}
const windowMenuItems = element('window-menu-items');
function renderWindowMenu() {
    windowMenuItems.innerHTML = '';
    const lists = new Map();
    for (const category of ['Scene', 'Viewport', 'Authoring', 'Simulation', 'Robot', 'Data', 'Agent', 'Diagnostics']) {
        const heading = document.createElement('div');
        heading.className = 'menu-category';
        heading.textContent = category;
        const list = document.createElement('div');
        windowMenuItems.append(heading, list);
        lists.set(category, list);
    }
    for (const root of document.querySelectorAll('[data-panel]')) {
        const id = (root.dataset.panel ?? '');
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'menu-item window-menu-entry';
        item.innerHTML = `<span class="window-menu-check" aria-hidden="true">${workspace.isOpen(id) ? '✓' : ''}</span><span>${escapeHtml(root.dataset.panelTitle ?? id)}</span>`;
        item.addEventListener('click', () => {
            workspace.togglePanel(id);
            renderWindowMenu();
        });
        (lists.get(root.dataset.panelGroup ?? 'Diagnostics') ?? lists.get('Diagnostics')).appendChild(item);
    }
}
renderWindowMenu();
workspace.onChange(() => {
    renderWindowMenu();
    updateStatusBar();
});
function closeAllMenus() {
    for (const dropdown of document.querySelectorAll('.menu-dropdown')) {
        dropdown.hidden = true;
    }
    for (const trigger of document.querySelectorAll('.menu-trigger')) {
        trigger.setAttribute('aria-expanded', 'false');
    }
}
for (const menu of document.querySelectorAll('.menu')) {
    const trigger = menu.querySelector('.menu-trigger');
    const dropdown = menu.querySelector('.menu-dropdown');
    trigger?.addEventListener('click', (event) => {
        event.stopPropagation();
        const opening = dropdown?.hidden ?? false;
        closeAllMenus();
        if (dropdown && opening) {
            if (dropdown.contains(windowMenuItems))
                renderWindowMenu();
            dropdown.hidden = false;
            trigger.setAttribute('aria-expanded', 'true');
        }
    });
}
document.addEventListener('click', (event) => {
    if (!event.target.closest('.menu'))
        closeAllMenus();
});
document.addEventListener('click', (event) => {
    const target = event.target;
    const commandItem = target.closest('[data-menu-command]');
    if (commandItem) {
        closeAllMenus();
        void handleCommand(commandItem.dataset.menuCommand ?? '');
        return;
    }
    const actionItem = target.closest('[data-menu-action]');
    if (!actionItem)
        return;
    closeAllMenus();
    const action = actionItem.dataset.menuAction ?? '';
    if (action === 'reset-layout') {
        workspace.resetLayout();
        renderWindowMenu();
        showToast('Workspace layout reset');
    }
    else if (action.startsWith('preset-')) {
        const presetId = action.replace('preset-', '');
        if (workspace.applyPreset(presetId)) {
            element('layout-preset').value = presetId;
            renderWindowMenu();
            showToast(`Layout preset applied: ${presetId}`);
        }
    }
    else if (action === 'open-shortcuts')
        workspace.openPanel('shortcuts');
    else if (action === 'open-library')
        workspace.openLibrary();
});
for (const button of document.querySelectorAll('[data-panel-speed]')) {
    button.addEventListener('click', () => {
        void setSimulationSpeed(Number(button.dataset.panelSpeed));
    });
}
for (const button of document.querySelectorAll('[data-viewport-option]')) {
    button.addEventListener('click', () => {
        const option = button.dataset.viewportOption;
        const enabled = button.getAttribute('aria-pressed') !== 'true';
        button.setAttribute('aria-pressed', String(enabled));
        button.classList.toggle('active', enabled);
        setViewportFeature(option, enabled);
    });
}
element('add-window-button').addEventListener('click', () => workspace.openLibrary());
element('layout-preset').addEventListener('change', (event) => {
    const select = event.currentTarget;
    if (workspace.applyPreset(select.value)) {
        renderWindowMenu();
        showToast('Layout preset applied');
    }
});
configureViewport({
    onActorSelected: (actorId) => store.selectActor(actorId),
    onActorTransformChanged: (actorId, transform) => store.updateActorTransform(actorId, transform),
    resolveVisualGeometry: async (cachePath) => {
        const result = await bridge.call('getVisualGeometry', cachePath);
        if (result.ok && result.data)
            return result.data;
        store.appendLog(`Mesh cache load failed: ${result.error ?? cachePath}`);
        return null;
    },
    resolveVisualGeometryBundle: async (artifactId) => {
        const result = await bridge.call('getVisualGeometryBundle', artifactId);
        if (result.ok && result.data)
            return result.data;
        store.appendLog(`Mesh bundle load failed: ${result.error ?? artifactId}`);
        return null;
    },
});
function syncViewportSelection(state) {
    selectViewportActor(state.selectedActorId);
    const articulations = state.scene.robotics?.articulations ?? [];
    const selectedSensor = articulations.flatMap((item) => item.sensors)
        .find((item) => item.id === state.selectedSensorId);
    const relatedJointId = state.selectedJointId ?? selectedSensor?.joint_id ?? null;
    const jointLinkId = articulations.flatMap((item) => item.joints)
        .find((item) => item.id === relatedJointId)?.child_link_id;
    const colliderLinkId = selectedSensor?.collider_id
        ? articulations.flatMap((item) => item.links)
            .find((link) => link.colliders.some((collider) => collider.id === selectedSensor.collider_id))?.id
        : undefined;
    selectViewportLink(jointLinkId ?? selectedSensor?.link_id ?? colliderLinkId ?? null);
}
function viewportStructureSnapshot(scene) {
    return JSON.stringify({
        ...scene,
        actors: scene.actors.map((actor) => ({ ...actor, transform: null })),
    });
}
store.subscribe((state) => {
    const sceneJson = JSON.stringify(state.scene);
    const nextViewportStructure = viewportStructureSnapshot(state.scene);
    const nextRenderSnapshot = JSON.stringify({
        sceneJson,
        assets: state.assets,
        selectedActorId: state.selectedActorId,
        selectedJointId: state.selectedJointId,
        selectedSensorId: state.selectedSensorId,
        dirty: state.dirty,
        canUndo: state.canUndo,
        canRedo: state.canRedo,
        currentPath: state.currentPath,
        logs: state.logs,
    });
    if (nextRenderSnapshot !== renderSnapshot) {
        render();
        renderSnapshot = nextRenderSnapshot;
    }
    if (sceneJson !== previousSceneJson) {
        const updatedInPlace = previousViewportStructure === nextViewportStructure
            && updateViewportTransforms(state.scene);
        if (!updatedInPlace)
            setViewportScene(state.scene);
        // Keep the viewport selection synchronized after either an in-place transform update or a
        // full scene rebuild, even when the selected ids themselves did not change.
        syncViewportSelection(state);
        previousSceneJson = sceneJson;
        previousViewportStructure = nextViewportStructure;
        previousSelectedActorId = state.selectedActorId;
        previousSelectedJointId = state.selectedJointId;
        previousSelectedSensorId = state.selectedSensorId;
    }
    else if (state.selectedActorId !== previousSelectedActorId) {
        selectViewportActor(state.selectedActorId);
        previousSelectedActorId = state.selectedActorId;
    }
    if (state.selectedJointId !== previousSelectedJointId
        || state.selectedSensorId !== previousSelectedSensorId) {
        syncViewportSelection(state);
        previousSelectedActorId = state.selectedActorId;
        previousSelectedJointId = state.selectedJointId;
        previousSelectedSensorId = state.selectedSensorId;
    }
    const nextSync = `${sceneJson}:${state.dirty}`;
    if (nextSync !== syncSnapshot) {
        bridge.syncEditorState(sceneJson, state.dirty, state.currentPath);
        syncSnapshot = nextSync;
    }
});
let simulationRenderSnapshot = '';
simulationStore.subscribe((state) => {
    const nextRenderSnapshot = JSON.stringify({
        simulationStatus: state.simulationStatus,
        validationIssues: state.validationIssues,
    });
    if (nextRenderSnapshot !== simulationRenderSnapshot) {
        render();
        simulationRenderSnapshot = nextRenderSnapshot;
    }
    if (state.simulationState !== previousSimulationState) {
        applySimulationState(state.simulationState);
        updateRuntimeInspector(state.simulationState);
        updateTrajectoryRuntime(state.simulationState);
        updateRecordingRuntime(state.simulationState);
        updateControllerRuntime(state.simulationState);
        updateSimulationClock(state.simulationState);
        updateStatusBar();
        previousSimulationState = state.simulationState;
    }
});
window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        workspace.closeLibrary();
        closeAllMenus();
        return;
    }
    const control = event.ctrlKey || event.metaKey;
    if (!control)
        return;
    if (event.key.toLowerCase() === 'k') {
        event.preventDefault();
        workspace.openLibrary();
    }
    else if (event.key.toLowerCase() === 'z') {
        event.preventDefault();
        if (event.shiftKey)
            store.redo();
        else
            store.undo();
    }
    else if (event.key.toLowerCase() === 'y') {
        event.preventDefault();
        store.redo();
    }
    else if (event.key.toLowerCase() === 's') {
        event.preventDefault();
        void saveProject(event.shiftKey);
    }
});
async function initialize() {
    bridge = await EditorBridgeClient.connect();
    bridge.onSimulationState((state) => simulationStore.setSimulationState(state));
    bridge.onSimulationStatus((status) => {
        if (status === 'stopped')
            loadedController = null;
        simulationStore.setSimulation(status, simulationStore.current.simulationState);
    });
    bridge.onConsoleMessage((message) => store.appendLog(message));
    const backendStatus = document.getElementById('status-backend');
    if (backendStatus)
        backendStatus.textContent = 'backend connected';
    void loadAssetsWithRetry();
    bridge.syncEditorState(JSON.stringify(store.current.scene), store.current.dirty, store.current.currentPath);
    store.appendLog('TypeScript editor ready.');
    window.simlabEditorReady = true;
}
let lastAssetConnectionError = '';
async function loadAssetsWithRetry() {
    const assets = await bridge.call('getAssets');
    if (assets.ok && assets.data) {
        store.setAssets(assets.data.assets);
        if (lastAssetConnectionError)
            store.appendLog('Shared assets connected.');
        lastAssetConnectionError = '';
        bridge.syncEditorState(JSON.stringify(store.current.scene), store.current.dirty, store.current.currentPath);
        return;
    }
    const error = assets.error ?? 'Backend API unavailable';
    if (error !== lastAssetConnectionError)
        store.appendLog(`Assets: ${error}`);
    lastAssetConnectionError = error;
    element('asset-list').innerHTML = '<div class="empty-state">Connecting to shared assets…</div>';
    window.setTimeout(() => { void loadAssetsWithRetry(); }, 1000);
}
window.simlabEditorReady = false;
window.simlabEditor = {
    getRecording: () => bridge.call('getRecording'),
    setSimulationSpeed,
    // Keep the legacy flattened automation payload while the application uses separate stores.
    getStateJson: () => JSON.stringify({ ...store.current, ...simulationStore.current }),
    selectJoint: (actorId, jointId) => {
        store.selectJoint(actorId, jointId);
        return store.current.selectedActorId === actorId
            && store.current.selectedJointId === jointId;
    },
    selectSensor: (actorId, sensorId) => {
        store.selectSensor(actorId, sensorId);
        return store.current.selectedActorId === actorId
            && store.current.selectedSensorId === sensorId;
    },
};
void initialize();
