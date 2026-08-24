export type Vector3 = [number, number, number];
export type Quaternion = [number, number, number, number];
export type ActorType = 'object' | 'robot' | 'terrain' | 'camera' | 'light';
export type PrimitiveType = 'box' | 'sphere' | 'cylinder' | 'ellipsoid' | 'plane';
export type AssetCategory = 'primitive' | 'robot' | 'prop' | 'environment';
export type MaterialId = 'default' | 'rubber' | 'wood' | 'metal' | 'ice';
export type MassMode = 'mass' | 'density';
export type SimulationStatus = 'stopped' | 'running' | 'paused' | 'fault';
export type ActorVisualStyle =
  | 'shipping_package'
  | 'insulated_delivery_bag'
  | 'operations_ground'
  | 'cinematic_wet_asphalt'
  | 'landing_pad_pickup'
  | 'landing_pad_dropoff'
  | 'restaurant_pickup'
  | 'residential_dropoff'
  | 'dynamic_delivery_van'
  | 'dynamic_forklift'
  | 'dynamic_courier'
  | 'known_obstacle'
  | 'unmapped_obstacle'
  | 'safety_pillar';

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
  visual_cache?: string;
  stream_scene_id?: string;
  collision_mesh: string;
  bounds?: { min: Vector3; max: Vector3 };
}

export interface ActorVisualModelInstance {
  position: Vector3;
  rotation: Vector3;
  size: Vector3;
}

export type ActorLocomotionMode = 'walking' | 'cycling';

export interface ActorVisualAnimation {
  clip_url?: string;
  source_url?: string;
  license?: 'CC0-1.0' | 'CC-BY-4.0';
  author?: string;
  locomotion: ActorLocomotionMode;
  clips: {
    idle?: string;
    walking?: string;
    cycling?: string;
  };
  reference_speed: number;
  stop_speed?: number;
  min_playback_rate?: number;
  max_playback_rate?: number;
}

export interface ActorVisualModel {
  url: string;
  source_url: string;
  license: 'CC0-1.0' | 'CC-BY-4.0';
  author: string;
  resolution: string;
  instances: ActorVisualModelInstance[];
  animation?: ActorVisualAnimation;
}

export interface ActorProperties {
  primitive?: PrimitiveType;
  size?: number[];
  rgba?: [number, number, number, number];
  physics?: PhysicsProperties;
  geometry?: MeshGeometryProperties;
  import_warnings?: string[];
  mass?: number;
  propulsion?: QuadrotorPropulsion;
  visual_style?: ActorVisualStyle;
  visual_model?: ActorVisualModel;
  [key: string]: unknown;
}

export interface QuadrotorRotor {
  id: string;
  link_id: string;
  actuator_id: string;
  axis: Vector3;
  direction: -1 | 1;
  thrust_coefficient: number;
  torque_coefficient: number;
  min_angular_velocity: number;
  max_angular_velocity: number;
}

export interface QuadrotorPropulsion {
  type: 'quadrotor';
  model: 'quadratic';
  command_mode: 'angular_velocity';
  body_link_id: string;
  rotors: [QuadrotorRotor, QuadrotorRotor, QuadrotorRotor, QuadrotorRotor];
}

export interface Actor {
  id: string;
  name: string;
  type: ActorType;
  asset_id: string;
  transform: Transform;
  properties: ActorProperties;
}

export interface Attachment {
  id: string;
  type: 'connect' | 'weld';
  parent_body_id: string;
  child_body_id: string;
  parent_anchor: Vector3;
  child_anchor: Vector3;
  initially_active: boolean;
  capture_distance: number;
  capture_speed: number;
  capture_duration: number;
  require_contact: boolean;
  contact_probe_radius: number;
  gripper?: VacuumGripper;
  solref: [number, number];
  solimp: [number, number, number, number, number];
}

