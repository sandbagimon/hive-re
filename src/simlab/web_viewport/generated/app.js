import { EditorBridgeClient } from './bridge.js';
import { EditorStore } from './store.js';
import { captureTrajectoryKeyframe, createTrajectoryDraft, removeTrajectoryKeyframe, setTrajectoryDuration, trajectoryDuration, trajectoryFromDraft, updateTrajectoryKeyframeTarget, updateTrajectoryKeyframeTime, } from './trajectory-draft.js';
import { applySimulationState, configureViewport, selectViewportActor, selectViewportLink, setViewportScene, } from './viewport.js';
const materialPresets = {
    default: { density: 1000, friction: [0.8, 0.005, 0.0001], solref: [0.02, 1], solimp: [0.9, 0.95, 0.001, 0.5, 2], roughness: 0.55, metalness: 0.04 },
    rubber: { density: 1100, friction: [1.2, 0.01, 0.0002], solref: [0.03, 1], solimp: [0.88, 0.96, 0.002, 0.5, 2], roughness: 0.86, metalness: 0 },
    wood: { density: 700, friction: [0.6, 0.004, 0.0001], solref: [0.015, 1], solimp: [0.9, 0.95, 0.001, 0.5, 2], roughness: 0.72, metalness: 0 },
    metal: { density: 7800, friction: [0.35, 0.003, 0.0001], solref: [0.008, 1], solimp: [0.92, 0.97, 0.0005, 0.5, 2], roughness: 0.24, metalness: 0.82 },
    ice: { density: 917, friction: [0.03, 0.001, 0.00005], solref: [0.01, 1], solimp: [0.92, 0.98, 0.0005, 0.5, 2], roughness: 0.12, metalness: 0.08 },
};
const store = new EditorStore();
const trajectoryDrafts = new Map();
let bridge = new EditorBridgeClient(null);
let previousSceneJson = '';
let previousSelectedActorId = null;
let previousSelectedJointId = null;
let previousSimulationState = null;
let syncSnapshot = '';
let renderSnapshot = '';
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
function renderAssets(assets) {
    const list = element('asset-list');
    list.innerHTML = assets.length ? assets.map((asset) => {
        const rgba = asset.default_properties?.rgba ?? [0.55, 0.62, 0.7, 1];
        const color = `rgb(${rgba.slice(0, 3).map((part) => Math.round(part * 255)).join(',')})`;
        return `<button class="asset-item" type="button" data-asset-id="${escapeHtml(asset.id)}">
      <span class="asset-swatch" style="background:${color}"></span>
      <span class="item-label">${escapeHtml(asset.name)}</span>
      <span class="item-meta">${escapeHtml(asset.primitive ?? asset.source_format ?? asset.type)}</span>
    </button>`;
    }).join('') : '<div class="empty-state">No assets</div>';
    for (const button of list.querySelectorAll('[data-asset-id]')) {
        button.addEventListener('click', () => {
            const asset = store.current.assets.find((item) => item.id === button.dataset.assetId);
            if (asset)
                store.addAsset(asset);
        });
    }
}
function renderSceneTree(scene, selectedActorId, selectedJointId) {
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
      </div>`).join('');
        return `
    <button class="tree-item ${actor.id === selectedActorId && selectedJointId === null ? 'selected' : ''}" type="button" data-actor-row data-actor-id="${escapeHtml(actor.id)}">
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
}
function numberInput(label, field, value, options = '') {
    return `<div class="property-row"><label>${label}</label><input type="number" step="0.01" value="${value}" data-field="${field}" ${options}></div>`;
}
function vectorInput(label, field, values) {
    return `<div class="property-row"><label>${label}</label><div class="vector-row">${values.map((value, index) => `<input type="number" step="0.01" value="${value}" data-vector="${field}" data-index="${index}">`).join('')}</div></div>`;
}
function renderInspector(actor, scene, simulationState, selectedJointId) {
    const inspector = element('property-inspector');
    if (!actor) {
        inspector.innerHTML = '<div class="empty-state">No actor selected</div>';
        return;
    }
    const physics = actor.properties.physics ?? { dynamic: true };
    const friction = physics.friction ?? [0.8, 0.005, 0.0001];
    const geometry = actor.properties.geometry;
    const articulationIds = actor.properties.articulation_ids;
    const articulations = scene.robotics?.articulations.filter((item) => articulationIds?.includes(item.id)) ?? [];
    const selectedJoint = articulations.flatMap((item) => item.joints)
        .find((item) => item.id === selectedJointId);
    const jointStates = new Map((simulationState?.joints ?? []).map((item) => [item.id, item]));
    const actuatorStates = new Map((simulationState?.actuators ?? []).map((item) => [item.id, item]));
    const controller = simulationState?.controller ?? {
        status: 'ready', message: null, command_time: null, timeout: null,
    };
    const controllerStatus = `<div class="controller-status" data-controller-status="${controller.status}">
    <span data-controller-status-label>${controller.status.replace('_', ' ')}</span>
    <small data-controller-message>${controller.message ? escapeHtml(controller.message) : ''}</small>
  </div>`;
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
    const robotSection = jointControls ? `
    <section class="property-group"><div class="group-heading"><h3>Joint Control</h3><div class="joint-tools"><label>Step <input type="number" min="0.001" max="1" step="0.01" value="0.05" data-joint-step></label><button type="button" data-joint-home>Home</button></div></div>
      ${controllerStatus}
      ${jointControls}
    </section>` : '';
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
    const identitySections = selectedJoint ? `
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
    const physicsSection = selectedJoint ? '' : `
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
    ${robotSection}
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
    for (const input of inspector.querySelectorAll('[data-joint-target]')) {
        input.addEventListener('change', () => {
            const jointId = input.dataset.jointTarget;
            if (jointId)
                void sendJointTargets({ [jointId]: Number(input.value) });
        });
    }
    inspector.querySelector('[data-joint-step]')?.addEventListener('change', (event) => {
        const value = Number(event.currentTarget.value);
        if (!Number.isFinite(value) || value <= 0)
            return;
        for (const input of inspector.querySelectorAll('[data-joint-target]')) {
            input.step = String(value);
        }
    });
    for (const button of inspector.querySelectorAll('[data-joint-jog]')) {
        button.addEventListener('click', () => {
            const jointId = button.dataset.jointJog;
            const direction = Number(button.dataset.direction);
            const step = Number(inspector.querySelector('[data-joint-step]')?.value);
            const targetInput = Array.from(inspector.querySelectorAll('input[type="number"][data-joint-target]')).find((input) => input.dataset.jointTarget === jointId);
            const target = Number(targetInput?.value);
            if (!jointId || !Number.isFinite(step) || step <= 0
                || Math.abs(direction) !== 1 || !Number.isFinite(target)) {
                showToast('Joint jog requires a positive step and finite target', true);
                return;
            }
            void sendJointTargets({ [jointId]: target + direction * step });
        });
    }
    inspector.querySelector('[data-joint-home]')?.addEventListener('click', () => {
        const targets = Object.fromEntries(articulations.flatMap((articulation) => articulation.actuators.filter((actuator) => actuator.control_type === 'position')
            .filter((actuator) => selectedJointId === null || actuator.joint_id === selectedJointId)
            .map((actuator) => articulation.joints.find((joint) => joint.id === actuator.joint_id))
            .filter((joint) => joint !== undefined)
            .map((joint) => [joint.id, joint.initial_position])));
        void sendJointTargets(targets);
    });
}
function updateRuntimeInspector(simulationState) {
    if (!simulationState)
        return;
    const inspector = element('property-inspector');
    const controller = inspector.querySelector('[data-controller-status]');
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
        for (const item of inspector.querySelectorAll('[data-joint-position]')) {
            if (item.dataset.jointPosition === joint.id)
                item.textContent = `${joint.qpos.toFixed(3)} rad`;
        }
        for (const item of inspector.querySelectorAll('[data-joint-qpos]')) {
            if (item.dataset.jointQpos === joint.id)
                item.textContent = `qpos ${joint.qpos.toFixed(3)}`;
        }
        for (const item of inspector.querySelectorAll('[data-joint-qvel]')) {
            if (item.dataset.jointQvel === joint.id)
                item.textContent = `qvel ${joint.qvel.toFixed(3)}`;
        }
        for (const input of inspector.querySelectorAll('[data-joint-position-field]')) {
            if (input.dataset.jointPositionField === joint.id)
                input.value = joint.qpos.toFixed(3);
        }
    }
    for (const actuator of simulationState.actuators) {
        for (const input of inspector.querySelectorAll('[data-actuator-id]')) {
            if (input.dataset.actuatorId === actuator.id && document.activeElement !== input) {
                input.value = input.type === 'number' ? actuator.ctrl.toFixed(3) : String(actuator.ctrl);
            }
        }
    }
}
async function sendJointTargets(targets) {
    const result = await bridge.call('setJointTargets', JSON.stringify(store.current.scene), JSON.stringify(targets));
    if (!result.ok || !result.data) {
        if (result.data?.state)
            store.setSimulation('paused', result.data.state);
        showToast(result.error ?? 'Joint control failed', true);
        return;
    }
    const status = store.current.simulationStatus === 'running' ? 'running' : 'paused';
    store.setSimulation(status, result.data.state);
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
    const panel = element('validation-panel');
    panel.hidden = issues.length === 0;
    element('validation-count').textContent = String(issues.length);
    const list = element('validation-list');
    list.innerHTML = issues.map((issue, index) => `
    <button type="button" class="validation-item ${issue.severity}" data-issue-index="${index}">
      <span class="validation-code">${escapeHtml(issue.code)}</span>
      <span class="validation-message">${escapeHtml(issue.actor_name ?? issue.actor_id ?? 'Scene')}: ${escapeHtml(issue.message)}</span>
    </button>`).join('');
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
function renderTrajectoryPanel(actor, scene, simulationState) {
    const panel = element('trajectory-panel');
    panel.hidden = actor?.type !== 'robot';
    if (panel.hidden || !actor)
        return;
    const draftState = ensureTrajectoryDraft(actor, scene);
    if (!draftState) {
        element('trajectory-controls').innerHTML = '<div class="empty-state">No position joints</div>';
        return;
    }
    const { draft } = draftState;
    const bindings = positionJointBindings(actor, scene);
    const controls = element('trajectory-controls');
    controls.innerHTML = `
    <div class="trajectory-fields">
      <input type="text" value="${escapeHtml(draft.name)}" data-trajectory-name title="Trajectory name">
      <input type="number" min="0.05" step="0.1" value="${trajectoryDuration(draft)}" data-trajectory-duration title="Duration in seconds">
      <label><input type="checkbox" data-trajectory-loop ${draft.loop ? 'checked' : ''}>Loop</label>
    </div>
    <progress class="trajectory-progress" value="0" max="1" data-trajectory-progress></progress>
    <div class="trajectory-time" data-trajectory-time>0.00 / 0.00 s</div>
    <div class="trajectory-actions">
      <button type="button" data-trajectory-command="load">Load</button>
      <button type="button" class="icon-button" data-trajectory-command="play" title="Play">▶</button>
      <button type="button" class="icon-button" data-trajectory-command="pause" title="Pause">Ⅱ</button>
      <button type="button" class="icon-button" data-trajectory-command="stop" title="Stop">■</button>
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
    controls.querySelector('[data-trajectory-name]')?.addEventListener('change', (event) => { draft.name = event.currentTarget.value; });
    controls.querySelector('[data-trajectory-duration]')?.addEventListener('change', (event) => {
        try {
            draftState.draft = setTrajectoryDuration(draftState.draft, Number(event.currentTarget.value));
            renderTrajectoryPanel(actor, scene, store.current.simulationState);
        }
        catch (error) {
            showToast(error instanceof Error ? error.message : String(error), true);
        }
    });
    controls.querySelector('[data-trajectory-loop]')?.addEventListener('change', (event) => { draft.loop = event.currentTarget.checked; });
    for (const button of controls.querySelectorAll('[data-trajectory-command]')) {
        button.addEventListener('click', () => {
            void handleTrajectoryCommand(button.dataset.trajectoryCommand ?? '', actor, scene);
        });
    }
    controls.querySelector('[data-keyframe-add]')?.addEventListener('click', () => {
        draftState.draft = captureTrajectoryKeyframe(draftState.draft, `keyframe-${draftState.nextKeyframeId++}`, trajectoryDuration(draftState.draft) + 0.5, currentRobotTargets(actor, scene));
        draftState.targetsTouched = true;
        renderTrajectoryPanel(actor, scene, store.current.simulationState);
    });
    for (const row of controls.querySelectorAll('[data-keyframe-id]')) {
        const keyframeId = row.dataset.keyframeId ?? '';
        row.querySelector('[data-keyframe-time]')?.addEventListener('change', (event) => {
            draftState.draft = updateTrajectoryKeyframeTime(draftState.draft, keyframeId, Number(event.currentTarget.value));
            draftState.targetsTouched = true;
            renderTrajectoryPanel(actor, scene, store.current.simulationState);
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
                renderTrajectoryPanel(actor, scene, store.current.simulationState);
            }
            catch (error) {
                showToast(error instanceof Error ? error.message : String(error), true);
            }
        });
    }
    updateTrajectoryRuntime(simulationState);
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
function currentRobotTargets(actor, scene) {
    const actuatorStates = new Map((store.current.simulationState?.actuators ?? []).map((item) => [item.id, item.ctrl]));
    return Object.fromEntries(positionJointBindings(actor, scene).map(({ joint, actuator }) => [
        joint.id,
        actuatorStates.get(actuator.id) ?? joint.initial_position,
    ]));
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
    if (existing?.homeSignature === homeSignature)
        return existing;
    const created = {
        draft: createTrajectoryDraft(actor.id, homeTargets),
        homeSignature,
        targetsTouched: false,
        nextKeyframeId: 2,
    };
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
        store.setValidationIssues(result.data?.issues ?? []);
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
    store.setSimulation(status, result.data.state);
}
function updateTrajectoryRuntime(simulationState) {
    const panel = element('trajectory-panel');
    if (panel.hidden)
        return;
    const trajectory = simulationState?.trajectory;
    const status = trajectory?.status ?? 'stopped';
    const time = trajectory?.time ?? 0;
    const duration = trajectory?.duration ?? 0;
    element('trajectory-status').textContent = status.replace('_', ' ');
    const progress = panel.querySelector('[data-trajectory-progress]');
    if (progress) {
        progress.max = Math.max(duration, 0.001);
        progress.value = Math.min(time, progress.max);
    }
    const timeLabel = panel.querySelector('[data-trajectory-time]');
    if (timeLabel)
        timeLabel.textContent = `${time.toFixed(2)} / ${duration.toFixed(2)} s`;
    const loaded = trajectory?.name !== null && trajectory?.name !== undefined;
    const play = panel.querySelector('[data-trajectory-command="play"]');
    const pause = panel.querySelector('[data-trajectory-command="pause"]');
    const stop = panel.querySelector('[data-trajectory-command="stop"]');
    if (play)
        play.disabled = !loaded || status === 'playing';
    if (pause)
        pause.disabled = status !== 'playing';
    if (stop)
        stop.disabled = !loaded;
}
function render() {
    const state = store.current;
    element('project-label').textContent = `${state.dirty ? '* ' : ''}${state.scene.name}`;
    document.title = `${state.dirty ? '* ' : ''}SimLab - ${state.scene.name}`;
    const badge = element('simulation-badge');
    badge.textContent = state.simulationStatus[0].toUpperCase() + state.simulationStatus.slice(1);
    badge.dataset.status = state.simulationStatus;
    element('undo-button').disabled = !state.canUndo;
    element('redo-button').disabled = !state.canRedo;
    renderAssets(state.assets);
    renderSceneTree(state.scene, state.selectedActorId, state.selectedJointId);
    renderInspector(state.scene.actors.find((actor) => actor.id === state.selectedActorId), state.scene, state.simulationState, state.selectedJointId);
    renderTrajectoryPanel(state.scene.actors.find((actor) => actor.id === state.selectedActorId), state.scene, state.simulationState);
    renderValidation(state.validationIssues);
    renderConsole(state.logs);
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
    if (command === 'new' && allowDiscard())
        store.newScene();
    else if (command === 'open' && allowDiscard()) {
        const result = await bridge.call('openProject');
        if (result.ok && result.data) {
            store.loadScene(result.data.scene, result.data.path);
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
        await importOpenUsd();
    else if (command === 'undo')
        store.undo();
    else if (command === 'redo')
        store.redo();
    else if (command === 'clear-console')
        store.clearLogs();
    else if (command === 'export') {
        const result = await bridge.call('exportMjcf', JSON.stringify(store.current.scene));
        store.setValidationIssues(result.data?.issues ?? []);
        if (result.ok && result.data) {
            store.appendLog(`Exported MJCF: ${result.data.path}`);
            showToast('MJCF exported');
        }
        else
            showToast(result.error ?? 'Export failed', true);
    }
    else if (command === 'run') {
        const result = await bridge.call('runSimulation', JSON.stringify(store.current.scene));
        store.setValidationIssues(result.data?.issues ?? []);
        if (result.ok && result.data)
            store.setSimulation('running', result.data.state);
        else
            showToast(result.error ?? 'Simulation failed', true);
    }
    else if (command === 'pause') {
        const result = await bridge.call('pauseSimulation');
        if (result.ok)
            store.setSimulation('paused', store.current.simulationState);
    }
    else if (command === 'step') {
        const result = await bridge.call('stepSimulation', JSON.stringify(store.current.scene));
        store.setValidationIssues(result.data?.issues ?? []);
        if (result.ok && result.data)
            store.setSimulation('paused', result.data.state);
        else
            showToast(result.error ?? 'Simulation step failed', true);
    }
    else if (command === 'reset') {
        const result = await bridge.call('resetSimulation');
        if (result.ok && result.data?.state) {
            store.setSimulation('paused', result.data.state);
        }
        else if (result.ok) {
            store.setSimulation('stopped', null);
        }
        else {
            showToast(result.error ?? 'Simulation reset failed', true);
        }
    }
}
async function importOpenUsd(path) {
    const result = path
        ? await bridge.call('importOpenUsdPath', path)
        : await bridge.call('importOpenUsd');
    if (result.ok && result.data) {
        store.upsertAsset(result.data.asset);
        store.addAsset(result.data.asset, result.data.robotics);
        for (const warning of result.data.warnings)
            store.appendLog(`USD: ${warning}`);
        showToast(`Imported ${result.data.asset.name}`);
    }
    else if (result.error !== 'Cancelled') {
        showToast(result.error ?? 'OpenUSD import failed', true);
    }
    return result;
}
for (const button of document.querySelectorAll('[data-command]')) {
    button.addEventListener('click', () => void handleCommand(button.dataset.command ?? ''));
}
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
});
store.subscribe((state) => {
    const sceneJson = JSON.stringify(state.scene);
    const nextRenderSnapshot = JSON.stringify({
        sceneJson,
        assets: state.assets,
        selectedActorId: state.selectedActorId,
        selectedJointId: state.selectedJointId,
        dirty: state.dirty,
        canUndo: state.canUndo,
        canRedo: state.canRedo,
        currentPath: state.currentPath,
        simulationStatus: state.simulationStatus,
        validationIssues: state.validationIssues,
        logs: state.logs,
    });
    if (nextRenderSnapshot !== renderSnapshot) {
        render();
        renderSnapshot = nextRenderSnapshot;
    }
    if (sceneJson !== previousSceneJson) {
        setViewportScene(state.scene);
        previousSceneJson = sceneJson;
    }
    if (state.selectedActorId !== previousSelectedActorId) {
        selectViewportActor(state.selectedActorId);
        previousSelectedActorId = state.selectedActorId;
    }
    if (state.selectedJointId !== previousSelectedJointId) {
        const childLinkId = state.scene.robotics?.articulations
            .flatMap((item) => item.joints)
            .find((item) => item.id === state.selectedJointId)?.child_link_id ?? null;
        selectViewportLink(childLinkId);
        previousSelectedJointId = state.selectedJointId;
    }
    if (state.simulationState !== previousSimulationState) {
        applySimulationState(state.simulationState);
        updateRuntimeInspector(state.simulationState);
        updateTrajectoryRuntime(state.simulationState);
        previousSimulationState = state.simulationState;
    }
    const nextSync = `${sceneJson}:${state.dirty}`;
    if (nextSync !== syncSnapshot) {
        bridge.syncEditorState(sceneJson, state.dirty, state.currentPath);
        syncSnapshot = nextSync;
    }
});
window.addEventListener('keydown', (event) => {
    const control = event.ctrlKey || event.metaKey;
    if (!control)
        return;
    if (event.key.toLowerCase() === 'z') {
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
    bridge.onSimulationState((state) => store.setSimulationState(state));
    bridge.onSimulationStatus((status) => store.setSimulation(status, store.current.simulationState));
    bridge.onConsoleMessage((message) => store.appendLog(message));
    const assets = await bridge.call('getAssets');
    if (assets.ok && assets.data)
        store.setAssets(assets.data.assets);
    else
        store.appendLog(assets.error ?? 'Python bridge unavailable.');
    bridge.syncEditorState(JSON.stringify(store.current.scene), store.current.dirty, store.current.currentPath);
    store.appendLog('TypeScript editor ready.');
    window.simlabEditorReady = true;
}
window.simlabEditorReady = false;
window.simlabEditor = {
    importOpenUsdPath: (path) => importOpenUsd(path),
    getStateJson: () => JSON.stringify(store.current),
    selectJoint: (actorId, jointId) => {
        store.selectJoint(actorId, jointId);
        return store.current.selectedActorId === actorId
            && store.current.selectedJointId === jointId;
    },
};
void initialize();
