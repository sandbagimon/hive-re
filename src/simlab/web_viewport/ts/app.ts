import { EditorBridgeClient } from './bridge.js';
import { EditorStore } from './store.js';
import type {
  Actor,
  ActorProperties,
  AssetMetadata,
  ExportPayload,
  OpenUsdImportPayload,
  PhysicsProperties,
  PreflightPayload,
  ProjectPayload,
  SavePayload,
  Scene,
  SimulationState,
  Transform,
  ValidationIssue,
  VisualGeometryPayload,
} from './types.js';
import {
  applySimulationState,
  configureViewport,
  selectViewportActor,
  selectViewportLink,
  setViewportScene,
} from './viewport.js';

interface AssetsPayload {
  assets: AssetMetadata[];
}

interface RunPayload {
  state: SimulationState;
  issues?: ValidationIssue[];
}

const materialPresets: Record<string, Partial<PhysicsProperties>> = {
  default: { density: 1000, friction: [0.8, 0.005, 0.0001], solref: [0.02, 1], solimp: [0.9, 0.95, 0.001, 0.5, 2], roughness: 0.55, metalness: 0.04 },
  rubber: { density: 1100, friction: [1.2, 0.01, 0.0002], solref: [0.03, 1], solimp: [0.88, 0.96, 0.002, 0.5, 2], roughness: 0.86, metalness: 0 },
  wood: { density: 700, friction: [0.6, 0.004, 0.0001], solref: [0.015, 1], solimp: [0.9, 0.95, 0.001, 0.5, 2], roughness: 0.72, metalness: 0 },
  metal: { density: 7800, friction: [0.35, 0.003, 0.0001], solref: [0.008, 1], solimp: [0.92, 0.97, 0.0005, 0.5, 2], roughness: 0.24, metalness: 0.82 },
  ice: { density: 917, friction: [0.03, 0.001, 0.00005], solref: [0.01, 1], solimp: [0.92, 0.98, 0.0005, 0.5, 2], roughness: 0.12, metalness: 0.08 },
};

const store = new EditorStore();
let bridge = new EditorBridgeClient(null);
let previousSceneJson = '';
let previousSelectedActorId: string | null = null;
let previousSelectedJointId: string | null = null;
let previousSimulationState: SimulationState | null = null;
let syncSnapshot = '';
let renderSnapshot = '';

const element = <T extends HTMLElement>(id: string): T => {
  const value = document.getElementById(id);
  if (!value) throw new Error(`Missing editor element: #${id}`);
  return value as T;
};

const escapeHtml = (value: unknown): string => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;');

function showToast(message: string, error = false): void {
  const toast = element('toast');
  toast.textContent = message;
  toast.classList.toggle('error', error);
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 3200);
}

function renderAssets(assets: AssetMetadata[]): void {
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
  for (const button of list.querySelectorAll<HTMLButtonElement>('[data-asset-id]')) {
    button.addEventListener('click', () => {
      const asset = store.current.assets.find((item) => item.id === button.dataset.assetId);
      if (asset) store.addAsset(asset);
    });
  }
}

