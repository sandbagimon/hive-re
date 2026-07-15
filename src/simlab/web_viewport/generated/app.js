import { EditorBridgeClient } from './bridge.js';
import { EditorStore } from './store.js';
import { applySimulationState, configureViewport, selectViewportActor, setViewportScene, } from './viewport.js';
const materialPresets = {
    default: { density: 1000, friction: [0.8, 0.005, 0.0001], solref: [0.02, 1], solimp: [0.9, 0.95, 0.001, 0.5, 2], roughness: 0.55, metalness: 0.04 },
    rubber: { density: 1100, friction: [1.2, 0.01, 0.0002], solref: [0.03, 1], solimp: [0.88, 0.96, 0.002, 0.5, 2], roughness: 0.86, metalness: 0 },
    wood: { density: 700, friction: [0.6, 0.004, 0.0001], solref: [0.015, 1], solimp: [0.9, 0.95, 0.001, 0.5, 2], roughness: 0.72, metalness: 0 },
    metal: { density: 7800, friction: [0.35, 0.003, 0.0001], solref: [0.008, 1], solimp: [0.92, 0.97, 0.0005, 0.5, 2], roughness: 0.24, metalness: 0.82 },
    ice: { density: 917, friction: [0.03, 0.001, 0.00005], solref: [0.01, 1], solimp: [0.92, 0.98, 0.0005, 0.5, 2], roughness: 0.12, metalness: 0.08 },
};
const store = new EditorStore();
let bridge = new EditorBridgeClient(null);
let previousSceneJson = '';
let previousSelectedActorId = null;
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
function renderSceneTree(scene, selectedActorId) {
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
          <div class="tree-subitem joint" title="${escapeHtml(joint.id)}">
            <span class="item-icon"></span><span class="item-label">${escapeHtml(joint.name)}</span>
          </div>`).join('')}
      </div>`).join('');
        return `
    <button class="tree-item ${actor.id === selectedActorId ? 'selected' : ''}" type="button" data-actor-id="${escapeHtml(actor.id)}">
      <span class="item-icon"></span>
      <span class="item-label">${escapeHtml(actor.name)}</span>
      <span class="delete-actor" data-delete-id="${escapeHtml(actor.id)}" title="Delete">×</span>
    </button>${robotRows}`;
    }).join('') : '<div class="empty-state">Scene is empty</div>';
    for (const button of tree.querySelectorAll('[data-actor-id]')) {
        button.addEventListener('click', (event) => {
            const deleteTarget = event.target.closest('[data-delete-id]');
            if (deleteTarget?.dataset.deleteId)
                store.deleteActor(deleteTarget.dataset.deleteId);
            else
                store.selectActor(button.dataset.actorId ?? null);
        });
    }
}
function numberInput(label, field, value, options = '') {
    return `<div class="property-row"><label>${label}</label><input type="number" step="0.01" value="${value}" data-field="${field}" ${options}></div>`;
}
function vectorInput(label, field, values) {
    return `<div class="property-row"><label>${label}</label><div class="vector-row">${values.map((value, index) => `<input type="number" step="0.01" value="${value}" data-vector="${field}" data-index="${index}">`).join('')}</div></div>`;
}
function renderInspector(actor) {
    const inspector = element('property-inspector');
    if (!actor) {
        inspector.innerHTML = '<div class="empty-state">No actor selected</div>';
        return;
    }
    const physics = actor.properties.physics ?? { dynamic: true };
    const friction = physics.friction ?? [0.8, 0.005, 0.0001];
    const geometry = actor.properties.geometry;
    const sourceSection = geometry ? `
    <section class="property-group"><h3>Imported Geometry</h3>
      <div class="property-row"><label>Format</label><input type="text" value="OpenUSD" disabled></div>
      <div class="property-row"><label>Source</label><input type="text" value="${escapeHtml(geometry.source)}" title="${escapeHtml(geometry.source)}" disabled></div>
      <div class="property-row"><label>Collider</label><input type="text" value="Mesh" disabled></div>
    </section>` : '';
    inspector.innerHTML = `
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
    ${sourceSection}
    <section class="property-group"><h3>Physics</h3>
      <div class="property-row"><label>Dynamic</label><input type="checkbox" data-field="dynamic" ${physics.dynamic ? 'checked' : ''}></div>
      <div class="property-row"><label>Material</label><select data-field="material">${Object.keys(materialPresets).map((id) => `<option value="${id}" ${physics.material === id ? 'selected' : ''}>${id[0].toUpperCase()}${id.slice(1)}</option>`).join('')}</select></div>
      <div class="property-row"><label>Mass Mode</label><select data-field="mass_mode"><option value="mass" ${physics.mass_mode !== 'density' ? 'selected' : ''}>Explicit Mass</option><option value="density" ${physics.mass_mode === 'density' ? 'selected' : ''}>Material Density</option></select></div>
      ${numberInput('Mass', 'mass', physics.mass ?? actor.properties.mass ?? 1, physics.mass_mode === 'density' ? 'disabled' : '')}
      ${numberInput('Density', 'density', physics.density ?? 1000, physics.mass_mode !== 'density' ? 'disabled' : '')}
      ${numberInput('Friction', 'friction', friction[0], 'min="0"')}
    </section>`;
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
    renderSceneTree(state.scene, state.selectedActorId);
    renderInspector(state.scene.actors.find((actor) => actor.id === state.selectedActorId));
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
    else if (command === 'import-openusd') {
        const result = await bridge.call('importOpenUsd');
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
    }
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
        await bridge.call('resetSimulation');
        store.setSimulation('stopped', null);
    }
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
    if (state.simulationState !== previousSimulationState) {
        applySimulationState(state.simulationState);
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
}
void initialize();
