export type Vector3 = [number, number, number];
export type Quaternion = [number, number, number, number];
export type ActorType = 'object' | 'robot' | 'terrain' | 'camera' | 'light';
export type PrimitiveType = 'box' | 'sphere' | 'cylinder' | 'ellipsoid' | 'plane';
export type MaterialId = 'default' | 'rubber' | 'wood' | 'metal' | 'ice';
export type MassMode = 'mass' | 'density';
export type SimulationStatus = 'stopped' | 'running' | 'paused';

export interface Transform {
  position: Vector3;
  rotation: Vector3;
  scale: Vector3;
}

export interface PhysicsProperties {
  dynamic: boolean;
  material?: MaterialId;
  mass_mode?: MassMode;
  mass?: number;
  density?: number;
  friction?: [number, number, number];
  solref?: [number, number];
  solimp?: [number, number, number, number, number];
  roughness?: number;
  metalness?: number;
  [key: string]: unknown;
}

export interface ActorProperties {
  primitive?: PrimitiveType;
  size?: number[];
  rgba?: [number, number, number, number];
  physics?: PhysicsProperties;
  mass?: number;
  [key: string]: unknown;
}

export interface Actor {
  id: string;
  name: string;
  type: ActorType;
  asset_id: string;
  transform: Transform;
  properties: ActorProperties;
}

export interface Scene {
  version: string;
  name: string;
  units: 'meters';
  actors: Actor[];
  simulation_config: {
    timestep: number;
    duration: number;
    [key: string]: unknown;
  };
}

export interface AssetMetadata {
  id: string;
  name: string;
  type: ActorType;
  primitive?: PrimitiveType;
  default_transform?: Transform;
  default_properties?: ActorProperties;
}

export interface ActorSimulationState {
  id: string;
  position: Vector3;
  quaternion: Quaternion;
}

export interface SimulationState {
  time: number;
  actors: ActorSimulationState[];
}

export interface ValidationIssue {
  severity: 'error' | 'warning';
  code: string;
  message: string;
  actor_id?: string | null;
  actor_name?: string | null;
  field?: string | null;
}

export interface RpcResult<T = unknown> {
  ok: boolean;
  data?: T;
  error?: string | null;
}

export interface ProjectPayload {
  scene: Scene;
  path: string | null;
}

export interface PreflightPayload {
  valid: boolean;
  issues: ValidationIssue[];
}

export interface SavePayload {
  path: string;
}

export interface ExportPayload {
  path: string;
  issues: ValidationIssue[];
}

export interface QtSignal<T extends unknown[]> {
  connect(callback: (...args: T) => void): void;
}

export interface PythonBridgeObject {
  getAssets(callback: (result: string) => void): void;
  openProject(callback: (result: string) => void): void;
  saveProject(sceneJson: string, saveAs: boolean, callback: (result: string) => void): void;
  exportMjcf(sceneJson: string, callback: (result: string) => void): void;
  preflight(sceneJson: string, callback: (result: string) => void): void;
  runSimulation(sceneJson: string, callback: (result: string) => void): void;
  pauseSimulation(callback: (result: string) => void): void;
  stepSimulation(sceneJson: string, callback: (result: string) => void): void;
  resetSimulation(callback: (result: string) => void): void;
  setEditorState(sceneJson: string, dirty: boolean, currentPath: string): void;
  simulationStateChanged: QtSignal<[string]>;
  simulationStatusChanged: QtSignal<[string]>;
  consoleMessage: QtSignal<[string]>;
}

export interface QWebChannelInstance {
  objects: { simlabBridge: PythonBridgeObject };
}

declare global {
  interface Window {
    qt?: { webChannelTransport: unknown };
    QWebChannel?: new (
      transport: unknown,
      callback: (channel: QWebChannelInstance) => void,
    ) => unknown;
  }
}
