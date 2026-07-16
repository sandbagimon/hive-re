export type Vector3 = [number, number, number];
export type Quaternion = [number, number, number, number];
export type ActorType = 'object' | 'robot' | 'terrain' | 'camera' | 'light';
export type PrimitiveType = 'box' | 'sphere' | 'cylinder' | 'ellipsoid' | 'plane';
export type MaterialId = 'default' | 'rubber' | 'wood' | 'metal' | 'ice';
export type MassMode = 'mass' | 'density';
export type SimulationStatus = 'stopped' | 'running' | 'paused' | 'fault';

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

export interface MeshGeometryProperties {
  kind: 'mesh';
  source_format: 'openusd';
  source: string;
  visual_cache: string;
  collision_mesh: string;
  bounds?: { min: Vector3; max: Vector3 };
}

export interface ActorProperties {
  primitive?: PrimitiveType;
  size?: number[];
  rgba?: [number, number, number, number];
  physics?: PhysicsProperties;
  geometry?: MeshGeometryProperties;
  import_warnings?: string[];
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

export interface RoboticsModel {
  version: string;
  articulations: RobotArticulation[];
}

export interface RobotArticulation {
  id: string;
  name: string;
  root_link_id: string;
  fixed_base: boolean;
  source_uri?: string | null;
  source_prim_path?: string | null;
  links: RobotLink[];
  joints: RobotJoint[];
  actuators: RobotActuator[];
  sensors: RobotSensor[];
}

export interface RobotLink {
  id: string;
  name: string;
  parent_link_id: string | null;
  transform: { position: Vector3; quaternion: Quaternion };
  visual_geometries: RobotVisualGeometry[];
  colliders: RobotCollider[];
  inertial: unknown | null;
  source_prim_path?: string | null;
}

export interface RobotGeometry {
  id: string;
  name: string;
  geometry_type: 'box' | 'sphere' | 'ellipsoid' | 'cylinder' | 'capsule' | 'mesh';
  transform: { position: Vector3; quaternion: Quaternion };
  size: number[];
  asset_uri: string | null;
  source_prim_path?: string | null;
}

export interface RobotVisualGeometry extends RobotGeometry {
  rgba: [number, number, number, number];
  roughness: number | null;
  metalness: number | null;
}

export interface RobotCollider extends RobotGeometry {
  friction: [number, number, number];
  restitution: number;
}

export interface RobotJoint {
  id: string;
  name: string;
  type: 'fixed' | 'revolute' | 'continuous' | 'prismatic';
  parent_link_id: string;
  child_link_id: string;
  origin: { position: Vector3; quaternion: Quaternion };
  axis: Vector3;
  limits: {
    lower: number | null;
    upper: number | null;
    effort: number | null;
    velocity: number | null;
  } | null;
  initial_position: number;
  source_prim_path?: string | null;
}

export interface RobotActuator {
  id: string;
  name: string;
  joint_id: string;
  control_type: 'position' | 'velocity' | 'motor';
  control_range: [number, number];
  stiffness: number;
  damping: number;
  max_force: number | null;
  source_prim_path?: string | null;
}

export interface RobotSensor {
  id: string;
  name: string;
  sensor_type: string;
  link_id: string | null;
  joint_id: string | null;
  update_rate_hz: number | null;
  source_prim_path?: string | null;
}

export interface Scene {
  version: string;
  name: string;
  units: 'meters';
  actors: Actor[];
  robotics?: RoboticsModel;
  trajectories?: SceneTrajectory[];
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
  source_format?: 'openusd';
  default_transform?: Transform;
  default_properties?: ActorProperties;
}

export interface ActorSimulationState {
  id: string;
  position: Vector3;
  quaternion: Quaternion;
}

export interface LinkSimulationState extends ActorSimulationState {}

export interface JointSimulationState {
  id: string;
  qpos: number;
  qvel: number;
}

export interface ActuatorSimulationState {
  id: string;
  ctrl: number;
  force: number;
}

export interface ControllerSimulationState {
  status: 'ready' | 'active' | 'timed_out' | 'fault';
  message: string | null;
  command_time: number | null;
  timeout: number | null;
  mode: 'manual' | 'python';
  name: string | null;
  step_count: number;
  last_duration: number | null;
  deadline: number | null;
}

export interface TrajectorySimulationState {
  status: 'stopped' | 'playing' | 'paused' | 'completed';
  time: number;
  duration: number;
  name: string | null;
}

export interface RecordingSimulationState {
  active: boolean;
  sample_count: number;
  limit_reached: boolean;
  name: string | null;
}

export interface ClockSimulationState {
  target_rtf: number;
  actual_rtf: number;
  timestep: number;
}

export interface JointTrajectoryKeyframe {
  time: number;
  targets: Record<string, number>;
}

export interface JointTrajectory {
  version: '1.0';
  name: string;
  loop: boolean;
  keyframes: JointTrajectoryKeyframe[];
}

export interface SceneTrajectory {
  id: string;
  actor_id: string;
  trajectory: JointTrajectory;
}

export interface SimulationState {
  time: number;
  actors: ActorSimulationState[];
  links: LinkSimulationState[];
  joints: JointSimulationState[];
  actuators: ActuatorSimulationState[];
  trajectory: TrajectorySimulationState;
  recording: RecordingSimulationState;
  clock: ClockSimulationState;
  controller: ControllerSimulationState;
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

export interface OpenUsdImportPayload {
  asset: AssetMetadata;
  warnings: string[];
  robotics?: RoboticsModel | null;
}

export interface VisualGeometryPayload {
  positions: number[];
  indices: number[];
}

export interface QtSignal<T extends unknown[]> {
  connect(callback: (...args: T) => void): void;
}

export interface PythonBridgeObject {
  getAssets(callback: (result: string) => void): void;
  importOpenUsd(callback: (result: string) => void): void;
  importOpenUsdPath(path: string, callback: (result: string) => void): void;
  getVisualGeometry(cachePath: string, callback: (result: string) => void): void;
  openProject(callback: (result: string) => void): void;
  openProjectPath(path: string, callback: (result: string) => void): void;
  saveProject(sceneJson: string, saveAs: boolean, callback: (result: string) => void): void;
  saveProjectPath(sceneJson: string, path: string, callback: (result: string) => void): void;
  exportMjcf(sceneJson: string, callback: (result: string) => void): void;
  preflight(sceneJson: string, callback: (result: string) => void): void;
  runSimulation(sceneJson: string, callback: (result: string) => void): void;
  pauseSimulation(callback: (result: string) => void): void;
  setSimulationSpeed(factor: number, callback: (result: string) => void): void;
  stepSimulation(sceneJson: string, callback: (result: string) => void): void;
  resetSimulation(callback: (result: string) => void): void;
  setJointTargets(sceneJson: string, targetsJson: string, callback: (result: string) => void): void;
  loadController(sceneJson: string, callback: (result: string) => void): void;
  loadControllerPath(sceneJson: string, path: string, callback: (result: string) => void): void;
  detachController(callback: (result: string) => void): void;
  loadTrajectory(sceneJson: string, trajectoryJson: string, callback: (result: string) => void): void;
  playTrajectory(callback: (result: string) => void): void;
  pauseTrajectory(callback: (result: string) => void): void;
  stopTrajectory(callback: (result: string) => void): void;
  startRecording(sceneJson: string, configJson: string, callback: (result: string) => void): void;
  stopRecording(callback: (result: string) => void): void;
  getRecording(callback: (result: string) => void): void;
  exportRecording(path: string, formatName: string, callback: (result: string) => void): void;
  exportRecordingDialog(formatName: string, callback: (result: string) => void): void;
  setEditorState(sceneJson: string, dirty: boolean, currentPath: string): void;
  simulationStateChanged: QtSignal<[string]>;
  simulationStatusChanged: QtSignal<[string]>;
  consoleMessage: QtSignal<[string]>;
}

export interface QWebChannelInstance {
  objects: { simlabBridge: PythonBridgeObject };
}

export interface SimLabEditorAutomation {
  importOpenUsdPath(path: string): Promise<RpcResult<OpenUsdImportPayload>>;
  openProjectPath(path: string): Promise<RpcResult<ProjectPayload>>;
  saveProjectPath(path: string): Promise<RpcResult<SavePayload>>;
  getRecording(): Promise<RpcResult<{ recording: unknown }>>;
  exportRecordingPath(
    path: string,
    formatName: 'json' | 'csv',
  ): Promise<RpcResult<{ path: string; format: string; sample_count: number }>>;
  setSimulationSpeed(factor: number): Promise<RpcResult<{
    target_rtf: number;
    state: SimulationState | null;
  }>>;
  loadControllerPath(path: string): Promise<RpcResult<{
    state: SimulationState;
    controller: { path: string; name: string };
  }>>;
  getStateJson(): string;
  selectJoint(actorId: string, jointId: string): boolean;
}

declare global {
  interface Window {
    qt?: { webChannelTransport: unknown };
    QWebChannel?: new (
      transport: unknown,
      callback: (channel: QWebChannelInstance) => void,
    ) => unknown;
    simlabEditor?: SimLabEditorAutomation;
    simlabEditorReady?: boolean;
  }
}