export interface VacuumGripper {
  type: 'four_cup_vacuum';
  plate_half_extents: Vector3;
  cup_offset: [number, number];
  cup_radius: number;
  cup_height: number;
  mount_radius: number;
  mount_length: number;
}

export interface DeliveryTask {
  id: string;
  type: 'aerial_delivery';
  attachment_id: string;
  payload_body_id: string;
  pickup_position: Vector3;
  dropoff_position: Vector3;
  position_tolerance: number;
  settle_speed: number;
  settle_duration: number;
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
  visual_bundle?: string | null;
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
  visual_cache?: string | null;
  source_prim_path?: string | null;
}

export interface RobotVisualGeometry extends RobotGeometry {
  rgba: [number, number, number, number];
  roughness: number | null;
  metalness: number | null;
}

export interface RobotCollider extends RobotGeometry {
  collision_mesh?: string | null;
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
  parent_frame?: { position: Vector3; quaternion: Quaternion };
  child_frame?: { position: Vector3; quaternion: Quaternion };
  axis: Vector3;
  limits: {
    lower: number | null;
    upper: number | null;
    effort: number | null;
    velocity: number | null;
  } | null;
  initial_position: number;
  initial_velocity?: number;
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
  target_position?: number | null;
  target_velocity?: number | null;
  source_prim_path?: string | null;
}

export interface RobotSensor {
  id: string;
  name: string;
  sensor_type: string;
  link_id: string | null;
  joint_id: string | null;
  collider_id?: string;
  aggregation_mode?: 'sum';
  update_rate_hz: number | null;
  local_transform?: {
    position: [number, number, number];
    quaternion: [number, number, number, number];
  };
  max_distance?: number;
  noise?: {
    seed: number;
    channels: Partial<Record<
      | 'qpos'
      | 'qvel'
      | 'orientation'
      | 'angular_velocity'
      | 'linear_acceleration'
      | 'normal_force'
      | 'tangent_force'
      | 'distance',
      { bias: number | Vector3; standard_deviation: number | Vector3 }
    >>;
  };
  source_prim_path?: string | null;
}

export interface Scene {
  version: string;
  name: string;
  units: 'meters';
  actors: Actor[];
  robotics?: RoboticsModel;
  trajectories?: SceneTrajectory[];
  attachments?: Attachment[];
  delivery_tasks?: DeliveryTask[];
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
  category?: AssetCategory;
  primitive?: PrimitiveType;
  source_format?: 'openusd';
  license?: string;
  source_url?: string;
  default_transform?: Transform;
  default_properties?: ActorProperties;
  robotics?: RoboticsModel;
}

export interface LocalSceneStatus {
  scene_id: string;
  name: string;
  content_profile: 'optimized' | 'full';
  status: 'disabled' | 'unavailable' | 'preparing' | 'ready' | 'failed';
  error?: string;
  statistics?: Record<string, number>;
}

export interface LocalSceneChunk {
  id: string;
  tile: [number, number];
  byte_length: number;
  vertex_count: number;
  triangle_count: number;
  bounds: { min: Vector3; max: Vector3 };
}

export interface LocalSceneMaterial {
  id: string;
  name: string;
  base_color: [number, number, number, number];
  roughness: number;
  metalness: number;
  opacity: number;
  normal_scale: number;
  texture_scale: [number, number];
  texture_offset: [number, number];
  texture_rotation: number;
  emissive_color: [number, number, number];
  emissive_intensity: number;
  source_model: 'displayColor' | 'USD' | 'MDL:OmniPBR';
  textures: Partial<Record<
    | 'base_color'
    | 'normal'
    | 'roughness'
    | 'metalness'
    | 'orm'
    | 'opacity'
    | 'emissive',
    string
  >>;
}

export interface LocalSceneTexture {
  id: string;
  filename: string;
  media_type: string;
  byte_length: number;
}