function renderSceneTree(
  scene: Scene,
  selectedActorId: string | null,
  selectedJointId: string | null,
): void {
  element('actor-count').textContent = String(scene.actors.length);
  const tree = element('scene-tree');
  tree.innerHTML = scene.actors.length ? scene.actors.map((actor) => {
    const articulationIds = actor.properties.articulation_ids as string[] | undefined;
    const articulations = scene.robotics?.articulations.filter(
      (item) => articulationIds?.includes(item.id),
    ) ?? [];
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
  for (const button of tree.querySelectorAll<HTMLButtonElement>('[data-actor-row]')) {
    button.addEventListener('click', (event) => {
      const deleteTarget = (event.target as HTMLElement).closest<HTMLElement>('[data-delete-id]');
      if (deleteTarget?.dataset.deleteId) store.deleteActor(deleteTarget.dataset.deleteId);
      else store.selectActor(button.dataset.actorId ?? null);
    });
  }
  for (const button of tree.querySelectorAll<HTMLButtonElement>('[data-joint-id]')) {
    button.addEventListener('click', () => {
      const actorId = button.dataset.ownerActorId;
      const jointId = button.dataset.jointId;
      if (actorId && jointId) store.selectJoint(actorId, jointId);
    });
  }
}

function numberInput(label: string, field: string, value: number, options = ''): string {
  return `<div class="property-row"><label>${label}</label><input type="number" step="0.01" value="${value}" data-field="${field}" ${options}></div>`;
}

function vectorInput(label: string, field: string, values: number[]): string {
  return `<div class="property-row"><label>${label}</label><div class="vector-row">${values.map((value, index) =>
    `<input type="number" step="0.01" value="${value}" data-vector="${field}" data-index="${index}">`).join('')}</div></div>`;
}

function renderInspector(
  actor: Actor | undefined,
  scene: Scene,
  simulationState: SimulationState | null,
  selectedJointId: string | null,
): void {
  const inspector = element('property-inspector');
  if (!actor) {
    inspector.innerHTML = '<div class="empty-state">No actor selected</div>';
    return;
  }
  const physics = actor.properties.physics ?? { dynamic: true };
  const friction = physics.friction ?? [0.8, 0.005, 0.0001];
  const geometry = actor.properties.geometry;
  const articulationIds = actor.properties.articulation_ids as string[] | undefined;
  const articulations = scene.robotics?.articulations.filter(
    (item) => articulationIds?.includes(item.id),
  ) ?? [];
  const selectedJoint = articulations.flatMap((item) => item.joints)
    .find((item) => item.id === selectedJointId);
  const jointStates = new Map((simulationState?.joints ?? []).map((item) => [item.id, item]));
  const actuatorStates = new Map(
    (simulationState?.actuators ?? []).map((item) => [item.id, item]),
  );
  const controller = simulationState?.controller ?? {
    status: 'ready', message: null, command_time: null, timeout: null,
  };
  const controllerStatus = `<div class="controller-status" data-controller-status="${controller.status}">
    <span data-controller-status-label>${controller.status.replace('_', ' ')}</span>
    <small data-controller-message>${controller.message ? escapeHtml(controller.message) : ''}</small>
  </div>`;
  const jointControls = articulations.flatMap((articulation) =>
    articulation.actuators
      .filter((item) => item.control_type === 'position')
      .filter((item) => selectedJointId === null || item.joint_id === selectedJointId)
      .map((actuator) => {
      const joint = articulation.joints.find((item) => item.id === actuator.joint_id);
      if (!joint) return '';
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
    }),
  ).join('');
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
  const parentLink = selectedArticulation?.links.find(
    (item) => item.id === selectedJoint?.parent_link_id,
  );
  const childLink = selectedArticulation?.links.find(
    (item) => item.id === selectedJoint?.child_link_id,
  );
  const identitySections = selectedJoint ? `
    <section class="property-group"><h3>Joint</h3>
      <div class="property-row"><label>Name</label><input type="text" value="${escapeHtml(selectedJoint.name)}" disabled></div>
      <div class="property-row"><label>Type</label><input type="text" value="${escapeHtml(selectedJoint.type)}" disabled></div>
      <div class="property-row"><label>Parent</label><input type="text" value="${escapeHtml(parentLink?.name ?? selectedJoint.parent_link_id)}" disabled></div>
      <div class="property-row"><label>Child</label><input type="text" value="${escapeHtml(childLink?.name ?? selectedJoint.child_link_id)}" disabled></div>
      <div class="property-row"><label>Axis</label><input type="text" value="${selectedJoint.axis.join(', ')}" disabled></div>
      <div class="property-row"><label>Range</label><input type="text" value="${selectedJoint.limits?.lower ?? '—'} to ${selectedJoint.limits?.upper ?? '—'}" disabled></div>
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
  for (const input of inspector.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-field]')) {
    input.addEventListener('change', () => updateProperty(actorId, input));
  }
  for (const input of inspector.querySelectorAll<HTMLInputElement>('[data-vector]')) {
    input.addEventListener('change', () => {
      const current = store.current.scene.actors.find((item) => item.id === actorId);
      if (!current) return;
      const transform = structuredClone(current.transform);
      const vector = transform[input.dataset.vector as keyof Transform] as [number, number, number];
      vector[Number(input.dataset.index)] = Number(input.value);
      store.updateActorTransform(actorId, transform);
    });
  }
  for (const input of inspector.querySelectorAll<HTMLInputElement>('[data-joint-target]')) {
    input.addEventListener('change', () => {
      const jointId = input.dataset.jointTarget;
      if (jointId) void sendJointTargets({ [jointId]: Number(input.value) });
    });
  }
  inspector.querySelector<HTMLInputElement>('[data-joint-step]')?.addEventListener('change', (event) => {
    const value = Number((event.currentTarget as HTMLInputElement).value);
    if (!Number.isFinite(value) || value <= 0) return;
    for (const input of inspector.querySelectorAll<HTMLInputElement>('[data-joint-target]')) {
      input.step = String(value);
    }
  });
  for (const button of inspector.querySelectorAll<HTMLButtonElement>('[data-joint-jog]')) {
    button.addEventListener('click', () => {
      const jointId = button.dataset.jointJog;
      const direction = Number(button.dataset.direction);
      const step = Number(inspector.querySelector<HTMLInputElement>('[data-joint-step]')?.value);
      const targetInput = Array.from(
        inspector.querySelectorAll<HTMLInputElement>('input[type="number"][data-joint-target]'),
      ).find((input) => input.dataset.jointTarget === jointId);
      const target = Number(targetInput?.value);
      if (
        !jointId || !Number.isFinite(step) || step <= 0
        || Math.abs(direction) !== 1 || !Number.isFinite(target)
      ) {
        showToast('Joint jog requires a positive step and finite target', true);
        return;
      }
      void sendJointTargets({ [jointId]: target + direction * step });
    });
  }
  inspector.querySelector<HTMLButtonElement>('[data-joint-home]')?.addEventListener('click', () => {
    const targets = Object.fromEntries(
      articulations.flatMap((articulation) =>
        articulation.actuators.filter((actuator) => actuator.control_type === 'position')
          .filter((actuator) => selectedJointId === null || actuator.joint_id === selectedJointId)
          .map((actuator) => articulation.joints.find((joint) => joint.id === actuator.joint_id))
          .filter((joint) => joint !== undefined)
          .map((joint) => [joint.id, joint.initial_position] as const),
      ),
    );
    void sendJointTargets(targets);
  });
}

function updateRuntimeInspector(simulationState: SimulationState | null): void {
  if (!simulationState) return;
  const inspector = element('property-inspector');
  const controller = inspector.querySelector<HTMLElement>('[data-controller-status]');
  if (controller) {
    controller.dataset.controllerStatus = simulationState.controller.status;
    const label = controller.querySelector<HTMLElement>('[data-controller-status-label]');
    const message = controller.querySelector<HTMLElement>('[data-controller-message]');
    if (label) label.textContent = simulationState.controller.status.replace('_', ' ');
    if (message) message.textContent = simulationState.controller.message ?? '';
  }
  for (const joint of simulationState.joints) {
    for (const item of inspector.querySelectorAll<HTMLElement>('[data-joint-position]')) {
      if (item.dataset.jointPosition === joint.id) item.textContent = `${joint.qpos.toFixed(3)} rad`;
    }
    for (const item of inspector.querySelectorAll<HTMLElement>('[data-joint-qpos]')) {
      if (item.dataset.jointQpos === joint.id) item.textContent = `qpos ${joint.qpos.toFixed(3)}`;
    }
    for (const item of inspector.querySelectorAll<HTMLElement>('[data-joint-qvel]')) {
      if (item.dataset.jointQvel === joint.id) item.textContent = `qvel ${joint.qvel.toFixed(3)}`;
    }
    for (const input of inspector.querySelectorAll<HTMLInputElement>('[data-joint-position-field]')) {
      if (input.dataset.jointPositionField === joint.id) input.value = joint.qpos.toFixed(3);
    }
  }
  for (const actuator of simulationState.actuators) {
    for (const input of inspector.querySelectorAll<HTMLInputElement>('[data-actuator-id]')) {
      if (input.dataset.actuatorId === actuator.id && document.activeElement !== input) {
        input.value = input.type === 'number' ? actuator.ctrl.toFixed(3) : String(actuator.ctrl);
      }
    }
  }
}

async function sendJointTargets(targets: Record<string, number>): Promise<void> {
  const result = await bridge.call<RunPayload>(
    'setJointTargets',
    JSON.stringify(store.current.scene),
    JSON.stringify(targets),
  );
  if (!result.ok || !result.data) {
    if (result.data?.state) store.setSimulation('paused', result.data.state);
    showToast(result.error ?? 'Joint control failed', true);
    return;
  }
  store.setSimulation('paused', result.data.state);
}

function updateProperty(actorId: string, input: HTMLInputElement | HTMLSelectElement): void {
  const actor = store.current.scene.actors.find((item) => item.id === actorId);
  if (!actor) return;
  const field = input.dataset.field;
  if (field === 'name') {
    store.updateActorName(actorId, input.value);
    return;
  }
  const physics: PhysicsProperties = structuredClone(actor.properties.physics ?? { dynamic: true });
  if (field === 'dynamic') physics.dynamic = (input as HTMLInputElement).checked;
  else if (field === 'material') {
    physics.material = input.value as PhysicsProperties['material'];
    Object.assign(physics, structuredClone(materialPresets[input.value]));
  } else if (field === 'mass_mode') physics.mass_mode = input.value as PhysicsProperties['mass_mode'];
  else if (field === 'mass') physics.mass = Number(input.value);
  else if (field === 'density') physics.density = Number(input.value);
  else if (field === 'friction') {
    const friction = [...(physics.friction ?? [0.8, 0.005, 0.0001])] as [number, number, number];
    friction[0] = Number(input.value);
    physics.friction = friction;
  }
  store.updateActorProperties(actorId, { physics, mass: physics.mass });
}

function renderValidation(issues: ValidationIssue[]): void {
  const panel = element('validation-panel');
  panel.hidden = issues.length === 0;
  element('validation-count').textContent = String(issues.length);
  const list = element('validation-list');
  list.innerHTML = issues.map((issue, index) => `
    <button type="button" class="validation-item ${issue.severity}" data-issue-index="${index}">
      <span class="validation-code">${escapeHtml(issue.code)}</span>
      <span class="validation-message">${escapeHtml(issue.actor_name ?? issue.actor_id ?? 'Scene')}: ${escapeHtml(issue.message)}</span>
    </button>`).join('');
  for (const button of list.querySelectorAll<HTMLButtonElement>('[data-issue-index]')) {
    button.addEventListener('click', () => {
      const issue = issues[Number(button.dataset.issueIndex)];
      if (issue.actor_id) store.selectActor(issue.actor_id);
    });
  }
}

function renderConsole(logs: string[]): void {
  const output = element('console-output');
  output.innerHTML = logs.map((line) => `<div class="console-line">${escapeHtml(line)}</div>`).join('');
  output.scrollTop = output.scrollHeight;
}

function render(): void {
  const state = store.current;
  element('project-label').textContent = `${state.dirty ? '* ' : ''}${state.scene.name}`;
  document.title = `${state.dirty ? '* ' : ''}SimLab - ${state.scene.name}`;
  const badge = element('simulation-badge');
  badge.textContent = state.simulationStatus[0].toUpperCase() + state.simulationStatus.slice(1);
  badge.dataset.status = state.simulationStatus;
  (element('undo-button') as HTMLButtonElement).disabled = !state.canUndo;
  (element('redo-button') as HTMLButtonElement).disabled = !state.canRedo;
  renderAssets(state.assets);
  renderSceneTree(state.scene, state.selectedActorId, state.selectedJointId);
  renderInspector(
    state.scene.actors.find((actor) => actor.id === state.selectedActorId),
    state.scene,
    state.simulationState,
    state.selectedJointId,
  );
  renderValidation(state.validationIssues);
  renderConsole(state.logs);
}

async function saveProject(saveAs = false): Promise<boolean> {
  const result = await bridge.call<SavePayload>('saveProject', JSON.stringify(store.current.scene), saveAs);
  if (!result.ok || !result.data) {
    if (result.error !== 'Cancelled') showToast(result.error ?? 'Save failed', true);
    return false;
  }
  store.markSaved(result.data.path);
  store.appendLog(`Saved scene: ${result.data.path}`);
  return true;
}

function allowDiscard(): boolean {
  return !store.current.dirty || window.confirm('Discard unsaved scene changes?');
}

async function handleCommand(command: string): Promise<void> {
  if (command === 'new' && allowDiscard()) store.newScene();
  else if (command === 'open' && allowDiscard()) {
    const result = await bridge.call<ProjectPayload>('openProject');
    if (result.ok && result.data) {
      store.loadScene(result.data.scene, result.data.path);
      store.appendLog(`Opened scene: ${result.data.path}`);
    } else if (result.error !== 'Cancelled') showToast(result.error ?? 'Open failed', true);
  } else if (command === 'save') await saveProject(false);
  else if (command === 'save-as') await saveProject(true);
  else if (command === 'import-openusd') {
    const result = await bridge.call<OpenUsdImportPayload>('importOpenUsd');
    if (result.ok && result.data) {
      store.upsertAsset(result.data.asset);
      store.addAsset(result.data.asset, result.data.robotics);
      for (const warning of result.data.warnings) store.appendLog(`USD: ${warning}`);
      showToast(`Imported ${result.data.asset.name}`);
    } else if (result.error !== 'Cancelled') {
      showToast(result.error ?? 'OpenUSD import failed', true);
    }
  }
  else if (command === 'undo') store.undo();
  else if (command === 'redo') store.redo();
  else if (command === 'clear-console') store.clearLogs();
  else if (command === 'export') {
    const result = await bridge.call<ExportPayload>('exportMjcf', JSON.stringify(store.current.scene));
    store.setValidationIssues(result.data?.issues ?? []);
    if (result.ok && result.data) {
      store.appendLog(`Exported MJCF: ${result.data.path}`);
      showToast('MJCF exported');
    } else showToast(result.error ?? 'Export failed', true);
  } else if (command === 'run') {
    const result = await bridge.call<RunPayload>('runSimulation', JSON.stringify(store.current.scene));
    store.setValidationIssues(result.data?.issues ?? []);
    if (result.ok && result.data) store.setSimulation('running', result.data.state);
    else showToast(result.error ?? 'Simulation failed', true);
  } else if (command === 'pause') {
    const result = await bridge.call('pauseSimulation');
    if (result.ok) store.setSimulation('paused', store.current.simulationState);
  } else if (command === 'step') {
    const result = await bridge.call<RunPayload>('stepSimulation', JSON.stringify(store.current.scene));
    store.setValidationIssues(result.data?.issues ?? []);
    if (result.ok && result.data) store.setSimulation('paused', result.data.state);
    else showToast(result.error ?? 'Simulation step failed', true);
  } else if (command === 'reset') {
    const result = await bridge.call<RunPayload>('resetSimulation');
    if (result.ok && result.data?.state) {
      store.setSimulation('paused', result.data.state);
    } else if (result.ok) {
      store.setSimulation('stopped', null);
    } else {
      showToast(result.error ?? 'Simulation reset failed', true);
    }
  }
}

for (const button of document.querySelectorAll<HTMLButtonElement>('[data-command]')) {
  button.addEventListener('click', () => void handleCommand(button.dataset.command ?? ''));
}

configureViewport({
  onActorSelected: (actorId) => store.selectActor(actorId),
  onActorTransformChanged: (actorId, transform) => store.updateActorTransform(actorId, transform),
  resolveVisualGeometry: async (cachePath) => {
    const result = await bridge.call<VisualGeometryPayload>('getVisualGeometry', cachePath);
    if (result.ok && result.data) return result.data;
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
  if (!control) return;
  if (event.key.toLowerCase() === 'z') {
    event.preventDefault();
    if (event.shiftKey) store.redo();
    else store.undo();
  } else if (event.key.toLowerCase() === 'y') {
    event.preventDefault();
    store.redo();
  } else if (event.key.toLowerCase() === 's') {
    event.preventDefault();
    void saveProject(event.shiftKey);
  }
});

async function initialize(): Promise<void> {
  bridge = await EditorBridgeClient.connect();
  bridge.onSimulationState((state) => store.setSimulationState(state));
  bridge.onSimulationStatus((status) => store.setSimulation(status, store.current.simulationState));
  bridge.onConsoleMessage((message) => store.appendLog(message));
  const assets = await bridge.call<AssetsPayload>('getAssets');
  if (assets.ok && assets.data) store.setAssets(assets.data.assets);
  else store.appendLog(assets.error ?? 'Python bridge unavailable.');
  bridge.syncEditorState(
    JSON.stringify(store.current.scene),
    store.current.dirty,
    store.current.currentPath,
  );
  store.appendLog('TypeScript editor ready.');
}

void initialize();
