const emptyScene = () => ({
    version: '1.0',
    name: 'Untitled Scene',
    units: 'meters',
    actors: [],
    simulation_config: { timestep: 0.01, duration: 1.0 },
});
const cloneScene = (scene) => structuredClone(scene);
const sceneSnapshot = (scene) => JSON.stringify(scene);
export class EditorStore {
    state = {
        scene: emptyScene(),
        assets: [],
        selectedActorId: null,
        selectedJointId: null,
        dirty: false,
        canUndo: false,
        canRedo: false,
        currentPath: null,
        simulationStatus: 'stopped',
        simulationState: null,
        validationIssues: [],
        logs: [],
    };
    listeners = new Set();
    undoStack = [];
    redoStack = [];
    savedSnapshot = sceneSnapshot(this.state.scene);
    get current() {
        return this.state;
    }
    subscribe(listener) {
        this.listeners.add(listener);
        listener(this.state);
        return () => this.listeners.delete(listener);
    }
    setAssets(assets) {
        this.patch({ assets });
    }
    upsertAsset(asset) {
        this.patch({
            assets: [...this.state.assets.filter((item) => item.id !== asset.id), asset],
        });
    }
    loadScene(scene, path) {
        this.undoStack = [];
        this.redoStack = [];
        this.savedSnapshot = sceneSnapshot(scene);
        this.patch({
            scene: cloneScene(scene),
            currentPath: path,
            selectedActorId: null,
            selectedJointId: null,
            dirty: false,
            canUndo: false,
            canRedo: false,
            simulationStatus: 'stopped',
            simulationState: null,
            validationIssues: [],
        });
    }
    newScene() {
        this.loadScene(emptyScene(), null);
        this.appendLog('Created a new scene.');
    }
    markSaved(path) {
        this.savedSnapshot = sceneSnapshot(this.state.scene);
        this.patch({ currentPath: path, dirty: false });
    }
    selectActor(actorId) {
        this.patch({ selectedActorId: actorId, selectedJointId: null });
    }
    selectJoint(actorId, jointId) {
        const actor = this.state.scene.actors.find((item) => item.id === actorId);
        const articulationIds = actor?.properties.articulation_ids;
        const jointExists = this.state.scene.robotics?.articulations.some((articulation) => articulationIds?.includes(articulation.id)
            && articulation.joints.some((joint) => joint.id === jointId));
        if (!jointExists)
            return;
        this.patch({ selectedActorId: actorId, selectedJointId: jointId });
    }
    addAsset(asset, robotics) {
        const scene = cloneScene(this.state.scene);
        const actor = {
            id: this.nextActorId(scene),
            name: asset.name,
            type: asset.type,
            asset_id: asset.id,
            transform: structuredClone(asset.default_transform ?? {
                position: [0, 0, 0],
                rotation: [0, 0, 0],
                scale: [1, 1, 1],
            }),
            properties: structuredClone(asset.default_properties ?? {}),
        };
        if (asset.primitive) {
            actor.properties.primitive = asset.primitive;
        }
        scene.actors.push(actor);
        if (robotics) {
            const existing = scene.robotics?.articulations ?? [];
            const importedIds = new Set(robotics.articulations.map((item) => item.id));
            scene.robotics = {
                version: robotics.version,
                articulations: [
                    ...existing.filter((item) => !importedIds.has(item.id)),
                    ...structuredClone(robotics.articulations),
                ],
            };
        }
        this.commit(scene, actor.id);
        this.appendLog(`Added actor: ${actor.name}`);
    }
    deleteActor(actorId) {
        const actor = this.state.scene.actors.find((item) => item.id === actorId);
        if (!actor)
            return;
        const scene = cloneScene(this.state.scene);
        scene.actors = scene.actors.filter((item) => item.id !== actorId);
        const articulationIds = actor.properties.articulation_ids;
        if (scene.robotics && articulationIds) {
            scene.robotics.articulations = scene.robotics.articulations.filter((item) => !articulationIds.includes(item.id));
            if (scene.robotics.articulations.length === 0)
                delete scene.robotics;
        }
        if (scene.trajectories) {
            scene.trajectories = scene.trajectories.filter((item) => item.actor_id !== actorId);
            if (scene.trajectories.length === 0)
                delete scene.trajectories;
        }
        this.commit(scene, this.state.selectedActorId === actorId ? null : this.state.selectedActorId);
        this.appendLog(`Deleted actor: ${actor.name}`);
    }
    updateActorName(actorId, name) {
        this.updateActor(actorId, (actor) => { actor.name = name || 'Actor'; });
    }
    updateActorTransform(actorId, transform) {
        this.updateActor(actorId, (actor) => { actor.transform = structuredClone(transform); });
    }
    updateActorProperties(actorId, properties) {
        this.updateActor(actorId, (actor) => {
            actor.properties = { ...actor.properties, ...structuredClone(properties) };
            if (properties.physics) {
                actor.properties.physics = {
                    ...actor.properties.physics,
                    ...structuredClone(properties.physics),
                };
            }
        });
    }
    upsertTrajectory(actorId, trajectory, trajectoryId) {
        const actor = this.state.scene.actors.find((item) => item.id === actorId);
        if (actor?.type !== 'robot')
            return null;
        const scene = cloneScene(this.state.scene);
        const id = trajectoryId ?? this.nextTrajectoryId(scene);
        const item = {
            id,
            actor_id: actorId,
            trajectory: structuredClone(trajectory),
        };
        const index = scene.trajectories?.findIndex((existing) => existing.id === id) ?? -1;
        if (index >= 0 && scene.trajectories)
            scene.trajectories[index] = item;
        else
            scene.trajectories = [...(scene.trajectories ?? []), item];
        this.commit(scene, actorId, true);
        this.appendLog(`${index >= 0 ? 'Updated' : 'Saved'} trajectory: ${trajectory.name}`);
        return id;
    }
    removeTrajectory(trajectoryId) {
        const item = this.state.scene.trajectories?.find((trajectory) => trajectory.id === trajectoryId);
        if (!item)
            return;
        const scene = cloneScene(this.state.scene);
        scene.trajectories = scene.trajectories?.filter((trajectory) => trajectory.id !== trajectoryId);
        if (scene.trajectories?.length === 0)
            delete scene.trajectories;
        this.commit(scene, this.state.selectedActorId, true);
        this.appendLog(`Deleted trajectory: ${item.trajectory.name}`);
    }
    undo() {
        const previous = this.undoStack.pop();
        if (!previous)
            return;
        this.redoStack.push(cloneScene(this.state.scene));
        this.restoreHistory(previous, 'Undo.');
    }
    redo() {
        const next = this.redoStack.pop();
        if (!next)
            return;
        this.undoStack.push(cloneScene(this.state.scene));
        this.restoreHistory(next, 'Redo.');
    }
    setSimulation(status, state = null) {
        this.patch({ simulationStatus: status, simulationState: state });
    }
    setSimulationState(state) {
        this.patch({ simulationState: state });
    }
    setValidationIssues(validationIssues) {
        this.patch({ validationIssues });
    }
    appendLog(message) {
        this.patch({ logs: [...this.state.logs.slice(-199), message] });
    }
    clearLogs() {
        this.patch({ logs: [] });
    }
    updateActor(actorId, update) {
        const scene = cloneScene(this.state.scene);
        const actor = scene.actors.find((item) => item.id === actorId);
        if (!actor)
            return;
        update(actor);
        this.commit(scene, actorId);
    }
    commit(scene, selectedActorId, preserveJointSelection = false) {
        if (sceneSnapshot(scene) === sceneSnapshot(this.state.scene))
            return;
        this.undoStack.push(cloneScene(this.state.scene));
        if (this.undoStack.length > 100)
            this.undoStack.shift();
        this.redoStack = [];
        this.patch({
            scene,
            selectedActorId,
            selectedJointId: preserveJointSelection ? this.state.selectedJointId : null,
            dirty: sceneSnapshot(scene) !== this.savedSnapshot,
            canUndo: true,
            canRedo: false,
            simulationStatus: 'stopped',
            simulationState: null,
            validationIssues: [],
        });
    }
    restoreHistory(scene, message) {
        const selected = this.state.selectedActorId;
        const selectedJoint = this.state.selectedJointId;
        const jointStillExists = selectedJoint && scene.robotics?.articulations.some((articulation) => articulation.joints.some((joint) => joint.id === selectedJoint));
        this.patch({
            scene,
            selectedActorId: selected && scene.actors.some((actor) => actor.id === selected)
                ? selected
                : null,
            selectedJointId: jointStillExists ? selectedJoint : null,
            dirty: sceneSnapshot(scene) !== this.savedSnapshot,
            canUndo: this.undoStack.length > 0,
            canRedo: this.redoStack.length > 0,
            simulationStatus: 'stopped',
            simulationState: null,
        });
        this.appendLog(message);
    }
    nextActorId(scene) {
        const highest = scene.actors.reduce((current, actor) => {
            const match = /^actor_(\d+)$/.exec(actor.id);
            return match ? Math.max(current, Number(match[1])) : current;
        }, 0);
        return `actor_${String(highest + 1).padStart(3, '0')}`;
    }
    nextTrajectoryId(scene) {
        const used = new Set((scene.trajectories ?? []).map((item) => item.id));
        let index = 1;
        while (used.has(`trajectory_${String(index).padStart(3, '0')}`))
            index += 1;
        return `trajectory_${String(index).padStart(3, '0')}`;
    }
    patch(values) {
        this.state = { ...this.state, ...values };
        for (const listener of this.listeners)
            listener(this.state);
    }
}