export interface LocalSceneManifest {
  format: 'beefoundrysim-local-scene';
  version: 3;
  scene_id: string;
  name: string;
  content_profile: 'optimized' | 'full';
  bounds: { min: Vector3; max: Vector3 };
  chunks: LocalSceneChunk[];
  materials: Record<string, LocalSceneMaterial>;
  textures: Record<string, LocalSceneTexture>;
  statistics: Record<string, number>;
  warnings: string[];
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

export interface AttachmentSimulationState {
  id: string;
  status: 'inactive' | 'pending' | 'active';
  active: boolean;
  requested_active: boolean;
  eligible: boolean;
  contact: boolean;
  distance: number;
  relative_speed: number;
}

export interface DeliveryTaskSimulationState {
  id: string;
  status: 'waiting_pickup' | 'in_transit' | 'released' | 'settling' | 'completed';
  attachment_id: string;
  payload_body_id: string;
  distance_to_dropoff: number;
  payload_speed: number;
  stable_time: number;
}

export interface JointStateSensorSample {
  id: string;
  sensor_type: 'joint_state';
  joint_id: string;
  time: number;
  sequence: number;
  qpos: number;
  qvel: number;
}

export interface ImuSensorSample {
  id: string;
  sensor_type: 'imu';
  link_id: string;
  time: number;
  sequence: number;
  orientation: [number, number, number, number];
  angular_velocity: [number, number, number];
  linear_acceleration: [number, number, number];
}

export interface ContactSensorSample {
  id: string;
  sensor_type: 'contact';
  time: number;
  sequence: number;
  contact_count: number;
  normal_force: number;
  tangent_force: [number, number, number];
  normal_impulse: number;
  points: [number, number, number][];
  normals: [number, number, number][];
}

export interface RangefinderSensorSample {
  id: string;
  sensor_type: 'rangefinder';
  link_id: string;
  time: number;
  sequence: number;
  distance: number;
  max_distance: number;
  hit: boolean;
}

export type SensorSample =
  | JointStateSensorSample
  | ImuSensorSample
  | ContactSensorSample
  | RangefinderSensorSample;

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
  reset_deadline: number | null;
}

export interface NavigationSimulationState {
  status: 'idle' | 'ready' | 'planning' | 'following' | 'blocked' | 'arrived' | 'complete';
  route: [number, number, number][];
  route_revision: number;
  map_revision: number;
  replan_count: number;
  occupied_cell_count: number;
  last_replan_time: number | null;
  message: string | null;
}

export interface DynamicEventSimulationState {
  id: string;
  actor_id: string;
  label: string;
  status: 'scheduled' | 'active' | 'completed';
  progress: number;
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
  sensor_event_count: number;
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
  attachments: AttachmentSimulationState[];
  delivery_tasks: DeliveryTaskSimulationState[];
  dynamic_events: DynamicEventSimulationState[];
  sensors: SensorSample[];
  navigation: NavigationSimulationState;
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
  colors?: number[] | null;
  uvs?: number[] | null;
  base_color_texture?: string | null;
  base_color_texture_url?: string | null;
  normal_texture?: string | null;
  normal_texture_url?: string | null;
  roughness_texture?: string | null;
  roughness_texture_url?: string | null;
  metallic_texture?: string | null;
  metallic_texture_url?: string | null;
  roughness?: number | null;
  metalness?: number | null;
}

export interface BeeFoundrySimEditorAutomation {
  getRecording(): Promise<RpcResult<{ recording: unknown }>>;
  setSimulationSpeed(factor: number): Promise<RpcResult<{
    target_rtf: number;
    state: SimulationState | null;
  }>>;
  getStateJson(): string;
  selectJoint(actorId: string, jointId: string): boolean;
  selectSensor(actorId: string, sensorId: string): boolean;
}

declare global {
  interface Window {
    beefoundrysimEditor?: BeeFoundrySimEditorAutomation;
    beefoundrysimEditorReady?: boolean;
  }
}
