import type {
  Actor,
  ActorProperties,
  AssetMetadata,
  Scene,
  SimulationState,
  SimulationStatus,
  Transform,
  ValidationIssue,
} from './types.js';

export interface EditorState {
  scene: Scene;
  assets: AssetMetadata[];
  selectedActorId: string | null;
  dirty: boolean;
  canUndo: boolean;
  canRedo: boolean;
  currentPath: string | null;
  simulationStatus: SimulationStatus;
  simulationState: SimulationState | null;
  validationIssues: ValidationIssue[];
  logs: string[];
}

type Listener = (state: EditorState) => void;

const emptyScene = (): Scene => ({
  version: '1.0',
  name: 'Untitled Scene',
  units: 'meters',
  actors: [],
  simulation_config: { timestep: 0.01, duration: 1.0 },
});

const cloneScene = (scene: Scene): Scene => structuredClone(scene);
const sceneSnapshot = (scene: Scene): string => JSON.stringify(scene);

export class EditorStore {
  private state: EditorState = {
    scene: emptyScene(),
    assets: [],
    selectedActorId: null,
    dirty: false,
    canUndo: false,
    canRedo: false,
    currentPath: null,
    simulationStatus: 'stopped',
    simulationState: null,
    validationIssues: [],
    logs: [],
  };
  private readonly listeners = new Set<Listener>();
  private undoStack: Scene[] = [];
  private redoStack: Scene[] = [];
  private savedSnapshot = sceneSnapshot(this.state.scene);

  get current(): EditorState {
    return this.state;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => this.listeners.delete(listener);
  }

  setAssets(assets: AssetMetadata[]): void {
    this.patch({ assets });
  }

  upsertAsset(asset: AssetMetadata): void {
    this.patch({
      assets: [...this.state.assets.filter((item) => item.id !== asset.id), asset],
    });
  }

  loadScene(scene: Scene, path: string | null): void {
    this.undoStack = [];
    this.redoStack = [];
    this.savedSnapshot = sceneSnapshot(scene);
    this.patch({
      scene: cloneScene(scene),
      currentPath: path,
      selectedActorId: null,
      dirty: false,
      canUndo: false,
      canRedo: false,
      simulationStatus: 'stopped',
      simulationState: null,
      validationIssues: [],
    });
  }

  newScene(): void {
    this.loadScene(emptyScene(), null);
    this.appendLog('Created a new scene.');
  }

  markSaved(path: string): void {
    this.savedSnapshot = sceneSnapshot(this.state.scene);
    this.patch({ currentPath: path, dirty: false });
  }

  selectActor(actorId: string | null): void {
    this.patch({ selectedActorId: actorId });
  }

  addAsset(asset: AssetMetadata): void {
    const scene = cloneScene(this.state.scene);
    const actor: Actor = {
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
    this.commit(scene, actor.id);
    this.appendLog(`Added actor: ${actor.name}`);
  }

  deleteActor(actorId: string): void {
    const actor = this.state.scene.actors.find((item) => item.id === actorId);
    if (!actor) return;
    const scene = cloneScene(this.state.scene);
    scene.actors = scene.actors.filter((item) => item.id !== actorId);
    this.commit(scene, this.state.selectedActorId === actorId ? null : this.state.selectedActorId);
    this.appendLog(`Deleted actor: ${actor.name}`);
  }

  updateActorName(actorId: string, name: string): void {
    this.updateActor(actorId, (actor) => { actor.name = name || 'Actor'; });
  }

  updateActorTransform(actorId: string, transform: Transform): void {
    this.updateActor(actorId, (actor) => { actor.transform = structuredClone(transform); });
  }

  updateActorProperties(actorId: string, properties: Partial<ActorProperties>): void {
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

  undo(): void {
    const previous = this.undoStack.pop();
    if (!previous) return;
    this.redoStack.push(cloneScene(this.state.scene));
    this.restoreHistory(previous, 'Undo.');
  }

  redo(): void {
    const next = this.redoStack.pop();
    if (!next) return;
    this.undoStack.push(cloneScene(this.state.scene));
    this.restoreHistory(next, 'Redo.');
  }

  setSimulation(status: SimulationStatus, state: SimulationState | null = null): void {
    this.patch({ simulationStatus: status, simulationState: state });
  }

  setSimulationState(state: SimulationState): void {
    this.patch({ simulationState: state });
  }

  setValidationIssues(validationIssues: ValidationIssue[]): void {
    this.patch({ validationIssues });
  }

  appendLog(message: string): void {
    this.patch({ logs: [...this.state.logs.slice(-199), message] });
  }

  clearLogs(): void {
    this.patch({ logs: [] });
  }

  private updateActor(actorId: string, update: (actor: Actor) => void): void {
    const scene = cloneScene(this.state.scene);
    const actor = scene.actors.find((item) => item.id === actorId);
    if (!actor) return;
    update(actor);
    this.commit(scene, actorId);
  }

  private commit(scene: Scene, selectedActorId: string | null): void {
    if (sceneSnapshot(scene) === sceneSnapshot(this.state.scene)) return;
    this.undoStack.push(cloneScene(this.state.scene));
    if (this.undoStack.length > 100) this.undoStack.shift();
    this.redoStack = [];
    this.patch({
      scene,
      selectedActorId,
      dirty: sceneSnapshot(scene) !== this.savedSnapshot,
      canUndo: true,
      canRedo: false,
      simulationStatus: 'stopped',
      simulationState: null,
      validationIssues: [],
    });
  }

  private restoreHistory(scene: Scene, message: string): void {
    const selected = this.state.selectedActorId;
    this.patch({
      scene,
      selectedActorId: selected && scene.actors.some((actor) => actor.id === selected)
        ? selected
        : null,
      dirty: sceneSnapshot(scene) !== this.savedSnapshot,
      canUndo: this.undoStack.length > 0,
      canRedo: this.redoStack.length > 0,
      simulationStatus: 'stopped',
      simulationState: null,
    });
    this.appendLog(message);
  }

  private nextActorId(scene: Scene): string {
    const highest = scene.actors.reduce((current, actor) => {
      const match = /^actor_(\d+)$/.exec(actor.id);
      return match ? Math.max(current, Number(match[1])) : current;
    }, 0);
    return `actor_${String(highest + 1).padStart(3, '0')}`;
  }

  private patch(values: Partial<EditorState>): void {
    this.state = { ...this.state, ...values };
    for (const listener of this.listeners) listener(this.state);
  }
}
